# STAGE-01: Scaffolding & Conventions

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief (§"Repository layout", §"Hard rules", §"The four-layer memory
model", §"What goes in the post-stage handoff"):

- Empty repo → green CI on `main`.
- `CLAUDE.md`, `AGENTS.md` (redirect), `CONSTITUTION.md`, `README.md`, `CITATION.cff`,
  `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`.
- `pyproject.toml` with optional extras enumerated (see brief; populated as skeletons,
  no heavy deps installed yet).
- `.pre-commit-config.yaml` with ruff, mypy (lenient), pytest unit, gitleaks, validate-
  pyproject, large-file check.
- `.github/workflows/` with `lint`, `type`, `test`, `docs-sync` workflows; `CODEOWNERS`.
- `.claude/` directory with `settings.json` (hooks + allowedTools + MCP placeholders),
  `rules/`, `agents/`, `skills/`, `commands/` (the latter three with at minimum
  README placeholders).
- `docs/handoffs/_template.md` — the canonical post-stage handoff template.
- `docs/adrs/_template.md` — ADR template (MADR or Nygard style).
- `docs/handoffs/STAGE-01-scaffolding-and-conventions-DONE-YYYY-MM-DD.md` — this
  stage's own post-stage handoff, written at the end.
- Branch protection on `main` configured (PR required, status checks required,
  linear history, 24-hour cooling-off rule, CODEOWNERS approval).
- First git tag: `v0.0.1`.

## ROLE

You are bootstrapping a greenfield, peer-review-grade aerodynamics research platform
from an empty GitHub repository. This is the only session in which the scaffolding
exists in a malleable form — get every convention right now, because every subsequent
session will inherit them.

You will not write any solver, ML, or domain-specific code in this session. You are
building the structural foundation.

## GOAL

Numbered deliverables:

1. Clone the empty repo locally; verify it is truly empty (no README, no license, no
   .gitignore).
2. Create the file tree from §"Repository layout" in the project brief. Directories
   may be empty (with `.gitkeep`) except where this stage explicitly creates content.
3. Author `CLAUDE.md` using the drop-in starter from Pass 3 §"Sample CLAUDE.md",
   adapted to current paths. **Hard rules section is verbatim from the project brief
   §"Hard rules".**
4. Author `AGENTS.md` as a one-line redirect: `See [CLAUDE.md](./CLAUDE.md).` plus
   a paragraph of context for non-Claude tools.
5. Author `CONSTITUTION.md` in spec-kit-compatible form, codifying:
   - PLATFORM-NOT-HUB invariant
   - FAIL-LOUD invariant
   - PROVENANCE-FROM-DAY-ONE invariant
   - Optional-extras-only-for-heavy-deps invariant
   - GPL-3/LGPL-3/Apache-2/BSD-3-only license posture
   - Conventional Commits + Conventional Comments contract
6. Author `README.md` with sections: Project name, one-paragraph what-it-is,
   `## Status` (auto-regenerated marker — see deliverable 13), `## Quick start`
   (just `pip install aero` for now), `## Documentation`, `## License`, `## Citation`.
7. Author `CITATION.cff` (CFF v1.2.0) with placeholder Zenodo DOI to be filled in
   Stage 04. Validate with `cffconvert --validate`.
8. Author `CHANGELOG.md` following Keep-a-Changelog, with one `[v0.0.1]` section for
   this stage's deliverables.
9. Author `CONTRIBUTING.md` documenting Conventional Commits format
   `<type>(<stage-NN>): <subject>`, Conventional Comments labels, PR workflow,
   pre-commit, the 24-hour PR cooling-off rule, the post-stage handoff requirement.
10. Author `SECURITY.md` documenting: no secrets in repo, `.env` gitignored, Vault
    pointer (placeholder host), threat model (single-developer with Claude Code agent
    as elevated actor), responsible disclosure path.
11. Choose and add `LICENSE`. **Propose either AGPL-3.0 or GPL-3.0 to the user with
    the tradeoff**: AGPL-3.0 closes the SaaS loophole for academic platforms; GPL-3.0
    is the OpenFOAM-aligned default. **Wait for the user's pick.**
12. Author `pyproject.toml` (uv-managed; PEP 621 metadata):
    - Project name `aero`, version `0.0.1`, Python `>=3.12`.
    - Base dependencies: `numpy`, `pydantic`, `typer`, `loguru`, `dvc`.
    - All optional extras enumerated as empty/skeleton lists (the brief's table) so
      stages can add to them without changing structure.
    - `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` configured.
    - `[tool.uv]` configured for `requires-python = ">=3.12"`.
13. Author `.pre-commit-config.yaml` with:
    - `ruff` (lint + format)
    - `mypy` (start with `--strict` enabled on `aero/` only, lenient elsewhere — relax
      per-module only with ADR)
    - `pytest -q tests/unit -x` (fail-fast)
    - `gitleaks` for secret scanning
    - `validate-pyproject`
    - `check-added-large-files --maxkb=500`
    - `check-merge-conflict`
    - A custom local hook `docs-status-sync` that fails if `README.md`'s `## Status`
      block is hand-edited (i.e., differs from what's regenerated from the latest
      `docs/handoffs/STAGE-NN-*-DONE-*.md` frontmatter)
14. Author `.github/workflows/`:
    - `lint.yml`: ruff
    - `type.yml`: mypy
    - `test.yml`: pytest -q tests/unit on Python 3.12, matrix-ready for 3.13
    - `docs-sync.yml`: regenerates README's `## Status` from latest handoff and
      fails if a hand-edit is detected
    - `commit-lint.yml`: enforces Conventional Commits on PR titles AND every commit
    - `vv-smoke.yml`: placeholder workflow that just echoes "V&V smoke not yet wired";
      Stage 05 turns this real
15. Author `.github/CODEOWNERS` with `* @ernesto01louis`.
16. Configure branch protection on `main` (via `gh` CLI):
    - Require PR before merging
    - Require status checks: `lint`, `type`, `test`, `docs-sync`, `commit-lint`
    - Require linear history
    - Require CODEOWNERS approval (1 approver)
    - Disallow force pushes
    - Disallow direct pushes
17. Author `.claude/settings.json` with:
    - `hooks`: `PreToolUse` matchers blocking `rm -rf` of any non-temp path,
      `git push --force*`, `dvc destroy`, `DROP TABLE`; `Stop` hook checking for
      the post-stage handoff existing
    - `allowedTools`: explicit list (Bash, Read, Write, Edit, Glob, Grep,
      WebFetch — Task and SlashCommand as needed)
    - `mcp_servers`: filesystem (scoped to repo), github (PAT placeholder), postgres
      (deferred to Stage 04) commented out
18. Author `.claude/rules/conventional-commits.md`, `.claude/rules/handoff-discipline.md`,
    `.claude/rules/fail-loud-pydantic.md` as path-scoped lazy-loaded rules.
19. Author `.claude/commands/stage-start.md`, `.claude/commands/stage-end.md`,
    `.claude/commands/handoff-write.md` as slash command definitions.
20. Author `docs/handoffs/_template.md` — copy the post-stage handoff template from
    Pass 3 §4.2 verbatim.
21. Author `docs/adrs/_template.md` — MADR-style.
22. Author `docs/architecture/README.md`, `docs/sota/README.md`,
    `docs/handoff-bundle/README.md` as one-line placeholders pointing to where the
    Pass 1, Pass 2, and Pass 3 documents will be archived (the operator will commit
    those documents in this stage as well — propose this and wait for paths).
23. Create the empty subdirectories under `aero/`, `tests/`, `containers/`, `data/`,
    `ansible/`, `scripts/` with `.gitkeep` files.
24. Write the FIRST `tests/unit/test_smoke.py` that imports `aero` and asserts the
    version string. Verify it passes locally.
25. Commit everything in **logical chunks** following Conventional Commits (e.g.,
    `chore(stage-01): scaffold repository layout`, `feat(stage-01): add CLAUDE.md and
    CONSTITUTION`, `ci(stage-01): wire pre-commit and GitHub Actions`, `docs(stage-01):
    add post-stage handoff template`). Open the first PR. Wait for the operator to
    review and merge. Then tag `v0.0.1`.
26. Write the post-stage handoff at `docs/handoffs/STAGE-01-scaffolding-and-conventions-
    DONE-YYYY-MM-DD.md` using the template you just created. **Do not tag `v0.0.1`
    until this handoff exists and is committed.**

## WHY

The orchestrator project's audit lessons (cited in the RF bundle README) and the
best-practices research (Pass 3) converge on a single point: documentation and
enforcement debt accumulated at Stage 01 is unrecoverable later. The README that
claimed Phase 0 when Phase 3 was done, the deferred branch protection that bit
later, the inline schema fallback that drifted from reality — all of these are
Stage-01 sins. We pay the tax up front.

The post-stage handoff template is the bridge across Claude Code's session amnesia.
Every subsequent stage's "BEFORE YOU START — READ" line names the previous handoff.
Get the template right now; every later session benefits.

The four-layer memory model (CLAUDE.md, `.claude/rules/`, STAGE-NN, post-stage
handoff) requires all four layers to exist before Stage 02. This stage stands them
all up.

## HOW (think through this)

- Bootstrap with `gh repo clone` (or `git clone` after the operator confirms the
  remote exists and is empty).
- For each file, **write it locally, run `pre-commit run --all-files`, then commit**.
  Pre-commit hooks are not yet installed in the repo at the moment of the very first
  commit; install them in the second commit, then re-run on everything.
- `pyproject.toml`'s optional extras can use empty version specs (`physicsnemo-cu12 =
  []`) as placeholders; Stage 08+ will populate them. Mark them with a comment
  pointing to the stage that will fill them.
- For CITATION.cff: leave `doi:` blank and add a TODO comment pointing to Stage 04
  where the Zenodo concept DOI gets reserved.
- The README `## Status` block must contain machine-readable markers:
  `<!-- STATUS:START -->` / `<!-- STATUS:END -->`. The `docs-status-sync` hook
  regenerates the content between those markers from the latest handoff frontmatter
  (`stage`, `stage_name`, `stage_tag`, `date_completed`).
- For branch protection: `gh api -X PUT repos/:owner/:repo/branches/main/protection`
  with the JSON body. Verify with `gh api repos/:owner/:repo/branches/main/protection`.
- For the Stop hook (post-stage handoff existence check): a small shell script under
  `scripts/check_handoff_exists.sh` that grep's `docs/handoffs/` for a file matching
  `STAGE-NN-*-DONE-*.md` where `NN` is the current stage (passed via env or inferred
  from latest commit message). Refuse to allow Stop until the file exists and has
  the required frontmatter fields.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md` (always, every session)
- `STAGE-01-scaffolding-and-conventions.md` (this file)
- The Pass 3 best-practices guide (operator will provide path or paste relevant
  sections, especially the "Sample CLAUDE.md" and §4.2 handoff template)
- No previous handoff exists for Stage 01

## GUARDRAILS — DO NOT

1. Do NOT install or pin any solver, ML framework, or cloud SDK in this stage. The
   `pyproject.toml` optional extras are placeholders.
2. Do NOT push directly to `main`. Even the initial commit goes through a PR.
3. Do NOT use `--no-verify`, `--force`, or `--dangerously-skip-permissions`.
4. Do NOT generate boilerplate license text from memory; pull it from the canonical
   SPDX/GNU sources. Verify the LICENSE file character-for-character matches the
   reference.
5. Do NOT commit a `.env` file. Add `.env`, `.env.*`, `*.key`, `*.pem`, `*.sif`,
   `.dvc/cache/`, `mlruns/` to `.gitignore` from the start.
6. Do NOT enable Dependabot, Renovate, or auto-merge in this stage. Add manually
   later if needed (separate stage / ADR).
7. Do NOT skip writing the post-stage handoff. The git tag `v0.0.1` is gated on it.

## DELIVERABLES (acceptance criteria — each is a shell command)

- [ ] Repository cloned, layout matches §"Repository layout": `tree -L 2 -a -I '.git'`
- [ ] CLAUDE.md, AGENTS.md, CONSTITUTION.md, README.md, CITATION.cff, CHANGELOG.md,
      CONTRIBUTING.md, SECURITY.md, LICENSE present: `ls -1`
- [ ] `pyproject.toml` validates: `validate-pyproject pyproject.toml`
- [ ] CITATION.cff validates: `cffconvert --validate`
- [ ] Pre-commit hooks installed and clean: `pre-commit run --all-files`
- [ ] First smoke test passes: `pytest -q tests/unit/test_smoke.py`
- [ ] Branch protection active: `gh api repos/:owner/:repo/branches/main/protection
      | jq '.required_pull_request_reviews.required_approving_review_count' = 1`
- [ ] All CI workflows green on the first PR
- [ ] PR merged via squash with linear history preserved
- [ ] `docs/handoffs/_template.md` exists
- [ ] `docs/handoffs/STAGE-01-*-DONE-*.md` exists and frontmatter complete
- [ ] Tag created: `git tag v0.0.1` (only after handoff exists)
- [ ] CHANGELOG.md has `[v0.0.1]` section listing deliverables

## PROPOSE FIRST, EXECUTE LATER

Wait for the literal word `approved` from the operator before:

- Pushing the first commit (operator should sanity-check the file tree)
- Enabling branch protection (it locks you out of direct push; confirm intent)
- The LICENSE choice between AGPL-3.0 and GPL-3.0
- The tag `v0.0.1` (only after the operator confirms the handoff is satisfactory)

## POST-STAGE HANDOFF

Before tagging `v0.0.1`, write `docs/handoffs/STAGE-01-scaffolding-and-conventions-
DONE-YYYY-MM-DD.md` following the template in `docs/handoffs/_template.md`. Required
sections (all of them, even if "none" — write "none" explicitly):

1. Deliverables status — checkbox table mirroring the DELIVERABLES list above
2. Decisions made — at minimum: LICENSE choice (with rationale), mypy strictness
   policy, branch protection ruleset details
3. Deviations from the stage plan — be honest; partial counts
4. Environment / dependency / schema changes — `pyproject.toml` extras structure
5. CI/CD changes — workflows added, status checks required
6. Gotchas discovered — pre-commit caveats, branch protection lockout traps
7. Open items for the next stage — Stage 02 needs the Proxmox inventory; remind
   the user to run `PROMPT-00-proxmox-inspection.md` if not done
8. Pointers for Stage 02 — read first / do not re-read / run first to verify
9. Artifacts produced — list of files committed
10. Confidence / risk note — flag anything you're unsure about

Commit the handoff with `docs(stage-01): post-stage handoff`, then tag `v0.0.1`.
