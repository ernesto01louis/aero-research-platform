# ADR-037 — Authored coupled cases: the physical spec rides on the source

- **Status:** accepted
- **Date:** 2026-08-06
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 20)
- **Stage:** 20
- **Supersedes:** none

## Context and problem statement

Stage 19 ran the *supported upstream* Turek-Hron FSI3 tutorial. Its integrity contract is
"these bytes ARE the pinned bytes": every file is verified against a git-tracked per-file
digest manifest, and exactly two declared mutations may deviate from it (ADR-036 C2/C3).

The Heathcote-Gursul flexible foil has **no upstream equivalent**. Its bytes are *authored*
by this platform — a rendered `precice-config.xml`, a dimensional OpenFOAM case, a CalculiX
deck — so there is no pin to compare against and the contract has to invert to "these bytes
are exactly what this spec renders, and re-reading them reproduces the spec".

That inversion raises one question with a provenance consequence, and it is the decision this
ADR records. `config_hash` is computed over the **serialized `CoupledCaseSpec`**
(`compute_provenance(resolved_config=json.loads(spec.model_dump_json()))`). Anything the
materializer *builds* rather than *reads off the spec* is therefore invisible to it. The two
arms of Stage 20's gated increment differ in **exactly one number** — the plate's
half-thickness — so if the geometry does not ride on the spec, the flexible and rigid arms
**hash identically**, and so do the three GCI rungs.

## Decision drivers

- **PROVENANCE FROM DAY ONE** (Hard Rule 3) and the four-fold contract (ADR-004): a run must
  be reproducible from its tuple. A `config_hash` that does not distinguish the two arms of a
  gated increment does not describe the run.
- **PLATFORM-NOT-HUB** (Invariant 1): `aero/` core is stdlib + numpy + pydantic only.
- **FAIL-LOUD** (Invariant 2): a mis-specified case must fail at construction, not at
  readout, and not silently.
- `_materialize`'s own docstring warns that whatever `case.py` imports at module level is
  pulled into every `launcher.py` consumer.
- ADR-038's roster closes the *container* half of the same question; this is the *config*
  half.

## Considered options

1. **The physical spec rides ON `AuthoredSource`** — `fluid: FlexibleFoilSpec` and
   `solid: CalculiXSolidSpec` as fields, so `config_hash` covers them.
2. **Derive at materialization** — keep `AuthoredSource` thin (chord, thickness, Re, St) and
   build the two writer specs inside `_materialize`.
3. **Carry canonical JSON plus a digest** — `physics_json: str` + `physics_sha256: str` on
   the source, parsed inside the materializer.

## Decision outcome

Chose **Option 1** because it is the only one under which `config_hash` distinguishes two
runs that differ in their geometry, and because putting both specs on one object is what made
a whole class of cross-check *expressible* for the first time.

### Consequences

- **Positive.** The two arms hash differently, as do the three rungs. Every rung knob, the
  wall spacing, the materials, `ddt_scheme` and the RBF support radius enter the tuple — none
  of them recoverable from a bundle otherwise. The manifest's `spec_sha256` is computed by
  **calling `config_hash`**, so the on-disk record and the MLflow tag provably describe one
  spec rather than being believed to.
- **Positive, and the reason the cost is worth paying.** `assert_calculix_deck` compares a
  deck against the spec it was written from — self-consistent by construction — and nothing
  anywhere compared the solid's geometry against the fluid's. A pair carrying the flexible
  plate on the fluid and the rigid plate on the solid validated, wrote, meshed, coupled,
  converged and would have reported a thrust coefficient somewhere between the two arms.
  `assert_authored_consistent` closes that plus seven more agreements. Two further silent
  failures became checkable at the same time and for the same reason (below).
- **Negative.** `case.py` now imports `aero.adapters.openfoam.flexible_foil` and
  `aero.adapters.precice.calculix` at module level, and `launcher.py` consumers inherit them:
  roughly 250 → 457 modules. **This is module weight, not correctness.** Verified rather than
  assumed: the import chain was traced step by step, there is no cycle (the `precice` package
  is already in `sys.modules` when `calculix` is reached), `aero/adapters/openfoam/solver.py`
  has no module-level `xarray`/`meshio`/`scipy`, and the `import-platform-only` job names all
  six new modules explicitly so a future heavy import is a named failure rather than a
  mystery.
- **Negative, recorded as a fragility.** Neither writer may ever do a *package-level*
  `from aero.adapters.precice import X`: `case.py` runs while `precice/__init__` is half
  initialised, so that would raise. A comment marks it and a fresh-interpreter test pins it.
- **Neutral.** `AuthoredSource.coupling_values()` is a **method**, not a field: all six
  rendered token values are functions of `fluid`/`solid`/layout, so carrying them would add a
  thing that can disagree with its own inputs for no gain — the inputs are already hashed.

## The integrity contract, and where each half is enforced

| | tutorial (Stage 19) | authored (Stage 20) |
|---|---|---|
| claim | these bytes ARE the pinned bytes | these bytes are what this spec renders |
| verified by | per-file digest manifest | every writer ships a **re-reader** |
| deviations | two, declared | three declared authorship acts |
| manifest | schema v1 | schema v2, with `spec_sha256` |

`_materialize`, `_render_manifest` and `load` each dispatch on `source.kind` with
`assert_never`, so a third source type in a future stage is a **type error** rather than a
silent fall-through into the wrong contract. That is the same reasoning that put ONE `source`
field on `MaterializedTree` instead of a nullable `pin` XOR `authored` pair: `model_copy(update=…)`
bypasses `mode="after"` validators, and `case.py` uses that idiom twice, so the XOR would have
been forgeable and a forged tree would emit a tutorial manifest naming an upstream pin for a
case this platform wrote.

`assert_authored_consistent` runs **both** as an after-validator and as the first statement of
the materializer, for the same reason: a validator alone is a convention, and the materializer
is the one door every byte goes through.

## Three silent failures this made checkable

None was reachable before both specs were on one object.

1. **Fluid-vs-solid geometry.** Eight numbers plus the whole station list, compared with `==`
   rather than `isclose` (both sides are the same floats from the same fields, so a tolerance
   could only hide a substitution). `surface_x` must BE `hg2007_coordinates(2*n_surface+1)[1:, 0]`
   bitwise, which is what makes "the solid's wetted curve IS the fluid's" an identity.
2. **An odd `n_through_thickness`.** `_grid` lays nodes at `eta = linspace(-1, 1, n+1)`, which
   contains `0.0` only for even `n`. At an odd count there is no mid-surface node and **preCICE
   snaps a watch-point to the nearest vertex with no diagnostic**, so D0 becomes the angle of a
   surface fibre — offset by the plate half-thickness times the local rotation, and entirely
   plausible.
3. **Mixed participant uids and a wrong exchange directory.** Both hang the run to its
   wall-clock ceiling with every participant still alive, which is an ending **gate K2 admits**
   as a budget outcome. Cost: one full 14-day wave before anything complains.

## Two honest divergences, recorded rather than smoothed over

**FSI3's `config_hash` moved, `c524faff…` → `3f94f394…`.** The Stage-19 *materialized bytes*
are proved identical by `test_stage19_materialization_is_byte_identical.py`, whose fixtures
and assertions have not moved since `67d8e82`. What moved is the *spec serialization*: five
fields went behind `source`. **Those are different claims and the ADR says so rather than
letting "byte-identical" cover both.**

A second caveat, found while deciding where ADR-039's binding tests go: `TutorialPin.manifest_path`
and `TutorialSource.archive_path` are `Path` fields and serialize as **absolute** strings, so
`3f94f394…` is a property of *this checkout path*, not a portable fact. It is recorded as a
regression pin, not as a reproducibility anchor. **`AuthoredSource` is path-free**, and a test
pins that it stays so.

**The driver's K1 became window-scoped.** `_assert_coupling_converged_over` applies the
convergence gate to the analysis window rather than the whole run, because upstream documents
that the first windows legitimately need many iterations. Provably a **no-op on the tagged
Stage-19 record**: `data/vv/stage19_turek_hron_fsi3.json` reports `n_nonconverged: 0` over
8000/8000 windows for both participants, so whole-run and window-scoped agree there. That
evidence is what makes the change safe rather than merely plausible.

## Pros and cons of considered options

### Option 1 — the spec rides on the source

- Good: `config_hash` covers the geometry; the cross-checks become expressible; a typo is a
  construction-time `ValidationError` under `extra="forbid"`.
- Bad: module weight in every launcher consumer, and a package-level import in either writer
  would deadlock.

### Option 2 — derive at materialization

- Good: `case.py` stays light.
- Bad: **the derived knobs are not derivable.** `n_surface`/`n_normal`/`n_front`/`n_wake`/`n_te`
  and `first_cell_height` are the *rung*; `ddt_scheme` is an I8 outcome; the two materials and
  `n_through_thickness` are modelling choices; `rbf_support_radius_spacings` is tuning. Every
  one would live in code and be invisible to `config_hash`, so **the three GCI rungs would hash
  identically** — a strictly worse hole than the one being closed. Widening the "handful" until
  it covers them yields Option 1 with an extra indirection plus a new silent bug class
  ("I forgot to forward a field"). It also puts physical inputs on a solver *method* rather
  than on the *case*, so the bundle and `aero vv list` never see them.

### Option 3 — canonical JSON plus a digest

- Good: no import weight.
- Bad: defeats `extra="forbid"` — the string is validated only when parsed, i.e. inside
  `_materialize`, i.e. after `prepare()` has begun, so a typo'd key becomes a runtime failure
  instead of a construction failure. `physics_sha256` duplicates what `config_hash` already
  covers byte-for-byte, creating a pair that can disagree and a validator to check that it
  does not. And every cross-consistency check above becomes impossible to express as a
  validator and migrates to materialization — the placement Option 2 was rejected for.

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-20-flexible-flapping-wing-fsi.md` (deliverables 1, 2)
- Related ADRs: ADR-004 (four-fold contract), ADR-016 (why CalculiX, and why coupling
  correctness and application fidelity stay separate), ADR-036 (the tutorial-path integrity
  contract this inverts), ADR-038 (the container half of the same question), ADR-039 (the
  Stage-20 pre-registration)
- Code: `aero/adapters/precice/{case,solver,manifest,template,calculix}.py`,
  `aero/adapters/openfoam/flexible_foil.py`, `aero/vv/fsi/{hg2007_flexible_foil,hg2007_readout}.py`
- Tests: `tests/stage_20/{test_authored_materialization,test_source_seam,test_hg2007_case}.py`,
  `tests/stage_20/test_stage19_{load_path_unchanged,materialization_is_byte_identical}.py`
- Handoff: `docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` §6.14, §6.22-§6.25
