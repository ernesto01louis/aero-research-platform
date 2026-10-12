# Constitution

This document codifies the non-negotiable design rules of
`aero-research-platform` in [GitHub Spec-Kit](https://github.com/github/spec-kit)
compatible form. Any change to this file requires an ADR explaining the
rationale, signed off by the operator, and a CHANGELOG entry.

## Invariant 1 — PLATFORM-NOT-HUB

The `aero/` core imports only stdlib + `numpy` + `pydantic`. Every solver,
ML framework, cloud SDK, and physics library is gated behind an optional
extra (`cad`, `dev`, `gpu-rental`, `jax-fluids`, `nekrs`, `openfoam`,
`physicsnemo-cu12`, `precice`, `provenance`, `pyfr`, `su2`, `surrogate-smoke`,
`vv`; see `pyproject.toml`).

**Enforcement:**
- **`import aero with no extras`** (required; `import-platform-only.yml`, live since Stage 06)
  installs the package with no extras in a fresh environment. It asserts that `import aero`, and
  the listed core modules, succeed without Torch, JAX, PhysicsNeMo, OpenFOAM or any other banned
  module. It installs from the checkout, never `pip install aero`: that PyPI name belongs to an
  unrelated project.
- **The crate round-trip read legs (Invariant 13)** go further. On fresh Linux, macOS and Windows
  runners they install only the built wheel, numpy and pydantic, and verify every result crate
  with the stdlib CLI.

**Why:** A platform that bleeds adapter dependencies into core is no
longer a platform — it is a hub for one specific stack. The orchestrator
project taught us this; the new build will not repeat that mistake.

## Invariant 2 — FAIL-LOUD

Pydantic configurations are strict: `model_config = ConfigDict(extra='forbid')`.
No silent fallback for missing required keys; no implicit type coercion
between domain types; no inline schema-drift band-aids. The system fails
at startup with a clear error message and a pointer to the config that is
wrong.

**Enforcement:** mypy `--strict` is required on `aero/` (loose elsewhere
only with per-module ADR). `pydantic.ValidationError` propagates;
do-not-catch in production code unless the caller is the user-facing CLI
boundary where a friendly error string is rendered.

**Why:** Silent fallbacks become silent corruption. Provenance breaks
when a config field drifts and nobody notices.

## Invariant 3 — PROVENANCE-FROM-DAY-ONE

Every CFD solve and every ML training run logs four tags to MLflow:

1. `git_sha` — `git rev-parse HEAD` at submission time (suffix `-dirty`
   only with `--allow-dirty` and a prominent warning)
2. `dvc_input_hash` — sha256 over the sorted list of `dvc status -c`
   outputs for all `.dvc`-tracked inputs the case touches
3. `container_sif_sha256` — SHA256 of the Apptainer SIF that ran the job,
   pulled from `containers/SHA256SUMS`. A run spanning more than one
   container (a partitioned FSI coupling runs its fluid and solid
   participants out of different SIFs) records the **container of record**
   here and the full roster in `ProvenanceTuple.containers`, logged as the
   additional `container_sif_set` tag — see ADR-038. The rule below is
   unchanged: the four tags are always present, always in this shape.
4. `config_hash` — sha256 of the resolved Hydra config serialized as
   canonical JSON

Postgres mirror table `aero_provenance.mlflow_artifact_provenance` (Stage
04+) indexes these for fast cross-run queries.

**Enforcement:**
- **Structural.** `aero.provenance.four_fold.ProvenanceTuple` validates all four fields, and the
  CLI fails loud before logging a run with fewer. Every `ReportableResult` and every result crate
  (Invariant 13) carries a `ProvenanceTuple`.
- **CI job `provenance-completeness`** (live since Stage 04) runs the walking-skeleton case on the
  self-hosted `vv` runner. It asserts that all four tags are populated on the resulting MLflow
  run and that the Postgres mirror row exists. It is **not** a required check: a required check
  on a self-hosted runner blocks every PR while that runner is offline. Promoting it is ledgered.

**Why:** A peer-review-grade platform must produce citable results; the
four-tuple is the citation. Without it, a published number is a guess.

## Invariant 4 — HEAVY-DEPS-IN-OPTIONAL-EXTRAS-ONLY

Every dependency that pulls in a compiled toolchain, a >100 MB wheel, a
CUDA wheel, a JAX-fluids-style domain library, a cloud-provider SDK, or
proprietary connectivity must live in an optional extra. Base `aero`
installs with only `numpy`, `pydantic`, `typer`, `loguru`, `dvc`.

**Enforcement:** The same `import aero with no extras` job as Invariant 1. The dependency licence
scan (Invariant 5) also computes the base-install closure from `uv.lock` on every PR, and checks
it against `uv export`.

**Why:** Researchers reading our code should be able to inspect the core
abstractions without provisioning a 30 GB CUDA environment.

## Invariant 5 — LICENSE-POSTURE — GPL-3.0-compatible

The platform is **GPL-3.0-or-later**.
- **Dependencies.** Every package `uv.lock` can install carries a licence on the ADR-048
  allowlist, or holds a reviewed exact-version exception. The allowlist is GPL-3.0-compatible
  per the FSF licence list: MIT, MIT-0, MIT-CMU, X11, HPND, BSD-1/2/3-Clause and the OSI BSD
  family, 0BSD, Apache-2.0 (including `WITH LLVM-exception`), ISC, PSF-2.0, Python-2.0,
  CNRI-Python, MPL-2.0, LGPL-2.1/3.0, GPL-2.0-or-later, GPL-3.0, ZPL-2.1, Zlib, CC0-1.0,
  Unlicense, BSL-1.0.
- **Proprietary components.** The base install and the supported extras are proprietary-free.
  NVIDIA's proprietary CUDA components are admitted only in the frozen-optional GPU extras
  (`jax-fluids`, `surrogate-smoke`, `physicsnemo-cu12`) and their container images (ADR-010).
- **Excluded outright.** No commercial CFD or CAE dependency; no closed-source Intel MKL build.

**Enforcement:**
- **`dependency licence scan — Invariant 5`** (required; `dependency-licences.yml`).
  `scripts/licence_scan.py` reads `uv.lock` and a hash-bound metadata snapshot. It normalises each
  package's licence along a fixed ladder, and refuses anything unknown, ambiguous or
  contradictory. It evaluates the SPDX expression in every scope that can install the package.
  An exception fails when it is stale (the lock moved), unneeded, or used outside its scopes.
- **An ADR** is required for every new heavy dependency, naming its licence (ADR-048).

**Why:** Reproducibility for peer review requires an open stack. A researcher reading our paper
must be able to install everything we used without a commercial licence. A literal four-licence
whitelist was never what the platform shipped (its base install is MIT/MPL/ISC/PSF from day one),
so the rule now states the real constraint: GPL-3.0 compatibility, scoped, and machine-checked.
Amended at Stage 21 by ADR-048, which delivers the licence scan promised here since Stage 16.

## Invariant 6 — CONVENTIONAL-COMMITS + CONVENTIONAL-COMMENTS

Commit format: `<type>(stage-NN): <subject>`. PR review comments use
Conventional Comments labels (`praise:`, `nitpick:`, `suggestion:`,
`issue:`, `todo:`, `question:`, `thought:`, `chore:`, `note:`).

**Enforcement:** `commit-lint` CI check enforces commit format on every
commit and the PR title. Conventional Comments are a humans-and-agents
convention enforced by review discipline, not CI.

**Why:** A staged build (21 stages to v0.1.0) with frequent context handoffs to fresh Claude
Code sessions needs uniform commit semantics so changelogs, release notes,
and post-stage handoffs assemble cleanly.

## Invariant 7 — TYPED-SOLVE-HISTORY

Every solver adapter's `Solver.load()` returns a typed `SolveResult` carrying a
discriminated union `ConvergenceHistory | TimeHistory` — either a steady-state
monitored-residual series `(iteration, residual)` or a time-accurate monitor
series `(t, monitor, monitor_name)`, each as a validated equal-length pair —
never a solver-native container (`xarray.Dataset`, raw dict, CSV path).
Steady-state scalars (`cd`, `cl`) and case-specific scalars (Taylor-Green peak
dissipation, periodic-hill re-attachment length, ...) ride in typed fields
(`SolveResult.cd: float | None`, `.cl: float | None`,
`.scalars: dict[str, float]`), never `.attrs`-style untyped metadata.

**Enforcement:** the V&V harness types `solver.load(result)` as `SolveResult`
against the `aero.adapters._base.SolverProtocol`. A per-adapter test asserts
`isinstance(result, SolveResult)` and discriminator-correct round-trip of the
history; mypy `--strict` on `aero/adapters/_base.py` pins the schema. Airfoil
V&V cases that read `result.cd`/`.cl` `assert ... is not None` at the top of
their `evaluate()` — fail-loud per Invariant 2. The `import-platform-only` CI
job verifies the typed result types are usable without any solver extra
installed.

**Why:** A solve's history is the primary evidence the result is trustworthy.
If it is trapped in a solver-native format, the V&V dashboard, the UQ layer
(Stage 12), and any cross-solver comparison must each learn N formats. A typed
discriminated union is the citation-grade contract that survives both
steady-state RANS (OpenFOAM, SU2) and time-accurate scale-resolving runs (PyFR,
NekRS, JAX-Fluids). First codified in Stage 06 as TYPED-CONVERGENCE-HISTORY
when SU2 forced the multi-solver abstraction (ADR-006); promoted in Stage 07
to cover the time-accurate branch and the optional/case-specific scalars that
PyFR + NekRS revealed (ADR-007).

## Invariant 8 — COST-CAP-ENFORCED-CLOUD-EXECUTION

Every rented-GPU launch — RunPod, Lambda Labs, Vast.ai, future Slurm cluster
allocations — passes through a budget check *before* any spend is committed.
The check sums the month-to-date estimated cost from a local append-only ledger
(`/etc/aero/runpod-ledger.json` by default) plus the projected cost of the new
launch and fails loud with a `CostCapExceeded` exception if the result exceeds
the configured ceiling (`AERO_RUNPOD_MONTHLY_CAP_USD`, default `150.0`, raised from
50.0 by ADR-014). Every
launch records a ledger entry pre-execution and is amended with the actual
hours and cost on termination (or marked `tag="ORPHANED"` if termination polling
fails — further launches are then refused until the operator clears the entry
manually).

**Enforcement:** the `aero.orchestration.cost_cap.CostCap.check_budget(...)`
call is the only legal pre-launch gate for any cloud executor; `RunPodExecutor`
(Stage 07) and the future Lambda/Vast executors construct one in `__init__` and
must call it inside `run()` before any pod-spin. A unit test in
`tests/stage_07/test_cost_cap.py` proves the budget overrun raises and the
ledger persists across runs.

**Why:** A peer-review-grade platform with a multi-cloud GPU back end cannot
allow silent cost overruns. The exact failure mode the cap prevents is well-
attested in the field: a runaway `for` loop that launches 30 H100 pods at
~$3/hr, or a terminate-API that returns 200 but leaves billing running. Added
in Stage 07 with the first paid cloud GPU run (ADR-007).

## Invariant 9 — CERTIFICATE-OF-VALIDITY-REQUIRED-FOR-SURROGATE-INVOCATION

*(Text note, Stage 21: the agentic CAE layer was deferred indefinitely by ADR-013. Today the
caller this invariant guards is the surrogate-accelerated optimizer loop (Stage 17, ADR-031/032).
The gate is unchanged.)*

Every call from the agentic CAE layer (Stage 14) to
`aero.surrogates._common.base:Surrogate.predict(...)` is gated on a current
`aero.surrogates._common.certificate:CertificateOfValidity`. "Current" means
**both** of the following hold at invocation time:

1. **Time gate.** `now < certificate.expires_at`. Default lifetime 180 days
   (ADR-008 §D5; 6 months OR training-dataset DVC hash change, whichever
   first). Surrogates that have not been revalidated within the window are
   refused — the agent layer falls back to a validated solver.
2. **Data gate.** `current_dataset_hash == certificate.training_dataset_dvc_hash`.
   The training-dataset DVC hash is recomputed at invocation time via
   `aero.surrogates._common.loaders.dataset_hash(repo_root, dvc_path)`; any
   drift between the value baked into the cert and the current value fails
   the gate.

`CertificateOfValidity.assert_current(current_dataset_hash, now)` is the only
canonical check; it raises `CertExpired` on the first failing gate. The
agent layer wraps the call in `try / except CertExpired` and on failure
routes to a validated solver (Principle 4 — *ML augments, never replaces,
validated physics*).

**Enforcement:** three layers (ADR-008 §D4 covers the related CC-BY-NC
quarantine):

1. **`Surrogate.predict()` base-class guard.** The platform base class
   calls `self.certificate()` at the top of every `predict()`; if no
   cert has been issued (no `set_certificate()` call after `fit()`) the
   guard raises `UncertifiedSurrogate`. Concrete subclasses MUST call
   `self.certificate()` (NOT `self._certificate` directly) at the top
   of their `predict()` implementation so the guard fires before any
   GPU work.
2. **Stage-14 agent runtime call.** Every agent path that resolves to a
   surrogate calls `surrogate.certificate().assert_current(current_dataset_hash,
   now)` immediately before `predict(...)`; on `CertExpired` the agent
   falls back to a validated solver.
3. **Training-time MLflow contract.** The four-fold provenance tuple
   plus the surrogate-specific tags compose into
   `aero.surrogates._common.provenance:SurrogateProvenanceTags`. The
   `aero surrogate train` CLI logs all eight tags and attaches the cert
   JSON as the MLflow artifact `certificates/<name>.json`.

`tests/stage_08/test_surrogate_certificate.py` pins the predict-before-fit
guard, the time gate, and the data gate; `tests/stage_08/
test_drivaernet_quarantine.py` pins the CC-BY-NC taint propagation that
locks `non_commercial=True` into the cert.

**Why:** A surrogate without a verifiable proof of fitness-for-purpose is a
plausibility engine, not a research instrument. Stage 08 codifies the cert
BEFORE the first production surrogate (Stage 09 DoMINO) lands so the
contract is structural, not retrofit. The 180-day expiry catches "set and
forget" drift even on frozen datasets; the data gate catches the dataset
itself drifting. Added in Stage 08 with the surrogate plumbing (ADR-008).

## Invariant 10 — IMPROVEMENT-EXCEEDS-UNCERTAINTY

No reported effect or claimed improvement is thesis-grade unless its
**CFD-verified delta exceeds `k · U95`** (margin `k ≥ 1`, default `k = 2`). The
combined 95% uncertainty is the root-sum-square of three independent
contributions:

```
U95 = sqrt( u95_numerical**2 + u95_statistical**2 + u95_input**2 )
```

where `u95_numerical` is the discretization uncertainty (ASME V&V 20 / Roache
GCI — which covers *only* this), `u95_statistical` is the sampling uncertainty
of a time- or phase-averaged quantity (batch-means / autocorrelation
effective-sample-size, after a periodic-steady-state cycle-convergence check),
and `u95_input` is the parametric uncertainty. For an optimization **delta**,
the baseline and the candidate are evaluated at matched numerics/mesh-topology
so correlated errors cancel — the uncertainty of the delta is then below the
RSS of the two absolute uncertainties.

**Enforcement:** the typed `aero.vv.reportable:ReportableResult` (skeleton lands
Stage 10; full U95 composition Stage 12) is the only object that may carry an
MLflow `validation_tag="thesis-grade"`; its validator asserts
`abs(delta) > k * u95_total` (default `k = 2`, never `k < 1`) for any
`ImprovementClaim`. CI job `small-signal-gate` (required, landed Stage 12; ADR-020)
re-runs the assertion. `u95_delta` is *measured* by the paired-difference estimator
(`aero/vv/paired_difference.py` — NOBM on the per-cycle difference series over the
common converged window, with the empirical baseline↔candidate correlation recorded)
and composed by `compose_improvement()`; a hand-entered `u95_delta` cannot reach
`thesis-grade` (landed at the review-F1 remediation; ADR-023). The pattern mirrors
Invariant 5's "enforcement tooling lands at a named stage."

**Why:** the platform's product is *trustworthy improvements*. A claimed
improvement smaller than the solver's own uncertainty is numerical noise, not a
result. GCI alone is insufficient for unsteady flows; the three-part U95 closes
that hole, and the matched-condition delta is what makes a small but real
improvement defensible. Added at the optimizer-mission refocus (ADR-013/015).

## Invariant 11 — NO-SURROGATE-ON-FOREIGN-DATA

Surrogates train only on the platform's **own validated CFD**. A foreign dataset
(automotive, transport-aircraft, or any corpus the platform did not generate and
validate) may seed `smoke`-tier experiments but **cannot produce a `validated`
or `production` `CertificateOfValidity`**.

**Enforcement:** the `Sample` / `TaintedSample` union and `CertificateOfValidity`
carry `data_origin: Literal["platform-validated", "foreign"]` (landed Stage 12;
ADR-020; reuses the Stage-08 CC-BY-NC taint machinery); `promote_to_validated(...)`
raises on `data_origin == "foreign"`, and a foreign + validated/production cert is
unconstructible (schema validator). CI adds the `data-origin-fence` alongside `non-commercial-fence`
workflow to assert that every loader under
`aero/surrogates/_common/loaders/` emits `data_origin="foreign"` and that no
`validated`/`production` cert is constructible from foreign-origin samples.

**Why:** the optimizer's surrogates accelerate *its own* design space; a
surrogate trained on car shapes cannot certify a wing prediction, and
cross-domain neural-operator transfer is unresolved in the literature. Training
on own validated CFD (the data flywheel the optimization loop produces) keeps
the certificate meaningful. Added at the optimizer-mission refocus (ADR-013/015).

## Invariant 12 — CFD-VERIFIED-OPTIMUM-ONLY

Every reported optimum is verified by a ground-truth CFD run before it is
reported; no optimum is claimed on a surrogate prediction alone. Best-of-N
reporting is selection-bias-aware: the reported optimum is verified on a
**held-out** CFD evaluation not seen by the optimizer, and the pool size N
(`n_candidates`) is recorded.

**Enforcement:** `aero/vv/reportable.py::OptimizationResult` carries the
four-fold provenance of the verifying ground-truth CFD run (`cfd_verified`) and
refuses to construct a best-of-N result (`n_candidates > 1`) without
`held_out_verification`; `aero/optimize` evaluates every candidate by direct
CFD (ADR-026). Guards the documented AI-scientist failure modes (Luo,
Kasirzadeh & Shah, arXiv:2509.08713: post-hoc selection bias, metric misuse,
data leakage).

**Why:** the optimizer's only product is a *trustworthy* improvement; a
surrogate-predicted or selection-biased optimum is exactly the hallucinated
result the platform exists to refuse. Pairs with Invariant 10 (the improvement
must also exceed its uncertainty). Promoted from CLAUDE.md Hard Rule 14 per
ADR-027 (proposed 2026-07-10; ≥72 h window elapsed 2026-07-13; ratified
2026-07-15, operator-delegated).

## Invariant 13 — RESULTS-MUST-TRAVEL

Every result the platform reports outside the repository is a self-describing **result crate**
(`aero-result-crate` format v1, ADR-047).

**What a crate carries:**
- the exact as-hashed CaseSpec bytes of every run it cites, whose sha256 *is* the recorded
  `config_hash`;
- the four-fold provenance tuple (Invariant 3);
- the U95 envelope (Invariant 10);
- its **validity context**: claim tier, pre-registered gate verdicts kept apart from reported
  diagnostics, applicability bounds, and the limitations its own content makes mandatory.

**Portability.** A crate verifies, and reads back to the same numbers, without the cluster, the DVC
remotes, MLflow or the repository.

**Partial results.** A result that cannot carry its four-tuple, U95 or CaseSpec travels only as an
**evidence-only** crate. Such a crate declares each missing component and carries no claim.

**Enforcement:**
- **One writer and reader.** `aero/crate/` (stdlib + numpy + pydantic only) is the one writer and
  reader. `verify_crate`:
  - hashes every member before parsing it;
  - refuses unknown or unsafe members, duplicate keys and non-finite numbers;
  - recomputes every computed field bit for bit, and refuses content the schema would drop;
  - checks every config preimage against its hash;
  - enforces the required limitations;
  - regenerates the RO-Crate 1.3 / Process Run Crate 0.6 and PROV-JSON projections byte for byte.
- **Required checks:**
  - `pytest unit (py3.12)`: the round-trip, tamper, archive-safety, import-isolation and
    committed-crate tests;
  - `crate round-trip — Invariant 13`: crates are written on one runner, moved, and verified on
    fresh Linux, macOS and Windows runners that hold only the built wheel, numpy and pydantic. The
    numbers are compared bit for bit against an independent stdlib oracle built from the
    committed records.
- **Immutability.** Published crates are immutable; format changes need format v2 and an ADR.
- **Citation.** A result is cited by its crate digest (the sha256 of its `SHA256SUMS`) together with
  its four-tuple.

**Why:** a number that cannot leave the cluster cannot be checked by anyone else. The result crate
is what makes a thesis- or paper-grade claim reproducible from the artifact alone. It also makes the
limits of a claim travel with the number. Promoted from CLAUDE.md Hard Rule 16 per ADR-047
(proposed 2026-10-12; ratified by the merge of the Stage-21 constitution PR, after the ≥72 h
window and the operator's recorded sign-off).

## Amendment process

To amend a Constitution invariant:

1. Open an ADR proposing the change with rationale.
2. Open a PR that updates both `CONSTITUTION.md` and the ADR.
3. Wait at least 72 h for review (longer than the standard 24-hour
   cooling-off, since invariants are load-bearing).
4. Operator approves; CI green; merge; CHANGELOG entry under the next
   `v0.0.NN` or `v0.x.y` section.
