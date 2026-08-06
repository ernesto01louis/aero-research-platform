#!/usr/bin/env bash
# scripts/regenerate_status.sh
#
# Regenerate the README.md STATUS block between the markers
#   <!-- STATUS:START -->  ...  <!-- STATUS:END -->
# from the frontmatter of the most recent post-stage handoff in
# docs/handoffs/STAGE-NN-*-DONE-*.md.
#
# Usage:
#   scripts/regenerate_status.sh           # rewrite README.md in place
#   scripts/regenerate_status.sh --check   # diff-check; exit 1 if drift
#   scripts/regenerate_status.sh --print   # print regenerated block to stdout
#
# Policy:
# - If no handoff exists yet (bootstrap window during Stage 01), the
#   status block is a fixed "Stage 01 in progress — scaffolding" message.
#   --check accepts this state.
# - On `--check` mode used by pre-commit and CI: any drift between
#   README's STATUS block and the regenerated content fails. The fix is
#   to re-run this script without --check (or it's run automatically by
#   the docs-sync workflow).
#
# Limitation: this is a deliberately simple regex+sed implementation;
# upgrades to a templating engine (Jinja, mustache) can wait until the
# block grows beyond a few lines.

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
readme="$repo_root/README.md"
handoffs_dir="$repo_root/docs/handoffs"

mode="rewrite"
case "${1:-}" in
  --check) mode="check" ;;
  --print) mode="print" ;;
  "") ;;
  *)
    echo "usage: $0 [--check|--print]" >&2
    exit 64
    ;;
esac

shopt -s nullglob
handoffs=("$handoffs_dir"/STAGE-*-DONE-*.md)
shopt -u nullglob

extract_field() {
  local file="$1" field="$2"
  awk -v f="$field" '
    /^---[[:space:]]*$/ {
      n++
      if (n == 2) exit
      next
    }
    n == 1 && $0 ~ "^"f":" {
      val = $0
      sub("^"f":[[:space:]]*", "", val)
      gsub(/^["'\''[:space:]]+|["'\''[:space:]]+$/, "", val)
      print val
      exit
    }
  ' "$file"
}

generate_block() {
  if [[ ${#handoffs[@]} -eq 0 ]]; then
    # Bootstrap state: Stage 01 in progress, no handoff yet.
    cat <<'EOF'
**Stage 01 in progress** — repository scaffolding and conventions. No solver,
ML, or domain code yet.
EOF
    return
  fi

  # Most recent handoff = latest by sort key (sort by stage number then date)
  local latest
  latest="$(printf '%s\n' "${handoffs[@]}" | sort | tail -n 1)"

  local stage stage_name status date_completed stage_tag next_stage next_stage_name
  stage="$(extract_field "$latest" stage)"
  stage_name="$(extract_field "$latest" stage_name)"
  status="$(extract_field "$latest" status)"
  date_completed="$(extract_field "$latest" date_completed)"
  stage_tag="$(extract_field "$latest" stage_tag)"
  next_stage="$(extract_field "$latest" next_stage)"
  next_stage_name="$(extract_field "$latest" next_stage_name)"

  # Strip any leading "Stage NN — " prefix from next_stage_name (frontmatter
  # convention from the template puts it there; output template adds its own).
  local next_clean
  next_clean="$(printf '%s' "$next_stage_name" | sed -E 's/^Stage[[:space:]]+[0-9]+[[:space:]]+(—|-)[[:space:]]*//')"

  # A handoff's `stage_tag` states the tag the stage is HEADED FOR, not one that
  # exists. Rendering it as "Latest tag" unconditionally publishes a tag that may
  # never have been pushed: at Stage 19 the README claimed v0.0.19 before the tag
  # was created, and the handoff had to carry a correction saying so (ledger item
  # 7). Ask git instead of trusting the frontmatter.
  local tag_line
  if [[ -n "$stage_tag" ]] && git -C "$repo_root" rev-parse -q --verify "refs/tags/$stage_tag" >/dev/null 2>&1; then
    tag_line="**Latest tag:** $stage_tag"
  else
    # Name the intended tag, but do not claim it exists.
    tag_line="**Latest tag:** ${stage_tag:-v0.0.0} (not yet tagged)"
  fi

  # A `partial` stage is not finished, so the next thing to do is FINISH IT.
  # Pointing at the following stage would tell a reader — and the next session —
  # to start work that this one has not earned.
  local next_line
  if [[ "$status" == "partial" || "$status" == "blocked" ]]; then
    # `stage_name` already carries its own "Stage NN — " prefix.
    next_line="**Next:** resume $stage_name — ${status}, not finished."
  else
    next_line="**Next:** Stage ${next_stage:-?} — ${next_clean:-TBD}."
  fi

  cat <<EOF
$tag_line  ·  **Status:** ${status:-unknown}  ·  **Completed:** ${date_completed:-—}

**$stage_name** — most recent stage.

$next_line

See [\`docs/handoffs/\`](docs/handoffs/) for per-stage exit notes and
[\`CHANGELOG.md\`](CHANGELOG.md) for the version-tagged change log.
EOF
}

new_block="$(generate_block)"

if [[ "$mode" == "print" ]]; then
  printf '%s\n' "$new_block"
  exit 0
fi

if [[ ! -f "$readme" ]]; then
  echo "ERROR: $readme not found" >&2
  exit 2
fi

# Extract current block between markers
current_block="$(
  awk '
    /<!-- STATUS:START -->/ { inside=1; next }
    /<!-- STATUS:END -->/   { inside=0; next }
    inside { print }
  ' "$readme"
)"

# Both forms with leading/trailing whitespace stripped for comparison
canon() {
  printf '%s' "$1" | awk 'BEGIN{p=0} { if (NF){ p=1 } if (p) print }' \
    | sed -e 's/[[:space:]]*$//'
}

current_canon="$(canon "$current_block")"
new_canon="$(canon "$new_block")"

if [[ "$mode" == "check" ]]; then
  if [[ "$current_canon" != "$new_canon" ]]; then
    echo "ERROR: README.md STATUS block is out of sync with latest handoff." >&2
    echo "  Expected:" >&2
    printf '%s\n' "$new_canon" | sed 's/^/    /' >&2
    echo "  Actual:" >&2
    printf '%s\n' "$current_canon" | sed 's/^/    /' >&2
    echo "Run 'scripts/regenerate_status.sh' to fix." >&2
    exit 1
  fi
  exit 0
fi

# Rewrite mode: in-place substitution between the markers
tmp="$(mktemp)"
awk -v new_block="$new_block" '
  /<!-- STATUS:START -->/ {
    print
    print new_block
    inside=1
    next
  }
  /<!-- STATUS:END -->/ {
    inside=0
    print
    next
  }
  !inside { print }
' "$readme" > "$tmp"
mv "$tmp" "$readme"
echo "Updated $readme STATUS block."
