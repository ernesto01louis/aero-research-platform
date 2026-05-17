# Rule — Conventional Commits + Conventional Comments

## Scope

This rule applies to every commit, PR title, and review comment in the
repository. Loaded lazily when a Bash command involves `git commit` /
`gh pr create` / `gh pr review`.

## Format

```
<type>(stage-NN): <subject>

[optional body]

[optional footers: Refs #N, Co-Authored-By: ...]
```

**type** ∈ {`feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `ci`, `perf`,
`style`, `build`}

**scope** is always `stage-NN` (two-digit zero-padded, 01-16). Use the
current stage from `.aero-stage` at repo root.

**subject** is imperative, no trailing period, ≤ 72 chars.

## Examples

Good:
- `feat(stage-03): add OpenFOAM walking-skeleton adapter`
- `fix(stage-05): tighten Cf tolerance on TMR flat plate`
- `ci(stage-01): wire pre-commit and GitHub Actions workflows`
- `chore(stage-02): bootstrap aero-build LXC via Ansible`
- `docs(stage-04): ADR-004 four-fold provenance contract`

Bad:
- `Add OpenFOAM adapter.` (no type, no scope, trailing period)
- `feat: add OpenFOAM adapter` (missing scope)
- `feat(openfoam): add adapter` (scope must be `stage-NN`, not topic)
- `Stage 3: openfoam` (not Conventional Commits at all)

## Enforcement

`commit-lint.yml` validates the PR title AND every commit in the PR. The
build fails on any mismatch. Local pre-commit also runs commitlint when
configured.

## Review labels — Conventional Comments

Use these prefixes on PR review comments:

| Label | When |
|---|---|
| `praise:` | recognising something positive |
| `nitpick:` | trivial; can be ignored |
| `suggestion:` | reviewer prefers, author may push back |
| `issue:` | must be addressed before merge |
| `todo:` | author should address, not blocking |
| `question:` | reviewer wants clarification |
| `thought:` | reflection; no action required |
| `chore:` | mechanical change (rebase, lint, etc.) |
| `note:` | informational |

## Why

Stage-NN scoping makes the changelog assemble cleanly per `v0.0.NN` tag.
Labels make review threads scannable for "what blocks merge" vs "nice to
have".
