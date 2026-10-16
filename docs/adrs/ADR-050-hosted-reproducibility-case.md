# ADR-050 — An outsider-reproducible CFD number: a hosted, CPU-only end-to-end case that emits one number, its four-tuple and a result crate

- **Status:** proposed. Written at Stage 21 (operator decision 2026-10-13: "write the ADR now,
  build later"). It is implemented after v0.1.0. It is not a v0.1.0 deliverable, and it changes no
  release gate.
- **Date:** 2026-10-13
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 21)
- **Stage:** 21 (proposal); implementation in Stage 23, Foundation II (ADR-051)
- **Supersedes:** none. It extends ADR-047 (result crates) with one new claim scope. It interacts
  with the ledgered O-07 (content-addressed `dvc_input_hash`).

## Context and problem statement

An external review (2026-10-11) observed that **every physics number the platform reports was
computed on self-hosted runners** against the private Proxmox / Apptainer stack. An outsider
can verify a published result crate (Invariant 13): the crate round trip proves that on clean
Linux, macOS and Windows machines. What an outsider cannot do is **recompute a CFD number from
the repository alone.** The review's other claim, that the reference data is DVC-only, is wrong:
28 CSV/DAT reference files are in-repo, against 10 `.dvc` pointers.

The Stage-21 gate "bundle round-trips on a clean machine" is already met by
`crate round-trip — Invariant 13`. This ADR is about the narrower, real gap: one end-to-end solve
that anyone can rerun on free hosted CI.

Four facts frame the design:
1. **There is no local executor.** `aero/orchestration/` implements two executors:
   `LocalSSHExecutor` (SSH to the aero LXCs) and `RunPodExecutor`. The `lambda_labs/`, `vast/`
   and `slurm/` directories contain no executor yet. Every OpenFOAM run goes through
   `build_apptainer_exec` on an LXC.
2. **The OpenFOAM image is already public and digest-pinned.** `containers/openfoam-esi.def`
   wraps `opencfd/openfoam-default:2412@sha256:1ba02114b1c025c370f2e269a07677c16c9bea8d990fcd75ac8378aff9d41b50`.
   The SIF's own sha256 (`c9d7f329…` in `containers/SHA256SUMS`) is the cluster artefact. A SIF
   built from the same OCI image elsewhere is not byte-identical.
3. **Two of the four tuple terms change meaning off-cluster:**
   - `container_sif_sha256` is a basename lookup in `containers/SHA256SUMS` (ADR-004; documented
     weakness H-33). A hosted runner has no SIF of record.
   - `dvc_input_hash` is the sha256 of `dvc status -c` against the configured remote. A hosted
     runner has no remote credentials, so the command fails.

   CONSTITUTION Invariant 3 actually defines the DVC term over "the `.dvc`-tracked inputs *the
   case touches*". The implementation hashes the whole repository's sync state. That divergence
   is the ledgered O-07.
4. **MLflow is cluster-only.** Hard Rule 3 says every run logs the four-tuple to MLflow tags. A
   hosted run has no tracking server.

## Decision drivers

- **Portability, not physics.** The artefact proves an outsider can reproduce the pipeline. It
  must never be presented as a validation or optimization claim (record-faithful wording, D2).
- **FAIL-LOUD provenance.** No term of the four-tuple may silently mean something else. Each
  off-cluster term must be named, typed and stated as a limitation.
- **PLATFORM-NOT-HUB and Principle 2 (compute is fungible).** A local container executor is a
  legitimate backend. It must not leak runner specifics into `aero/` core.
- **Free, fast and pinned.** It runs on `ubuntu-24.04` hosted runners in under about 15 minutes on
  2 vCPUs, with the image digest and the runtime version pinned.

## Considered options

1. **Do nothing; the crate round trip suffices.** Rejected (operator): it leaves the
   recompute-from-repo gap open.
2. **A hosted runner with Docker running the pinned OCI image directly.** Docker is preinstalled
   on hosted runners. But the adapter's command builder is Apptainer-shaped, so this needs a
   second command builder.
3. **A hosted runner with a pinned Apptainer release running `docker://…@sha256:…`.** Chosen. It
   keeps `build_apptainer_exec` unchanged and the solver invocation byte-identical to the
   cluster's. Only the executor and the image source differ.
4. **A self-hosted round trip.** Rejected: it does not close the outsider gap.

## Decision outcome

### D1 — The case

`blasius_flat_plate` is the registered forward-regime case: a laminar flat plate compared against
the analytic Blasius `Cf` law, with a 5 % tolerance.
- It is steady and laminar.
- Its reference is the analytic law, tabulated in the **git-tracked**
  `data/references/forward_regime/blasius_flat_plate/cf.csv`, which has no `.dvc` pointer. So it
  touches **no DVC-tracked inputs**.
- It runs on one CPU.

If the measured wall time on a 2-vCPU hosted runner exceeds 15 minutes, a coarser registered
variant (`blasius_flat_plate_ci`) is added, with its mesh written into this ADR before the first
run. The production case is never coarsened in place.

### D2 — Execution

- **A new `LocalContainerExecutor`** in `aero/orchestration/local_container.py`. It runs the
  command with `subprocess` on the current host, with no SSH, and satisfies the existing
  `Executor` protocol, including `transport_error`.
- **Apptainer comes from a pinned release `.deb`.** Its sha256 is checked in the workflow.
- **The image source is `docker://opencfd/openfoam-default@sha256:1ba02114…`.** It is pulled by
  digest, never by tag.

### D3 — The four-tuple off-cluster

Each term stays present and typed:

| Term | On the cluster | On a hosted runner (this ADR) |
|---|---|---|
| `git_sha` | `git rev-parse HEAD` (clean tree) | same; the workflow refuses a dirty tree |
| `config_hash` | sha256 of the canonical resolved config | same, unchanged |
| `container_sif_sha256` | SIF sha256 by basename from `containers/SHA256SUMS` | the **OCI manifest digest** of the pinned image, recorded in a new `containers/OCI-DIGESTS` file (`<digest>  <name>`) and looked up by name exactly like the SIF. The crate's container `Reference` says `oci` |
| `dvc_input_hash` | sha256 of the repo-wide `dvc status -c` sync state | for a case that **declares no DVC inputs**: the sha256 of the canonical empty input set (`{}`), computed without contacting a remote. A case that declares DVC inputs is refused on a hosted runner (fail-loud). |

The DVC row is the Invariant-3 definition, "the inputs the case touches", applied honestly to a
case that touches none. It is the first, narrow step of O-07. It must not be used to relabel a
repo-wide sync-state hash elsewhere.

### D4 — The output is a result crate, not an MLflow run

- **No tracking server is contacted.** The run is exported as an `aero-result-crate`, which:
  - declares `Unavailable(item="mlflow_run")`;
  - has claim tier `smoke`;
  - uses a **new claim scope `reproducibility-proof`**.

  That scope is an additive schema extension to ADR-047 format v1. Existing crates verify
  unchanged, and adding it is this ADR's change to the frozen format.
- **Required limitations** for that scope, enforced by `rules.py`:
  - `not-a-physics-claim`: a portability proof of the pipeline, not a validation result;
  - `hosted-provenance`: the container and DVC terms carry the off-cluster meanings in D3;
  - `no-experiment-anchor`.
- **The Blasius comparison** is reported as a **diagnostic** gate, never a gated verdict.

### D5 — CI

- **`hosted-repro.yml`** runs on `ubuntu-24.04`. It is non-required, scheduled weekly, runnable
  by `workflow_dispatch`, and on PRs that touch the solver adapter. It:
  1. installs the pinned Apptainer;
  2. runs the case;
  3. writes and verifies the crate;
  4. uploads it.
- **It compares the number against two bands:**
  - against Blasius, within the case's 5 % diagnostic tolerance;
  - against a committed reference value from the first successful run, within a pre-registered
    reproducibility band of **1 % relative**, recorded here before that first run.

  It **never** compares bitwise: floating-point results legitimately differ across CPUs.
- **A miss fails the workflow loudly.** The band is never widened after the fact.

## Consequences

- **Positive:**
  - Anyone can recompute one CFD number, with its full provenance, from the public repository on
    free CI.
  - The provenance code gains its first honest off-cluster semantics, a step toward O-07.
- **Negative:**
  - One new executor.
  - One new provenance file (`containers/OCI-DIGESTS`).
  - One additive crate-schema value.
  - A weekly hosted CI cost (free for public repositories).
  - The OCI digest is not the cluster SIF digest, so a hosted number and a cluster number are
    two runs under two container identities, and the crate says so.
- **Out of scope:**
  - Any physics claim, or any optimizer run on hosted CI.
  - Flexible or coupled FSI. Coupled restart transparency stays ADR-045 A19 / ADR-046 S5.
  - Changing the cluster's provenance semantics.

## Links

- ADR-004 (four-fold provenance), ADR-047 (result crates), ADR-049 (H-33, O-07, O-08).
- CONSTITUTION Invariants 3 and 13.
- `containers/openfoam-esi.def`.
- External review addendum, 2026-10-11 (item B).
