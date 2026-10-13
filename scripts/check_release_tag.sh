#!/usr/bin/env bash
# scripts/check_release_tag.sh <tag> [--ci|--pre-tag]
#
# The tag gate (Hard Rule 10, extended to release tags by ADR-049 R1). tag-handoff-gate.yml runs it on
# every `v*.*.*` tag push with --ci. Run it locally with --pre-tag before cutting a release tag.
#
# scripts/check_handoff_exists.sh, the Claude Code Stop hook, is NOT edited and NOT bypassed: this
# wrapper calls it as the five-field validator.
#
#   v0.0.N  (stage tags)    the legacy path, unchanged: the stage-N handoff passes the validator.
#   vX.Y.Z  (release tags)  exactly one docs/handoffs/STAGE-*-DONE-*.md carries `stage_tag: <tag>`.
#                           It is the only handoff for its stage, and it passes the validator. Also:
#                             - status: complete;
#                             - git_sha_end resolves as a commit, and its code tree equals the
#                               tagged tree (ancestry cannot be checked under squash merges);
#                             - next_stage and next_stage_name are set, and the next stage's prompt
#                               file exists;
#                             - pyproject version == CITATION.cff version == X.Y.Z, and CHANGELOG
#                               has a `## [X.Y.Z] - ` heading.
#
#   --ci       on a tag push. The tag must point at HEAD. The tagged stage is written into the
#              runner's .aero-stage, as the legacy workflow did.
#   --pre-tag  locally, before tagging. The tag must not exist yet; HEAD is the commit to be tagged.
#              .aero-stage is only asserted, never rewritten.
#
# Exit: 0 pass, 1 fail, 2 usage.

set -euo pipefail

usage() { echo "usage: $0 <tag> [--ci|--pre-tag]" >&2; exit 2; }
[[ $# -ge 1 && $# -le 2 ]] || usage
tag="$1"
mode="${2:-}"
[[ -z "$mode" || "$mode" == "--ci" || "$mode" == "--pre-tag" ]] || usage

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The paths whose tree must match between the handoff's git_sha_end and the tagged commit.
CODE_PATHS=(aero scripts conf containers tests .github pyproject.toml uv.lock)

fail=0
problem() { echo "[release-tag-gate] FAIL: $*" >&2; fail=1; }
ok() { echo "[release-tag-gate] ok: $*" >&2; }

set_stage() {
  local padded="$1"
  if [[ "$mode" == "--ci" ]]; then
    echo "$padded" > .aero-stage
  elif [[ "$(tr -d '[:space:]' < .aero-stage)" != "$padded" ]]; then
    problem ".aero-stage is '$(tr -d '[:space:]' < .aero-stage)', the tagged stage is $padded"
  fi
}

field() {  # field FILE NAME -> the frontmatter scalar (quotes stripped), as the Stop hook reads it
  awk -v f="$2" '
    /^---[[:space:]]*$/ { n++; if (n == 2) exit; next }
    n == 1 && $0 ~ "^"f":" {
      val = $0; sub("^"f":[[:space:]]*", "", val)
      gsub(/^["'\''[:space:]]+|["'\''[:space:]]+$/, "", val); print val; exit
    }' "$1"
}

if [[ "$tag" =~ ^v0\.0\.([0-9]+)$ ]]; then
  # --- The legacy stage-tag path: exactly what tag-handoff-gate.yml did before Stage 21. --------
  set_stage "$(printf '%02d' "${BASH_REMATCH[1]}")"
  [[ $fail -eq 0 ]] || exit 1
  bash "$here/check_handoff_exists.sh"
  exit $?
fi

[[ "$tag" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || { echo "[release-tag-gate] '$tag' is not vX.Y.Z" >&2; exit 2; }
version="${tag#v}"

# --- Exactly one handoff names this release tag. ---------------------------------------------------
shopt -s nullglob
carriers=()
for f in docs/handoffs/STAGE-*-DONE-*.md; do
  [[ "$(field "$f" stage_tag)" == "$tag" ]] && carriers+=("$f")
done
shopt -u nullglob
if [[ ${#carriers[@]} -ne 1 ]]; then
  problem "${#carriers[@]} handoffs carry 'stage_tag: $tag' (exactly one must): ${carriers[*]:-none}"
  exit 1
fi
handoff="${carriers[0]}"
ok "handoff $handoff"
stage="$(printf '%02d' "$((10#$(field "$handoff" stage)))")"
shopt -s nullglob
same_stage=(docs/handoffs/STAGE-"$stage"-*-DONE-*.md)
shopt -u nullglob
if [[ ${#same_stage[@]} -ne 1 ]]; then
  # The Stop hook validates the NEWEST handoff of the stage; for a release there must be no doubt
  # which file that is.
  problem "stage $stage has ${#same_stage[@]} handoff files; a release stage must have exactly one"
fi

# --- The five-field validator (the Stop hook), unchanged. ------------------------------------------
set_stage "$stage"
if [[ $fail -eq 0 ]]; then
  bash "$here/check_handoff_exists.sh" || problem "the five-field handoff validator refused $handoff"
fi

# --- Release-only checks. --------------------------------------------------------------------------
status="$(field "$handoff" status)"
[[ "$status" == "complete" ]] || problem "handoff status is '$status'; a release needs 'complete'"

sha_end="$(field "$handoff" git_sha_end)"
if [[ "$sha_end" =~ ^[0-9a-f]{40}$ ]] && git cat-file -e "${sha_end}^{commit}" 2>/dev/null; then
  ok "git_sha_end $sha_end resolves"
else
  problem "git_sha_end '$sha_end' does not resolve as a commit (CI fetches refs/pull/*/head)"
  sha_end=""
fi

if [[ "$mode" == "--ci" ]]; then
  tagged="$(git rev-parse -q --verify "refs/tags/$tag^{commit}" || true)"
  [[ -n "$tagged" && "$tagged" == "$(git rev-parse HEAD)" ]] || problem "$tag does not point at HEAD"
  target="$tag"
else
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    [[ "$mode" == "--pre-tag" ]] && problem "$tag already exists"
    target="$tag"
  else
    target="HEAD"
  fi
fi
if [[ -n "$sha_end" ]]; then
  if git diff --quiet "$sha_end" "$target" -- "${CODE_PATHS[@]}"; then
    ok "code tree of $sha_end == $target over ${CODE_PATHS[*]}"
  else
    problem "the code tree at git_sha_end differs from $target in: $(git diff --name-only "$sha_end" "$target" -- "${CODE_PATHS[@]}" | tr '\n' ' ')"
  fi
fi

next="$(field "$handoff" next_stage)"
next_name="$(field "$handoff" next_stage_name)"
if [[ "$next" =~ ^[0-9]+$ && -n "$next_name" ]]; then
  shopt -s nullglob
  prompts=(docs/handoff-bundle/STAGE-"$(printf '%02d' "$((10#$next))")"-*.md)
  shopt -u nullglob
  [[ ${#prompts[@]} -ge 1 ]] && ok "next stage prompt ${prompts[0]}" \
    || problem "no prompt file docs/handoff-bundle/STAGE-$(printf '%02d' "$((10#$next))")-*.md for next_stage $next"
else
  problem "next_stage '$next' / next_stage_name '$next_name' must both be set"
fi

py_version="$(python3 -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' pyproject.toml)"
[[ "$py_version" == "$version" ]] || problem "pyproject version is $py_version, the tag is $tag"
cff_version="$(awk '/^version:/ { gsub(/["'\'' ]/, "", $2); print $2; exit }' CITATION.cff)"
[[ "$cff_version" == "$version" ]] || problem "CITATION.cff version is '$cff_version', the tag is $tag"
grep -qE "^## \[${version//./\\.}\] - [0-9]{4}-[0-9]{2}-[0-9]{2}" CHANGELOG.md \
  || problem "CHANGELOG.md has no '## [$version] - YYYY-MM-DD' heading"

if [[ $fail -ne 0 ]]; then
  echo "[release-tag-gate] $tag REFUSED (fix the handoff / versions; the operator deletes a bad tag, propose-first)" >&2
  exit 1
fi
echo "[release-tag-gate] OK -- $tag is gated by $handoff" >&2
exit 0
