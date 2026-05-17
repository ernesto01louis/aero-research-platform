# Contributing

This project is built session-by-session against a staged handoff bundle (16
stages, each `v0.0.NN`). All work funnels through pull requests; `main` is
protected. The conventions below apply to everyone (humans and AI agents
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
5. CI must go green: `lint`, `type`, `test`, `docs-sync`, `commit-lint`,
   and any stage-specific checks (`vv-required`, `provenance-completeness`,
   `production-budget`, `import-platform-only` from later stages).
6. **24-hour cooling-off rule** — no merge within 24 h of the PR's last
   non-trivial change unless it's a documented hotfix; this gives a chance
   for second thoughts and external reviewers to weigh in.
7. Merge: squash, linear history. The PR title becomes the squash commit
   message — keep it clean.

## Branch protection on `main`

After Stage 01 merges:

- Required status checks: `lint`, `type`, `test`, `docs-sync`, `commit-lint`
- 1 approving review via CODEOWNERS
- Linear history required (no merge commits except via squash)
- No force pushes
- No direct pushes
- `enforce_admins: false` — repo admin can self-merge for solo-developer
  workflow (revisit once collaborators join; see ADR-001)

## Post-stage handoff (mandatory)

Every stage completes with a handoff at
`docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md`, written from the template
at `docs/handoffs/_template.md`. The `v0.0.NN` git tag is gated on the
handoff existing with valid frontmatter. The `Stop` hook in
`.claude/settings.json` enforces this in Claude Code sessions; CI enforces
it on tag push.

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

Base `pip install aero` pulls only stdlib + numpy + pydantic + typer + loguru
+ dvc. Every heavy dependency (solver Python wrapper, ML framework, cloud
SDK) lives in an optional extra (`aero[openfoam]`, `aero[su2]`, etc.). Every
heavy version pin is documented in an ADR. See [`CONSTITUTION.md`](CONSTITUTION.md).

## Secret hygiene

No secrets in the repo, ever. `.env*`, `*.key`, `*.pem` are gitignored.
Secrets live in Vault (host TBD in Stage 02) and are injected as env vars at
job time. `gitleaks` pre-commit hook plus CI scan catches leaks.

## Code of conduct

We adhere to academic norms of intellectual honesty and crediting prior
work. The literature pipeline (Stage 15) is part of the citation
infrastructure — use `auto_cite` to generate BibTeX from MLflow runs rather
than reconstructing citations by hand.
