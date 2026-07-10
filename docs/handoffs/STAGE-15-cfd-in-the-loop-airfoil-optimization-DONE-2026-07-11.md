---
stage: 15
stage_name: "Stage 15 — CFD-in-the-Loop Airfoil Shape Optimization"
status: complete
date_started: 2026-07-10
date_completed: 2026-07-11
session_duration_hours: 0
claude_code_version: "2.1.150 (Claude Code)"
model: claude-fable-5
git_sha_start: "24cc7d0ca4fd000000000000000000000000000000"
git_sha_end: "PENDING_PR_SQUASH"
stage_tag: v0.0.15
next_stage: 16
next_stage_name: "Stage 16 — Surrogate-Accelerated Optimization (own-data)"
---

# Stage 15 — CFD-in-the-Loop Airfoil Shape Optimization — (2026-07-11)  [THESIS CHECKPOINT — GO]

> `git_sha_start` is the Stage-14-close commit `24cc7d0` (this branch's base); `git_sha_end` is
> provisional (reconcile to the `stage-15-airfoil-opt`→`main` squash SHA at the `v0.0.15` tag).
> **This is the mission's first thesis-grade result** — a CFD-verified aerodynamic improvement that
> exceeds its combined uncertainty. Re-targeted from flapping to airfoil per the operator's pivot.

## 0. Headline

**The platform produced its first CFD-verified improvement — the product exists.** A direct-CFD
Bayesian optimizer (`aero/optimize/`) optimized a 2-D airfoil's shape (NACA-4 camber) to maximize
lift-to-drag at fixed AoA on the trusted laminar NACA-0012 case (Re=1000). Over **14 CFD-evaluated
candidate shapes** it found a cambered section (max_camber ≈ 0.075, camber_position ≈ 0.59) that
raises **L/D from 1.481 (baseline NACA 0012 at AoA 4°) to 2.172 — a +47% improvement**. The
improvement is **matched-condition** (baseline and optimum solved at identical mesh topology, so the
systematic CFD bias cancels), **CFD-verified on a held-out solve** (clean SHA), and clears the
thesis-grade bar: `delta = 0.691 > 2·U95 = 0.378` (Invariant 10). The result is a self-describing
`ReportableResult` bundle (`data/vv/stage15_optimization.json`, `validation_tag=thesis-grade`).

This is the F3 re-sequencing realized: the optimization + delta-UQ loop is proven on a **cheap,
trusted** case (the airfoil validates cleanly; ~1-2 min/solve), decoupled from the flapping model's
2-D-vs-3-D magnitude wall. The delta cancels the very systematic bias that failed the Stage-14
flapping absolute anchor — which is why an airfoil ASO was the right first product target.

## 1. Deliverables status

| # | Deliverable | Status | Note |
|---|---|:-:|---|
| 1 | The optimization loop (direct-CFD BO) | ✅ | `aero/optimize/`: design_space, gp (numpy Matérn-5/2 + Cholesky), acquisition (EI via erf), bo (ask/tell, discrete-pool EI, best-of-N), objective (DV→ground-truth CFD→L/D), airfoil_case. Every candidate CFD-evaluated (Hard Rule 14). |
| 2 | The delta-UQ report | ✅ | Matched-grid GCI-on-the-delta (steady; no paired-difference) → `compose_improvement(kind="steady")`; thesis-grade only if delta > k·U95, clean SHA, held-out. `data/vv/stage15_optimization.json`. |
| 3 | Hard Rule 14 constitutional promotion | ⏳ proposed | ADR-027 (Invariant 12 — CFD-VERIFIED-OPTIMUM-ONLY); parallel Constitution micro-PR, ≥72 h window (ADR-015 process). |
| 4 | ADR(s) + handoff + Stage-16 prompt + tag | ✅ | ADR-026 (optimizer pin) + ADR-027 (proposed); this handoff; Stage-16 prompt authored; tag `v0.0.15`. |

## 2. Decisions made

- **Direct-CFD Bayesian optimization, numpy GP+EI backend, NACA-4 y-only parametrization**
  (ADR-026). Rejected: BoTorch/Ax (heavy deps, overkill for 2-6 DVs — reserved for `aero[bo]` /
  Stage 17+); Hicks-Henne (deferred; NACA-4 camber is the cheapest certain-win first demo);
  importing `infill.py`'s EI (branch dependency — reimplemented).
- **Objective = maximize L/D at fixed AoA** (lift-constrained cd-at-fixed-cl needs an AoA-trim loop,
  deferred). Base = the trusted `laminar_airfoil` (the only green + reliably-converging airfoil case)
  at AoA 4° (lift + head-room; below the ~9° shedding onset).
- **Matched-condition delta cancels systematic bias** — the key insight that makes an improvement
  trustworthy even where the absolute anchor is not (the pivot's whole rationale).

## 3. Deviations from the stage plan

- **Re-targeted flapping → airfoil** (operator mission pivot, 2026-07-10): Stage 14's flapping
  forward validation was a documented NO-GO (2-D-vs-3-D), and the product (the optimizer) was
  unbuilt. The committed (flapping-oriented) Stage-15 prompt is superseded by this airfoil target;
  the F3 "cheap trusted case first" is realized by the airfoil rather than the cylinder/plunging.
- **MLflow logging deferred for the campaign** (ran `--no-mlflow` for robustness); the JSON bundle
  carries the full four-fold provenance. Wiring the optimization run's MLflow logging is ledgered.

## 4. Environment / dependency / schema changes

- New package `aero/optimize/` (design_space, gp, acquisition, bo, objective, airfoil_case, report),
  core stdlib+numpy+pydantic. New `scripts/stage15_airfoil_opt.py` driver.
- `aero/adapters/openfoam/geometry.py`: `naca4_coordinates` (camber+thickness shape DVs, y-only).
- `aero/adapters/openfoam/schemas.py` `CaseSpec`: `max_camber`, `camber_position`,
  `max_thickness_frac` (strict, bounded, baseline-recovering); `conf/case/naca0012.yaml` updated
  (provenance-complete). `case_writer._surfaces`/`_blockmeshdict` thread the shape (de-mirrored
  lower mid-chord vertex; baseline byte-identical).
- `pyproject.toml`: `aero[bo]` placeholder extra reserved (ADR-026). No new hard deps.

## 5. CI/CD changes

- No new required checks. 27 host-side `tests/stage_15/` tests (NACA-4 geometry + matched topology;
  the numpy optimizer core; GO/NO-GO composition + guards). Full suite green. The optimizer core
  imports only stdlib+numpy+pydantic (import-platform-only fence intact).

## 6. Gotchas discovered

- **`SmallSignalError` surfaces as a pydantic `ValidationError`** (raised inside a validator) — the
  GO/NO-GO branch is a `MatchedGridDelta.is_significant()` PRE-check, not an exception catch.
- **Untracked files make the tree dirty for `compute_provenance`** (`git status --porcelain`), so a
  clean-SHA thesis-grade campaign requires not touching the repo mid-run (P1b interaction).
- **`np.vectorize(math.erf)` fails on size-0 inputs** unless `otypes` is set (all-std=0 EI batch).
- Steady L/D has `u95_statistical = 0` (valid for `kind="steady"`) — the entire delta uncertainty is
  the matched-grid Richardson; the ~16-20-cycle campaign budget (flapping) does NOT apply.

## 7. Open items for the next stage (and beyond)

- **Stage 16 (Surrogate-Accelerated Optimization):** prompt authored
  (`docs/handoff-bundle/STAGE-16-surrogate-accelerated-optimization.md`). Train surrogates on the
  platform's OWN Stage-15 CFD corpus (Invariant 11 — no foreign data), accelerate the loop, and
  consume the concurrent **ADR-025** anti-surrogate-exploitation stack (ensemble/calibration/
  trust-region/infill on `feat/stage-14-anti-surrogate-exploitation`) — reconcile that branch.
- **Ledgered (this stage's honest limits):** GP length-scale is fixed (add a coarse LML grid-search);
  discrete-pool EI is low-D only (a gradient/optimizer acquisition for higher DVs); fixed-AoA L/D
  (add an AoA-trim loop for lift-constrained cd); Hicks-Henne / 3-DV thickness parametrization;
  wire the optimization campaign's MLflow logging; M1 (batch-size vs τ_int — inherited).
- **ADR-027 Constitution amendment** (Invariant 12) — parallel micro-PR, ≥72 h window + operator
  approval.

## 8. Pointers for next session

- **Read first:** this handoff, ADR-026 + ADR-027, `data/vv/stage15_optimization.json`, the Stage-16
  prompt, `.claude/rules/optimization-integrity.md`.
- **Run first to verify:** `pytest tests/stage_15 -q` (green), `mypy aero`, `ruff check`. Re-run the
  optimizer: `python scripts/stage15_airfoil_opt.py --host aero-dev --n-init 6 --n-iter 8 --aoa 4`.
- **Do not re-read:** the flapping Stage-14 work (closed as a documented NO-GO; separate lineage).

## 9. Artifacts produced

Commits `25b013f`, `66fef60` on `stage-15-airfoil-opt`: the NACA-4 parametrization; the `aero/optimize`
BO package + delta-UQ + driver; 27 tests; ADR-026/027; this handoff. Data:
`data/vv/stage15_optimization.json` (the thesis-grade CFD-verified improvement bundle:
L/D 1.481→2.172, +47%, delta 0.691 > 2·U95 0.378, DVs {m=0.075, p=0.59}, n_candidates=14, held-out).

## 10. Confidence / risk note

High confidence: the optimizer core (GP/EI/BO validated on analytic objectives + 27 host tests); the
CFD-verified improvement (real solves, matched topology, held-out verification, clean SHA, delta
clears 2·U95); the physics (camber raises L/D at incidence — the expected, well-understood result).
The matched-condition delta is the robust product quantity. Lower confidence / honest limits: the
absolute L/D values inherit the low-Re laminar case's ~10% reference band (irrelevant to the delta);
the GP length-scale is fixed (a mild over/under-exploration risk the LML grid-search would tighten);
the objective is fixed-AoA L/D, not lift-constrained drag (the classic ASO objective — a deferred
trim loop). None of these weaken the headline: **a trustworthy, CFD-verified aerodynamic improvement
— the platform's first product output, and the thesis checkpoint met.**
