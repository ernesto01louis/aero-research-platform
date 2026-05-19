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

## Invariant 7 — TYPED-CONVERGENCE-HISTORY

Every solver adapter's `Solver.load()` returns a typed `SolveResult` carrying
a `ConvergenceHistory` — the monitored residual as a validated equal-length
`(iteration, residual)` series — never a solver-native container
(`xarray.Dataset`, raw dict, CSV path). Converged scalars (`cd`, `cl`,
`iterations_to_convergence`, `final_residual`) are typed fields on
`SolveResult`, not `.attrs`-style untyped metadata.

**Enforcement:** the V&V harness types `solver.load(result)` as
`SolveResult` against the `aero.adapters._base.SolverProtocol`. A
per-adapter test asserts `isinstance(result, SolveResult)`; mypy `--strict`
on `aero/adapters/_base.py` pins the schema. The `import-platform-only` CI
job verifies the typed result types are usable without any solver extra
installed.

**Why:** Convergence history is the primary evidence a CFD result is
trustworthy. If it is trapped in a solver-native format, the V&V dashboard,
the UQ layer (Stage 12), and any cross-solver comparison must each learn N
formats. A typed series is the citation-grade contract. Added in Stage 06
when SU2 forced the multi-solver abstraction (ADR-006); the OpenFOAM adapter
was migrated off `xr.Dataset.attrs[...]` to the typed schema in the same PR.

## Amendment process

To amend a Constitution invariant:

1. Open an ADR proposing the change with rationale.
2. Open a PR that updates both `CONSTITUTION.md` and the ADR.
3. Wait at least 72 h for review (longer than the standard 24-hour
   cooling-off, since invariants are load-bearing).
4. Operator approves; CI green; merge; CHANGELOG entry under the next
   `v0.0.NN` or `v0.x.y` section.
