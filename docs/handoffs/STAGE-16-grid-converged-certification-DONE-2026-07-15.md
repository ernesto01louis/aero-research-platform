---
stage: 16
stage_name: "Stage 16 — Grid-Converged Certification of the Airfoil Optimum"
status: complete
date_started: 2026-07-12
date_completed: 2026-07-15
session_duration_hours: 71
claude_code_version: 2.1.150
model: claude-fable-5
git_sha_start: c385c01
git_sha_end: e6d45fd89043d0e3a9baacc2f7aac8b53a6a49a5
stage_tag: v0.0.16
next_stage: 17
next_stage_name: "Stage 17 — Surrogate-Accelerated Optimization (own-data)"
---

# Stage 16 — Grid-Converged Certification — DONE

## Headline

**Honest NO-GO — by exactly one pre-registered gate.** On the final 4-grid graded family
(claim triplet {231², 136², 80²}, finest grid included; all eight solves converged inside
the pre-registered gates, margins 1.6×–46×, tightest the 231² optimum's steadiness at 1.6×),
the matched L/D delta is **monotone** (25.738 → 23.482 → 21.719) and clears the bar under
the Fs=3, assumed-first-order (p=1) fallback GCI (21.719 vs required 2·U95 = 15.108) — but
its **observed order is 0.465 vs the pre-registered 0.5 floor**, and at that measured
sub-floor order the same GCI construction gives 2·U95 ≈ 37.7, which the delta would NOT
clear: significance is conditional on the fallback order, which is one more reason the order
gate is a hard NO-GO. The bar was committed
before any campaign ran; it was not adjusted after the fact. Result ships as
`validation_tag="validated"` (`data/vv/stage16_relaxed_optimization.json`). The stage's
single job — certify or render a fully documented honest NO-GO with the fallback taken —
is complete, and it produced three durable scientific artifacts along the way: the corrected
divergence mechanism, the nesting (fixed-mapping) mesh-family machinery, and the
spurious-attractor finding with its measured Courant threshold.

## The story arc (read this first)

1. **Steady graded campaign** (`stage16_grid_convergence.json`): the graded family CURES the
   old 136² SIGFPE and reproduces Stage-15 at the shared 80² grid to <0.01% — but the loaded
   optimum at 136² is a violent two-iteration numerical limit cycle (cd sign-crossings
   341/1000 tail iterations) and the delta is non-monotone at the finest grid. NO-GO on all
   four hard gates.
2. **Impulsive-start URANS at maxCo 8** (`stage16_urans_pathology.json`): settling on the
   100c domain is O(100+ t*) (infeasible), and the loaded optimum falls into a SPURIOUS
   high-circulation attractor at medium/fine (cl≈+3.9, cd≈−0.65 at 80²; cl swinging 2.5–6.7,
   cd<0 at 136², impulsive-start evidence) while every recorded baseline run and the coarse
   optimum stay physical. At 80² the departure also occurs when initialized FROM the
   converged steady field (within 2 t*).
3. **Attribution diagnostics** (`stage16_courant_diag.json`): at maxCo 2 and 4 (steady
   init, 80²) the solve STAYS on the physical solution through 20 t* (final windows: cd
   +0.0211/+0.0211, cl +1.0040/+1.0032) → the attractor is a
   large-timestep (Euler + Co 8) artifact; threshold in (4, 8]. The physical flow is STEADY;
   the pseudo-time SIMPLE iteration and large-Co Euler are what destabilize.
4. **Relaxed certification** (ADR-030; `stage16_relaxed_convergence.json`): steady-init +
   maxCo 4 + last-5-t* means + pre-registered drift/steadiness/physicality gates. First
   family {136,80,47}: all six converged, delta significant but NON-monotone at 136² → the
   family measurably hadn't reached the asymptotic range. **Refine-to-test**: extended one
   rung finer (231², mapFields grid continuation, six rows reused verbatim). Final verdict
   above.

## 1. Deliverables status

| Deliverable | Status | Note |
|---|---|---|
| Grid family reaching the asymptotic range for the loaded optimum | ⚠️ | Graded (nesting) family built + verified (`mesh_family.py`); monotone at {231,136,80} but observed order 0.465 — one rung short of asymptotic by the 0.5 floor |
| Thesis-grade improvement OR honest documented NO-GO | ✅ | Honest NO-GO by the order gate alone; delta monotone, significant only under the p=1 fallback; full 4-grid evidence |
| Adversarial panel re-run before any GO | ✅ (n/a for GO) | No GO to verify; an 18-finding adversarial honesty review (2026-07-15) was dispositioned into this handoff + ADRs before commit — every correction reduced the claim |
| ADR + handoff + Stage-17 prompt + tag v0.0.16 | ⚠️ | ADR-028/029/030 + this handoff + STAGE-17 prompt (corrected headline) done; v0.0.16 tag pends operator PR merge |

## 2. Decisions made

- **Corrected mechanism (ADR-028):** `refined()` at fixed first cell makes near-wall grading
  GENTLER with refinement (r 1.468@28² → 1.067@136²) — the Stage-15 handoff's "steepening"
  one-liner was directionally wrong; the old 136² SIGFPE was resolved unsteadiness, and the
  old family's true defect was non-self-similarity (mapping drift).
- **Fixed-mapping (pinned-G) refinement** with `refined(ratio, graded=True)` default flip;
  front/wake first cells promoted to `CaseSpec` fields; fail-loud wall-BC-branch guard.
- **Hard-gated verdicts** (`certification_gates`): significance alone is never a GO — closes
  the Stage-15 gap where `all_converged` was recorded but not gated.
- **Estimator-artifact disclosure over post-hoc re-derivation** (ADR-028): the pointwise
  cl/cd SEM statistic is invalid when cd sign-crosses (it spuriously PASSED the 136²
  baseline and failed the optimum); the verdict was not re-derived with a friendlier
  statistic.
- **ADR-029 `IndependentDeltaU95`**: measured, no-cancellation RSS for unpaired unsteady
  deltas — landed + tested; ultimately not needed (relaxed tails are flat).
- **ADR-030 relaxation certification** + refine-to-test extension; **the 0.5 order floor was
  NOT adjusted** when the final result landed at 0.465.

## 3. Deviations from the stage plan

- The stage prompt's primary route (graded refinement fixes divergence → steady GCI) was
  half right: the graded family fixed the crash and the family legitimacy, but steady SIMPLE
  remained unusable at the finest grids; TWO further sanctioned-path iterations (impulsive
  URANS → time-accurate relaxation) were needed, each forced by measured evidence.
- `transient_fvschemes` lacked `wallDist` for k-ω SST (pimpleFoam exits pre-step) — caught
  by the first cost probe; fixed for non-laminar only (cylinder byte-identical).

## 4. Environment / dependency / schema changes

- `CaseSpec` += `first_cell_front`, `first_cell_wake` (defaults keep the baseline
  blockMeshDict byte-identical); `conf/case/naca0012.yaml` updated (Hydra completeness).
- `aero/vv/reportable.py`: `IndependentDeltaU95` joins the `DeltaU95` union; thesis-grade
  gate accepts composed OR independent measured variants; `compose_independent_improvement`
  (`reportable_compose.py`); `compose_independent_result` + `certification_gates`
  (`aero/optimize/report.py`).
- New modules: `aero/optimize/mesh_family.py`; `aero/adapters/openfoam/transient_airfoil.py`;
  `aero/postprocess/window_means.py`; `OpenFOAMSolver.load_force_series` + spec dispatch.
- Drivers: `scripts/stage16_grid_cert.py` (steady, hard-gated, --diag),
  `scripts/stage16_urans_cert.py` (probe / extend / --grids / concurrent),
  `scripts/stage16_relaxed_cert.py` (steady-init relaxation, --reuse-rows, mapFields
  continuation). 33 new tests (`tests/stage_16/`); suite 502 green; mypy strict + ruff clean.

## 5. CI/CD changes

None.

## 6. Gotchas discovered

- Untracked files count as dirty for provenance — commit `data/vv` artifacts before
  launching the next campaign.
- `LocalSSHExecutor` default 2 h long-timeout silently converts long solves into failures.
- `ThreadPool.map` hides worker exceptions until collection — wrap workers into evidence
  rows; serialize concurrent git provenance reads (index.lock race suspected: the first
  URANS campaign silently lost its medium pair).
- pimpleFoam + SST requires `wallDist` in fvSchemes.
- OpenFOAM `adjustTimeStep`: ONE tiny LE cell Courant-caps the whole run; check
  `Courant Number max` early. **maxCo 8 + Euler produced a stable, wildly non-physical
  attractor (cl≈+3.9, cd≈−0.65) — always sanity-check URANS attractors against the steady
  solution.** Threshold measured between Co 4 and 8 for this family.
- Impulsive starts on a 100c C-grid settle over O(100 t*): initialize URANS from steady
  fields (and finer rungs by `mapFields -consistent` continuation — SIZE-MATCH the source:
  grid labels are positional and collide across campaigns).
- Host-level contention (Proxmox nightly backup window) can starve LXC solvers to ~10% duty
  cycle (R-state, near-zero CPU) — not a hang. SIGFPE mid-run with endTime-only writes loses
  the segment: checkpoint `writeInterval 10`.
- The pointwise-cl/cd SEM statistic breaks when cd sign-crosses (both false-pass and
  false-fail observed at 136²) — disclosed in ADR-028; estimator replacement ledgered.

## 7. Open items for the next stage (and beyond)

- **Stage-17 prompt exists**: `docs/handoff-bundle/STAGE-17-surrogate-accelerated-optimization.md`
  (renamed from STAGE-16-*; its retracted "+47% thesis-grade" headline corrected).
- **Certification gap is ONE order estimate wide**: the 393² rung (~2 weeks serial / ~10 days concurrent on
  aero-dev via the relaxation route, scaling the measured 231² wall times) or a wall-resolved family on bigger hardware would
  settle the asymptotic-range question. Costed, ledgered — a strong candidate to fold into a
  later stage or a RunPod burst.
- Stage-map renumbering ripple (surrogate→17 … release→21): keep 21 stages or compress —
  OPERATOR decision (note in `README-handoff.md`).
- ADR-027 (Invariant 12) still `proposed`; ≥72 h window; operator merge pending.
- **Trunk bookkeeping (state as of 2026-07-15):** the operator merged stage-15 to main as
  PR #29 (`f5d5ead`) and cut v0.0.14 + v0.0.15 while Stage 16 ran; this branch was
  reconciled with that main (merge commit, stage-16 side kept for stage files) and its PR
  targets main. Only v0.0.16 remains to tag, after the operator merges.
- Ledgered: replace the steady drivers' pointwise-SEM statistic (per-batch ratio-of-means);
  root-cause the medium-pair thread exception (suspected git index.lock race); reclaim the
  abandoned impulsive-URANS run dirs on /mnt/aero/runs (propose-first); carried from
  Stage 15: GP length-scale LML, gradient acquisition, AoA-trim loop, Hicks-Henne 3-DV,
  MLflow campaign logging.

## 8. Pointers for next session

- **Read first:** this handoff; ADR-028 → ADR-029 → ADR-030 (in that order — they are the
  story); `data/vv/stage16_relaxed_convergence.json` (the final 4-grid record);
  `data/vv/stage16_urans_pathology.json` (the attractor evidence).
- **Do not re-derive:** the divergence mechanism, the Courant threshold, the settling-time
  problem — all measured, all committed.
- **Run first to verify:** `pytest -m "stage_15 or stage_16"` (64 green), full suite (502),
  `mypy aero`, `ruff check`.
- **Reproduce the final campaign:** the exact invocations are in the driver docstrings; the
  optimum DVs are in `data/vv/stage15_optimization.json::design_variables`.

## 9. Artifacts produced

22 commits on `stage-16-grid-cert` (`3b6afc6`…`e6d45fd` + docs): the graded mesh-family
package + tests; three campaign drivers; the URANS substrate (transient case, window means,
IndependentDeltaU95); nine `data/vv/stage16_*.json` evidence bundles (divergence diag,
steady NO-GO pair, URANS probe/convergence/pathology, Courant diag, relaxed
convergence/optimization);
ADR-028/029/030; the renamed+corrected Stage-17 prompt; the renumbered stage map.

## 10. Confidence / risk note

**Certain** (measured, committed, reproducible): the corrected divergence mechanism; the
family's G-invariance (test-pinned); the spurious attractor and its (4, 8] Courant threshold
(`stage16_courant_diag.json`); the final 4-grid values (drift/osc gates satisfied at
1.6×–46× margin); the verdict arithmetic. **Disclosed for the auditor:** the endpoint L/D
series are themselves far from converged (observed orders −0.8 baseline / −3.9 optimum;
per-quantity u95_numerical 59% of the baseline value, 18% of the optimum) — only the MATCHED
delta partially cancels, which is consistent with the y+-drift hypothesis and is exactly why
the order gate matters. **Less certain:** the physical interpretation of the sub-0.5
observed order (wall-function y+ drift 25→9 across rungs is the leading hypothesis,
untested); whether 393² would clear the floor. **Bus factor:** raw force series live on `/mnt/aero/runs` (aero-dev);
every claim-relevant number is also in the committed JSONs with run_ids; if the NFS runs are
reclaimed, the committed artifacts remain sufficient to audit (not to re-derive) the
verdict.
