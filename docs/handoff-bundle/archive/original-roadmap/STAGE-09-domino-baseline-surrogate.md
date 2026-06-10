# STAGE-09: DoMINO Baseline Surrogate (PhysicsNeMo)

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"ML layer" and Pass 2 §3.2 + §11.3:

- NVIDIA PhysicsNeMo deployed as a containerized environment, pinned to a
  specific tag (e.g., `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08` or current
  stable per release notes).
- DoMINO surrogate trained on a DrivAerML subset, full four-tuple provenance,
  CertificateOfValidity issued.
- Predictor-Corrector fine-tuning recipe applied (per Pass 2 §11.3: "10x faster
  end to end training recipe for DoMINO").
- The Stage 07 RunPod executor is exercised for multi-day training; verify
  fault tolerance and cost tracking.
- Cross-validation against DrivAerML's hold-out set within Pass-2 SOTA-published
  accuracy (target: RMSE within 5% of CFD ground truth on Cd, with explicit UQ).

## ROLE

You are training the platform's first production-grade ML surrogate. Everything
about this run is publishable: the four-tuple traces every input, the
certificate documents every claim, the predictor-corrector recipe matches
NVIDIA's published 10x-speedup pattern.

## GOAL

1. Author `containers/physicsnemo.def` — Apptainer SIF wrapping
   `nvcr.io/nvidia/physicsnemo/physicsnemo:<tag>`. Pin the tag explicitly. Include
   PyG (per ADR-008), Warp-Lang, the RAPIDS suite as needed for DoMINO's data
   loaders. Build, sign, append SHA.
2. Author `aero/surrogates/domino/`:
   - `model.py` — wraps PhysicsNeMo's DoMINO implementation behind the
     `Surrogate` protocol from Stage 08
   - `training.py` — Hydra-configurable training script with the Predictor-
     Corrector recipe
   - `certificate.py` — generates the `CertificateOfValidity` post-training,
     using DrivAerML's hold-out set as the empirical envelope
3. Add `aero[surrogate-domino]` extras: `nvidia-physicsnemo[cu12]` (or cu13
   matching Stage 02 inventory), pinned PyG, pinned Warp-Lang.
4. Author the training Hydra config under `configs/surrogate/domino/`:
   - Base hparams from PhysicsNeMo's reference example
   - DrivAerML subset selection: which variants, which fraction for train/val/
     test, deterministic split seed logged
5. Run the baseline training on RunPod (multi-day; use `tmux` long-running
   pattern + RunPod's persistent volume). Monitor cost; log progress to MLflow.
6. After baseline, run the Predictor-Corrector fine-tuning recipe per the
   PhysicsNeMo 25.08 release docs:
   - Y_finetuned = Y_predictor + Y_corrector
   - Document the speedup factor observed (vs the no-PC baseline) for the ADR
7. Generate the `CertificateOfValidity`:
   - Training distribution: which DrivAerML variants
   - Held-out test error: RMSE on Cd, Cl, Cm; quantile errors (median, 95th,
     max); surface field RMSE
   - Applicability envelope: Re range, geometry topology (DrivAer notchback,
     not general sedan)
   - Expiry: 6 months or DrivAerML hash change
8. Run a full V&V cross-check: predict on a few hand-picked DrivAerML variants;
   compare against held-out CFD; verify the certificate's claimed envelope is
   not exceeded. Log a `surrogate_vv` artifact in MLflow.
9. Author `aero/vv/surrogate/`:
   - `compare_surrogate_cfd.py` — given a surrogate handle and a case set,
     produces a comparison report against the CFD reference
   - Used here for DoMINO; reused in Stage 10 for the ensemble
10. Update `vv-scale-resolving.yml` to include a `surrogate-inference-smoke` job
    that loads the trained DoMINO checkpoint and runs prediction on one case
    weekly (catches model degradation, file format breakage, etc.).
11. Author ADR-009 documenting:
    - PhysicsNeMo container pin (rationale and update procedure)
    - DoMINO baseline hparams and the rationale for the train/val/test split
    - Observed Predictor-Corrector speedup
    - The certificate's specific envelope and the threshold for re-training
    - Cost: total $ for the training run; comparison vs Pass 1 architecture's
      $50/month CI cap
12. Update CLAUDE.md with the new `aero[surrogate-domino]` extras and the
    PhysicsNeMo container pin.
13. Tag `v0.0.9`.

## WHY

DoMINO is the platform's flagship surrogate (Pass 2 §3.2 confirms it as the
NVIDIA-recommended production starting point with the 10x training speedup via
Predictor-Corrector). Getting it right — and certified — establishes the
template that Stage 10's three additional surrogates will follow.

The certificate is what makes the surrogate composable with the agent layer
(Stage 14). Without it, the agent has no principled way to decide "can I trust
this surrogate for this query?"

The Predictor-Corrector recipe (released in PhysicsNeMo 25.08) is the current
SOTA for DoMINO training. Skipping it costs ~10x compute time, which Stage 10
needs for the ensemble.

The full V&V cross-check is what separates "I trained a model" from "I have a
verified surrogate." Both numbers (training metric, V&V comparison) are in
the certificate.

## HOW

- PhysicsNeMo container: NVIDIA's NGC container is the recommended path
  (Pass 3 §9.1). Pull via `apptainer pull docker://nvcr.io/nvidia/physicsnemo/
  physicsnemo:<tag>`. The pull is large (~20 GB) and slow; do it once on the
  build LXC and the RunPod pod separately.
- Training run: H100 PCIe or SXM. Estimate ~24-72 hours for the baseline on a
  reasonable DrivAerML subset, then ~4-8 hours for the Predictor-Corrector
  fine-tuning. Budget accordingly; check against the cost cap.
- Use RunPod's persistent storage feature to avoid re-downloading the dataset
  per training restart. Mount the DVC-managed dataset directory into the pod.
- For MLflow logging: the model artifact can be large (>1 GB). Use MLflow's
  remote artifact storage (MinIO) directly; don't try to fit the model into the
  Postgres backend.
- The DGL→PyG migration is current upstream; this is the first stage that
  exercises it in earnest. Watch for API drift — patch in `aero/surrogates/
  domino/` if upstream changes break the example code.
- `--shm-size=1g` is mandatory in the container run command for PhysicsNeMo
  training (it uses shared memory for the data loaders). Document this in the
  container `run.sh`.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-09-domino-baseline-surrogate.md` (this file)
- `docs/handoffs/STAGE-08-*-DONE-*.md`
- ADR-008 (Surrogate protocol, certificate framework, PyG choice)
- Pass 1 §"ML / surrogate / autonomous layer" (subsection on PhysicsNeMo)
- Pass 2 §3.2 (geometry-aware models / DoMINO) and §11.3
- PhysicsNeMo release notes for the chosen tag

## GUARDRAILS — DO NOT

1. Do NOT publish or share the surrogate without a current, non-expired
   certificate. Even internal use within the agent layer (Stage 14) checks the
   certificate.
2. Do NOT exceed the operator's cost cap for this stage. Propose the budget
   first, run within it, log the actuals.
3. Do NOT use `latest` for the PhysicsNeMo container. Pin a specific tag, with
   the rationale in ADR-009.
4. Do NOT mix DrivAerML with DrivAerNet++ in the training set without explicit
   `acknowledge_noncommercial=True` plumbed through (DrivAerNet++ is CC-BY-NC).
5. Do NOT skip the `surrogate_vv` artifact. The compare-against-CFD report is
   what makes the certificate's claims falsifiable.
6. Do NOT commit large model checkpoints to git. They live in MLflow + MinIO.
7. Do NOT bypass the Stage 08 `Surrogate` protocol. DoMINO wraps PhysicsNeMo;
   it does not bypass the platform layer.

## DELIVERABLES

- [ ] PhysicsNeMo SIF pinned and built; SHA in SHA256SUMS
- [ ] `pip install -e .[surrogate-domino,dev]` works
- [ ] DoMINO baseline trains successfully on RunPod with full four-tuple +
      surrogate-specific tags
- [ ] Predictor-Corrector fine-tuning applied; observed speedup logged
- [ ] Held-out test RMSE within target (Cd within 5% of CFD ground truth)
- [ ] `CertificateOfValidity` generated and committed (artifact, not the model
      weights — pointer to MLflow)
- [ ] `aero vv surrogate domino --baseline` produces a passing comparison report
- [ ] `surrogate-inference-smoke` weekly CI job active
- [ ] ADR-009 committed
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.9`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- The PhysicsNeMo container tag pin (operator may wish to read the release
  notes first)
- Total training budget (propose $-cost up front; e.g., "estimated $XXX for
  baseline + PC fine-tuning at current RunPod H100 PCIe price")
- The DrivAerML subset selection (which variants, which split)
- The certificate's expiry default if different from Stage 08's 6 months

## POST-STAGE HANDOFF

Required emphases:

- **Training run telemetry**: total wall-clock, GPU-hours, $-cost, achieved
  RMSE.
- **Predictor-Corrector observed speedup**: empirical vs the 10x NVIDIA
  reference; explain any gap.
- **The certificate** — paste its key fields into the handoff for posterity.
- **V&V cross-check report**: link to the MLflow artifact and summarize the
  numbers.
- **Open items for Stage 10**: Transolver/FIGConvNet/X-MGN will share the data
  loader + provenance helper; flag any reusable code paths that should be
  promoted to `aero/surrogates/_common/`.
- **Open items for Stage 14**: the agent's MCP tool for DoMINO must check the
  certificate before invoking the model; sketch the tool's signature.
- **Gotchas**: DGL→PyG migration warts, PhysicsNeMo API differences from older
  Modulus tutorials, shared-memory tuning, RunPod persistent storage quirks.
