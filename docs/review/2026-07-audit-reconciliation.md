# 2026-07 external audit — reconciliation against the actual platform state

> **What this is.** In July 2026 the operator commissioned an external audit of the
> project: (1) *"AI-Driven Aerodynamic Shape Optimization for 3D Geometry — Practical
> Roadmap and Repository Assessment"* and (2) *"Implementation Blueprint for the
> aero-research-platform"*. The audit read the **public** GitHub state (v0.0.6 /
> Stage 06, May 2026) and proposed a surrogate-accelerated shape-optimization module as
> "new Stages 15–18". The actual repo was mid-**Stage 14** of the ADR-013 **20-stage**
> roadmap when the audit landed, so much of it describes work already planned or built.
>
> **Why this file exists.** Operator directive: adopt what is genuinely new WITHOUT
> replacing or disregarding anything. This table gives every audit recommendation an
> explicit disposition — *already exists*, *planned (stage N)*, *adopted now
> (ADR-025)*, or *ledgered* — so nothing from the audit is dropped silently. The audit
> also expresses the operator's end-vision (arbitrary STL/STEP in → CFD-verified
> improved geometry out); the roadmap's Stages 15–20 remain the vehicle for it.

## Disposition table

| # | Audit recommendation | Disposition | Where / evidence |
|---|---|---|---|
| 1 | Surrogate-accelerated shape-optimization module ("Stages 15–18") | **Planned — is the roadmap** | Stage 15 (CFD-in-the-loop BO, prompt committed), Stage 16 (surrogate-accelerated, own-data), Stage 17 (geometry ingestion): `docs/handoff-bundle/README-handoff.md` rows 15–17 |
| 2 | Deep-ensemble / MC-dropout predictive uncertainty for surrogates | **Adopted now (ADR-025)** / MC-dropout ledgered | `aero/surrogates/_common/{ensemble,calibration}.py`; `SurrogatePrediction` in `base.py`; ledger §6 |
| 3 | Trust-region surrogate management (bound steps; expand/shrink on CFD outcome) | **Adopted now (ADR-025)** | `aero/surrogates/_common/trust_region.py` |
| 4 | Uncertainty-routed / EI active-learning infill (route high-uncertainty candidates to CFD, retrain) | **Adopted now (ADR-025)** | `aero/surrogates/_common/infill.py`; retrain→re-certify forced by the cert data gate (Invariant 9) |
| 5 | Always re-validate optimized candidates in real CFD; never report a surrogate optimum | **Already exists** | Hard Rule 14 (CFD-VERIFIED-OPTIMUM-ONLY); `OptimizationResult.cfd_verified` in `aero/vv/reportable.py`; `.claude/rules/optimization-integrity.md` |
| 6 | Treat surrogate-predicted gains as hypotheses; gate acceptance on CFD with drag-count error reporting | **Already exists** | `delta > k·U95` (Invariant 10, ADR-023 paired-difference); `aero/vv/surrogate/compare_surrogate_cfd.py` |
| 7 | Certificate/validity gating of surrogates | **Already exists** | Invariant 9; `CertificateOfValidity.assert_current` (ADR-008) — now extended with calibration evidence (ADR-025) |
| 8 | Selection-bias-aware best-of-N reporting | **Already exists** | `OptimizationResult.n_candidates` + held-out verification (Stage-10 schema; Stage-15 prompt) |
| 9 | FFD / kinematics-parametrization of the design space | **Planned (Stage 15)** | Stage-15 prompt: "Kinematics/planform parametrization (FFD/morphing, ~5–10 vars)" |
| 10 | Differentiable trilinear FFD in PyTorch (gradient-based optimization through the surrogate) | **Ledgered** | Ledger §6 → Stage 16+ / post-v0.1.0 adjoint seed; premature for Stage 15's 5–10-var BO |
| 11 | Arbitrary STL/STEP ingestion, repair, robust meshing; generic external-aero autogen template | **Planned (Stage 17)** | README-handoff row 17 "Arbitrary-Geometry Ingestion + Robust Meshing"; autogen template noted in ledger §6 |
| 12 | CMA-ES / BoTorch / Bayesian optimizer stack | **Planned (Stage 15)** | Stage-15 prompt pins BoTorch/Ax or lightweight GP+EI behind an extra, ADR at Stage 15 |
| 13 | SU2 adjoint baseline / classical ASO benchmark | **Ledgered (pre-existing)** | Post-v0.1.0 committed sequence (ledger §5): DAFoam v5 + SU2 adjoint; SU2 frozen-optional (ADR-013) |
| 14 | Transolver / FIGConvNet / X-MeshGraphNet / MoE surrogate zoo; automotive datasets & checkpoints (DoMINO warm-starts, SHIFT-SUV) | **Deliberately cut — stays cut** | ADR-013 optimizer-mission refocus; foreign data cannot certify (Invariant 11). The audit predates the refocus; not re-opened. |
| 15 | 2D-first pathway (AirfRANS surrogate → optimize → CFD re-validate) | **Superseded by the flapping ladder** | The platform's cheap-case Phase A (Stage-15 prompt, review F3) plays this de-risking role on the already-validated oscillating-cylinder/plunging-foil cases; AirfRANS would be foreign data (Invariant 11) |
| 16 | Self-generated CFD as the generality engine ("own-data factory") | **Planned (Stage 16) — sharpened by ADR-013** | Stage-16 map row: surrogates train ONLY on the platform's own validated CFD (the Stage-15 corpus flywheel) |
| 17 | Proxmox GPU passthrough (RTX 4090 VM) for local training | **Out of scope for this repo — operator infra** | Cloud GPU path exists (RunPod executor, Invariant 8 cost cap); local-GPU passthrough is a homelab decision, not a platform stage |
| 18 | Uncertainty-aware promotion gates (coverage bands) for surrogate certs | **Adopted now (ADR-025) + Stage-16 DRAFT gate** | `UncertaintyCalibration` cert evidence; smoke→validated calibration band in the Stage-16 DRAFT prompt |

## Notes

- Items 2–4 + 18 are the audit's genuinely-new contribution to this repo — the
  **anti-surrogate-exploitation stack** — and are what ADR-025 lands, tested, ahead of
  Stage 16 (the consuming stage), per the ADR-023 inter-stage precedent.
- Item 14 is the one place the audit and the mission disagree; ADR-013's cut stands.
  The audit's own caveats (car-trained checkpoints are bluff-body priors; OOD accuracy
  degrades; CC-BY-NC licensing) point the same direction as Invariant 11.
- The audit's repo assessment ("Stage 6 of 16, not a usable optimizer") was accurate
  **for the public state it could see** and is stale for the private tree; its verdict
  "mine it for architecture ideas, build the optimizer on the roadmap" is effectively
  what this reconciliation implements.

*Nothing in the audit is disregarded silently: every recommendation above is either
already load-bearing, scheduled on the 20-stage map, landed by ADR-025, or ledgered
with its unblocking condition in `docs/operator/deferred-work-ledger.md` §6.*
