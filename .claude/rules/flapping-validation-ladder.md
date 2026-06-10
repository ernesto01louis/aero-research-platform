# Rule — Flapping validation ladder (validate against experiment, not CFD-vs-CFD)

## Scope

Loaded lazily when work touches `aero/vv/`, reference data under `data/reference/`, or a
new physics-capability stage. Operational form of Hard Rule 15 (VALIDATE-AGAINST-EXPERIMENT)
and the validation ladder in `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` §4.

## The contract

Every new forward-physics capability ships with **at least one experiment- or DNS-anchored
validation case before it is trusted** in the optimization loop. Validate against
*measured/DNS reference data*, never against another CFD run or a workshop-consensus band
alone. A tolerance is a contract — a failing case is investigated, never relaxed to pass.

## The ladder (acquire reference data DVC-tracked under `data/reference/<case>/`)

| Tier | Case | Reference | Owning stage |
|---|---|---|---|
| Solver credibility (table-stakes) | NASA TMR flat plate, 2D bump, NACA 0012 | NASA TMR | Stage 10 (go/no-go) |
| Forward-regime credibility | Laminar flat plate (Blasius); low-Re cylinder Strouhal; transitional airfoil | Blasius; canonical cylinder St–Re; transition data | Stage 10 |
| Unsteady machinery | Pitching / plunging airfoil | McCroskey dynamic stall (NASA TM-84245); Heathcote-Gursul (2007) | Stage 13 |
| **Flapping (flagship)** | Revolving / flapping wing, rigid then flexible | Dickinson et al. (1999) Robofly; Wang-Birch-Dickinson (2004) | Stage 14 (rigid), 19 (flexible) |
| FSI machinery | Turek-Hron FSI3 | Turek & Hron (2006), via the supported preCICE tutorial (ADR-016) | Stage 18 |
| **Optimization delta (the mission)** | CFD-verified improvement on a parametric flapping case | held-out ground-truth CFD; delta > k·U95 | Stage 15 |

## Reference-data discipline

Each `data/reference/<case>/reference.md` records the citation, license, the
acquisition/digitization method, and the provenance of any digitized points (the Stage-08
dataset `reference.md` pattern). Digitized experimental points carry their own digitization
uncertainty into `u95_input`.

## Why

The platform's product is *trustworthy improvements*. An improvement validated only against
the platform's own CFD is circular. Anchoring each capability to experiment/DNS is what lets
a reported optimization delta clear the thesis-grade bar (`docs/vv/output-validity-bar.md`).
