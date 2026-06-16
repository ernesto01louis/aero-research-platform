---
# Required frontmatter — scripts/check_handoff_exists.sh parses these.
stage: 10
stage_name: "Stage 10 — V&V Debt Retirement + Output-Validity Bar"
status: complete
date_started: 2026-06-15
date_completed: 2026-06-16
session_duration_hours: 0
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-4-8
git_sha_start: "632678fda0d76dcf2a920f13bfd60ddd6ec8e237"
git_sha_end: "0122f35b5a4d476ed173ee5490f64857bc932f44"
stage_tag: v0.0.10
next_stage: 11
next_stage_name: "Stage 11 — Moving Mesh & Unsteady"
---

# Stage 10 — V&V Debt Retirement + Output-Validity Bar — DONE (2026-06-16)

> `git_sha_end` is provisional (= the last code commit `0122f35`); reconcile to the
> squash-merge SHA at the `v0.0.10` tag (the Stage-08 pattern). Work landed on branch
> `stage-10/vv-debt-naca0012` / PR #20.

## 0. Headline

The forward-regime laminar/transient regime — the one the flapping optimizer actually
operates in — is **validated GREEN** (3 new cases). The turbulent table-stakes debt is
**honestly characterised**: NACA 0012 is a documented NO-GO (the blunt-TE remedy is not
steady-convergeable) and the 2D bump is a documented CONCERN (an iterative-convergence
plateau); neither tolerance was relaxed. A reusable **laminar** and **transient
(pimpleFoam)** OpenFOAM capability now exists — the transient seed Stage 11 builds on.

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Retire turbulent canonical debt (NACA 0012 Cd, flat-plate Cf, 2D bump) | ⚠️ | NACA → **documented NO-GO** (blunt-TE not steady-convergeable; §3). Flat-plate Cf self-milestoned **Stage 12** (correlation-spread). Bump → **documented CONCERN** (p-residual plateau ~3e-4, confirmed; §3). xfails retained, tolerances NOT relaxed. |
| 2 | Add forward-regime canonical cases (Blasius plate, laminar airfoil, cylinder Strouhal) | ✅ | **All 3 GREEN** — see §3. New `aero/vv/forward_regime/` package + a laminar + a transient OpenFOAM path. |
| 3 | Output-validity bar (`docs/vv/output-validity-bar.md` + `aero/vv/reportable.py` + tests) | ✅ | Landed at Stage-09 close-out (22 tests); verified green. |
| 4 | Budget cap bump $50 → $150 (ADR-014) | ✅ | `aero/orchestration/cost_cap.py` (commit 632678f). |
| 5 | Merge ADR-015 constitution PR (Invariants 10 + 11) | ✅ | Ratified/merged 2026-06-15 (PR #15). |
| 6 | ADRs + handoff + Stage-11 prompt + tag v0.0.10 | ✅ | **ADR-017** (forward-regime + laminar/transient + NACA NO-GO); this handoff; **STAGE-11 prompt** at `docs/handoff-bundle/STAGE-11-moving-mesh-and-unsteady.md`; tag at close-out. |

## 2. Decisions made

- **Pre-cluster adversarial validation before any solve.** A 4-dimension workflow
  (routing / geometry / mesh-topology / drag-physics, each adversarially re-checked) found
  4 blockers in the never-tested blunt-TE C-grid — caught before spending cluster CPU.
- **NACA 0012 = documented NO-GO** (operator-chosen "diagnostic + honest NO-GO", then
  confirmed beyond it): the blunt-TE remedy is rejected (ADR-017). See §3.
- **Add forward-regime cases + a laminar and a transient OpenFOAM path** (ADR-017) — invest
  effort in the mission's regime; all 3 cases are GREEN.
- **2D bump = documented CONCERN, not forced** — the iterative-convergence plateau is a
  deep turbulent-numerics issue (the stage prompt's "rabbit-hole = rethink trigger"); defer
  to a dedicated convergence pass / a transient-mean treatment (Stage 11).
- **Provenance env** — operator derived `AERO_PROVENANCE_DSN` by swapping the DB name in
  `MLFLOW_BACKEND_STORE_URI` to `aero_provenance` (same owner role `aero_mlflow_user` owns
  both DBs, per `db/provision/aero_databases.sql`); validated end-to-end (MLflow runs log).

## 3. Results

**Forward-regime cases — all GREEN (validated on aero-dev, MLflow runs logged):**

| Case | Regime | Reference | Result |
|---|---|---|---|
| `blasius_flat_plate` | steady laminar | Blasius Cf=0.664/√Re_x (exact) | **GO** — Cf 2.15% (tol 5%) |
| `laminar_airfoil_naca0012` | steady laminar, Re=1000 | Kurtuluş 2015 Cd + Cl=0 symmetry | **GO** — Cd 0.16%, Cl 0.23% |
| `cylinder_strouhal_re100` | **transient** shedding | Roshko/Williamson St≈0.165 | **GO** — St 4.0% (tol 5%) |

**NACA 0012 — documented NO-GO (blunt-TE remedy rejected).** The blunt-TE C-grid was
repaired to checkMesh-valid (BW e_wake grading; outlet-split 5u/5l replacing a collapsed-prism
zero-area face; `airfoil_te` patch + nutUSpaldingWallFunction; base-wake taper to the
sharp-baseline aspect ratio; PCG + under-relaxation), and a pressure/viscous drag
decomposition was added (`forces` FO → `SolveResult.cd_pressure`/`cd_viscous`). But the steady
solve does **not converge** across 3 attempts: U=0.9 → SIGFPE iter ~33; under-relaxed →
diverged iter ~61 (DICPCG pinned at 1000-iter cap = base-wake AR ~28800); after the taper
(AR → 2954) → ~83 stable iters then a momentum/pressure blow-up while turbulence stayed
converged = the finite blunt base's **unsteady/shedding wake defeating a steady solver**.
The closed-form budget also shows blunt-TE can't reach 3% even converged. Resolution deferred
(transient + time-average / sharp-TE remesh / SU2 cross-check — ADR-017). xfail retained,
tolerance NOT relaxed.

**2D bump — documented CONCERN.** A single-grid diagnostic at end_time=8000 confirmed the
p initial-residual **plateaus at ~2-5e-4 from iter ~2000 through 4000+** and never reaches the
1e-6 target — a genuine convergence stall (not iteration-limited), so `cp_min` is not cleanly
grid-converged for a reliable GCI. Deferred to a dedicated convergence pass / transient-mean
(Stage 11). xfail retained, tolerance NOT relaxed.

## 4. Environment / dependency / schema changes

- `SolveResult` (`aero/adapters/_base.py`): `cd_pressure`, `cd_viscous` optional fields.
- `CaseSpec` / `FlatPlateSpec` (`schemas.py` / `tmr_specs.py`): `turbulence_model` accepts
  `"laminar"`; `CaseSpec` validator ties `trailing_edge_thickness` to the open-TE geometry.
- New `aero/adapters/openfoam/cylinder.py` (`CylinderSpec` + transient O-grid case writer).
- New `aero/vv/forward_regime/` package (3 cases) + registry, wired into `aero vv list/run`.
- New reference data under `data/references/forward_regime/` (git-tracked, small/analytical).
- No new pyproject extras; no DB/bucket/container-SHA changes.

## 5. CI/CD changes

New cluster-bound (slow) V&V tests: `tests/vv/test_forward_regime_{blasius,laminar_airfoil,
cylinder}.py` (real PASS assertions, not xfail). Host-side `tests/stage_10/` tests added.
No new required status checks.

## 6. Gotchas discovered

- **`aero-vv` (LXC 213) lacks apptainer** — only the SIF is present; run SIF solves on
  `aero-dev` (16 cores) or `aero-build` (8). `aero vv run --host aero-vv` fails.
- `settings.local.json`'s `env` block did not reach Bash subprocesses; the operator exports
  the provenance vars from the shell profile instead (each Bash tool call re-inits from it).
- A symmetric cylinder + axial inflow won't shed within a finite run; a small freestream tilt
  (5°, axisymmetric body → St unaffected) seeds it; the FFT detrends the small mean lift.
- pimpleFoam `fvSolution` needs `"(U|UFinal)"` (no space) or it fails on `UFinal` at PIMPLE
  iter 2.
- The NACA blunt-TE base wake (constant tiny height over 100c) gave AR ~3e4 → ill-conditioned
  pressure eqn; tapering the outlet fixes it. Solver choice (PCG) + under-relaxation are
  robustness-only (don't change the converged solution).

## 7. Open items for the next stage (and beyond)

- **Stage 11 (Moving Mesh & Unsteady):** prompt is written. Builds on the transient seed —
  moving meshes, `aero/postprocess/` (phase-avg, propulsive efficiency, cycle-convergence),
  oscillating-cylinder + plunging-airfoil V&V. The deferred NACA transient-mean rethink + the
  bump transient-mean treatment fit here.
- **Stage 12:** `u95_statistical` for the unsteady St (the cylinder St=4% carries no
  statistical-uncertainty envelope yet); flat-plate Cf correlation-spread.
- **Rigor follow-ups (cheap):** clean-SHA reportable re-runs of the 3 forward-regime cases
  (the GO runs used `--allow-dirty`); a GCI mesh-independence sweep per forward-regime case.
- **Reference reconcile:** NACA `cd.csv` 0.008120 is the SA value (true SST ~0.00808-0.00809)
  — flagged in `reference.md`, operator decision (touches the V&V contract + `_CD_REFERENCE`).

## 8. Pointers for next session

- **Read first:** this file + ADR-017 + `git log --oneline origin/main..` (or the v0.0.10 tag).
- **Run first to verify:** `pytest tests/stage_10 tests/unit -q`, `ruff check aero tests`,
  `mypy aero`. Cluster V&V: `aero vv run --case <name> --host aero-dev` (NOT aero-vv).
- **Do not re-read:** the full validation/diagnostic transcripts — conclusions are in §3.

## 9. Artifacts produced

Commits on `stage-10/vv-debt-naca0012` (PR #20): `9103999` open; `a3c907b` blunt-TE mesh +
decomposition fixes; `7952e66` handoff; `60d5711` base-wake taper; `05c24d5` NACA NO-GO docs;
`6ab3c99` Blasius flat plate (GO); `63e5049` laminar airfoil (GO); `0122f35` transient cylinder
(GO); + this close-out (ADR-017, Stage-11 prompt, bump-xfail update, this handoff). New code:
`aero/adapters/openfoam/cylinder.py`, `aero/vv/forward_regime/{blasius_flat_plate,laminar_airfoil,
cylinder_strouhal}.py`, the laminar/transient adapter paths, `data/references/forward_regime/`,
host + cluster tests. MLflow runs (aero-mlflow): the 3 forward-regime GO runs.

## 10. Confidence / risk note

High confidence: the 3 forward-regime GOs (analytical/literature matches on well-conditioned
meshes, MLflow-logged); the NACA NO-GO + bump CONCERN (multiple cluster runs, evidence-based).
Medium: the cylinder St (4%, single grid, no statistical-U95 yet — Stage 12) and the FFT
sampling; the laminar-airfoil 10% band reflects the genuine low-Re Cd spread. The transient
path is new — exercised on one case (the cylinder); Stage 11 hardens it (moving mesh,
cycle-convergence). The bump/NACA root-cause attributions are evidence-based but their
*resolutions* (transient-mean, remesh) are unproven and deferred.
