# ADR-016 — FSI structural-solver strategy (verify on the supported tutorial; CalculiX for the application)

- **Status:** accepted (2026-07-28, Stage 19 — the Turek-Hron FSI3 gate PASSED; see the validation record at the end. Body stage numbers predate the ratified Stage-16 insertion: read 18→19, 19→20. Editorial note added Stage 18; decision unchanged.)
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


---

## Validation record — Stage 19 (2026-07-28): the FSI3 gate passed, ADR accepted

This ADR was recorded `proposed` at Stage 09 with an explicit condition: *"this ADR moves
to `accepted` once the Turek-Hron gate passes."* It has now passed, so the status changes.

**What was run.** The supported upstream preCICE Turek-Hron FSI3 tutorial — OpenFOAM-ESI
v2412 (pimpleFoam) fluid coupled to the Nutils St. Venant-Kirchhoff solid — verbatim at
the pinned commit `cd33e2db`, through the platform's own plumbing
(`aero/adapters/precice/`), on the upstream default mesh (20 969 cells) to
`max-time = 8.0 s`. 8000 coupled time windows in 20.30 h wall clock, both participants
exiting cleanly. Run `turek_hron_fsi3-20260727-152140`; bundle
`data/vv/stage19_turek_hron_fsi3.json`.

**Against the bands pre-registered in ADR-036 before any campaign run:**

| gate | quantity | measured | reference | error | band | |
|---|---|---|---|---|---|---|
| D1 | flag-tip transverse amplitude | 3.408544e-2 m | 3.495533e-2 | +2.49 % | 15 % | PASS |
| D2 | fundamental frequency | 5.490204 Hz | 5.539872 | +0.90 % | 5 % | PASS |
| D3 | streamwise amplitude | 2.827944e-3 m | 2.700146e-3 | +4.73 % | 25 % | PASS |
| D4 | streamwise mean | −2.727524e-3 m | −2.856809e-3 | +4.53 % | 25 % | PASS |
| D5 | streamwise frequency | 10.94931 Hz | 11.07420 | +1.13 % | 5 % | PASS |

Diagnostic, never gated: transverse mean 1.644498e-3 m.

Supporting gates: **K1** — 8000 of 8000 windows converged, mean 5.40 coupling iterations
against a cap of 100, zero non-converged. **S3** — 19 settled cycles after the
unconditional 4.0 s discard. **P3** — four-fold provenance from a clean tree
(`git_sha 2a5bbd63`, `container_sif_sha256 ce795873…` = the recorded `precice-fsi.sif`).

**What this does and does not establish.** It establishes **coupling correctness**: the
platform can drive a partitioned FSI problem through preCICE and reproduce a published
benchmark's flag-tip motion. It does **not** establish application fidelity for a flexible
flapping wing — that is a separate claim, with a CalculiX solid and its own experimental
reference (Heathcote-Gursul), and it is Stage 20's to make. Keeping those two claims
distinct is the whole substance of this ADR, and the split survives its own validation:
`calculix-precice.sif` is built and digest-recorded here, but nothing about the FSI3 result
transfers to it.
