# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Stage tags
`v0.0.NN` are pre-alpha; v0.1.0 ships after Stage 16.

## [0.0.13] - 2026-07-06

### Added — Stage 13 (Transition + Unsteady-Airfoil Validation)

- **`kOmegaSSTLM` (gamma-Re_theta Langtry-Menter) transition path** in the OpenFOAM adapter:
  `gammaInt`/`ReThetat` field writers (steady airfoil + moving plunging), gated transport
  schemes/solvers (laminar output byte-identical), and the Langtry-Menter `rethetat_freestream(Tu)`
  correlation. `CaseSpec`/`PlungingAirfoilSpec` gain `"kOmegaSSTLM"`. ADR-021.
- **ERCOFTAC T3A transition-onset V&V case** (`aero/vv/ercoftac/`, `ERCOFTAC_CASES`) — a faithful
  port of the ESI v2412 `simpleFoam/T3A` tutorial (`aero/adapters/openfoam/t3a.py`). Cluster
  **PASS**: transition-onset Re_x 18.4% (< 20%), Cf(x) 24.4% (< 25%) vs the Savill/ERCOFTAC data.
  `wall_distribution` gains an optional `u_inf` (dimensional case). ADR-021.
- **Plunging-foil re-anchor** (`PlungingAirfoilHG2007` parametrized by Strouhal + turbulence model):
  variants at pre-bifurcation St 0.2/0.3 x {laminar, kOmegaSSTLM}; `refined_dt()` for a space+time
  GCI. `scripts/stage13_{gci,reportable}.py` (generalized U95 drivers; thrust C_T = -mean(Cd)).

### Changed / Findings — the plunging over-prediction resolved (documented NO-GO)

- The Stage-11/12 plunging CONCERN is **resolved as a documented, root-caused NO-GO** (ADR-022):
  the 2-D solve's C_T(St) slope is too steep vs the flat HG experiment (C_T 0.13/0.35 vs ref
  0.20/0.22; crosses near St~0.23, misses both measured points); transition barely moves it (~5-11%,
  near-laminar at Re=1e4/Tu=1%). **No rung clears the 15% contract — tolerance NOT relaxed.** Still a
  massive improvement over Stage-12 (anchor error 320% -> 28-58%) with a validated trend. The
  transition MODEL is verified (T3A) — the piece Stage 14 builds on — so the foil NO-GO does not
  block the flagship.
- Recorded the Stage-12 Invariant-10/11 required-check promotions in the deferred-work ledger.

### Deferred (operator scope — tight GO path)

- Pitching-airfoil dynamic stall (McCroskey) + the NACA-0012 transient-mean debt — ledgered
  follow-ups; neither on the GO path.

### Added — paired-difference u95_delta (review finding F1; ADR-023)

- **External review committed** at `docs/review/2026-07-external-review.md` (reviewed at
  v0.0.12); finding **F1** — `ImprovementClaim.u95_delta` was a free input; Invariant 10's
  matched-condition cancellation asserted, never measured — remediated in this release.
- **`aero/vv/paired_difference.py`** — paired-difference estimator: the existing NOBM + tau_int
  machinery runs on the per-cycle DIFFERENCE series over the common converged window
  (`[max(converged_from), min(n_cycles))`); the empirical baseline<->candidate correlation and
  `variance_reduction` vs the independent RSS are recorded — failed cancellation surfaces
  (>= 1), never hides. Fail-loud: period mismatch, unconverged sides, short windows (< 8 pairs;
  practical reliability bar ~16-20), self-comparison, diffs dead at signal scale, degenerate
  batch means.
- **`DeltaU95 = HandEnteredDeltaU95 | ComposedDeltaU95`** discriminated union replaces the free
  float on `ImprovementClaim`; the RSS is a computed field; `kind` is required (no default); the
  thesis-grade gate refuses hand-entered u95_delta / zero paired-numerical / unreliable diff
  estimates — also through `OptimizationResult.improvement`. **BREAKING:**
  `ImprovementClaim(u95_delta=...)` removed (all construction sites were test-only; updated).
- **`compose_improvement()`** alongside `compose_reportable()` (same caller-supplies-absolute-GCI
  seam; input fraction of |baseline|, anti-circular); known-answer tests (independent -> RSS;
  correlated -> well below RSS — the Invariant-10 prose, measured; AR(1)-diff ESS) + the F1
  tripwire on a committed paired fixture in the required `small-signal-gate`.
- **CI:** `data-origin-fence` now runs on every PR (a path-filtered *required* check never
  reports outside its paths and permanently blocks those merges).
- **Constitution:** Invariant 10's Enforcement-paragraph amendment is PR #25 (ADR-023; 72 h
  window from 2026-07-06T17:50Z — ratification pending).

## [0.0.12] - 2026-07-05

### Added — Stage 12 (Verification & UQ Core — the `u95` machinery)

- `aero/vv/statistical_uncertainty.py` — batch-means `u95_statistical` (NOBM primary + Sokal
  integrated-autocorrelation-time cross-check → N_eff; Student-t committed table; relative
  dead-signal guard; soft `reliable` flag). Consumes the Stage-11 `CycleSamples.per_cycle_mean`
  converged-tail seam. Validated on the real cylinder run (Cd u95_stat=0.0131, reliable).
- `aero/vv/reportable_compose.py` + `scripts/stage12_reportable.py` — full
  `U95 = RSS(numerical, statistical, input)` composition into a live `ReportableResult`,
  MLflow-logged; conservative tag policy (thesis-grade only with a positive + reliable
  statistical U95 and a passing anchor).
- `scripts/stage12_cylinder_gci.py` + `OscillatingCylinderLockin.refined_dt` — combined
  space+time GCI (`u95_numerical`) for the oscillating cylinder (the thesis-grade GO vehicle).
- **Required CI gates:** `small-signal-gate` (Invariant 10) + `data-origin-fence` (Invariant 11),
  both ubuntu-latest (runner-independent). ADR-020.

### Changed — CONSTITUTION (ADR-015 ratified)

- **Invariants 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) + 11 (NO-SURROGATE-ON-FOREIGN-DATA)
  ratified** (ADR-015 → accepted; ≥72 h review elapsed + operator approval + CI green);
  enforcement landed this stage (ADR-020). Invariant 11 adds `data_origin` to the Sample/cert
  with a schema validator making a foreign + validated/production cert unconstructible.
- **Invariant 8 doc-drift fixed:** descriptive `default 50.0` → `default 150.0` (ADR-014) — the
  deferred constitution-touch from [0.0.10].

### Fixed — Stage 12 (V&V debt)

- HG rigid-foil reference corrected to primary-source values (Heathcote thesis: C_T ≈ 0.20–0.22
  over St 0.2–0.3, not the digitized 0.04/0.11/0.21). Re-attributes the Stage-11 CONCERN: our
  2-D laminar foil **over-predicts** (~2–4×), not the reference; root-cause → Stage 13.
- `vv-required` selector excludes the multi-hour moving-mesh cases (`moving` marker) — they
  exceed the 60-min CI budget and run via the driver.

## [0.0.11] - 2026-07-01

### Added — Stage 11 (Moving-Mesh + Unsteady Post-Processing Toolkit)

- Moving-mesh (`dynamicMotionSolverFvMesh`, ADR-018) + `aero/postprocess/` unsteady toolkit
  (ADR-019). Oscillating-cylinder lock-in GO (St 0.63 %, 35 converged cycles); plunging-foil
  CONCERN. See `docs/handoffs/STAGE-11-moving-mesh-and-unsteady-DONE-2026-07-01.md`.

## [0.0.10] - 2026-06-15

Optimizer-mission refocus continued + the Stage-10 output-validity bar.

### Added — Stage 10 (output-validity bar)

- `aero/vv/reportable.py` — the thesis-grade output contract for Invariant 10:
  `ReportableResult` / `ReportableQuantity` / `ImprovementClaim` / `OptimizationResult`.
  `U95 = RSS(numerical, statistical, input)`; a `kind` field (steady / time_averaged /
  phase_averaged) makes the **statistical-U95 requirement enforceable** (closes the
  GCI-only hole — a non-steady quantity can no longer be thesis-grade with zero sampling
  uncertainty); `delta > k·U95` (k≥1, default 2; `u95_delta` strictly > 0); matched-
  condition deltas; CFD-VERIFIED-OPTIMUM-ONLY + best-of-N selection-bias guard;
  improvement/optimization mutual-exclusion.
- `docs/vv/output-validity-bar.md` — the operational definition of "thesis-grade output."
- `tests/stage_10/` — 22 tests pinning the contract.

### Changed — budget (ADR-014)

- `aero/orchestration/cost_cap.py` default cap **$50 → $150** (baseline tier; raised by
  ADR-014, superseding ADR-007's value). Sustained ($200–600) and burst ($1–2k) tiers are
  per-campaign env-var overrides. Test now asserts the concrete default.
  - *Known doc-drift:* `CONSTITUTION.md` Invariant 8's descriptive parenthetical still
    reads `default 50.0`; syncing it touches the constitution, so it is deferred to a
    constitution-touch PR rather than edited outside the amendment process.

### Added — provenance / docs

- `docs/architecture/BRIEFING-architecture-review-for-independent-challenge.md` filed
  (non-normative reference, partially adopted per ADR-013). The pre-refocus planning
  bundle (original brief, two-flagship mission draft, 16-stage roadmap prompts) and both
  architecture reviews archived under `docs/handoff-bundle/archive/`.
- `docs/handoff-bundle/PROMPT-CONTEXT-RESTORE.md` — the single "start here" pointer at
  current scope, with a scope-drift guard steering sessions away from `archive/`.

## [0.0.9] - 2026-06-01

### Added — Stage 09 (DoMINO Baseline Surrogate; PhysicsNeMo)

- `aero/surrogates/domino/` — the platform's first production surrogate.
  `DominoSurrogate(Surrogate)` (`model.py`) wraps NVIDIA PhysicsNeMo's DoMINO
  behind the Stage-08 protocol with a swappable `DominoEngine`
  (`PhysicsNeMoDominoEngine` lazy-imports PhysicsNeMo; cluster-gated; host-side
  tests inject a fake engine). `training.py`'s `train_domino` runs the no-PC
  baseline + the Predictor-Corrector recipe and returns a certified
  `DominoTrainingResult`; `certificate.py` owns the smoke→validated gate
  (held-out Cd MAE p95 < 5%, strict `<`) — the only path to `"validated"`.
- `aero/vv/surrogate/compare_surrogate_cfd.py` — the surrogate-vs-CFD cross-check
  producing a `SurrogateVVReport` (per-target RMSE, Cd-within-5% verdict,
  applicability-envelope check). New CLI `aero vv surrogate`.
- `aero/cli.py` — `aero surrogate train --baseline domino --executor
  {runpod,local-ssh}` routes to the on-pod entrypoint
  `scripts/stage09_domino_train.py` (dvc pull → baseline + PC → cert → eight
  MLflow tags → checkpoint → surrogate_vv); cost-cap gated (Invariant 8).
- `containers/physicsnemo.{def,run.sh}` + `scripts/build_physicsnemo_sif.sh` —
  the PhysicsNeMo SIF wraps the NGC container
  `nvcr.io/nvidia/physicsnemo/physicsnemo:25.08` (pinned); the
  `aero[physicsnemo-cu12]` extra is populated (PyG + warp-lang).
- `scripts/_apptainer_sign.sh` — non-interactive Vault-fed SIF signer (ADR-012),
  fixing the over-SSH signing failure; the Stage-07/08 build scripts route through it.
- Pluggable DVC-remote storage backend (ADR-011): `conf/storage/{cloud,nas,minio}.yaml`
  + `aero-cloud`/`aero-nas` remotes in `.dvc/config` + the `- storage: cloud`
  default in `conf/config.yaml` — cloud-now → on-prem-NAS-later by config only.
- `docs/runbooks/stage-09-nas-parallel-cutover.md` — the TrueNAS-VM → dedicated-NAS
  parallel-cutover→re-IP runbook (preserves 192.168.2.100; ZFS-replicates the
  signing-key escrow).
- `ansible/roles/aero-buildah-storage/` + the `aero-apptainer` signing extension.
- `tests/stage_09/` — host-side tests: DoMINO seams, cert gate (both ways),
  taint propagation, PC speedup, surrogate-vs-CFD compare, storage switch.
- ADR-010 (DoMINO baseline surrogate), ADR-011 (pluggable storage backend),
  ADR-012 (non-interactive signing + Stage-09 cleanup).
- `aero/adapters/openfoam/{schemas,geometry,case_writer}.py` — NACA 0012
  **blunt-TE C-grid** (ADR-012 V&V hardening): `trailing_edge_thickness`/`n_te`
  split the singular sharp-TE vertex into a finite base + a base-wake wedge,
  targeting the +21% pressure-drag error (the NACA 0012 TMR xfail). Sharp TE
  stays the default for all other cases; the xfail flips on the Phase-3 cluster
  mesh-sweep. The `aero-cloud` DVC remote is now a RunPod network volume.

### Changed

- `aero/surrogates/_common/loaders/non_commercial/drivaernet_plus_plus.py` —
  `body_length_m` (`gt=0.0`) → `body_length_param` (sign-neutral; ADR-012
  option 3), unblocking the lite-mode schema. `dvc.yaml` drops the
  not-yet-buildable DrivAerNet++ `manifest.json` out.
- `containers/SHA256SUMS` + `SECURITY.md` — corrected the "all SIFs are signed" /
  "Vault not yet stood up" doc drift.
- The 7 xfail V&V tests now carry `[resolution-milestone: ...]` tags.
- Stages 01–09 cleanup pass: the JAX-Fluids `solver_version` provenance string now
  reflects the pinned commit (`v0.2.1+ac7c090f`, was the broken `v0.2.1` tag);
  CLAUDE.md footer + the SHA256SUMS physicsnemo placeholder + the handoff-template
  `model` field clarified; new `docs/operator/deferred-work-ledger.md` consolidates
  the hardware-gated backlog (the audit found zero design debt).

### CI

- `vv-scale-resolving.yml` — new weekly `surrogate-inference-smoke` job (DoMINO
  checkpoint degradation check; GPU-gated, non-required).

### Changed — Stage-09 close-out: optimizer-mission refocus (2026-06-10)

- **Mission refocus (ADR-013):** the platform is now a **hypothesis-driven aerodynamic
  shape/topology optimizer** (flapping-wing flagship; CFD as ground truth). The
  optimization loop is the mission (Stage 15 = thesis checkpoint), not backlog. Cut: the
  automotive surrogate zoo (DoMINO-on-DrivAerML as designed, Transolver/FIGConvNet/X-MGN,
  MoE), DPW-7/HLPW-5 (NASA TMR kept), the NeMo agent layer + literature miner (deferred
  indefinitely), riblet/channel-DNS (riblets demote to an example). SU2/PyFR/NekRS/JAX-Fluids
  frozen-optional (SU2 = post-v0.1.0 adjoint seed). **Stage-09 Phase-3 DoMINO training
  CANCELLED** ($67–191 avoided); DoMINO code + SIF + 353 GiB DrivAerML frozen, not deleted.
- `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` (governing scope, reworked) +
  `README-handoff.md` (Stage 10–20 map) + `STAGE-10-vv-debt-and-validity-bar.md` (committed
  stage prompt — the new convention) + `archive/` (superseded planning docs).
- `docs/architecture/BRIEFING-architecture-review-for-independent-challenge.md` — filed as a
  partially-adopted reference.
- ADR-013 (optimizer-mission refocus), ADR-014 (budget tiers: $150/mo baseline, supersedes
  ADR-007's cap value), ADR-016 (FSI structural-solver strategy: deal.II/Nutils for
  Turek-Hron verification, CalculiX for the flexible-wing application).
- CLAUDE.md — mission rewrite + Hard Rules 12–17 (IMPROVEMENT-EXCEEDS-UNCERTAINTY,
  NO-SURROGATE-ON-FOREIGN-DATA, CFD-VERIFIED-OPTIMUM-ONLY, VALIDATE-AGAINST-EXPERIMENT,
  RESULTS-MUST-TRAVEL, SCOPE-GATE) + Stage-09.5 refocus block. README intro, CITATION.cff
  abstract/keywords, and the `pyproject.toml` description re-pointed to the optimizer mission.
- New rules `.claude/rules/{flapping-validation-ladder,optimization-integrity}.md`.
- `docs/operator/deferred-work-ledger.md` rewritten around the refocus.

### Proposed (constitution PR, 72 h review)

- ADR-015 + **CONSTITUTION Invariants 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) and 11
  (NO-SURROGATE-ON-FOREIGN-DATA)** — proposed here; **ratified post-`v0.0.9`** after the
  72 h review (see [Unreleased]).

## [0.0.8] - 2026-05-30

### Added — Stage 08 (JAX-Fluids 2.x Differentiable Solver; Surrogate Plumbing)

- `aero/adapters/jax_fluids/` — the platform's **fifth** concrete solver and
  the **first differentiable** one. `JaxFluidsSolver(Solver)` with
  `JaxFluidsShockTubeSpec` (Sod's 1-D Riemann problem) +
  `JaxFluidsMeshFileSpec` (JAX-Fluids' native JSON case-pair); the
  `case_writer.write_shock_tube_case_files` emitter for the canonical
  HLLC + WENO5 + RK3 numerical setup; an embedded `run_case.py` driver
  the SIF executes. The additive
  `JaxFluidsSolver.differentiable_run(case, jax_grad_target)` method runs
  in-process against `jaxfluids`, bypasses the executor + cost-cap by
  design, and returns a typed `JaxGradientResult`. The `Solver` ABC is
  NOT amended (ADR-008 §D3).
- `aero/surrogates/__init__.py` + `aero/surrogates/_common/` — the
  surrogate scaffolding the Stage-09+ production models build on:
  `Surrogate` ABC + structural `SurrogateProtocol`, `Sample` /
  `TaintedSample` Pydantic discriminated union, `CertificateOfValidity`
  (strict pydantic, frozen) with `MetricQuantiles` (p50/p95/p99
  monotonicity) and `ApplicabilityEnvelope`, dual
  `validate(current_dataset_hash, now)` time + data gates, 180-day
  default lifetime, and `SurrogateProvenanceTags` composing the
  four-fold tuple with five surrogate-specific fields →
  `as_mlflow_tags()` returns the 8-tag dict logged on every training run.
- `aero/surrogates/_common/loaders/` — `DatasetLoader` structural
  protocol + per-loader `dataset_hash` helper; loader modules for
  AhmedML, WindsorML, and DrivAerML each parse a `manifest.json`.
- `aero/surrogates/_common/loaders/non_commercial/` — the structural
  quarantine subpackage (ADR-008 §D4). `DrivAerNetPlusPlusDataset`
  enforces three layers: constructor guard raises
  `LicenseAcknowledgmentRequired` without
  `acknowledge_noncommercial=True`, `__getitem__` yields
  `TaintedSample`, and `log_acknowledgment(run_id)` writes the MLflow
  audit trail.
- `aero/surrogates/baselines/` — three smoke surrogates: `MLPBaseline`
  (4-feature → Cd MLP), `FNOSmoke` (1-D single-block Fourier Neural
  Operator), `MGNSmoke` (PyG `MessagePassing` on a fixed 8-node chain
  graph). All three lazy-import torch / torch-geometric, produce
  `cert_status="smoke"` certs (NOT for publication), and refuse
  `predict()` without the cert. `MGNSmoke` demonstrates the
  tainted-sample flow when fed `TaintedSample`s.
- `aero/surrogates/_common/_dataset_pick.py` — `build_loader` dispatch
  helper used by the CLI; the DrivAerNet++ branch carries the
  `# non-commercial: justified` pragma the CI fence accepts.
- `aero/cli.py` — `aero surrogate train --baseline {mlp_baseline,
  fno_smoke,mgn_smoke}` subcommand that computes the four-fold tuple,
  runs `fit()` + `set_certificate()`, composes
  `SurrogateProvenanceTags`, sets all eight MLflow tags, and logs the
  cert JSON as the `certificates/<baseline>.json` MLflow artifact. The
  `--solver` enum gains `jax-fluids`; the solver-version, SIF basename,
  required-modules, and extras-hint tables extend accordingly.
- `containers/jax-fluids.{Dockerfile,def}` + `scripts/build_jax_fluids_sif.sh`
  — two-step OCI→Apptainer build on
  `nvidia/cuda:12.4.1-devel-ubuntu24.04` + Python 3.12, installing JAX
  + `jaxfluids` from `git+https://github.com/tumaer/JAXFLUIDS.git@
  JAX-Fluids-v0.2.1` (no PyPI package exists for JAX-Fluids).
- `containers/surrogate-smoke.{Dockerfile,def}` +
  `scripts/build_surrogate_smoke_sif.sh` — second new SIF (Torch 2.5
  + PyG 2.6 + mlflow + einops + h5py + scipy). Torch and JAX are NEVER
  in the same SIF (ADR-008 guardrail).
- `data/datasets/{ahmedml,windsorml,drivaerml,drivaernet_plus_plus}/` —
  per-dataset `reference.md` (citation + licence + source URL + mirror
  procedure + capacity guidance); `.dvc` pointer files land at PR-merge
  after the operator runs the download scripts on aero-build.
- `scripts/download_{ahmedml,windsorml,drivaerml,drivaernet_plus_plus}.sh`
  — operator-side mirror scripts. The DrivAerNet++ script requires
  `AERO_ACKNOWLEDGE_NONCOMMERCIAL=1` and refuses to start if TrueNAS
  `aero/datasets/` has < 1 TB free.
- `dvc.yaml` — populated with `ingest-{ahmedml,windsorml,drivaerml,
  drivaernet-plus-plus}` stages.
- `conf/surrogate/baselines/{mlp_baseline,fno_smoke,mgn_smoke}.yaml` —
  three Hydra-shape configs.
- `.github/workflows/non-commercial-fence.yml` — CI gate asserting
  every import of `aero.surrogates._common.loaders.non_commercial`
  under `aero/` either produces `non_commercial=True` in the same file
  or carries the `# non-commercial: justified` pragma. Greppable, no
  import-hook machinery.
- `docs/adrs/ADR-008-jax-fluids-and-surrogate-protocol.md` — six
  decisions bundled: D1 JAX-Fluids version pin (`JAX-Fluids-v0.2.1`),
  D2 licence-posture correction (MIT, not GPL-3), D3 differentiability
  seam (additive on adapter only), D4 DrivAerNet++ quarantine
  (three-layer defence), D5 cert expiry (6 months OR hash change),
  D6 GNN library choice (PyG).
- `tests/stage_08/` — 24 host-side tests pinning the Surrogate
  protocol guards, the DrivAerNet++ three-layer quarantine, the
  JAX-Fluids adapter surface (incl. the ABC-vs-adapter
  `differentiable_run` placement test), and the three baseline
  end-to-end fit→cert→predict flows (`@pytest.mark.slow`; skip when
  `aero[surrogate-smoke]` not installed).
- `tests/conftest.py` — four new session-scoped fixtures
  (`jax_fluids_sif_present`, `jax_fluids_extra_installed`,
  `surrogate_smoke_sif_present`, `surrogate_smoke_extra_installed`).

### Changed

- `pyproject.toml` — `aero[jax-fluids]` populated with `h5py>=3.10`,
  `jax[cuda12]==0.4.34`, `jaxlib==0.4.34`, `jaxfluids @ git+url@JAX-
  Fluids-v0.2.1`. New `aero[surrogate-smoke]` extra carrying
  `torch>=2.5`, `torch-geometric>=2.6`, `einops>=0.8`, `mlflow>=2.20`,
  `numpy>=1.26`. Base `pip install aero` (no extras) still imports
  cleanly without torch / jax / jaxfluids / pyg in `sys.modules` —
  PLATFORM-NOT-HUB invariant preserved (verified end-to-end in-session).
- `containers/SHA256SUMS` — comment header extended with
  `surrogate-smoke.sif` (alongside the pre-listed `jax-fluids.sif`).
  Actual SHAs land at PR-merge after the operator runs the build
  scripts (Stage-07 NekRS precedent).
- `.aero-stage` — `07` → `08`.
- `CLAUDE.md` — Stage 08 section appended; the certificate-of-validity
  pointer updates from "TBD in Stage 08" to the concrete
  `aero.surrogates._common.certificate:CertificateOfValidity.assert_current`
  reference.

### CONSTITUTION

- **Invariant 9 added** — `CERTIFICATE-OF-VALIDITY-REQUIRED-FOR-
  SURROGATE-INVOCATION`. Every `Surrogate.predict()` call (especially
  from the Stage-14 agent layer) is gated on a current
  `CertificateOfValidity.assert_current(current_dataset_hash, now)`. Both
  the time gate (`now < expires_at`, default 180 days) and the data
  gate (`current_dataset_hash == training_dataset_dvc_hash`) must hold.
  `CertExpired` on failure; agents fall back to a validated solver.

## [0.0.7] - 2026-05-20

### Added — Stage 07 (PyFR + NekRS GPU Adapters; First Cloud GPU Run)

- `aero/adapters/pyfr/` — the platform's third concrete solver: `PyFRSolver`
  with `PyFRTaylorGreenSpec` + `PyFRMeshFileSpec`, a host-side gmsh-MSH2 mesh
  emitter for the triply-periodic Taylor-Green cube, and a `solver.ini`
  writer that bakes in the Brachet 1983 analytic IC + the `[soln-plugin-
  integrate]` monitor that powers the dissipation-rate `TimeHistory`.
- `aero/adapters/nekrs/` — the platform's fourth concrete solver:
  `NekRSSolver` with `NekRSTaylorGreenSpec` + `NekRSCaseDirSpec`, host-side
  emitters for the Nek5000 `.box` / `.par` / `.udf` triplet, and a log-grep
  loader that parses `gradKE:` lines (rank-0-only) into the same typed
  `TimeHistory(monitor_name="dissipation_rate")` PyFR produces.
- `aero/adapters/_meshing/` — solver-agnostic host-side mesh emitters:
  `write_taylor_green_msh2` (numpy hex-cube, six periodic face physical
  groups, no gmsh host dep) and `write_taylor_green_box` (Nek5000 `.box`,
  all-periodic BCs).
- `aero/orchestration/cost_cap.py` — `CostCap` / `Ledger` / `LedgerEntry`
  with append-only persistence at `/etc/aero/runpod-ledger.json`,
  `check_budget(estimated_usd)` pre-launch gate, `record_launch` /
  `record_termination` with explicit `orphaned` state when terminate
  polling fails. Default cap: `$50/month` (env var
  `AERO_RUNPOD_MONTHLY_CAP_USD`).
- `aero/orchestration/runpod/` — `RunPodExecutor` satisfying the existing
  `Executor` protocol. Lifecycle: estimate cost → `cost_cap.check_budget`
  → `cost_cap.record_launch` → GraphQL `podFindAndDeployOnDemand` → SSH
  poll → `_ssh_exec` → `podTerminate` (in `finally:`) → poll for
  `desiredStatus=TERMINATED` → `cost_cap.record_termination`. GraphQL via
  `requests` (no vendor SDK); container image is a GHCR-mirror of the
  SIF.
- `aero/vv/scale_resolving/` — `TaylorGreenVortex` (Brachet 1983 Re=1600
  dissipation-rate reference, 10 % tolerance, peak_dissipation as the
  GCI metric) and `PeriodicHillLES` (Breuer 2009 re-attachment-length
  scalar; full pointwise profile compare deferred to Stage 12 with a
  fail-loud stub).
- `containers/pyfr.{Dockerfile,def}` + `scripts/build_pyfr_sif.sh` —
  two-step OCI-then-SIF build on `nvidia/cuda:12.4.1-devel-ubuntu22.04`,
  PyFR 1.15.0 from PyPI with `setuptools<70` (pkg_resources requirement).
- `containers/nekrs.{Dockerfile,def}` + `scripts/build_nekrs_sif.sh` —
  source build of NekRS v23.0 with OCCA + libParanumal kernels for
  CUDA sm_80/sm_89/sm_90; Make + serial-HYPRE-fallback handles the
  HYPRE ExternalProject ordering.
- `data/references/scale_resolving/{taylor_green,periodic_hill}/reference.md`
  — citation + digitisation runbook for the two reference datasets.
- `aero[pyfr]` extra (`h5py>=3.10`, `mako>=1.3`); `aero[nekrs]` extra
  (`meshio>=5.3`); new `aero[gpu-rental]` extra (`requests>=2.32`).
- `aero/cli.py`: `aero run/vv run --executor {local-ssh,runpod}` +
  `--solver {openfoam,su2,pyfr,nekrs}` + `--pod-type` + `--container-image`
  + `--projected-hours`; new `aero cost {show,clear-orphan}` subcommand.
- `tests/stage_07/` — 58 unit tests covering the protocol refactor, the
  cost-cap module (mocked tmpdir ledger), the RunPod executor lifecycle
  (mocked GraphQL), both new adapters' host-side surface, and the
  meshing helpers.
- `.github/workflows/vv-scale-resolving.yml` — new nightly workflow,
  gated on a `[self-hosted, gpu]` runner (Stage-13-provisioned; skips
  with a message until then).
- `docs/adrs/ADR-007-gpu-solver-adapters-and-cost-cap.md` — the four
  decisions: protocol refactor, PyFR + NekRS as third + fourth, minimal
  RunPod executor, local-ledger cost cap.

### Changed

- **Breaking:** `MeshHandle.n_cells` → **`n_elements`** (rename); new
  sibling `n_dof: int | None` for FR/SEM solvers. Catch-up edits in
  `aero/adapters/openfoam/solver.py`, `aero/adapters/su2/solver.py`,
  `aero/vv/_base.py` (the `BenchmarkResult` field is also renamed), and
  every test that asserts on the field. `aero/vv/mesh_sweep.py`'s
  `GridPoint.n_cells` keeps its GCI-domain naming and reads from
  `obs.n_elements`.
- **Breaking:** `SolveResult.cd` / `.cl` are now `float | None` (previously
  required). Airfoil V&V cases now `assert result.cd is not None` at the
  top of `evaluate()` — FAIL-LOUD per Invariant 2. Non-airfoil cases
  (Taylor-Green, periodic hill, future internal-flow / heat-transfer
  cases) leave them `None` and write their measurements to
  `SolveResult.scalars: dict[str, float]` (new field).
- **Breaking:** `SolveResult.history` is now a Pydantic discriminated union
  `ConvergenceHistory | TimeHistory` keyed on `kind`. Existing
  `ConvergenceHistory(iteration=..., residual=...)` constructors keep
  working (Pydantic defaults `kind="convergence"`). The new `TimeHistory`
  branch carries `(t, monitor, monitor_name)` for time-accurate solvers.
- `build_apptainer_exec` gains `gpu: bool = False` (appends `--nv` for
  GPU pass-through) and `mpi_n: int | None = None` (wraps the inner
  command in `mpirun -n N`). Defaults preserve every existing
  OpenFOAM/SU2 command string byte-for-byte.
- `aero/cli.py:aero run` no longer requires `cd`/`cl` to be present;
  it logs whichever scalar metrics are non-None plus everything in
  `solve.scalars`.

### CONSTITUTION

- **Invariant 7 amended** — TYPED-CONVERGENCE-HISTORY → **TYPED-SOLVE-HISTORY**.
  The discriminated union now covers both branches; case-specific scalars
  ride on `SolveResult.scalars`, not on `.attrs`.
- **Invariant 8 added** — **COST-CAP-ENFORCED-CLOUD-EXECUTION**. Every
  rented-GPU launch passes through `CostCap.check_budget()` *before* any
  spend; orphaned-termination ledger entries refuse further launches until
  an operator clears them via `aero cost clear-orphan`.

## [0.0.6] - 2026-05-19

### Added — Stage 06 (SU2 Adapter — Forcing the Abstraction)

- `aero/adapters/_base.py` — the generalised `Solver` ABC (template-method
  `prepare`, abstract `mesh`/`run`/`load`/`wall_distribution` seams) and the
  structural `SolverProtocol` the V&V harness types against; shared
  lifecycle handles `CaseDir` / `MeshHandle` / `ResultHandle`
  (`post_processing_host_path` → `output_host_path`); solver-neutral
  `SolveResult` + `ConvergenceHistory` + `WallDistribution`;
  `build_apptainer_exec` promoted from the OpenFOAM adapter.
- `aero/adapters/su2/` — the SU2 v8 adapter: `SU2CaseSpec` discriminated
  union (`SU2AirfoilSpec` + `SU2MeshFileSpec`), a native `.su2` structured
  quad mesh writer with geometric wall-normal clustering (airfoil O-grid,
  TMR flat plate, TMR bump), a compressible RANS `.cfg` writer (Roe for
  transonic / JST for subsonic), and `SU2Solver(Solver)`. The adapter
  consumes both the OpenFOAM TMR specs and the SU2-native specs so the
  Stage-05 TMR cases run through either solver unchanged.
- `aero[su2]` extra (`mpi4py>=4.0`, `meshio>=5.3`) — independent of
  `aero[openfoam]` (Stage-06 guardrail 3).
- `containers/su2-v8.{Dockerfile,def}` + `scripts/build_su2_sif.sh` —
  two-step OCI-then-SIF build (rootless buildah on `aero-build` source-
  compiles SU2 v8 with autodiff / Mutation++ / pysu2 / OpenBLAS; the SIF
  bootstraps from the OCI archive `%post`-filesystem-only).
- `aero/vv/transonic/` — the platform's first compressible V&V cases:
  `NACA0012Transonic` (M=0.7, AoA=1.49 deg, Cd vs AGARD-AR-138 /
  Schmitt-Charpin, 5% tolerance) and `OneraM6` (M=0.84, AoA=3.06 deg, Cp at
  η=0.44 vs Schmitt-Charpin / ONERA TR-1).
- `aero/vv/cross_solver_compare.py` — `compare_solvers` runs the same
  `BenchmarkCase` through both adapters; emits a `CrossSolverReport` (JSON
  + markdown) suitable for an MLflow artefact and the V&V dashboard.
- `aero run --solver {openfoam,su2}` and `aero vv run --solver ...`; per-
  solver required-modules check and `solver_version` MLflow tag.
- `tests/stage_06/` — protocol-satisfaction asserts for both adapters;
  mesh-writer, cfg-writer, SU2 CSV-parser unit tests; cross-solver compare
  shape tests. `tests/vv/test_tmr_*_su2.py` + `test_transonic_*.py` (cluster-
  bound).
- `.github/workflows/import-platform-only.yml` — Constitution
  Invariants 1/4 are now structurally enforced in CI.
- `.github/workflows/vv-transonic.yml` — nightly-only transonic suite.
- ADR-006 — the Solver-protocol-generalisation + SU2-adapter decisions.

### Changed — Stage 06

- **CONSTITUTION Invariant 7 — TYPED-CONVERGENCE-HISTORY** added (every
  solver's `load()` returns a typed `SolveResult` with a typed
  `ConvergenceHistory`; never a solver-native container or `.attrs` dict).
- `OpenFOAMSolver` refactored onto `Solver`; `load()` now returns
  `SolveResult` (was `xr.Dataset`). Numbers are bit-unchanged from Stage 05
  (no behaviour regression — Stage-06 guardrail 2).
- `vv-smoke.yml` installs `aero[openfoam,su2,provenance,vv,dev]` and runs
  the TMR suite through both solvers (per-solver readiness gated by the
  cluster fixtures).
- `aero/vv/_base.SolverLike` is now an alias of
  `aero.adapters._base.SolverProtocol` — one source of truth.
- `aero/vv/tmr/{flat_plate,bump_2d}.py` call `solver.wall_distribution(...)`
  instead of importing `extract_wall_distributions` directly (closes a
  PLATFORM-NOT-HUB leak).

### Status — Stage 06 (partial)

- The structural deliverables ship (protocol, adapter, container defs,
  V&V cases, cross-solver compare, CI).
- SU2 cluster validation against the TMR cases is the cluster follow-up
  (xfail-strict-false until the first cluster run lands); the SU2 SIF
  SHA256 lands in `containers/SHA256SUMS` after `build_su2_sif.sh` runs.
- ONERA M6 host-side 3D wing-slice extraction is flagged for a follow-up
  stage; the case fails loud until it lands.

## [0.0.5] - 2026-05-19

### Added — Stage 05 (V&V Harness Against NASA TMR)

- `aero/vv/` — the solver-agnostic V&V harness: `BenchmarkCase` / `SolverLike`
  protocols, the `BenchmarkResult` model family, and `BenchmarkRunner`
  (prepare → mesh → solve → evaluate → compare, logging the four-fold tuple
  with a `validation_tag`)
- `aero/vv/mesh_sweep.py` — `MeshSweep` and `grid_convergence_index`, an
  ASME V&V 20 / Celik (2008) Grid Convergence Index primitive
- `aero/vv/tmr/` — the NASA TMR cases (turbulent flat plate, 2D bump, NACA
  0012) and the `TMR_CASES` registry
- `aero/vv/dashboard.py` — the HTML V&V status dashboard (`docs/vv-dashboard.html`)
- `aero/adapters/openfoam/` — `tmr_specs.py`, `tmr_geometry.py`,
  `tmr_case_writer.py` (flat-plate / 2D-bump cases), `fields.py` (Cf/Cp wall
  extraction), `_foam_common.py` (shared FOAM helpers)
- `aero vv list / run / report` CLI; `aero vv run --mesh-sweep` for a GCI study
- `aero[vv]` extra (scipy); `data/references/tmr/` reference data
- `vv-required.yml` — the stage-gated, required V&V CI check; `vv-smoke.yml`
  promoted to the full NASA TMR suite with a PR-comment status post
- ADR-005 — the V&V harness decisions

### Changed — Stage 05

- The airfoil mesh is rebuilt as an eight-block multi-block C-grid (rectangular
  100-chord far field, explicit wake cut); the Stage-03 four-block O-grid is
  retired — `checkMesh` skewness drops ~17 → ~2.8 (ADR-005 supersedes ADR-003's
  O-grid decision)
- Resolved-wall turbulence treatment (`nutLowReWallFunction`); the four-fold
  MLflow run tag `stage` is now parametrised

### Known issues — Stage 05

- The three TMR case tests are `xfail`: NACA 0012 Cd is +21 % (trailing-edge
  pressure-drag resolution), the flat-plate Cf is ~7–15 % off the White
  correlation (the TMR CFD reference data could not be fetched — no network),
  and the 2D bump solve stalls on high-aspect-ratio cells. See the Stage-05
  handoff §6–§7. No tolerance was relaxed.

## [0.0.4] - 2026-05-19

### Added — Stage 04 (Provenance Backbone)

- `aero/provenance/four_fold.py` — the four-fold provenance contract:
  `compute_provenance` → `ProvenanceTuple` (`git_sha`, `dvc_input_hash`,
  `container_sif_sha256`, `config_hash`), fail-loud `ProvenanceError`
- `aero/provenance/mlflow.py` — `start_provenance_run`, logging the four-fold
  tuple as MLflow tags to the remote tracking server (supersedes
  `mlflow_basic.py`)
- `aero/provenance/db.py` — transactional Postgres mirror of the tuple into
  `mlflow_artifact_provenance`
- `conf/` — Hydra config tree; `aero run` composes a case and validates it
  through the strict `CaseSpec` boundary; `aero run --allow-dirty`
- `aero[provenance]` extra — mlflow, dvc[s3], boto3, hydra-core, omegaconf,
  psycopg2-binary, alembic; `uv.lock` committed
- `alembic` migration `004_provenance` — the `mlflow_artifact_provenance`
  mirror table; `db/provision/aero_databases.sql` (additive LXC 202 DDL)
- DVC initialized; `data/references/naca0012/naca0012.csv` moved to DVC
  tracking; `aero-minio` S3 remote on the MinIO sidecar
- Ansible roles `aero-vault` (LXC 217) and `aero-mlflow` (MinIO + MLflow +
  Vault Agent); `aero-vault` added to the inventory and the provisioner
- `tests/stage_04/` (48 hermetic + the slow `provenance-completeness` test);
  `.github/workflows/provenance-completeness.yml`
- `docs/adrs/ADR-004-four-fold-provenance-contract.md`,
  `docs/release/zenodo.md`, `docs/runbooks/stage-04-provenance-deploy.md`

### Deployed — Stage 04

- New LXC 217 `aero-vault` running HashiCorp Vault 1.20.4 (raft, TLS)
- MinIO + MLflow 3.12.0 + a Vault Agent on `aero-mlflow`, under systemd
- `aero_mlflow` + `aero_provenance` databases on the shared Postgres LXC 202
  (additive); the `004_provenance` migration applied
- Verified end-to-end: `aero run naca0012` logs all four provenance tags and
  the matching Postgres mirror row

### Changed — Stage 04

- `.pre-commit-config.yaml` — `check-added-large-files` exempts `uv.lock`
- `aero/provenance/mlflow_basic.py` removed (superseded by `mlflow.py`)

## [0.0.3] - 2026-05-19

### Added — Stage 03 (OpenFOAM Walking Skeleton)

- `containers/openfoam-esi.def` + `scripts/build_openfoam_sif.sh` — OpenFOAM-ESI
  v2412 solver SIF, bootstrapped from the digest-pinned
  `opencfd/openfoam-default:2412`, built/signed/recorded in `SHA256SUMS`
- `aero/orchestration/` — `Executor` Protocol + `ExecResult`; `LocalSSHExecutor`
  (short commands over SSH, long solves via `run_long.sh`)
- `aero/adapters/openfoam/` — analytic NACA 0012 geometry, strict pydantic
  schemas, a four-block O-grid `blockMesh` case writer, and `OpenFOAMSolver`
  (`prepare`/`mesh`/`run`/`load`)
- `aero/provenance/mlflow_basic.py` — interim MLflow logger (`git_sha`,
  `container_sif_sha256` tags; local `mlruns/`)
- `aero/cli.py` — `aero run naca0012 --executor local-ssh`, end-to-end
  (verified Cd ≈ 0.00875, within the ±25% walking-skeleton band of 0.0079)
- `aero[openfoam]` extra — pyfoam, ofpp, xarray, mlflow
- `data/references/naca0012/` — analytic geometry CSV + reference notes
- `tests/unit/test_openfoam_adapter.py`, `tests/stage_03/test_naca0012_smoke.py`,
  `tests/conftest.py` (the `--run-slow` gate)
- `docs/adrs/ADR-003-openfoam-walking-skeleton.md`

### Changed — Stage 03

- `scripts/run_long.sh` — accepts an optional `[user@]alias` target so jobs
  run as the LXC root (solver SIFs require it)
- `.github/workflows/vv-smoke.yml` — real NACA 0012 smoke test on a
  self-hosted `vv` runner (was a Stage 01 placeholder)

## [0.0.2] - 2026-05-19

### Added — Stage 02 (Proxmox Topology & Container Build Pipeline)

- `docs/architecture/proxmox-inventory-2026-05-16.md` — committed host inventory
- Seven `aero-*` LXCs provisioned (IDs 210-216, unprivileged Ubuntu 24.04,
  dual-NIC: LAN + private `10.10.10.0/24`) via `scripts/provision_aero_lxc.sh`
- `ansible/` — inventory, `site.yml`, three roles: `aero-base` (users, scoped
  sudo, ufw, baseline packages, node-exporter), `aero-apptainer` (pinned
  Apptainer 1.5.0), `aero-nfs-client` (NFS bind-mount symlinks)
- TrueNAS `aero/` NFS dataset — host-mounted at `/mnt/aero-nfs`, bind-mounted
  into build/dev/vv/mlflow at `/mnt/aero` (NFS subdirs: dvc-remote,
  mlflow-artifacts, datasets, containers)
- Apptainer SIF pipeline — `containers/_base.def`, `hello-world.def`,
  `scripts/build_base_sifs.sh`; `_base.sif` + `hello-world.sif` built, PGP-
  signed (key `682F6145…`), recorded in `containers/SHA256SUMS`
- `scripts/run_long.sh` — tmux-based long-running-job submit/poll helper
- `scripts/verify_stage_02.sh` — Stage 02 verification gate (30 checks)
- Interim `vzdump` backup job (aero LXCs only, daily 03:00, keep-7)
- `docs/adrs/ADR-002-proxmox-topology.md`; `docs/architecture/`
  `proxmox-topology.md`, `ssh-conventions.md`, `backup-interim.md`
- Hardened `.claude/hooks/block-dangerous-bash.sh` (pct/qm guard, protected
  host paths, shared-host SSH guard)

## [0.0.1] - 2026-05-17

### Added — Stage 01 (Scaffolding & Conventions)

- `LICENSE` — GPL-3.0 (canonical FSF copy)
- Governance: `CLAUDE.md`, `AGENTS.md`, `CONSTITUTION.md`, `CONTRIBUTING.md`,
  `SECURITY.md`, `CITATION.cff` (Zenodo DOI placeholder), `CHANGELOG.md`
- Repository layout per project brief: `aero/{adapters,surrogates,
  orchestration,vv,uq,provenance,agentic,literature}/` skeleton with
  per-subdir `.gitkeep`; `containers/`, `data/`, `ansible/`, `tests/`,
  `scripts/`, `docs/`
- `pyproject.toml` (uv-managed, PEP 621); base deps numpy/pydantic/typer/
  loguru/dvc; optional extras enumerated as placeholders (openfoam, su2,
  pyfr, nekrs, jax-fluids, physicsnemo-cu12, precice, gpu-rental, uq,
  agentic, literature, orchestration, dev, docs)
- `.pre-commit-config.yaml` with ruff, mypy (strict on `aero/`), gitleaks,
  validate-pyproject, large-file check, local pytest-unit hook, local
  docs-status-sync hook
- GitHub Actions: `lint`, `type`, `test`, `docs-sync`, `commit-lint`,
  `vv-smoke` (placeholder)
- `.github/CODEOWNERS`; `PULL_REQUEST_TEMPLATE.md`
- `.claude/` agent configuration: `settings.json` with hooks (PreToolUse
  guards, Stop handoff-existence check), `rules/`, `commands/`, `agents/`,
  `skills/`
- Templates: `docs/handoffs/_template.md`, `docs/adrs/_template.md`
- `docs/adrs/ADR-001-license-and-governance.md` — captures GPL-3.0 choice,
  branch protection ruleset, mypy strict-on-aero policy, commit conventions,
  solo-developer admin-bypass posture
- `scripts/check_handoff_exists.sh` (Stop-hook gate),
  `scripts/regenerate_status.sh` (README STATUS sync)
- `tests/unit/test_smoke.py` — first smoke test (import + version)
- Branch protection on `main`: PR required, status checks (lint/type/test/
  docs-sync/commit-lint), linear history, no force pushes, no direct pushes,
  CODEOWNERS 1-approval; `enforce_admins: false` for solo-admin self-merge
- Post-stage handoff: `docs/handoffs/STAGE-01-scaffolding-and-conventions-DONE-2026-05-17.md`

[Unreleased]: https://github.com/ernesto01louis/aero-research-platform/compare/v0.0.3...HEAD
[0.0.3]: https://github.com/ernesto01louis/aero-research-platform/releases/tag/v0.0.3
[0.0.2]: https://github.com/ernesto01louis/aero-research-platform/releases/tag/v0.0.2
[0.0.1]: https://github.com/ernesto01louis/aero-research-platform/releases/tag/v0.0.1
