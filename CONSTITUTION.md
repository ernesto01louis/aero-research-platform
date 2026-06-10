# Constitution

This document codifies the non-negotiable design rules of
`aero-research-platform` in [GitHub Spec-Kit](https://github.com/github/spec-kit)
compatible form. Any change to this file requires an ADR explaining the
rationale, signed off by the operator, and a CHANGELOG entry.

## Invariant 1 — PLATFORM-NOT-HUB

The `aero/` core imports only stdlib + `numpy` + `pydantic`. Every solver,
ML framework, cloud SDK, and physics library is gated behind an optional
extra (`aero[openfoam]`, `aero[su2]`, `aero[pyfr]`, `aero[nekrs]`,
`aero[jax-fluids]`, `aero[physicsnemo-cu12]`, `aero[precice]`,
`aero[gpu-rental]`, `aero[uq]`, `aero[agentic]`, `aero[literature]`,
`aero[orchestration]`).

**Enforcement:** CI job `import-platform-only` (live by Stage 06) runs
`pip install aero` (no extras) in a fresh venv and asserts `import aero`
succeeds without `Torch`/`JAX`/`PhysicsNeMo`/`OpenFOAM`/etc. The job is a
required status check on `main`.

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
   pulled from `containers/SHA256SUMS`
4. `config_hash` — sha256 of the resolved Hydra config serialized as
   canonical JSON

Postgres mirror table `aero_provenance.mlflow_artifact_provenance` (Stage
04+) indexes these for fast cross-run queries.

**Enforcement:** CI job `provenance-completeness` (live by Stage 04) runs
the walking-skeleton case and asserts all four tags are populated on the
resulting MLflow run, plus the Postgres mirror row exists. Required status
check on `main`.

**Why:** A peer-review-grade platform must produce citable results; the
four-tuple is the citation. Without it, a published number is a guess.

## Invariant 4 — HEAVY-DEPS-IN-OPTIONAL-EXTRAS-ONLY

Every dependency that pulls in a compiled toolchain, a >100 MB wheel, a
CUDA wheel, a JAX-fluids-style domain library, a cloud-provider SDK, or
proprietary connectivity must live in an optional extra. Base `aero`
installs with only `numpy`, `pydantic`, `typer`, `loguru`, `dvc`.

**Enforcement:** Same `import-platform-only` CI job as Invariant 1.

**Why:** Researchers reading our code should be able to inspect the core
abstractions without provisioning a 30 GB CUDA environment.

## Invariant 5 — LICENSE-POSTURE — GPL-3 / LGPL-3 / Apache-2 / BSD-3 only

No proprietary blob enters this repository or its container images. No
Intel MKL closed-source builds. No commercial CFD or CAE dependency. The
platform itself is **GPL-3.0**; any compatible permissive license among
the four listed is acceptable for dependencies.

**Enforcement:** ADR required for every new heavy dependency, naming the
license and demonstrating compatibility. CI license-scan tooling lands in
Stage 16.

**Why:** Reproducibility for peer review requires an open stack. A
researcher reading our paper must be able to install everything we used
without a commercial license. The orchestrator project's lesson on this
was clear.

## Invariant 6 — CONVENTIONAL-COMMITS + CONVENTIONAL-COMMENTS

Commit format: `<type>(stage-NN): <subject>`. PR review comments use
Conventional Comments labels (`praise:`, `nitpick:`, `suggestion:`,
`issue:`, `todo:`, `question:`, `thought:`, `chore:`, `note:`).

**Enforcement:** `commit-lint` CI check enforces commit format on every
commit and the PR title. Conventional Comments are a humans-and-agents
convention enforced by review discipline, not CI.

**Why:** A 16-stage build with frequent context handoffs to fresh Claude
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
the configured ceiling (`AERO_RUNPOD_MONTHLY_CAP_USD`, default `50.0`). Every
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
`ImprovementClaim`. CI job `small-signal-gate` (required, lands Stage 12)
re-runs the assertion. The pattern mirrors Invariant 5's "enforcement tooling
lands at a named stage."

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
carry `data_origin: Literal["platform-validated", "foreign"]` (lands Stage 12,
reusing the Stage-08 CC-BY-NC taint machinery); `promote_to_validated(...)`
raises on `data_origin == "foreign"`. CI extends the `non-commercial-fence`
workflow to assert that every loader under
`aero/surrogates/_common/loaders/` emits `data_origin="foreign"` and that no
`validated`/`production` cert is constructible from foreign-origin samples.

**Why:** the optimizer's surrogates accelerate *its own* design space; a
surrogate trained on car shapes cannot certify a wing prediction, and
cross-domain neural-operator transfer is unresolved in the literature. Training
on own validated CFD (the data flywheel the optimization loop produces) keeps
the certificate meaningful. Added at the optimizer-mission refocus (ADR-013/015).

## Amendment process

To amend a Constitution invariant:

1. Open an ADR proposing the change with rationale.
2. Open a PR that updates both `CONSTITUTION.md` and the ADR.
3. Wait at least 72 h for review (longer than the standard 24-hour
   cooling-off, since invariants are load-bearing).
4. Operator approves; CI green; merge; CHANGELOG entry under the next
   `v0.0.NN` or `v0.x.y` section.
