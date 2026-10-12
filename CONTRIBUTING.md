# Contributing

This project is built session-by-session against a staged handoff bundle: 21 stages to v0.1.0.
Stages 1–20 are tagged `v0.0.NN`, and Stage 21 is the `v0.1.0` release. All work funnels
through pull requests; `main` is protected. The conventions below apply to everyone (humans and AI agents
alike).

## Commit messages — Conventional Commits

Every commit follows `<type>(stage-NN): <subject>` where:

- **type** is one of: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`,
  `ci`, `perf`, `style`, `build`
- **stage-NN** is the current stage being worked (e.g. `stage-01`,
  `stage-04`). Stage-spanning changes use the most recent stage tag.
- **subject** is imperative, no trailing period, ≤ 72 chars.

Examples:
- `feat(stage-03): add OpenFOAM walking-skeleton adapter`
- `ci(stage-01): wire pre-commit and GitHub Actions workflows`
- `fix(stage-05): tighten Cf tolerance on TMR flat plate`
- `docs(stage-04): ADR-004 four-fold provenance contract`

The `commit-lint` CI check enforces this on every commit and the PR title.

Optional commit-body footers:
- `BREAKING CHANGE: <description>` — emits a major-version bump signal
- `Refs #<issue-number>`
- `Co-Authored-By: Name <email>`

## PR review — Conventional Comments

Review comments use the [Conventional Comments](https://conventionalcomments.org/)
labels:

| Label | Meaning |
|---|---|
| `praise:` | recognising something positive |
| `nitpick:` | trivial; suggestion can be ignored |
| `suggestion:` | reviewer prefers, author may push back |
| `issue:` | must be addressed before merge |
| `todo:` | author should address, not blocking |
| `question:` | reviewer wants clarification |
| `thought:` | reflection, no action required |
| `chore:` | mechanical change (rebase, lint, etc.) |
| `note:` | informational |

## PR workflow

1. Branch from `main`: `<type>/<short-slug>` or `stage-NN/<short-slug>`.
2. Make commits per the convention above.
3. `pre-commit run --all-files` locally; all green.
4. `gh pr create --base main --head <branch>` with PR title in Conventional
   Commits form and body describing what / why.
5. Every required check must go green (the list below). A skipped required job is not a pass.
   Non-required jobs (`vv-smoke`, `provenance-completeness`, `secret-scan`, the informational
   licence re-verify and pip-audit, crate conformance) are read, not ignored.
6. **24-hour cooling-off guideline.** Wait 24 h after a PR's last non-trivial change before
   merging, unless it is a documented hotfix, so there is time for second thoughts and outside
   review. It is a convention, not enforced by CI. Constitution amendments wait at least 72 h
   (`CONSTITUTION.md`, "Amendment process").
7. Merge: squash, linear history. The PR title becomes the squash commit
   message — keep it clean.

## Branch protection on `main`

- **Required status checks** (strict: the branch must be up to date). The registry of record is
  `.github/required-checks.json`; `tests/unit/test_workflow_hygiene.py` keeps it byte-identical
  to the workflow job names.
  - `ruff`
  - `mypy (strict on aero/)`
  - `pytest unit (py3.12)`
  - `README STATUS block consistency`
  - `enforce Conventional Commits on PR title and every commit`
  - `import aero with no extras`
  - `vv-required — stage-gated V&V`
  - `fence`
  - `small-signal-gate — Invariant 10`
  - `data-origin-fence — Invariant 11`

  At Stage 21, `crate round-trip — Invariant 13` and `dependency licence scan — Invariant 5` join
  them after their first green run on `main`.
- **Code-owner review** is required, with 0 approving reviews: the sole code owner is the repo
  admin, who merges.
- Linear history (squash merges); no force pushes; no direct pushes.
- `enforce_admins: false`, so the solo admin can self-merge (ADR-001). Because that means a red PR
  *can* be merged, a release is gated separately: `scripts/release_readiness.py --online` verifies
  every required context on the release commit (ADR-049).

## Post-stage handoff (mandatory)

Every stage completes with a handoff at
`docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md`, written from the template
at `docs/handoffs/_template.md`. The `v0.0.NN` git tag is gated on the
handoff existing with valid frontmatter, and so is a `vX.Y.Z` release tag (ADR-049). The `Stop`
hook in `.claude/settings.json` enforces this in Claude Code sessions. CI enforces it on tag push
(`tag-handoff-gate.yml`, which runs `scripts/check_release_tag.sh`).

Required handoff sections: deliverables status, decisions made (with
rationale), deviations from plan, environment/dependency/schema changes,
CI/CD changes, gotchas discovered, open items for the next stage, pointers
for next session, artifacts produced, confidence/risk note.

## Pre-commit hooks

Install once after cloning:

```sh
pre-commit install
```

The hooks include ruff (lint + format), mypy (strict on `aero/`), gitleaks
(secret scanning), `validate-pyproject`, large-file check, local pytest-unit
and docs-status-sync hooks. **Never bypass with `--no-verify`** — if a hook
is wrong, fix the hook, not the bypass.

## Dependency policy

Install from a clone with `uv sync` (add `--extra <name>` per extra). Released wheels are attached
to the GitHub Release. **Do not install `aero` from PyPI**: that name on PyPI belongs to an unrelated
project.

- **Base dependencies:** numpy, pydantic, typer, loguru and dvc. The `aero/` core imports only
  stdlib + numpy + pydantic (Invariant 1).
- **Heavy dependencies** (solver Python wrappers, ML frameworks, cloud SDKs) live in optional
  extras (`openfoam`, `su2`, `provenance`, …; Invariant 4). Every heavy version pin is documented
  in an ADR.
- **Licences:** every locked package must carry a GPL-3.0-compatible licence or a reviewed
  exact-version exception. This is checked by `dependency licence scan — Invariant 5` over
  `uv.lock` (ADR-048).
- **Changing dependencies:** after a change, run `uv lock`. If a new or changed package lacks clean
  metadata, run `python3 -I scripts/licence_scan.py refresh` and review the result. See
  [`CONSTITUTION.md`](CONSTITUTION.md).

## Secret hygiene

No secrets in the repo, ever. `.env*`, `*.key`, `*.pem` are gitignored.
Secrets live in Vault (`aero-vault`, LXC 217; ADR-004) and are injected as environment variables
at job time. In CI they are scoped to the step that needs them. The `gitleaks` pre-commit hook
and the `secret-scan` workflow catch leaks. See [`SECURITY.md`](SECURITY.md).

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). We also follow academic norms of intellectual
honesty and crediting prior work:
- cite results by their crate digest plus the four-tuple;
- never relax a pre-registered band to make something pass;
- report a NO-GO as plainly as a GO.

## Reporting bugs and asking for features

Use the issue templates. A bug report about a result names its four-tuple or its crate id and the
platform version. A feature request answers the SCOPE-GATE question: does it serve the optimizer
mission or the flapping-wing flagship?
