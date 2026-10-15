# ADR-051 — Foundation first: the post-v0.1.0 sequence puts an honest V&V base before any new optimization

- **Status:** proposed (2026-10-15). It is accepted by the operator's word on its PR, and that
  acceptance is recorded by the commit that lands this change, the ADR-046 pattern. Until then the
  plan of record is ADR-046's: rigid-flapping optimization is the first post-v0.1.0 stage.
- **Date:** 2026-10-15
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 21 close-out)
- **Stage:** 22 onward. This ADR defines Stages 22–26.
- **Amends on acceptance:** ADR-046's scheduling sentence ("the rigid-flapping optimization is
  therefore scheduled as the first post-v0.1.0 stage"); `README-handoff.md` rows 22+;
  `00-MISSION-AND-SCOPE.md`'s post-v0.1.0 line; the Stage-21 handoff's `next_stage_name`; the
  Stage-22 prompt. It moves **no** pre-registered band, tolerance, gate or budget clause, and it
  changes no CONSTITUTION text.

## Context and problem statement

v0.1.0 shipped on 2026-10-15 (tag → `9d02892`; Zenodo DOI 10.5281/zenodo.23396402). The release
was honest about its limitation: the optimizer has never been run on a flapping-wing case. ADR-046
scheduled rigid-flapping optimization as the next stage.

**The operator's direction (2026-10-15):** "build the base of this project first without rushing or
skipping anything", and only then improve steadily. The measured state of that base, read at the
close of Stage 21, does not support optimizing over it yet.

### 1. The V&V report under-reports, and the registry is mostly unevaluated

`aero vv report --latest` is the production gate (ADR-005: "before any `production`-tagged run,
verify `aero vv report --latest` shows all green"). On 2026-10-15 it printed 5 pass, 1 fail and
20 missing. That output is wrong in an important way:

- **It reads only the 500 most recent runs** (`aero/cli.py:858`, `search_runs(...,
  max_results=500)`). The V&V experiment holds 2388 runs. `vv-smoke` logs four smoke cases on every
  push, so `flat_plate_te` (435 runs), `blasius_flat_plate` (385), `laminar_airfoil_naca0012`
  (300) and `cylinder_strouhal_re100` (285) fill the window. Every older V&V run falls out of it and
  is reported `missing`.
- **The true latest status of the 25 registered cases**, read by paging the whole experiment
  (read-only, 2026-10-15):

  | Status | Cases |
  |---|---|
  | pass (7) | `blasius_flat_plate`, `cylinder_strouhal_re100`, `laminar_airfoil_naca0012`, `oscillating_cylinder_lockin`; and, hidden by the window, `t3a_flat_plate_transition` (2026-07-06), `turek_hron_cfd2` and `turek_hron_cfd3` (2026-07-26) |
  | fail (4) | `flat_plate_te`; and, hidden by the window, `naca0012_verification` (2026-06-10), `plunging_airfoil_hg2007_st03` and `plunging_airfoil_hg2007_st03_lm` (2026-07-06) |
  | no run at all (14) | `bump_2d`; `flapping_wing_wbd2004`, `_advanced`, `_delayed`; `hg2007_rigid_foil`; `plunging_airfoil_hg2007`, `_st02`, `_st02_lm`; `turek_hron_fsi3`; `hg2007_flexible_foil`; `naca0012_transonic`, `onera_m6` (SU2, frozen-optional); `taylor_green_p3_32`, `periodic_hill_2d` (PyFR GPU, frozen-optional) |

  Several "no run" cases did run in their own stages, as campaign records under `data/vv/` (for
  example Stage 19's FSI3 GO, and Stage 14's flapping runs). They never ran through the registry
  path that the production gate reads.

The verdict (RED) was right. The information behind it was not: three failures were displayed as
"missing", and three passes were invisible.

One CI job has the same defect. The nightly `vv-transonic` workflow is green on every run, but its
run of 2026-10-15 measured nothing:
- `test_onera_m6_cp_at_eta_044` was SKIPPED, because "onera_m6: solver failed (rc=1)". Its `dvc
  pull` step printed "dvc pull skipped", so the DVC-tracked mesh was never fetched.
- `test_transonic_naca0012_cd_within_tolerance` was XFAIL.

A green job that skips on a solver failure is the pattern H-19 removed from `vv-scale-resolving`.

### 2. The turbulent canonical cases have never passed

- **TMR flat plate:** Cf is 12.6 % off the CFL3D SST data against a 5 % tolerance, since Stage 5
  (`docs/handoffs/STAGE-05-…` §0). Stage 10 deferred it to Stage 12 ("correlation-spread"), and no
  stage picked it up.
- **NACA 0012 verification:** a documented NO-GO since Stage 10 (ADR-017: the blunt-TE remedy is
  not steady-convergeable).
- **2D bump:** a documented CONCERN since Stage 10 (a pressure-residual plateau near 3e-4).

The mission's publication bar (`00-MISSION-AND-SCOPE.md` §5) requires these cases to pass. No
tolerance was ever relaxed, and none may be.

### 3. The forward models the optimizer would use are not validated against experiment

- **Rigid flapping (Stage 14):** the gated symmetrical mean lift misses Wang–Birch–Dickinson (2004)
  by 45.7 % against a ±25 % band. The advanced and delayed timings miss by 38 % and 64 %. Overset
  wake-capture dissipation is the leading hypothesis. It is untested: the body-fitted (morph)
  alternative fails at the ±1.4c stroke amplitude, so the two meshes cannot be compared directly
  there (Stage-14 handoff §6).
- **Airfoil (Stages 15–17):** the forward model has no experiment anchor.

An optimizer run over a forward model with a 45.7 % systematic miss can claim a delta at most, and
only with a bias bound. That is what ADR-046 and the drafted rigid-flapping prompt planned for.
Building the base first means reducing or explaining that miss before relying on it.

### 4. Provenance has two documented weaknesses

`dvc_input_hash` is a repository-wide DVC sync-state digest, not a content address of the inputs a
case touches (O-07). That is not what CONSTITUTION Invariant 3 defines. `container_sif_sha256` is a
basename lookup, never a re-hash at launch (O-08; ADR-049 H-33). Every crate states both. Any new
validation evidence should be recorded under correct provenance.

### 5. Hygiene that is known and open

- pip-audit reports 161 advisories across 20 locked packages (2026-10-12).
- H-34 and H-35 (ADR-049 P2) are open.
- `regenerate_status.sh` has no unit test.
- The weekly `moving-vv` job times out at its ceiling.
- The Stage-17 surrogate certificate expires 2027-01-20.

## Decision drivers

- **The operator's direction:** the base first, nothing skipped, then steady improvement.
- **CONSTITUTION and Hard Rules 14/15:** never optimize over an unvalidated forward model (the
  reasoning ADR-046 applied to flexible FSI applies here in degree).
- **FAIL-LOUD and DOCS-MATCH-REALITY:** the production gate must show the truth, not a window of it.
- **Session-sized stages:** each stage has one theme, a pre-registered exit, and its own handoff.
- **A tolerance is a contract.** "Not yet" is an acceptable stage outcome; a relaxed band is not.

## Considered options

1. **Status quo: Stage 22 is rigid-flapping optimization (ADR-046).** It optimizes over a forward
   model with a 45.7 % mean-lift miss and an unevaluated registry. Rejected by the operator's
   direction.
2. **Foundation first, as a sequence of small themed stages, then rigid-flapping optimization.**
   Chosen.
3. **One large foundation stage.** Too big for one session-sized stage; progress would be invisible
   until the end, which is the Stage-20 pattern. Rejected.
4. **Re-scope the mission away from flapping.** Not this ADR's question; the mission is unchanged.

## Decision outcome

**Option 2.** Stages 22–26 build the foundation, in this order. Each stage pre-registers its gates
before any solve, ends with a handoff, and never relaxes a tolerance.

| Stage | Theme | Exit (pre-registered in detail at stage open) |
|---|---|---|
| 22 | **An honest V&V report** | The report reads each registered case's true latest run (no window); every case has a typed status; the frozen-solver and deferred cases are decided (D2); no V&V workflow reports green when it measured nothing; the handoff records the per-case table, cross-checked against a full read of MLflow. No campaign compute. |
| 23 | **Provenance you can trust** | `dvc_input_hash` content-addresses the inputs a case touches (O-07); the SIF is re-hashed at launch (O-08); each change has its own ADR. ADR-050's hosted CPU-only reproducible number is the end-to-end proof. The lock refresh for the pip-audit advisories rides here (one FULL run). |
| 24 | **Run the registry** | Every active-stack registered case runs through the registry path under Stage 23's provenance: the 9 with no run, the 4 failing, and the 7 passing, re-confirmed. Each result is triaged: pass, or fail with a written first diagnosis. A compute plan is approved before any run (D3). |
| 25 | **The turbulent canonical cases** | The TMR flat plate, NACA 0012 verification and the 2D bump each pass, or carry a *demonstrated* root cause (not a hypothesis) that the operator accepts. Never a relaxed tolerance. |
| 26 | **Forward-model validation for the optimization targets** | Flapping: a pre-registered test of the overset wake-capture hypothesis, for example a wake-resolution study, or overset vs body-fitted at an amplitude where morph works. Airfoil: an experiment anchor at the optimization conditions, or a recorded reason why none exists. |

**Rigid-flapping optimization follows** as the first stage after Stage 26, once Stages 22–26 have
met their exits. Its claim bound is set from Stage 26's result, not from Stage 14's. The prompt
drafted at Stage 21 is kept as its starting point
(`docs/handoff-bundle/LATER-rigid-flapping-optimization.md`), with external-review item C (the
per-evaluation retry) still among its pre-registration items.

### D1 — The order is part of the decision

Measurement comes first. Stage 22 makes the report true; Stage 23 makes provenance true. Then the
measuring runs: Stage 24 runs everything and Stage 25 fixes the oldest failures. Validation comes
last: Stage 26 validates the models the optimizer would rely on.

Running the registry (24) before the provenance fix (23) would record a whole campaign under the
weak semantics. The operator may reorder 23 and 24 at Stage 22's close if the provenance work blocks.

### D2 — Cases that cannot run on the active stack (operator decision at Stage 22 open)

Five registered cases cannot run on the stack the platform actively uses:
- the two SU2 transonic cases and the two PyFR GPU cases, whose solvers are frozen-optional by
  ADR-013;
- `hg2007_flexible_foil`, deferred by ADR-046 S4.

Options:
- **(a) Run them anyway.**
  - The SU2 pair runs on CPU in principle. Today the ONERA M6 solve fails, because its mesh is not
    pulled, and the transonic NACA 0012 test is xfail (§1).
  - The PyFR pair needs a GPU runner that does not exist, or RunPod spend.
- **(b) Scope the verdict per solver stack (recommended).** ADR-005's rule is "a V&V case outside
  tolerance means *the solver stack* is not trustworthy". A production run on the OpenFOAM stack
  would then need every OpenFOAM-stack case green, and a PyFR production run every PyFR case.
  Frozen or deferred cases stay registered and visible with a typed status (`frozen`, `deferred`),
  never `pass`. They no longer gate a stack they do not measure.
- **(c) Remove them from the registry.** Rejected: it hides them, the failure mode the
  registry-driven report was built to prevent (Stage 19).

### D3 — Compute

Stages 22 and 23 need no campaign compute beyond verification-scale runs. Stages 24–26 need cluster
CPU time, all on the platform's own LXCs with no cloud spend. One case alone is long: Stage 19's FSI3
took 20.3 h. Each of those stages opens with a compute plan (cases, wall-time estimates from the
recorded runs, the `run_long.sh` reap and timeout plan), and the operator approves it before any
run. Any cloud spend needs its own ADR (Invariant 8).

### D4 — Stage tags after v0.1.0 (operator decision at Stage 22 open)

ADR-049 R3 defines the version policy only up to v0.1.0. Recommended: each foundation stage closes
with a patch version, `v0.1.N` (Stage 22 → `v0.1.1`). It goes through the same release PR, tag gate
and readiness check as v0.1.0. A GitHub Release, which mints a Zenodo DOI, is published only when the
operator chooses. The alternative is untagged stages and one `v0.2.0` at the end of the foundation.

### Not in the foundation

- **JOSS** is deferred until the platform has evidence of research use (operator decision
  2026-10-15; `docs/release/joss.md`).
- **The Stage-17 certificate's re-certification (2027-01-20)** needs compute and is a separate
  operator decision. Its expiry is already a stated crate limitation.
- **Flexible flapping** stays deferred under ADR-046 S4/S5.

## Consequences

- **Positive:**
  - The production gate shows the truth.
  - Every later result rests on correct provenance and a validated forward model.
  - The flapping claim bound is measured, not inherited from a 45.7 % miss.
- **Negative:**
  - A flapping optimization result moves back by about five stages.
  - The mission's publication bar stays unmet for longer.
  - Stages 24–26 cost cluster time.
  - A foundation stage may end NO-GO, and "not yet" is then the honest outcome.
- **Follow-up:** the Stage-22 prompt (`docs/handoff-bundle/STAGE-22-foundation-honest-vv-report.md`)
  is written with this ADR. The prompts for Stages 23–26 are each written at the close of the stage
  before.

## Links

- ADR-005 (V&V harness; the production gate), ADR-013 (frozen-optional solvers), ADR-017 (NACA 0012
  NO-GO), ADR-046 (release-first; the rigid-flapping scheduling this amends), ADR-049 (O-07, O-08,
  H-33, R3), ADR-050 (the hosted reproducibility case).
- `docs/handoffs/STAGE-05-vv-harness-tmr-DONE-2026-05-19.md` §0;
  `docs/handoffs/STAGE-10-vv-debt-and-validity-bar-DONE-2026-06-15.md` §1;
  `docs/handoffs/STAGE-14-rigid-flapping-wing-DONE-2026-07-10.md` §6;
  `docs/handoffs/STAGE-21-release-portable-bundles-DONE-2026-10-12.md` §7.
- `docs/operator/deferred-work-ledger.md`.
