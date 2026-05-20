# ADR-005 — V&V Harness Against NASA TMR

- **Status:** accepted
- **Date:** 2026-05-19
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 05)
- **Stage:** 05
- **Supersedes:** the airfoil-mesh decision of ADR-003 (the four-block O-grid
  — see "The C-grid rebuild" below). ADR-003 otherwise stands.

## Context and problem statement

Stage 03 reported drag for the NACA 0012 against a loose ±25 % band; Stage 04
made every run provenanced but not *validated*. A research platform whose
numbers are not continuously checked against published reference data produces
unverified results. Stage 05 builds a V&V harness: canonical, public-domain
reference cases, run through the solver adapter, compared with tight tolerances,
with ASME V&V 20 grid-convergence automation, wired into CI as a gate.

This ADR records the decisions that frame that harness.

## Decision drivers

- **Reproducibility / peer-review grade** — reviewers expect a methods section
  with a named reference dataset, tolerance bands, and a GCI study.
- **Canonical, public-domain reference** — no licence encumbrance, no NASA
  endorsement implied.
- **Solver-agnostic** — Stage 06's SU2 adapter must reuse the harness unchanged.
- **PLATFORM-NOT-HUB** — `aero/` core stays stdlib + numpy + pydantic; new
  dependencies live behind extras.
- **Honest tolerances** — a tolerance is a contract; a failing case is
  investigated, never silenced by relaxing the band (Stage-05 guardrail 1).

## Considered options

1. **NASA TMR** — the Turbulence Modeling Resource verification cases (flat
   plate, 2D bump, NACA 0012).
2. **AIAA DPW-7 / HLPW-5** — the Drag / High-Lift Prediction Workshop cases.
3. **ERCOFTAC** — the classic separated-flow database (backward-facing step,
   periodic hill).

## Decision outcome

Chose **NASA TMR** for Stage 05 because it is the canonical, US-Government
public-domain turbulence-model verification set, its cases are 2D and cheap
enough to run on CPU LXCs in CI, and they isolate the solver + adapter + mesh +
provenance stack without the geometric complexity of a full aircraft. DPW-7 /
HLPW-5 are deferred to Stage 12 (3D, GPU-scale, the CRM geometries); ERCOFTAC
separated-flow cases are deferred to Stage 12 alongside the scale-resolving
work — RANS on a periodic hill is a weaker verification than on attached TMR
flows.

### Tolerance bands

| Metric | Case | Tolerance | Rationale |
|---|---|---|---|
| Cd (scalar) | NACA 0012 | 3 % | On the Richardson-extrapolated value; the spread between TMR's own CFL3D / FUN3D solutions is ~1 %, so 3 % bounds solver + mesh + adapter error. |
| Cf (pointwise) | flat plate | 5 % | Pointwise vs. the White correlation; correlation-vs-CFD spread is ~2-3 %, 5 % leaves headroom for the near-LE region. |
| Cp (pointwise) | 2D bump | 3 % | Normalised by the peak \|Cp\| (Cp changes sign), so 3 % is 3 % of the suction-peak magnitude. |

Tolerances are a **contract**: a failing case is investigated (mesh, BCs,
turbulence parameters) and the discrepancy documented — never relaxed to pass.

### Mesh-sweep refinement ratios

`MeshSweep` defaults to refinement ratios **(1.0, 1.3, 1.7)** — three grids,
fine to coarse. ASME V&V 20 requires a refinement ratio r > ~1.1 between grids
for the observed order of accuracy to be resolvable; 1.3 and 1.7 give
r21 ≈ r32 ≈ 1.3, comfortably above that floor while keeping the coarse grid
large enough to stay well-formed. The observed order is solved from the
transcendental equation (Celik et al., 2008), GCI_fine uses the
factor-of-safety 1.25 standard for a three-grid study.

### The "red dashboard = no production" rule

A V&V case outside tolerance means the solver stack is not trustworthy. The
rule, also recorded in CLAUDE.md: **before any `production`-tagged run, verify
`aero vv report --latest` shows all green.** CI enforces continuously — a red
`vv-required` check blocks the PR that broke physics.

### The C-grid rebuild (supersedes ADR-003's O-grid)

ADR-003 chose a four-block O-grid for the NACA 0012 walking skeleton, with the
far field at 20 chords. That mesh was walking-skeleton-grade: a badly skewed
sharp trailing edge (max skewness ~17) capped the pressure residual at ~1.5e-3.
Stage 05 replaces it with an **eight-block multi-block C-grid**: a rectangular
far field at 100 chords and an explicit wake cut downstream of the trailing
edge. The wake cut gives the sharp TE a discrete continuation instead of
forcing the grid to wrap a singular point — `checkMesh` max skewness fell from
~17 to ~2.8 and the solve now converges to a 1e-6 residual. The front and wake
blocks use `edgeGrading` so the boundary-layer clustering applies only on the
airfoil-side eta edge (a uniform `simpleGrading` there put a ~1e-6 cell 100
chords from any wall and gave a 2e7 cell aspect ratio).

### Wall treatment — low-Re, not log-law

The C-grid is wall-resolved (first cell y+ < 1). The Stage-03 fields used
`nutkWallFunction`, a high-Re log-law wall function; on a y+ < 1 mesh that
mis-modelled the near-wall eddy viscosity and biased Cd by ~+20 %. Stage 05
switches the `nut` wall BC to `nutLowReWallFunction` (the resolved-wall
treatment); `omegaWallFunction` is already valid across all y+.

### `aero[vv]` extra

The pointwise comparison spline-interpolates the measured distribution onto the
reference x-grid — `scipy`. A new `aero[vv]` extra (`scipy>=1.14`) carries it,
imported lazily inside `aero.vv` so `import aero.vv` stays core-clean
(PLATFORM-NOT-HUB). Not folded into `aero[openfoam]`: a future SU2-only V&V run
needs scipy but not pyfoam.

### TMR geometry specs — a discriminated union, not an extended `CaseSpec`

The flat plate and 2D bump are not airfoils. Rather than bloat the airfoil
`CaseSpec` with optional-and-ignored fields (which would violate FAIL-LOUD —
every field must be load-bearing), the TMR geometries get their own
strict-frozen models joined by a `geometry` discriminator (`TMRCaseSpec`).

### Consequences

- **Positive:** every solver and code change is now auto-tested against
  reference physics; the C-grid is genuinely V&V-grade; the GCI primitive is
  reused by every publish-quality run from here on.
- **Negative:** the V&V suite is cluster-bound and slow (~min per case); the
  `vv-required` check depends on the self-hosted runner being online.
- **Neutral / followup:** see the Stage-05 handoff for open items — chiefly the
  2D bump's TMR Cp/Cf reference files (the build host had no outbound network),
  and confirming the grid-converged NACA 0012 Cd lands within 3 %.

## Pros and cons of considered options

### Option A — NASA TMR

- Good: canonical, public-domain, 2D/cheap, isolates the solver stack, has
  published per-code verification data.
- Bad: simple geometries — does not exercise 3D meshing or separation.

### Option B — AIAA DPW-7 / HLPW-5

- Good: the community-standard drag/high-lift benchmark; 3D, realistic.
- Bad: 3D, GPU-scale, far too expensive for a CI gate; geometry complexity
  obscures whether a failure is solver, mesh, or adapter. Deferred to Stage 12.

### Option C — ERCOFTAC

- Good: classic separated-flow validation.
- Bad: separated flow is a weak RANS verification; better paired with the
  scale-resolving work. Deferred to Stage 12.

## Reference-data note (deviation)

The plan called for the TMR reference data to be DVC-tracked. The Stage-05
build host had no outbound network, so the data could not be fetched from
`turbmodels.larc.nasa.gov`. The reference data that *is* shippable — the White
flat-plate Cf correlation and the NACA 0012 grid-converged Cd — is small,
reproducible, and committed **in-tree** under `data/references/tmr/` rather
than DVC-tracked: this keeps the V&V CI job hermetic (no `dvc pull`) and
versions the reference exactly with the test. The 2D bump's TMR Cp/Cf files
remain an open item (its GCI mesh sweep needs no reference data and is
unaffected).

## Links

- Stage prompt: `STAGE-05-vv-harness-tmr.md`
- Related ADR: ADR-003 (OpenFOAM walking skeleton; O-grid superseded here),
  ADR-004 (four-fold provenance contract)
- Related handoff: `docs/handoffs/STAGE-05-vv-harness-tmr-DONE-2026-05-19.md`
- External: NASA Turbulence Modeling Resource —
  <https://turbmodels.larc.nasa.gov/>; I. B. Celik et al., "Procedure for
  Estimation and Reporting of Uncertainty Due to Discretization in CFD
  Applications", *J. Fluids Eng.* 130(7), 2008; F. M. White, *Viscous Fluid
  Flow*, 3rd ed., McGraw-Hill, 2006.
