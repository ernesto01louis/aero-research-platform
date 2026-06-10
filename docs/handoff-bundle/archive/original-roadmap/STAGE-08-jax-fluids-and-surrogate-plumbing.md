# STAGE-08: JAX-Fluids + Surrogate Plumbing

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Solver fleet" and Pass 2 §11.7:

- JAX-Fluids 2.0 adapter as `aero[jax-fluids]` extras. The first differentiable
  CFD solver in the platform.
- A surrogate base layer at `aero/surrogates/_common/` that codifies the
  certificate-of-validity framework, training-data loaders for AhmedML and
  DrivAerML, and the provenance hook for ML runs.
- DVC-tracked, license-checked download of AhmedML, WindsorML, DrivAerML
  (CC-BY-SA — fine to co-mingle) under `data/datasets/`.
- DrivAerNet++ flagged as CC-BY-NC and *quarantined* (downloadable, not pulled
  into training corpora that may later be commercial).
- Three small "smoke" surrogate models — one FNO, one MeshGraphNet, one MLP
  baseline — trained on a subset of AhmedML to validate the plumbing end-to-end.
  No production accuracy required; just the pipeline.

## ROLE

You are adding two things in parallel: the differentiable solver and the
surrogate scaffolding. The first is the bridge to learned closures and end-to-
end gradient-based shape optimization. The second is the infrastructure that
Stages 09–10 will load real surrogates onto.

You will NOT train production-grade surrogates in this stage. Stage 09
(DoMINO) and Stage 10 (Transolver/FIGConvNet/MoE) do that. This stage proves
the pipes are clean.

## GOAL

1. Author `containers/jax-fluids.def` — Apptainer SIF with JAX + CUDA, JAX-Fluids
   2.0 from upstream (GPL-3), pinned to a specific release. Note the license
   downstream implications in the ADR.
2. Build and sign the SIF; append SHA.
3. Author `aero/adapters/jax_fluids/`:
   - Implements the `Solver` protocol
   - Exposes a `differentiable_run(case, jax_grad_target)` method on top of the
     base `run` — this is the differentiability hook that Stage 13+ will use
   - Native JAX I/O for case state; export to xarray for the base protocol
4. Add `aero[jax-fluids]` extras.
5. Run a JAX-Fluids smoke case: 1D shock tube or 2D forced-isotropic-turbulence
   slice, just to validate the pipeline. Log the four-tuple.
6. Author the surrogate base layer at `aero/surrogates/_common/`:
   - `base.py` — `Surrogate` protocol: `fit(data)`, `predict(geometry)`,
     `certificate()` returning a typed `CertificateOfValidity` with training
     distribution, held-out test error, applicability envelope (Re range, Mach
     range, geometry class, etc.)
   - `certificate.py` — `CertificateOfValidity` pydantic strict; auto-quarantine
     logic (if cert is missing or expired, surrogate refuses to predict and the
     agent toolchain cannot call it)
   - `provenance.py` — the centralized helper that logs the four-tuple plus
     surrogate-specific tags (training dataset hash, model architecture, hparam
     hash) to MLflow
7. Author `aero/surrogates/_common/loaders/`:
   - `ahmedml.py` — downloads (via DVC pull from public CC-BY-SA source),
     validates checksums, exposes `AhmedMLDataset` (torch + jax loaders)
   - `drivaerml.py` — same shape, for DrivAerML
   - `windsorml.py` — same shape
   - `drivaernet_plus_plus.py` — DOWNLOADS BUT MARKS QUARANTINED (returns a
     dataset object whose `__getitem__` raises unless explicit
     `acknowledge_noncommercial=True` flag is set; logs the acknowledgment to
     MLflow as a tag)
8. Author three baseline surrogate stubs to validate the plumbing:
   - `aero/surrogates/baselines/mlp_baseline.py` — a tiny MLP on Cd prediction
     from geometry features (no production claim, just validates plumbing)
   - `aero/surrogates/baselines/fno_smoke.py` — minimal FNO on a 2D field
     (validates the operator-learning path)
   - `aero/surrogates/baselines/mgn_smoke.py` — minimal MeshGraphNet on a small
     mesh (validates the GNN path)
   Each runs in <10 minutes on a single H100; each produces a `CertificateOfValidity`
   with explicit "smoke / not for publication" status.
9. Add `aero[surrogate-smoke]` extras: torch, jax, dgl OR pyg (pick pyg per
   Pass 1's PhysicsNeMo migration note), einops, the standard ML stack.
10. Run the three baselines end-to-end on RunPod via the Stage-07 executor.
    Verify all four tags + the surrogate-specific tags are logged.
11. Author `tests/stage_08/`:
    - `test_jax_fluids_smoke.py` — runs the shock tube, asserts a scalar metric
      within tolerance
    - `test_surrogate_certificate.py` — asserts a surrogate without a current
      certificate raises on predict
    - `test_drivaernet_quarantine.py` — asserts DrivAerNet++ raises without the
      explicit acknowledgment flag
    - `test_baselines_run.py` — runs all three baselines on a CPU subset of the
      data
12. Author ADR-008 documenting:
    - JAX-Fluids GPL-3 license posture and downstream implications
    - The `Surrogate` protocol and `CertificateOfValidity` contract
    - The DrivAerNet++ quarantine policy
    - PyG vs DGL choice (per Pass 1: PyG, given PhysicsNeMo migration)
13. Update CLAUDE.md with the certificate-of-validity rule: "no surrogate may
    be invoked by the agent layer without a current, non-expired, in-envelope
    certificate."
14. Tag `v0.0.8`.

## WHY

JAX-Fluids is the differentiable solver that makes learned closures, learned
numerics, and end-to-end gradient-based shape optimization tractable (Pass 2
§11.7). It also tests the `Solver` protocol against a fundamentally different
codebase architecture (functional/pure JAX vs imperative C++/Fortran).

The surrogate base layer is the contract between the ML stages (09–10) and the
agent layer (Stage 14). Without the `CertificateOfValidity` framework codified
*before* the production surrogates land, every surrogate would become a
research artifact rather than a deployable component. The agent must refuse to
call uncertified models — that's how we keep "the ML augments, never replaces,
validated physics" from being a tagline.

The DrivAerNet++ quarantine is non-negotiable for license hygiene. CC-BY-NC
content cannot land in training corpora that might later be used commercially.
The flag forces explicit acknowledgment per use; the MLflow tag preserves the
audit trail.

## HOW

- JAX-Fluids 2.0 expects specific JAX/jaxlib versions for the CUDA build. Pin
  exactly; check the upstream README for the supported matrix.
- The `Surrogate` protocol is *not* a generic ML model interface. It's
  specifically for "this maps geometry/flow inputs to flow outputs and ships
  with a certificate." Wrappers around PhysicsNeMo's native modules in Stages
  09–10 will conform to this protocol.
- `CertificateOfValidity` fields: training-dataset DVC hash, held-out test
  metrics with quantiles (not just mean), applicability envelope as typed
  constraints, expiry policy (default: 6 months from generation, or until the
  training dataset hash changes).
- DrivAerNet++ quarantine: the simplest pattern is a `non_commercial`-only
  loader that requires `acknowledge_noncommercial=True` and logs an MLflow tag.
  Stage 09 surrogates trained on it are auto-tagged `non_commercial=True`,
  which propagates to any artifacts they produce.
- AhmedML/WindsorML/DrivAerML: large datasets. Use DVC's `dvc import-url` if the
  source is publicly hosted; otherwise mirror to MinIO via a one-time fetch
  script. Document the procedure in `data/datasets/README.md`.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-08-jax-fluids-and-surrogate-plumbing.md` (this file)
- `docs/handoffs/STAGE-07-*-DONE-*.md`
- ADR-006 (Solver protocol), ADR-007 (PyFR/NekRS + cloud-GPU)
- Pass 2 §11 (full ML-CFD section, especially 11.4 PINN dead-ends and 11.7
  differentiable CFD)

## GUARDRAILS — DO NOT

1. Do NOT skip the certificate-of-validity for the smoke baselines. Even the
   trivial MLP must produce a certificate (with status: smoke, not for
   publication).
2. Do NOT let DrivAerNet++ flow into the same `Dataset` collection as the CC-BY-
   SA sets. The license boundary must be structural.
3. Do NOT install Torch and JAX in the same environment unless the version
   matrix supports it. Prefer separate Apptainer SIFs for JAX-Fluids (JAX-only)
   and surrogates (Torch-only with optional JAX I/O bridges).
4. Do NOT pretend the smoke baselines are publishable. Their certificates say
   "smoke."
5. Do NOT bypass `aero[platform-only]` clean-install — `pip install aero` (no
   extras) must still import without Torch/JAX/PhysicsNeMo.
6. Do NOT skip the DrivAerNet++ acknowledgment flag in the public examples.
   Examples must show the *correct* pattern, including the flag.

## DELIVERABLES

- [ ] JAX-Fluids SIF builds; SHA in SHA256SUMS
- [ ] `pip install -e .[jax-fluids,dev]` works
- [ ] JAX-Fluids shock tube smoke test passes
- [ ] `Surrogate` protocol defined and documented
- [ ] `CertificateOfValidity` enforced by tests
- [ ] DrivAerNet++ quarantine enforced by tests
- [ ] AhmedML, WindsorML, DrivAerML accessible via DVC-tracked loaders
- [ ] Three baseline surrogates train and produce certificates on RunPod
- [ ] All four provenance tags + surrogate-specific tags logged for each
      baseline
- [ ] `pip install -e .` (no extras) still imports cleanly
- [ ] ADR-008 committed
- [ ] CLAUDE.md updated with certificate rule
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.8`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- Downloading the full DrivAerML / DrivAerNet++ to MinIO (size + cost — propose
  storage footprint first)
- The certificate expiry default (6 months proposed)
- Choosing PyG over DGL globally (propagates to Stages 09–10)
- The JAX-Fluids version pin

## POST-STAGE HANDOFF

Required emphases:

- **The `Surrogate` protocol and `CertificateOfValidity` final shape** — link,
  example certificate.
- **Dataset footprint**: total GB of CC-BY-SA datasets ingested; storage
  breakdown by bucket.
- **Quarantine pattern in action**: show one example of the DrivAerNet++ flag
  usage.
- **Open items for Stage 09**: DoMINO is the first production surrogate; it
  will train on DrivAerML. List the certificate's expected fields and the
  acceptance criteria.
- **Open items for Stage 10**: Transolver/FIGConvNet/MoE will reuse the
  protocol; flag any seams.
- **Gotchas**: JAX/CUDA version matrix, PyG vs DGL migration warts, MLflow
  tagging of large model artifacts.
