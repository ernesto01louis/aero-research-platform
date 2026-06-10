# STAGE-10: Surrogate Ensemble & Mixture-of-Experts

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"ML layer" and Pass 2 §3.2–3.4 (neural operators for
geometry-aware surrogates) and §11.2 (MoE for CFD):

- Three additional production surrogates trained on the same DrivAerML subset
  used in Stage 09, each conforming to the `Surrogate` protocol with its own
  `CertificateOfValidity`:
  - **Transolver** (linear-attention neural operator, geometry-aware)
  - **FIGConvNet** (Factorized Implicit Global Convolution Network)
  - **X-MeshGraphNet** (scalable mesh-aware GNN)
- A Mixture-of-Experts gating network that routes queries to the best surrogate
  per geometry/regime.
- A cross-surrogate comparison framework that ranks the four models (DoMINO from
  Stage 09 plus the three new ones) on the held-out test set.
- All four surrogates exposed through one unified `aero.surrogates.predict(case)`
  entry that auto-selects via the MoE gate.

## ROLE

You are widening the surrogate fleet from one (DoMINO) to four, and adding the
gating logic that makes the ensemble more than the sum of its parts. The
infrastructure from Stages 08–09 is reused as-is; you should not need to refactor
the `Surrogate` protocol — if you do, that is a signal to stop and discuss.

## GOAL

1. Author `aero/surrogates/transolver/`, `aero/surrogates/figconvnet/`,
   `aero/surrogates/xmgn/`. Each wraps PhysicsNeMo's native implementation behind
   the Stage 08 `Surrogate` protocol. Reuse the shared training scaffolding from
   `aero/surrogates/_common/`.
2. Author Hydra training configs for each at `configs/surrogate/{transolver,
   figconvnet, xmgn}/`. Mirror the Stage 09 DoMINO config structure; same
   DrivAerML subset and split seed so results are comparable.
3. Train each model on RunPod. Apply Predictor-Corrector fine-tuning where the
   architecture supports it (Transolver does; check FIGConvNet and X-MGN against
   PhysicsNeMo release notes). Log full four-tuple plus surrogate tags.
4. Generate a `CertificateOfValidity` for each — same envelope structure as
   DoMINO so they're comparable.
5. Author `aero/surrogates/moe/`:
   - `gate.py` — gating network that takes geometry features and predicts which
     expert (DoMINO / Transolver / FIGConvNet / X-MGN) to route to. Train on the
     same held-out set, with per-expert error as the gating loss.
   - `ensemble.py` — runtime that loads all four experts, queries the gate, and
     returns the routed prediction plus a per-expert second-opinion when the gate
     is uncertain (entropy > threshold).
   - `certificate.py` — issues a `CertificateOfValidity` for the ensemble as a
     whole, combining the four envelopes (intersection of supports).
6. Add `aero[surrogate-ensemble]` extras (the same PhysicsNeMo + PyG stack as
   `aero[surrogate-domino]`; consolidate the duplicate pins into a shared base
   extras group).
7. Author the cross-surrogate ranking script `aero/vv/surrogate/rank.py`:
   - For each surrogate (and the MoE), compute per-metric RMSE, MAE, 95th-
     percentile error on the held-out set
   - Produce a ranked table in markdown + JSON; commit as `docs/vv/surrogate-
     ranking-YYYY-MM-DD.md`
8. Author `aero.surrogates.predict(case)` as the unified entry: defaults to the
   MoE gate; allows `surrogate="domino"` override for direct access.
9. Extend the `surrogate-inference-smoke` weekly CI job to test all four
   surrogates plus the MoE gate.
10. Author ADR-010 documenting:
    - Why all four (rather than picking one): diversity helps the gate, and the
      ensemble covers DoMINO's known weaknesses (Pass 2 §3.2)
    - The MoE gate's training procedure and the entropy threshold
    - Cumulative training $-cost vs the Stage 09 budget
    - The certificate-intersection logic for the ensemble
11. Tag `v0.0.10`.

## WHY

A single surrogate has a single failure mode. Pass 2 §3.2 documents that DoMINO
excels on geometry-conditioned surface fields but is weak on far-field volume
prediction; Transolver is the inverse; FIGConvNet handles different scales;
X-MGN scales to larger meshes. The MoE gate is how the platform exploits this:
the agent layer (Stage 14) calls `predict()` and gets the right model
automatically, with the certificate-intersection guaranteeing the ensemble
never claims more than the weakest member can support.

## HOW

- Reuse the Stage 09 RunPod training pattern. With three models to train, parallelize:
  launch three pods simultaneously if cost cap allows; otherwise serial.
- Train the MoE gate AFTER all four experts are trained and have certificates.
  The gate's training set is "expert i's error on case j" — a small supervised
  problem that runs in minutes on CPU.
- Per-expert second-opinion threshold: gate entropy above 0.5 (tunable) triggers
  the ensemble to also run a fallback expert and surface the discrepancy.
- DO NOT refactor `Surrogate` for the MoE — the ensemble itself implements
  `Surrogate`, recursively.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-10-surrogate-ensemble-and-moe.md` (this file)
- `docs/handoffs/STAGE-09-*-DONE-*.md`
- ADR-008, ADR-009
- Pass 2 §3.2–3.4 and §11.2

## GUARDRAILS — DO NOT

1. Do NOT change the DrivAerML train/val/test split from Stage 09. Cross-model
   comparison requires identical inputs.
2. Do NOT skip any of the three certificates. The MoE certificate is the
   intersection of the four expert certificates; missing one breaks the math.
3. Do NOT let the gate route to an expert whose certificate has expired.
4. Do NOT exceed the cumulative cost cap. Propose the budget before training.
5. Do NOT publish results from the MoE with experts of different DrivAerML
   versions; the DVC hash must match across all four.

## DELIVERABLES

- [ ] All three new surrogate adapters present, each implementing `Surrogate`
- [ ] All three trained on RunPod with full provenance tuples
- [ ] All three certificates issued and validated
- [ ] MoE gate trained; `aero/surrogates/moe/` complete
- [ ] Cross-surrogate ranking report committed
- [ ] `aero.surrogates.predict(case)` works and routes correctly via MoE
- [ ] `surrogate-inference-smoke` covers all four + MoE
- [ ] ADR-010 committed
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.10`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- Total training budget across the three models
- The MoE gate's entropy threshold (default 0.5)
- Parallel-pod launches (cost concentrated)

## POST-STAGE HANDOFF

Required emphases:

- **Ranking table**: per-model + MoE error metrics, paste the markdown table.
- **MoE routing distribution**: which expert wins which fraction of cases.
- **Certificate intersection**: the resulting envelope and what got narrowed.
- **Open items for Stage 11**: preCICE coupling shouldn't touch the surrogate
  layer, but flag any cross-cutting concerns.
- **Open items for Stage 14**: the agent's MCP tool surface — one tool per
  expert plus one for the MoE, or a single tool that defaults to MoE? Sketch
  both.
- **Gotchas**: training-stability differences between architectures, memory
  footprint of running four models simultaneously for the MoE.
