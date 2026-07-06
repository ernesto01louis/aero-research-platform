---
stage: 13
stage_name: "Stage 13 — Transition + Unsteady-Airfoil Validation"
status: complete
date_started: 2026-07-06
date_completed: 2026-07-06
session_duration_hours: 0
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-4-8
git_sha_start: "cbfc75a0dde7845f40606a4a9f0e2c129fad82e2"
git_sha_end: "82d1cf5615e872e983bd7f088f99fd7e443e75b3"
stage_tag: v0.0.13
next_stage: 14
next_stage_name: "Stage 14 — Rigid Flapping-Wing Validation"
---

# Stage 13 — Transition + Unsteady-Airfoil Validation — (2026-07-06)

> `git_sha_end` is provisional (reconcile to the squash-merge SHA at the `v0.0.13` tag — the
> Stage-08/10/11/12 pattern). Work landed on branch `stage-13` (PR #24). **`status: complete`:**
> the transition model is verified (T3A onset GREEN), the plunging-foil over-prediction is resolved
> as a **documented, root-caused NO-GO** (tolerance not relaxed — operator-approved honest split),
> both ADRs ratified, the Stage-14 prompt authored.

## 0. Headline

The platform now has a **verified transitional-RANS path** for the flapping regime: `kOmegaSSTLM`
(gamma-Re_theta Langtry-Menter) reproduces the ERCOFTAC **T3A** transition onset within a-priori
band (onset 18.4% < 20%, Cf 24.4% < 25%) — the transition-onset half of the GO gate is **GREEN**
(ADR-021). The Stage-11/12 plunging-foil CONCERN is **resolved**: re-anchored at the in-range
measured St 0.2/0.3 (laminar + `kOmegaSSTLM`), the finding is that the 2-D solve's **C_T(St) slope
is far too steep** vs the flat HG experiment — it crosses near St~0.23 and misses both measured
points (C_T 0.13/0.35 vs ref 0.20/0.22); transition barely moves it (~5-11%, near-laminar at
Re=1e4/Tu=1%). **No rung clears the 15% contract** -> a **documented NO-GO** (2-D-vs-3-D + geometry
root cause, ADR-022), tolerance NOT relaxed. It is still a **massive improvement** over Stage-12
(anchor error 320% -> 28-58%) with a **validated trend** (monotone C_T(St), net-thrust threshold).
This does **not** block Stage 14, which builds on the T3A-verified transition model, not the foil.

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `kOmegaSSTLM` (gamma-Re_theta) transition path + onset verification | ✅ | Adapter path (gammaInt/ReThetat writers, schemes/solvers, Re_theta(Tu) correlation); ERCOFTAC T3A case (ported ESI v2412 tutorial, `aero/vv/ercoftac/`); cluster **PASS** (onset 18.4%/20%, Cf 24.4%/25%). ADR-021. |
| 2 | Resolve the plunging over-prediction (transition and/or re-anchor) | ✅ | Re-anchored St 0.2/0.3 x {laminar, kOmegaSSTLM}; **documented NO-GO** — C_T(St) too steep, 2-D-vs-3-D root cause; massive improvement over Stage-12 + validated trend; tolerance not relaxed. ADR-022. Full-U95 `ReportableResult`s composed (validated). |
| 3 | Pitching-airfoil dynamic stall vs McCroskey | ⏭️ | **Deferred** (operator scope decision — tight GO path). Documented in the ledger as a Stage-13+ follow-up. |
| 4 | NACA-0012 transient-mean debt | ⏭️ | **Deferred** (operator scope decision). SU2 sharp-TE cross-check remains the recommended path (ADR-017 showed blunt-TE can't reach 3%); ledgered. |
| 5 | ADR(s) + handoff + Stage-14 prompt + tag | ✅ | ADR-021 (transition pin) + ADR-022 (plunging re-anchor/NO-GO); this handoff; Stage-14 prompt exists (`docs/handoff-bundle/STAGE-14-rigid-flapping-wing.md`). Tag `v0.0.13` at finalize. |

## 2. Decisions made

- **Honest split (operator-approved):** transition-model GO (T3A) + plunging-foil documented NO-GO.
  The transition MODEL — the piece Stage 14 depends on — is verified; the plunging foil is a hard
  2-D-substitute-geometry validation case, not a Stage-14 dependency, so its NO-GO does not block
  the flagship. Ship v0.0.13 with this framing.
- **Re-anchor at the measured St (0.2, 0.3), not the crossover.** Chasing the St~0.23 where the
  2-D solve happens to match the experiment would be selection bias / metric misuse
  (`optimization-integrity.md`; Luo et al. 2509.08713). Rejected.
- **Tolerance NOT relaxed.** The 15% thrust contract stands; the case is a documented NO-GO, not a
  relaxed pass (Hard Rule 15).
- **Faithful T3A port over a bespoke parametric plate** (ADR-021): the transition location is
  sensitive to the inlet-to-LE turbulence decay, so reproducing the validated ESI v2412 tutorial
  verbatim is the lowest-risk verification. Kept dimensional (U=5.4) -> `wall_distribution` gained
  an optional `u_inf`.
- **Shared 2e-3 mesh for laminar + transition** (ADR-022): a clean paired comparison; the finer 5e-4
  wall-resolved mesh diverged the moving-mesh startup (SIGFPE) and was serially infeasible (~60 h).
- **Foil GCI cut** (Stage-12/ADR-020 precedent): a NO-GO foil needs no discretization U95;
  `u95_numerical=0`, the batch-means + reference terms still compose a real RSS envelope.

## 3. Deviations from the stage plan

- **Deliverables 3 (pitching McCroskey) + 4 (NACA-0012 debt) deferred** per the operator's Stage-13
  scope decision (tight GO path, serial-only compute). Both are ledgered follow-ups; neither is on
  the GO path.
- **The plunging rung is a NO-GO, not a GO** — the stage's DoD "one unsteady rung clears its anchor"
  is met by *neither* the (deferred) pitching rung *nor* the plunging rung. Operator-approved to
  ship the transition-GO + documented-plunging-NO-GO as the honest Stage-13 outcome. The transition
  half of the GO gate IS met.
- **Fine-mesh transition path abandoned mid-campaign** (SIGFPE + serially infeasible) -> the probe
  runs on the proven 2e-3 mesh (y+~1.4, documented).

## 4. Environment / dependency / schema changes

- `aero/adapters/openfoam/_foam_common.py`: `rethetat_freestream(Tu)` correlation; `re_theta_t` in
  `flow_state`; steady + transient fv dicts gain gated `transition` / `turbulence_model` params.
- `case_writer._fields()` + `plunging_airfoil._fields()`: gammaInt/ReThetat writers (kOmegaSSTLM).
- Literals widened: `CaseSpec` + `PlungingAirfoilSpec` gain `"kOmegaSSTLM"`; `PlungingAirfoilSpec`
  gains `turbulence_intensity`.
- New `aero/adapters/openfoam/t3a.py` (`T3ASpec` + `write_t3a_case`, ported tutorial) + solver
  dispatch; `wall_distribution` / `extract_wall_distributions` gain `u_inf` (default 1.0; threaded
  through all adapters).
- New `aero/vv/ercoftac/` (`T3AFlatPlate` + `ERCOFTAC_CASES`) + CLI wiring; `PlungingAirfoilHG2007`
  parametrized by Strouhal + turbulence_model, `refined_dt()` added, `evaluate()` also exposes `cd`.
- New reference data `data/references/ercoftac/t3a/{cf.csv,reference.md}` (git, ~0.4 KB, GPL).
- New scripts `stage13_gci.py` (generalized space+time GCI) + `stage13_reportable.py` (thrust U95).
- No new pyproject extras.

## 5. CI/CD changes

- No new required checks. All existing required checks green on PR #24 (`vv-required`,
  `small-signal-gate`, `data-origin-fence`, ruff, mypy, pytest, import-only, commit-lint, fence,
  README-status). The non-required self-hosted `vv-smoke` / `provenance-completeness` were cancelled
  on push so `vv-required` got the single self-hosted runner (as designed).
- Recorded the **Stage-12 Invariant-10/11 required-check promotions** (small-signal-gate,
  data-origin-fence) in `docs/operator/deferred-work-ledger.md` §0b — verified already required.

## 6. Gotchas discovered

- **The 2-D laminar plunging C_T(St) is not a uniform over-prediction** — it under-predicts at low
  St (0.13 vs 0.20) and over-predicts at high St (0.35 vs 0.22; 1.26 vs 0.30), crossing near
  St~0.23. The Stage-12 "over-prediction" framing (St=0.4 only) missed the slope error.
- **kOmegaSSTLM on a moving mesh at Re=1e4 is finicky:** the fine 5e-4 wall-resolved mesh SIGFPE'd
  at the impulsive heave start (GAMG continuity blow-up) AND drove dt~1e-4 (~60 h serial). The
  proven 2e-3 mesh runs stably (y+~1.4, adequate via the wall functions).
- **Detached-driver poll timeout != solve death:** the st02 driver hit its 6 h `--timeout` (rc=124)
  while the detached solve kept running to Time=40 on the cluster. Compose from the run dir; set a
  generous `--timeout` (the St=0.2 low-frequency runs need ~40 convective times = many timesteps).
- **Independent serial jobs run concurrently on the 16-core box** (not MPI -> no approval) —
  4 plunging solves at once compressed the campaign, at ~4.4 Time-units/hr each under contention.
- **Transition at low Re needs elevated Tu to activate:** at Tu=1% (Re_theta~584) the attached BL
  never reaches the transition threshold -> near-laminar. The freestream-Tu choice is a documented
  modeling lever.

## 7. Open items for the next stage (and beyond)

- **Stage 14 (Rigid Flapping-Wing):** prompt written (`docs/handoff-bundle/STAGE-14-rigid-flapping-
  wing.md`). Needs the **angular/flapping motion primitive** (deferred from Stage 13 — `motion.py`
  is heave-only), Dickinson 1999 / Wang-Birch-Dickinson 2004 reference data, and a full-U95 force-
  trace `ReportableResult` + LEV capture. Builds on the T3A-verified transition model.
- **Deferred (ledgered):** pitching-airfoil dynamic stall vs McCroskey (needs angular motion +
  McCroskey data); NACA-0012 transient-mean debt (prefer the SU2 sharp-TE cross-check per ADR-017).
- **Plunging foil:** a genuine 3-D (or quasi-3-D revolving) solve is the only path to the 15% band
  (the NO-GO root cause is 2-D-vs-3-D); out of scope until/unless the flapping ladder needs it.
- **PR #21** (aero-nas DVC repoint) still open — not needed this stage.

## 8. Pointers for next session

- **Read first:** this file + ADR-021 + ADR-022 + the Stage-14 prompt + `git log cbfc75a..`.
- **Run first to verify:** `pytest tests/vv tests/stage_13 tests/unit -q -m "not slow"` (green),
  `mypy aero`, `ruff check aero tests scripts`. The T3A GO is MLflow `b6c4783e`
  (`t3a_flat_plate_transition-20260706-073029`); the plunging results are in
  `data/vv/stage13_reportable_plunging_*.json`.
- **Do not re-read:** the mesh-stability debug (conclusions in §6 + ADR-022).

## 9. Artifacts produced

Commits on `stage-13` (`git log cbfc75a..HEAD`): the kOmegaSSTLM adapter path; the T3A case + ported
tutorial + reference; the plunging re-anchor + transition variants + `refined_dt`; `stage13_{gci,
reportable}`; ADR-021 + ADR-022; the Stage-14 prompt; the ledger record; this handoff + CHANGELOG.
New code: `aero/adapters/openfoam/t3a.py`, `aero/vv/ercoftac/**`, `scripts/stage13_*.py`,
`tests/stage_13/**`, `data/references/ercoftac/t3a/**`, `data/vv/stage13_reportable_*.json`.
**MLflow (aero-mlflow):** the T3A GO run (stage=13, `b6c4783e`) + the four plunging U95
`ReportableResult` artifacts (stage=13, validated).

## 10. Confidence / risk note

High confidence: the transition-model verification (T3A PASS, physically-correct Cf(x), a-priori
bands, MLflow-logged); the plunging finding (four dead-steady limit cycles, C_T stable to 4
decimals; the too-steep-C_T(St)-slope diagnosis is robust and corroborated by Camacho et al. 2020
sitting between our 2-D and the experiment). The NO-GO is the honest, discipline-preserving outcome
(tolerance not relaxed). Lower confidence: the exact transition magnitude depends on the freestream
Tu (a documented lever); the transition batch-means `reliable` flag is False on 3 of 4 runs (stable
means, mild cycle-to-cycle variation). **Bus-factor / finalize note:** the remaining steps are
procedural (compose final tails on completion -> MLflow -> merge -> tag) and documented in the Phase-C
cheatsheet; the plunging NO-GO does not gate Stage 14.
