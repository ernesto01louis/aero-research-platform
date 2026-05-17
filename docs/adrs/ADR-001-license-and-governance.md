# ADR-001 — License, Governance, and Stage-01 Bootstrap Posture

- **Status:** accepted
- **Date:** 2026-05-17
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 01)
- **Stage:** 01

## Context and problem statement

Stage 01 establishes the scaffolding and conventions that every
subsequent stage inherits. Four decisions are load-bearing and must be
recorded before any code lands:

1. **License posture** — GPL-3.0 vs AGPL-3.0 (the stage prompt
   explicitly defers this).
2. **Branch protection ruleset** for `main`, including the
   solo-developer admin-bypass posture.
3. **mypy strictness scope** — strict on `aero/` core, lenient
   elsewhere; relaxations require an ADR.
4. **Commit / PR conventions** — Conventional Commits scoped to
   `stage-NN` and Conventional Comments.

Constraints: peer-review-grade reproducibility, full open-source,
single developer with Claude Code agent as elevated actor, OpenFOAM-
heavy solver stack.

## Decision drivers

- **OpenFOAM compatibility.** OpenFOAM is GPL-3. Most of the
  computational aero open-source ecosystem (SU2 LGPL, PyFR BSD-3,
  NekRS BSD-3, JAX-Fluids GPL-3, preCICE LGPL) is comfortable with
  GPL-3.
- **Reviewer expectations.** Academic peer-review CFD platforms
  default to GPL-family licenses; reviewers don't ding for AGPL but
  they don't reward it either.
- **No SaaS plans.** This is a research platform, not a SaaS product.
  AGPL-3's main delta over GPL-3 (the network-use trigger) buys
  little.
- **Solo developer with admin role.** Strict 1-approver branch
  protection without admin bypass would prevent the operator from
  merging any PR. We need a structural escape valve.
- **Memory model anchored on stage-NN scope.** The handoff bundle is
  16 stages; every commit and review trace anchors on the stage.

## Considered options

### License

1. **GPL-3.0** — OpenFOAM-aligned. Standard for academic CFD.
2. **AGPL-3.0** — closes the SaaS loophole; otherwise identical.

### Branch protection

1. **Strict (no admin bypass).** Prevents *all* direct push to main.
   Solo developer cannot merge own PRs.
2. **Pragmatic (admin bypass enabled, `enforce_admins: false`).** PR +
   CI required for non-admins; admin can self-merge.

### mypy strictness

1. **Strict everywhere.** mypy --strict on `aero/` and `tests/` and
   `scripts/` and `ansible/` (where applicable).
2. **Strict on aero/ only.** Tests and ops scripts opt out via
   per-module overrides.

### Commit / PR conventions

1. **Conventional Commits with arbitrary scope.** `feat(openfoam):`,
   `feat(domino):`, etc.
2. **Conventional Commits with `stage-NN` scope.** Every commit
   anchored to the stage that's currently in flight.

## Decision outcome

1. **License: GPL-3.0.** Aligns with OpenFOAM and the broader open-
   source CFD ecosystem. No SaaS plans, so AGPL's incremental value is
   nil. LICENSE file is the canonical FSF copy (sha256
   `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`).

2. **Branch protection: pragmatic (admin bypass enabled).** Required
   status checks: `lint`, `type`, `test`, `docs-sync`, `commit-lint`.
   `enforce_admins: false` so the operator (sole admin) can
   self-merge. Linear history required, no force pushes, no direct
   pushes. CODEOWNERS approval set to 1 (will resolve via admin
   bypass for solo work). **Revisit if/when collaborators join.**

3. **mypy strictness: strict on `aero/` only.** Per-module override
   in `pyproject.toml` `[tool.mypy.overrides]`. Tests are
   `ignore_errors=true`. Relaxing the strict-on-aero rule for a
   specific module requires a new ADR documenting the reason.

4. **Conventions: Conventional Commits scoped to `stage-NN`** plus
   Conventional Comments for review. `commit-lint.yml` enforces the
   scope pattern `^stage-\d{2}$` on every commit AND the PR title.

### Consequences

- **Positive:**
  - License clarity from day one; CITATION.cff and Zenodo deposit
    (Stage 04) target a stable license string.
  - Solo developer can ship without procedural deadlock.
  - mypy strictness scoped to where it matters; tests stay agile.
  - Stage-anchored commits make changelogs assemble cleanly per
    `v0.0.NN` tag.
- **Negative:**
  - Admin bypass means the PR-review gate is *procedural* (the
    operator can override), not *technical*. The 24-hour cooling-off
    rule in CONTRIBUTING.md is the secondary safety net.
  - GPL-3 may complicate eventual commercial integrations downstream
    (e.g., closed-source FEM coupling). Out of scope for v0.1; if it
    arises later, an ADR addresses the specific case.
  - Stage-NN scope makes commits that *span* stages awkward; the
    convention is "use the most recent stage" (documented in
    `.claude/rules/conventional-commits.md`).
- **Neutral / followup work:**
  - Once collaborators join, revisit the admin-bypass posture in a
    new ADR.
  - License-scan tooling lands in Stage 16; this ADR is its anchor.

## Pros and cons of considered options

### License — GPL-3.0 (chosen)

- Good: OpenFOAM-aligned, recognized in academic CFD reviews, strong
  copyleft protects derivative works staying open.
- Bad: Network-use loophole (SaaS use without source release) — not
  relevant here.

### License — AGPL-3.0

- Good: Closes the SaaS loophole.
- Bad: No SaaS plans for this project; the incremental value is nil.
  AGPL also creates friction with some downstream OSS projects that
  shy from AGPL deps.

### Branch protection — strict (no admin bypass)

- Good: Maximum technical enforcement.
- Bad: Solo developer cannot self-merge any PR; project stalls.

### Branch protection — pragmatic (admin bypass)

- Good: Solo developer can ship; technical enforcement still kicks in
  for any non-admin contributor.
- Bad: PR review becomes a procedural gate (operator self-discipline +
  24-hour cooling-off) rather than a hard technical one.

### mypy — strict everywhere

- Good: Maximal type safety.
- Bad: Slows test iteration; ops scripts and ansible templates aren't
  meant to be statically typed.

### mypy — strict on aero/ only (chosen)

- Good: Type safety where the platform contract lives; flexibility
  elsewhere.
- Bad: Relies on developer discipline to keep test fixtures from
  drifting from their typed analogs.

### Conventions — arbitrary scope

- Good: More flexible naming.
- Bad: Hurts the per-stage changelog generation that the post-stage
  handoff model requires.

### Conventions — `stage-NN` scope (chosen)

- Good: Anchors every commit to the staged plan; changelog generation
  is trivial; cross-session memory model aligns.
- Bad: Cross-stage refactors need a convention (use the most-recent
  stage) — documented.

## Links

- Stage prompt: `STAGE-01-scaffolding-and-conventions.md` (operator's
  handoff bundle)
- Project brief: `00-CONTEXT-project-brief.md`
- LICENSE: <https://www.gnu.org/licenses/gpl-3.0.txt>
- Conventional Commits: <https://www.conventionalcommits.org/>
- Conventional Comments: <https://conventionalcomments.org/>
- ASME V&V 20 (informs Stage 05+ V&V harness): cited there
