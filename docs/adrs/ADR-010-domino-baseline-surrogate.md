# ADR-010 — DoMINO baseline surrogate (NVIDIA PhysicsNeMo)

- **Status:** accepted
- **Date:** 2026-06-01
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 09)
- **Stage:** 09

## Context and problem statement

Stage 09 trains the platform's first *production-grade* surrogate: NVIDIA
PhysicsNeMo's **DoMINO** on DrivAerML. Stage 08 (ADR-008) shipped the `Surrogate`
protocol + `CertificateOfValidity` framework but only scalar smoke baselines.
DoMINO differs in kind — it is geometry-aware (consumes a surface point cloud,
predicts surface fields + integrated coefficients) — yet it must conform to the
same platform contract and ship a verifiable certificate (CONSTITUTION
Invariant 9). This ADR records the container pin, the model wiring, the
Predictor-Corrector recipe, the certificate's validation gate, and — crucially —
how surrogate validation is de-conflated from the solver-V&V dashboard.

## Decision drivers

- **PLATFORM-NOT-HUB / pinned heavy deps** (Hard Rules 1, 8): PhysicsNeMo is a
  heavy CUDA stack and must be containerized + pinned.
- **Reproducibility** (Principle 1): every DoMINO run logs the four-fold tuple +
  the surrogate tags; the cert is the citation.
- **ML augments, never replaces, validated physics** (Principle 4): the cert is
  the agent layer's trust gate.
- **The existing scalar `predict` seam** vs DoMINO's mesh input.
- **A red solver-V&V dashboard** (all 8 TMR cases xfail since Stage 05) must not
  block a legitimately-validated surrogate, nor be hand-waved away.

## Considered options

1. **Wrap the NGC container `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08`** and
   conform DoMINO to the existing `Surrogate` protocol; validate against held-out
   DrivAerML; keep the solver-V&V dashboard a separate contract.
2. **Build PhysicsNeMo from a CUDA base + pip** (no NGC) and otherwise as above.
3. **Promote a mesh-native `GeometrySurrogate` protocol** distinct from the
   scalar `Surrogate`.

## Decision outcome

Chose **Option 1** because the NGC container is NVIDIA's recommended,
reproducible path (Pass 3 §9.1), carries the Predictor-Corrector recipe, and
keeps DoMINO inside the one `Surrogate` contract the whole platform already
speaks.

### Key decisions

- **Container pin:** `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08`, hard-pinned
  in `containers/physicsnemo.def` (`From:` line). The SIF wraps it (apptainer
  `Bootstrap: docker`) and adds `torch-geometric>=2.6` + `warp-lang>=1.4` (PyG is
  the platform GNN library, ADR-008 §D6). Torch-only — never jax in the same SIF.
  **Update procedure:** bump the `From:` tag + the `nvidia-physicsnemo` pin in
  `pyproject.toml[physicsnemo-cu12]` together, in a new ADR, and re-run
  `scripts/build_physicsnemo_sif.sh`. The exact `nvidia-physicsnemo` pip pin
  (proposed `==1.1.0`) is confirmed against the 25.08 base at first build (open
  decision — operator may read release notes first).
- **Licensing:** PhysicsNeMo is Apache-2.0. The NGC container bundles the NVIDIA
  CUDA/cuDNN redistributables — the same EULA category already relied on by every
  `nvidia/cuda` base image since Stage 03 (OpenFOAM/SU2/PyFR/NekRS/JAX-Fluids).
  No *new* proprietary-license posture; consistent with Invariant 5.
- **Mesh-vs-scalar bridge:** `DominoSurrogate(Surrogate)` keeps the scalar
  `predict(features)` seam (the agent-layer contract), where `features` is the
  *flattened DoMINO surface input*. `fit` consumes the loader's `Sample` stream
  for the split/ids/targets/taint; the surface meshes are read by `case_id` from
  the DVC-pulled `cases_root`. A mesh-native protocol (Option 3) is deferred until
  a second geometry model (Stage 10) reveals the right shape.
- **Predictor-Corrector recipe:** `train_domino` runs the no-PC baseline (timed)
  then the PhysicsNeMo 25.08 PC fine-tuning (timed); the observed speedup factor
  + per-phase seconds are logged (`pc_speedup_factor`, `baseline_seconds`,
  `pc_seconds`). The canonical comparison is time-to-target-RMSE; the ratio is the
  coarse end-to-end proxy.
- **Certificate gate:** the smoke→validated upgrade is gated SOLELY on held-out
  **Cd MAE p95 < 5%** vs held-out DrivAerML
  (`aero.surrogates.domino.certificate.meets_validated_gate`, strict `<`). The
  only path to `cert_status="validated"` is `DominoSurrogate.promote_to_validated()`;
  the model's `_build_certificate` always returns `"smoke"`. No tolerance is ever
  relaxed to force the upgrade. Expiry stays the Stage-08 default (6 months OR
  DrivAerML DVC-hash change).
- **Surrogate validation vs solver V&V (de-conflation):** DoMINO's `"validated"`
  cert is *surrogate validation* against held-out DrivAerML data (Invariant 9). It
  does **NOT** require a green NASA-TMR solver dashboard (Invariant 5) — those
  validate the physics *solvers*, a separate contract. The `"production"` cert
  tier (Stage-14 agent-callable) is what stays gated on the green dashboard + the
  Stage-12 UQ envelope. The falsifiable evidence is the `surrogate_vv` artifact
  (`aero/vv/surrogate/compare_surrogate_cfd.py`).

### Consequences

- **Positive:** one surrogate contract platform-wide; a legitimately-validated
  DoMINO without pretending the solver dashboard is green; reproducible NGC pin.
- **Negative:** the scalar `predict` seam carries a flattened surface input
  (documented, slightly unusual); a full DrivAerML DoMINO train likely exceeds the
  $50/mo cost cap (operator-approved per-run budget required — Invariant 8).
- **Followup:** confirm the `nvidia-physicsnemo` pip pin at first build; Stage 10
  reuses the `surrogate_vv` module + may trigger the mesh-native protocol.

## Cost

A multi-day H100 baseline + the short PC fine-tuning exceeds the $50/month CI cap;
this is an operator-approved **per-run** budget (the brief: "Production-tier or
large training runs are operator-approved per-run"). The DrivAerML subset size
bounds the spend; `aero cost show` reconciles the actual.

## Amendment — first-build version confirmation (Phase 2, 2026-06-02)

The open decision "confirm the `nvidia-physicsnemo` pip pin at first build" is now
closed. Probing the pinned `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08` base on
aero-build reports:

| Component | Version in the 25.08 base |
|---|---|
| `physicsnemo` | **1.2.0** (the proposed `==1.1.0` was wrong) |
| `torch` | 2.8.0a0+5228986c39.nv25.06 |
| `torch_geometric` | 2.6.1 (satisfies `>=2.6`) |
| `warp` | 1.8.1 (satisfies `warp-lang>=1.4`) |

Actions taken (Hard Rule 8 — PIN HEAVY DEPS):
- `pyproject.toml[physicsnemo-cu12]` pin bumped `nvidia-physicsnemo[cu12]==1.1.0`
  → `==1.2.0` to match the container.
- `containers/physicsnemo.def`: the `%post` `pip install torch-geometric warp-lang`
  was **removed** — both are already in the base, and the unprivileged aero-build
  LXC blocks `%post` network sockets (the SU2/jax-fluids two-step reason), so the
  pip layer would have failed. The SIF is now a clean apptainer-direct build from
  the NGC `Bootstrap: docker` image; `%test` imports physicsnemo/torch/pyg/warp and
  fails the build loud if any is missing. No buildah two-step was needed.

## Links

- Stage prompt: `STAGE-09-domino-baseline-surrogate.md` (operator-pasted)
- Related ADR: ADR-008 (surrogate protocol + PyG), ADR-011 (storage), ADR-012 (signing)
- External: NVIDIA PhysicsNeMo 25.08 release notes; Pass 2 §3.2 + §11.3; Pass 3 §9.1
