# ADR-016 — FSI structural-solver strategy (verify on the supported tutorial; CalculiX for the application)

- **Status:** proposed (decision recorded now; formalized + validated at Stage 18)
- **Date:** 2026-06-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 09)
- **Stage:** 09 (decision); 18 (execution)

## Context and problem statement

Flexible flapping wings — the flagship capstone forward capability (ADR-013;
governing scope §4) — are a fluid-structure-interaction problem. The repo's preCICE
path is unbuilt (`aero/adapters/precice/` and `aero/vv/fsi/` are `.gitkeep` stubs), and
FSI is the hardest, riskiest capability on the roadmap. Two facts shape the choice:

1. The **official preCICE Turek-Hron FSI3 tutorial** (the canonical coupling benchmark)
   pairs OpenFOAM with a **deal.II or Nutils** solid solver — **not** CalculiX. An
   OpenFOAM+CalculiX Turek-Hron exists only as community cases.
2. The **application** (a thin, flexible flapping wing) needs **shell/membrane** elements
   that **CalculiX** supports well and deal.II/Nutils do not provide out of the box.

The operator asked to decide the structural-solver fallback now, before the constitution
PR, so the roadmap (Stages 18–19) is concrete.

## Decision drivers

- **Trust the coupling benchmark.** Verifying preCICE itself should ride the *maintained,
  supported* tutorial, not a fight with an unmaintained community case.
- **Fit the application.** Flexible bio wings are thin shells — CalculiX is the mature
  open-source path; deal.II/Nutils are not shell-oriented.
- **Validate each layer independently.** Coupling-correctness and application-fidelity
  are separate claims with separate references.

## Considered options

1. **Split: deal.II/Nutils for Turek-Hron verification; CalculiX for the application** —
   chosen.
2. **CalculiX everywhere** (community Turek-Hron + application) — one solid solver, but
   verification rides an unmaintained case.
3. **deal.II/Nutils everywhere** — stays on the supported tutorial, but the flexible-wing
   application is poorly served (no shell elements).

## Decision outcome

Chose **Option 1** — use each named solver for its strength:

- **Stage 18 (coupling verification):** populate `aero/adapters/precice/` + the
  `aero[precice]` extra; verify the coupling on the **supported OpenFOAM + deal.II/Nutils
  Turek-Hron FSI3 tutorial** → gate on displacement amplitude + frequency within the
  published Turek & Hron (2006) bands (`aero/vv/fsi/`). Also build the CalculiX SIF here.
- **Stage 19 (flexible-flapping application):** **OpenFOAM + CalculiX** flexible-wing
  FSI, validated on its own against **Heathcote-Gursul** flexible-foil data, with a
  documented caveat that the canonical Turek-Hron used a different solid solver (so the
  coupling-correctness evidence and the application-fidelity evidence are distinct).

## Consequences

- **Positive:** coupling verification is trustworthy (supported tutorial); the
  application uses the right structural model (shells); each claim has its own reference.
- **Negative:** two solid solvers in the stack (deal.II/Nutils + CalculiX) — extra SIF
  build + maintenance surface. Accepted: each is used where it is strongest.
- **Neutral / followup:** confirm the preCICE 3.x OpenFOAM adapter + CalculiX adapter
  version pins at Stage 18 (Hard Rule 8); this ADR moves to `accepted` once the
  Turek-Hron gate passes.

## Links

- Related ADR: ADR-013 (mission refocus; FSI is the flagship capstone)
- Governing scope: `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` §2, §4
- Stage map: `docs/handoff-bundle/README-handoff.md` (Stages 18–19)
- External: Turek & Hron (2006) FSI benchmark; preCICE 3.x tutorials
  (precice.org/tutorials-turek-hron-fsi3); Heathcote & Gursul (2007), AIAA J. 45(5)
