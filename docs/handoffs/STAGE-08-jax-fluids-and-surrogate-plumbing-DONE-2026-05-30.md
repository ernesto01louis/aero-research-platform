---
stage: 08
stage_name: "Stage 08 — JAX-Fluids 2.x Differentiable Solver; Surrogate Plumbing"
status: partial
date_started: 2026-05-30
date_completed: 2026-05-30
session_duration_hours: 4.5
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-4-7
git_sha_start: "d6318fde2e5869159db5628fe3795a7e550978ff"
git_sha_end: "PENDING_PR_MERGE"
stage_tag: v0.0.8
next_stage: 09
next_stage_name: "Stage 09 — NVIDIA PhysicsNeMo DoMINO production surrogate"
---

# Stage 08 — JAX-Fluids 2.x + Surrogate Plumbing — DONE (partial) 2026-05-30

> Auto-loaded by the Stage 09 session as "BEFORE YOU START — READ".
>
> **The `JaxFluidsSolver` (the platform's fifth and first-differentiable
> solver), the `Surrogate` protocol + `CertificateOfValidity` framework,
> the `Sample`/`TaintedSample` discriminated-union taint propagation, the
> three smoke baselines (MLP / FNO / MeshGraphNet on PyG), the
> `aero surrogate train` CLI subcommand, the four CC-licensed dataset
> loaders + their reference docs + the DVC ingest stages, the
> `non-commercial-fence.yml` CI workflow, and ADR-008 (six bundled
> decisions including the JAX-Fluids licence-posture correction from
> assumed GPL-3 to actual MIT) all land in-session. Two operator
> follow-ups: the JAX-Fluids and surrogate-smoke SIF builds (no buildah
> on the dev host; build script ready, SHA lands at PR merge time),
> and any actual dataset bytes pulling to TrueNAS (capacity-gated; the
> Stage-07 NekRS / first-H100 precedent).** Status is `partial` for the
> same reason Stages 05 / 06 / 07 were: artifacts that need the cluster
> are queued for the operator.
>
> **Host-side verification this session:** 191 unit/integration tests
> green (171 Stage-07 baseline + 20 new Stage-08); ruff / mypy clean
> against the new packages; PLATFORM-NOT-HUB invariant preserved (no
> torch / jax / jaxlib / jaxfluids / mlflow in `sys.modules` after a
> plain `import aero`); `aero --help` shows the `surrogate train`
> subcommand; the discriminated-union `Sample` / `TaintedSample` flow
> exercises end-to-end with the fake Surrogate; the dual time + data
> cert gates fire correctly; the DrivAerNet++ constructor guard +
> tainted-sample propagation work as designed.

## 1. Deliverables status

| # | Deliverable (verbatim from stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `containers/jax-fluids.def` + SIF build | ⚠️ | Dockerfile + `.def` + `scripts/build_jax_fluids_sif.sh` ready; SHA lands at PR-merge after the operator runs the build on aero-build (Stage-07 NekRS precedent). MIT licence (not GPL-3 as stage prompt assumed; ADR-008 §D2). |
| 2 | `aero/adapters/jax_fluids/` (Solver + differentiable_run) | ✅ | `JaxFluidsSolver(Solver)` w/ `JaxFluidsShockTubeSpec` + `JaxFluidsMeshFileSpec`; case_writer for HLLC+WENO5+RK3 Sod tube; embedded run_case.py driver; `differentiable_run(case, jax_grad_target) → JaxGradientResult` additive method (Solver ABC NOT amended — ADR-008 §D3). |
| 3 | `aero[jax-fluids]` extra | ✅ | h5py + jax[cuda12] 0.4.34 + jaxlib 0.4.34 + jaxfluids from git+url@JAX-Fluids-v0.2.1. JAX-Fluids is NOT on PyPI. |
| 4 | JAX-Fluids smoke case (shock tube) | ⚠️ | `tests/stage_08/test_jax_fluids_smoke.py` ready (asserts shock position ±2% vs. analytic Riemann solution); skips until SIF ships. |
| 5 | `aero/surrogates/_common/` (Surrogate / CertificateOfValidity / provenance) | ✅ | `base.py`, `certificate.py`, `provenance.py`, `_dataset_pick.py`; strict pydantic, frozen, extra="forbid"; predict-before-fit guard + dual time + data gates pinned by tests. |
| 6 | `aero/surrogates/_common/loaders/{ahmedml,windsorml,drivaerml,non_commercial/drivaernet_plus_plus}.py` | ✅ | Four loaders; CC-BY-SA trio yields `Sample`; DrivAerNet++ subpackage yields `TaintedSample` with constructor guard + MLflow log helper. |
| 7 | DrivAerNet++ quarantine pattern | ✅ | Three layers: structural separator (`non_commercial/` subpackage + CI fence), constructor guard (`LicenseAcknowledgmentRequired` without `acknowledge_noncommercial=True`), tainted-sample union (auto-flips `Surrogate._non_commercial`). |
| 8 | Three baselines (MLP / FNO / MeshGraphNet) | ✅ | `MLPBaseline`, `FNOSmoke`, `MGNSmoke` (PyG); each produces `CertificateOfValidity(cert_status="smoke")`; lazy-import torch/pyg. |
| 9 | `aero[surrogate-smoke]` extra | ✅ | torch>=2.5, torch-geometric>=2.6, einops>=0.8, mlflow>=2.20, numpy>=1.26. |
| 10 | Three baselines train on RunPod with eight-tag MLflow + cert JSON | ⚠️ | `aero surrogate train --executor local-ssh` path lands; runpod-executor branch refuses (Stage-09 follow-up — needs the on-pod training script). Eight tags + cert JSON artifact wired end-to-end. |
| 11 | `tests/stage_08/` test suite | ✅ | 24 tests; 20 fast (green host-side); 4 slow (cluster + extras). `test_surrogate_certificate.py`, `test_drivaernet_quarantine.py`, `test_jax_fluids_adapter.py`, `test_jax_fluids_smoke.py`, `test_baselines_run.py`. |
| 12 | ADR-008 | ✅ | Six decisions: JAX-Fluids version pin (v0.2.1), licence posture (MIT not GPL-3), differentiability seam (additive on adapter only), DrivAerNet++ quarantine (three layers), cert expiry policy (180 d), GNN library (PyG). |
| 13 | CLAUDE.md updated with certificate rule | ✅ | "TBD in Stage 08" line replaced with concrete pointer; new Stage-08 entry appended. |
| 14 | Tag `v0.0.8` | ⚠️ | Applied at PR merge per Stage 02-07 precedent. |

## 2. Decisions made

- **JAX-Fluids licence posture: MIT, not GPL-3** (operator-prompt-correcting
  discovery 2026-05-30; ADR-008 §D2). The stage prompt and project brief
  assumed JAX-Fluids was GPL-3 and flagged "downstream implications";
  upstream `tumaer/JAXFLUIDS` is **MIT-licensed** (`setup.py
  license="MIT"`; the upstream LICENSE file confirms). The platform
  therefore incurs no copyleft obligation from this dependency, and
  Stage-13's adjoint-optimisation layer faces strictly fewer constraints
  than the brief predicted. *Rejected:* preserving the GPL-3 framing for
  consistency with the brief would mislead future readers and shape
  Stage-13 decisions against a constraint that does not exist.

- **JAX-Fluids version pin: `JAX-Fluids-v0.2.1`** (operator 2026-05-30
  via AskUserQuestion; ADR-008 §D1). Upstream tags the second-generation
  rewrite as `JAX-Fluids-v0.2.x` even though the academic literature
  calls it "2.0"; the latest 2.x-generation tag at session start is
  `v0.2.1`. Documented prominently because the literature-vs-tag
  mismatch will trip every future reader. *Rejected:* `v0.2.0` (one tag
  back, no improvement) and pinning to a commit SHA (loses the readable
  version string in MLflow tags and ADR prose).

- **Differentiability seam: additive method on `JaxFluidsSolver` only**
  (ADR-008 §D3). `JaxFluidsSolver.run(case_dir, executor) →
  ResultHandle` goes through the SIF executor for parity with every
  other adapter — same four-fold provenance, same cost-cap-gated cloud
  execution. `differentiable_run(case, jax_grad_target) →
  JaxGradientResult` is an additive in-process method, bypasses the
  executor AND the cost-cap by design, and exposes JAX gradients. The
  `Solver` ABC is NOT amended this stage. *Rejected:* promoting
  `differentiable_run` into the ABC would force four of five adapters
  to `raise NotImplementedError` (LSP-violating in spirit; lies to V&V
  harness authors); ADR-006/007 spent the protocol-promotion budget on
  patterns repeated across multiple adapters, and promoting at one data
  point (the only differentiable solver) would be speculative. A
  `JaxExecutor` + ABC-level promotion are deferred until a second
  differentiable adapter triangulates the design (Stage 10 Transolver
  gradients or a Stage-13 `jax-cfd` follow-on).

- **DrivAerNet++ CC-BY-NC quarantine: three-layer defence**
  (ADR-008 §D4). Constructor guard (`LicenseAcknowledgmentRequired`
  raises without explicit acknowledgment), structural separator
  (`aero/surrogates/_common/loaders/non_commercial/` subpackage + the
  new `non-commercial-fence.yml` CI workflow that greps every aero
  import of that subpackage for either `non_commercial=True` or the
  `# non-commercial: justified` pragma), and tainted-sample union
  (`TaintedSample` flips `Surrogate._non_commercial` via
  `Surrogate.ingest`; `set_certificate` overrides any author-supplied
  `non_commercial=False` to True). *Rejected:* loader-level guard
  alone (Option A — too fragile for a peer-review-grade project given
  the legal stakes); a full import-hook taint system (Option C — too
  heavy for one stage; hard to audit; premature without a second
  CC-BY-NC dataset to triangulate).

- **Cert expiry policy: 6 months OR training-dataset DVC hash change,
  whichever first** (operator 2026-05-30; ADR-008 §D5). Forces
  twice-yearly revalidation even on a frozen dataset; the hash gate
  catches dataset drift between expiries. *Rejected:* 12-month
  (stretches the trust window during solver/dataset churn);
  hash-only (risks "permanent" surrogates whose physical envelope
  drifts silently); 3-month (burns CI/cluster time on revalidation).

- **Global GNN library: PyG / torch-geometric** (operator 2026-05-30;
  ADR-008 §D6). Aligned with PhysicsNeMo's PyG migration
  (X-MeshGraphNet, FIGConvNet); larger maintainer base; cleaner GPU
  memory story under recent torch. Propagates to Stages 09 + 10.
  *Rejected:* DGL (misaligned with PhysicsNeMo; would force a bridge
  layer at Stage 09 + a re-architecting at Stage 14); defer the choice
  (would leave the MGN baseline reinventing `MessagePassing`).

- **Dataset ingest scope: all four datasets in full, including
  DrivAerNet++** (operator 2026-05-30). Maximum readiness for Stage 09.
  The quarantine boundary lands BEFORE any DrivAerNet++ bytes hit
  storage; the download script refuses to start without
  `AERO_ACKNOWLEDGE_NONCOMMERCIAL=1` and with TrueNAS
  `aero/datasets/` below 1 TB free. *Rejected:* subsets-only (would
  defer the full-data validation to a Stage 08.5), AhmedML-only
  (too narrow), CC-BY-SA-only (delays the quarantine pattern's first
  real exercise to Stage 09 where it would block production training).

## 3. Deviations from the stage plan

- **JAX-Fluids is NOT on PyPI.** The stage prompt and project brief
  implied a normal `pip install jax-fluids==<ver>` resolution. Reality:
  upstream maintains no PyPI release; installation is
  `pip install "jaxfluids @ git+https://github.com/tumaer/JAXFLUIDS.git@
  JAX-Fluids-v0.2.1"`. Both the `aero[jax-fluids]` extra and the
  `containers/jax-fluids.Dockerfile` reflect this.

- **JAX-Fluids "2.0" is `v0.2.x` on GitHub.** Documented prominently in
  ADR-008 §D1 and in the CLAUDE.md Stage-08 section.

- **`aero surrogate train --executor runpod` defers the on-pod training
  script to Stage 09.** The CLI branch is plumbed (cost-cap-aware,
  acquires GHCR image, projected-hours flag), but the actual on-pod
  training entrypoint is non-trivial (must orchestrate dataset pull,
  feature extraction, save the cert + state-dict for retrieval). Stage 08
  ships the host-side `--executor local-ssh` path end-to-end (the eight
  MLflow tags + cert JSON artifact are wired). Stage 09's production
  DoMINO training is the right place to land the on-pod script.

- **SIF SHAs land at PR-merge.** Two new SIFs in this stage
  (`jax-fluids.sif`, `surrogate-smoke.sif`), neither built in-session
  (no buildah on the dev host — same constraint Stage 06's SU2 SIF
  build observed). Build scripts ready; SHA lines land at PR merge after
  operator runs the builds on aero-build (Stage-07 NekRS precedent).

- **`differentiable_run` in-process exercising deferred.** The method is
  implemented and unit-tested for its structural placement (it lives on
  the adapter, not the ABC). Actual gradient evaluation requires
  `aero[jax-fluids]` host-side install + the JAX wheel matching the
  driver, which is a Stage-13 prerequisite at the earliest.

## 4. Environment / dependency / schema changes

- `pyproject.toml`:
  - `aero[jax-fluids] = ["h5py>=3.10", "jax[cuda12]==0.4.34",
    "jaxlib==0.4.34", "jaxfluids @ git+https://github.com/tumaer/
    JAXFLUIDS.git@JAX-Fluids-v0.2.1"]`
  - `aero[surrogate-smoke] = ["torch>=2.5", "torch-geometric>=2.6",
    "einops>=0.8", "mlflow>=2.20", "numpy>=1.26"]`
  - Base `pip install aero` (no extras) still imports cleanly without
    torch / jax / jaxfluids / pyg in `sys.modules` (verified
    end-to-end).
- `aero/cli.py`:
  - `_SOLVER_VERSIONS["jax-fluids"] = "JAX-Fluids v0.2.1"`
  - `_SOLVER_SIF["jax-fluids"] = "jax-fluids.sif"`
  - `_SOLVER_EXTRAS_HINT["jax-fluids"] = "jax-fluids,provenance"`
  - `_REQUIRED_MODULES_BY_SOLVER["jax-fluids"] = ("h5py",
    *_PROVENANCE_MODULES)`
  - `_build_solver` `"jax-fluids"` branch constructs `JaxFluidsSolver`
  - Stage-tag string: `solver_name == "jax-fluids" → stage_str = "08"`
  - New `surrogate_app` Typer subcommand registered at `surrogate`
- `aero/adapters/jax_fluids/{__init__, solver, schemas, case_writer}.py`
  — new package; `JaxFluidsSolver(Solver)` + spec discriminated union.
- `aero/surrogates/__init__.py` + `aero/surrogates/_common/{__init__,
  base, certificate, provenance, _dataset_pick}.py` — new modules.
- `aero/surrogates/_common/loaders/{__init__, ahmedml, windsorml,
  drivaerml}.py` + `aero/surrogates/_common/loaders/non_commercial/
  {__init__, drivaernet_plus_plus}.py` — new modules.
- `aero/surrogates/baselines/{__init__, mlp_baseline, fno_smoke,
  mgn_smoke}.py` — new modules.
- `containers/jax-fluids.{Dockerfile,def}` +
  `containers/surrogate-smoke.{Dockerfile,def}` — new; SIF SHAs
  pending operator build.
- `containers/SHA256SUMS` — comment header extended; SHAs pending.
- `scripts/build_jax_fluids_sif.sh` +
  `scripts/build_surrogate_smoke_sif.sh` +
  `scripts/download_{ahmedml,windsorml,drivaerml,
  drivaernet_plus_plus}.sh` — new; all chmod +x.
- `dvc.yaml` — empty `stages: {}` replaced with four `ingest-*` stages.
- `data/datasets/{ahmedml,windsorml,drivaerml,drivaernet_plus_plus}/
  reference.md` — new docs.
- `conf/surrogate/baselines/{mlp_baseline, fno_smoke, mgn_smoke}.yaml`
  — new Hydra-shape configs.
- `tests/stage_08/` (new dir, 5 modules, 24 tests) +
  `tests/conftest.py` (four new fixtures).
- `.github/workflows/non-commercial-fence.yml` — new CI workflow.
- `docs/adrs/ADR-008-jax-fluids-and-surrogate-protocol.md` — new ADR.
- `CONSTITUTION.md` — Invariant 9 added
  (CERTIFICATE-OF-VALIDITY-REQUIRED-FOR-SURROGATE-INVOCATION).
- `CHANGELOG.md` — `## [0.0.8]` section with Added / Changed /
  CONSTITUTION subsections.
- `CLAUDE.md` — Stage-08 entry; certificate rule updated from "TBD".
- `.aero-stage` — `07` → `08`.
- No aero LXC changes. No Postgres schema change. No DVC commits
  in-session (dataset bytes are an operator follow-up).

## 5. CI/CD changes

- `.github/workflows/non-commercial-fence.yml` — **new**. Runs on PR
  and on push to main. Greps `aero/**`, `tests/**`, `scripts/**` for
  imports of `aero.surrogates._common.loaders.non_commercial`; for
  each hit, requires either `non_commercial=True` somewhere in the
  file OR the `# non-commercial: justified` pragma on the import line
  (or the line immediately above). PR fails otherwise.
- The existing required checks (lint, type, test, docs-sync,
  commit-lint, `vv-required`, `import-platform-only`) are unchanged;
  Stage-08 PRs pass them.
- No branch protection changes this stage.

## 6. Gotchas discovered

- **JAX-Fluids' "2.0" is GitHub `v0.2.1`.** The academic literature and
  upstream marketing call this generation "JAX-Fluids 2.0"; the
  `tumaer/JAXFLUIDS` repo tags it `JAX-Fluids-v0.2.x`. The `aero[jax-
  fluids]` extra and ADR-008 §D1 pin to `v0.2.1` explicitly; the
  CHANGELOG and CLAUDE.md flag the mismatch.

- **JAX-Fluids licence is MIT, not GPL-3.** The stage prompt assumed
  GPL-3 and called out "downstream implications". Reality is MIT — no
  copyleft propagation. ADR-008 §D2 records the correction. Stage 13's
  adjoint-optimisation layer has strictly fewer licence constraints
  than the brief implies.

- **JAX-Fluids is NOT on PyPI.** Install is via git+url. The Dockerfile
  pins `jaxfluids @ git+https://github.com/tumaer/JAXFLUIDS.git@
  JAX-Fluids-v0.2.1` directly; `aero[jax-fluids]` follows the same
  shape. Future stages that try to `pip install jaxfluids` from a
  PyPI mirror will fail — they must use the git+url form.

- **JAX-Fluids requires Python ≥ 3.11.** The PyFR / NekRS SIFs use
  Python 3.10 on Ubuntu 22.04; JAX-Fluids' `setup.py` says
  `python_requires=">=3.11"`. The new SIF uses Ubuntu 24.04 (Python
  3.12 native) to avoid the deadsnakes PPA dance.

- **Torch + JAX must NOT be in the same SIF.** Their CUDA wheel
  version matrices conflict; matching memory accounting between
  competing CUDA contexts in the same process is fraught. Two SIFs
  ship: `jax-fluids.sif` (JAX-only) and `surrogate-smoke.sif`
  (Torch + PyG, no JAX). Cross-environment data flows via
  xarray / NumPy / parquet on disk.

- **Pydantic discriminated unions on `Sample | TaintedSample` do not
  narrow under `getattr(s, "kind", None) == "non_commercial"`.**
  Carry-forward of Stage-07 gotcha §6. The `Surrogate.ingest`
  implementation uses `isinstance(sample, TaintedSample)` for the
  narrowing path that mypy strict accepts.

- **`Surrogate.set_certificate()` overrides author-supplied
  `non_commercial=False`.** Subclass implementers might assume their
  `_build_certificate()` return is honored verbatim; it is NOT —
  if `_non_commercial` is True after fit, the base class
  `model_copy(update={"non_commercial": True})` overrides the field.
  This is the third defence layer of the quarantine; documented in
  the base class docstring.

- **MLflow tag values are strings only.** The eight tags
  `SurrogateProvenanceTags.as_mlflow_tags()` returns are all
  `str`-valued; numeric metrics ride as JSON serialised cert artifact
  under `certificates/<name>.json`. Stage 14's agent layer reads the
  artifact (not the tags) when making routing decisions on
  `held_out_metrics`.

- **The `non-commercial-fence.yml` CI fence accepts the pragma on the
  import line OR one line above.** Multi-line imports that put the
  comment on the line above the `from ... import (...)` block are
  accepted; comments three lines away are not. The
  `aero/surrogates/_common/_dataset_pick.py` file uses the pragma on
  the line above the `from aero.surrogates._common.loaders.
  non_commercial.drivaernet_plus_plus import (...)` line.

- **`test_drivaernet_quarantine.py` carries the pragma in its module
  docstring** (line 16: `# non-commercial: justified — quarantine
  tests live here intentionally.`). Without this, the fence CI would
  fail on the test file's import.

- **CUDA 12 wheels for the surrogate-smoke SIF use the official
  PyTorch index (`https://download.pytorch.org/whl/cu124`)** plus
  PyG's own `https://data.pyg.org/whl/torch-2.5.1+cu124.html`
  companion index. Without the second index, `torch-scatter` and
  `torch-sparse` (PyG's CUDA extensions) fall back to slow CPU paths.

- **The `aero surrogate train` runpod path raises by design.** Stage
  09 will land the on-pod training script. Until then, the CLI
  message points to `--executor local-ssh` as the supported smoke
  path.

## 7. Open items for the next stage (and beyond)

**Cluster follow-ups (operator):**

1. **Build the JAX-Fluids SIF.** On the Proxmox host with rootless
   buildah:
   ```bash
   ssh root@proxmox-host
   cd /root/projects/aero-research-platform
   ./scripts/build_jax_fluids_sif.sh
   ```
   Append the printed SHA256 line to `containers/SHA256SUMS`.

2. **Build the surrogate-smoke SIF.** Same pattern:
   ```bash
   ./scripts/build_surrogate_smoke_sif.sh
   ```
   Append the printed SHA256 line.

3. **GHCR mirror both new SIFs** (needed for RunPod cloud runs):
   ```bash
   buildah login ghcr.io
   buildah tag localhost/aero/jax-fluids:JAX-Fluids-v0.2.1 \
                ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1
   buildah push ghcr.io/ernesto01louis/aero-jax-fluids:JAX-Fluids-v0.2.1
   # repeat for surrogate-smoke
   ```
   Append each digest as a comment line to `containers/SHA256SUMS`.

4. **Pull the four datasets.** Capacity-gated; estimate ~1.5 TB
   compressed on MinIO / TrueNAS. Order: AhmedML first (~80 GB,
   exercises the loader end-to-end), then WindsorML (~30 GB), then
   DrivAerML (~600 GB), then DrivAerNet++ (~800 GB):
   ```bash
   ssh root@aero-build
   cd /opt/aero/repo
   ./scripts/download_ahmedml.sh
   ./scripts/download_windsorml.sh
   ./scripts/download_drivaerml.sh
   # DrivAerNet++ ONLY after CI fence + tests green + acknowledgment:
   AERO_ACKNOWLEDGE_NONCOMMERCIAL=1 ./scripts/download_drivaernet_plus_plus.sh
   ```

5. **JAX-Fluids shock-tube smoke** (after SIFs land):
   ```bash
   ssh aero-admin@aero-dev '/opt/aero/.venv/bin/aero run \
       jaxf_shock_tube_1d --solver jax-fluids --executor local-ssh'
   ```
   Asserts shock position within ±2% of analytic Riemann solution.

6. **Run the three baselines on RunPod** (host-side local-ssh first,
   then runpod once Stage 09 lands the on-pod script). Pre-launch
   ladder same as Stage-07 §7: SIFs verified, GHCR push complete,
   Vault key present, ledger initialised, cost estimate surfaced,
   operator types `approved`.

**Stage 06 follow-ups still open:**

- SU2 TMR cluster validation runs through the `xfail(strict=False)`
  tests (Stage-06 §7) — unchanged this stage.

**Stage 07 follow-ups still open (carried forward):**

- The first H100 PyFR run (Stage-07 §7 ladder). Stage 08 added two
  more SIFs that benefit from the same cost-cap ledger.

**Stage 09 (NVIDIA PhysicsNeMo DoMINO):**

- **DoMINO is the first production surrogate.** It trains on
  DrivAerML (CC-BY-SA, no taint). Expected certificate envelope:
  - `cert_status="validated"` (upgrade from "smoke" gated on Cd MAE
    p95 < 5% vs. held-out DrivAerML cases AND a passing V&V dashboard).
  - `model_architecture="domino"`.
  - `applicability_envelope` extended with surface-mesh count bounds
    (DrivAerML cases are 1–2M cells; DoMINO's training distribution
    pins these).
- **PhysicsNeMo container will conform to the same SIF pattern.**
  ADR-008 §D6's PyG choice carries over.
- **The on-pod training script for `aero surrogate train --executor
  runpod`** is a Stage-09 deliverable. It must: pull the DVC dataset,
  parse the surface mesh, run training, save the cert + state-dict
  for retrieval, and emit the eight MLflow tags.

**Stage 10 (Transolver / FIGConvNet / X-MGN / MoE):**

- Reuses the Surrogate protocol verbatim. Seams to bend (if any):
  - Transolver's gradient hook may want to share the
    `differentiable_run` shape. If a second differentiable adapter
    lands here, **the Solver ABC's `differentiable_run` promotion
    becomes paid-for** (ADR-008 §D3 sunset condition).
  - MoE gating will need a typed `RouterDecision` model; the
    `Surrogate.predict` shape is intentionally narrow and may
    benefit from a sibling `predict_with_provenance` that returns
    the routing trace.

**Stage 12 (UQ + V&V):**

- The `CertificateOfValidity.applicability_envelope` may want
  output-space bounds (a surrogate Cd prediction outside the V&V
  envelope's Cd range is a tell). Stage-08 ships input-space bounds
  only; Stage-12's UQ layer is the right place to land output-space
  constraints.

**Stage 14 (NeMo Agent Toolkit):**

- **CONSTITUTION Invariant 9 is operationally enforced here.** Every
  agent code path that resolves to a surrogate must
  `try: cert.assert_current(...); except CertExpired: route_to_solver()`.
  A Stage-14 mypy plugin (or a CI grep similar to the
  non-commercial-fence) should reject any `Surrogate.predict(...)`
  call site not immediately preceded by `validate(...)`.

## 8. Pointers for the next session

- **Read first:** this handoff; `docs/adrs/ADR-008-jax-fluids-and-
  surrogate-protocol.md`; `CONSTITUTION.md` (Invariant 9); the
  Stage-08 entry in `CLAUDE.md`.

- **Do not re-read:** `aero/adapters/_base.py` (Stage 07's promotion
  remains the canonical Solver protocol shape — no Stage-08 changes);
  the cost-cap module (Stage 07).

- **Run first to verify the world:**
  ```bash
  cd /root/projects/aero-research-platform
  uv pip install -e ".[openfoam,su2,pyfr,nekrs,jax-fluids,
                       surrogate-smoke,gpu-rental,provenance,vv,dev]"
  .venv/bin/pytest -q tests/unit tests/vv tests/stage_06 tests/stage_07 \
                       tests/stage_08
  # -> 191 pass + 17 slow-skipped (4 of those are Stage-08:
  #    test_jax_fluids_smoke + 3 test_baselines_run; pending SIFs +
  #    aero[surrogate-smoke])
  .venv/bin/aero vv list                           # -> 9 cases
  .venv/bin/aero cost show                          # -> $50/mo cap
  .venv/bin/aero --help                             # -> `surrogate` subcommand visible
  python -c "import aero; print('platform-only OK')"
  ```
  SIF presence (operator host, after build):
  ```bash
  ssh root@aero-build apptainer verify /mnt/aero/containers/jax-fluids.sif
  ssh root@aero-build apptainer verify /mnt/aero/containers/surrogate-smoke.sif
  ```

## 9. Artifacts produced

Branch `stage-08/jax-fluids-and-surrogate-plumbing`
(`d6318fd` → pending commit + PR merge):

- **ADR-008** — `docs/adrs/ADR-008-jax-fluids-and-surrogate-protocol.md`.
- **JAX-Fluids adapter** — `aero/adapters/jax_fluids/{__init__,
  solver, schemas, case_writer}.py`.
- **Surrogate protocol + cert framework** —
  `aero/surrogates/__init__.py`,
  `aero/surrogates/_common/{__init__, base, certificate, provenance,
  _dataset_pick}.py`.
- **Dataset loaders** — `aero/surrogates/_common/loaders/{__init__,
  ahmedml, windsorml, drivaerml}.py` +
  `aero/surrogates/_common/loaders/non_commercial/{__init__,
  drivaernet_plus_plus}.py`.
- **Baselines** — `aero/surrogates/baselines/{__init__, mlp_baseline,
  fno_smoke, mgn_smoke}.py`.
- **CLI** — `aero/cli.py` (`--solver jax-fluids`, `aero surrogate
  train`).
- **Containers** — `containers/{jax-fluids.Dockerfile,jax-fluids.def,
  surrogate-smoke.Dockerfile,surrogate-smoke.def}` +
  `scripts/{build_jax_fluids_sif.sh, build_surrogate_smoke_sif.sh,
  download_ahmedml.sh, download_windsorml.sh, download_drivaerml.sh,
  download_drivaernet_plus_plus.sh}`; `containers/SHA256SUMS` header
  extended.
- **Data + DVC** — `data/datasets/{ahmedml, windsorml, drivaerml,
  drivaernet_plus_plus}/reference.md`; `dvc.yaml` populated with four
  `ingest-*` stages.
- **Hydra configs** — `conf/surrogate/baselines/{mlp_baseline,
  fno_smoke, mgn_smoke}.yaml`.
- **Tests** — `tests/stage_08/` (5 modules, 24 tests; 20 fast green,
  4 slow gated on SIFs / extras); `tests/conftest.py` (4 new
  fixtures).
- **CI** — `.github/workflows/non-commercial-fence.yml`.
- **Docs** — CHANGELOG `v0.0.8`; CONSTITUTION Invariant 9;
  CLAUDE.md Stage-08 entry; this handoff.
- **Stage marker** — `.aero-stage` flipped `07` → `08`.

## 10. Confidence / risk note

- **High confidence:** the surrogate protocol contract (24 tests
  pinning the predict-before-fit guard, the time / data gates, the
  taint propagation, the licence-acknowledgment constructor guard,
  the Pydantic discriminator narrowing); the JAX-Fluids adapter
  structure (the discriminated case-spec union + the `_write_case`
  dispatch + the `wall_distribution` `NotImplementedError` for
  periodic cases + the `Solver` ABC subclass conformance); the
  PLATFORM-NOT-HUB invariant (verified end-to-end — no torch / jax /
  jaxfluids / pyg / mlflow in `sys.modules` after a base `import
  aero`); the ADR-008 licence-posture correction (upstream's `setup.py`
  + LICENSE confirm MIT).

- **Medium confidence:** the JAX-Fluids embedded `run_case.py` driver
  (the v0.1 / v0.2 stable API contract was inferred from the upstream
  README + setup.py; the actual cluster smoke run will validate
  whether the three-class API holds for `v0.2.1` specifically); the
  HDF5 output parser (`load()` assumes `primitives/rho`, `primitives/
  u`, `mesh/x_cell_centers` keys — these are the documented
  JAX-Fluids conventions but the cluster run is the verification);
  the `non-commercial-fence.yml` regex matchers (greppable patterns
  are stable but multi-line import edge cases may surface in PR).

- **Low confidence / bus factor:** the actual SIF build wall-clock
  time (the JAX wheel for CUDA 12 is 600+ MB; the surrogate-smoke
  SIF's torch-scatter / torch-sparse compile is non-trivial); the
  `differentiable_run` body's correctness against the live `jaxfluids`
  API (the in-process gradient hook uses a one-parameter mock
  multiplier on the left-state density — the body is structurally
  correct but the actual gradient values will depend on whether
  `SimulationManager.simulate` returns a differentiable result type,
  not just the side-effected buffers); the GHCR push step
  (Stage-07's first-paid-run blocker carries over — operator's GHCR
  PAT is the gate).

- **Outstanding risks:**
  - The DrivAerNet++ download is ~800 GB; TrueNAS `aero/datasets/`
    capacity must be confirmed before the pull. The download script
    refuses below 1 TB free; operator should verify total free space
    accounts for all four datasets before the first pull.
  - The cert's MLflow artifact path (`certificates/<name>.json`)
    becomes a Stage-14 query target. If MLflow's artifact store
    backend (the MinIO sidecar on `aero-mlflow`) is reconfigured,
    the agent's cert-lookup path must update accordingly.
  - The 6-month cert expiry means surrogates trained at Stage 09 are
    on the clock from issue; if Stage 14 doesn't ship within 6
    months, all Stage-09 production certs expire and must be
    revalidated. Operator should set a calendar reminder against
    Stage 09's first production cert issue date.
