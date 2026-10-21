# ADR-050 — An outsider-reproducible CFD number: a hosted, CPU-only end-to-end case that emits one number and its four-tuple

- **Status:** **accepted as amended** — written at Stage 21 (operator decision 2026-10-13: "write the
  ADR now, build later"); amended 2026-10-21 at Stage 23 after the operator's decision D5 ("Amend:
  cluster SIF, no crate"), and the amended text was **accepted by the operator on 2026-10-21**
  ("Accept as amended"); the acceptance is recorded by the commit that lands it. The amendments are
  listed in the change history at the end. It changes no release gate.
- **Date:** 2026-10-13 (amended 2026-10-21)
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 21; amended at
  Stage 23)
- **Stage:** 21 (proposal); implementation in Stage 23, Foundation II (ADR-051 row 23)
- **Supersedes:** none. As amended it changes no result-crate format and adds no provenance file. It
  uses the Stage-23 semantics of ADR-052 (`dvc_input_hash`) and ADR-053 (`container_sif_sha256`).

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
   `LocalSSHExecutor` (SSH to the aero LXCs) and `RunPodExecutor`. Every OpenFOAM run goes through
   `build_apptainer_exec` on an LXC.
2. **The OpenFOAM image is public and digest-pinned.** `containers/openfoam-esi.def` wraps
   `opencfd/openfoam-default:2412@sha256:1ba02114b1c025c370f2e269a07677c16c9bea8d990fcd75ac8378aff9d41b50`
   and adds the `/case`, `/work` and `/opt/aero` bind points (`%post`) and `LC_ALL`/`LANG`
   (`%environment`). The SIF's own sha256 (`c9d7f329…` in `containers/SHA256SUMS`) is the cluster
   artefact. A SIF built from the same OCI image elsewhere is not byte-identical, and the raw image
   lacks the recipe's bind points and locale.
3. **Before Stage 23, two of the four terms had no off-cluster meaning** (the change history below
   records how ADR-052 and ADR-053 remove both obstacles once implemented):
   - `dvc_input_hash` was the sha256 of a repository-wide `dvc status -c` against the configured
     remote; a hosted runner has no remote credentials. ADR-052 replaces it with a content address of
     the declared `.dvc` pointers, computed from git alone.
   - `container_sif_sha256` was a basename lookup in `containers/SHA256SUMS`, which names no SIF that a
     hosted runner runs; ADR-053 checks the bytes at every launch, on whatever host launches.
4. **MLflow is cluster-only, but Invariant 3 and Hard Rule 3 ("Every run logs the four-tuple to MLflow
   tags. No exceptions.") apply to every run.** A hosted run therefore logs to its own run-local
   MLflow store and a throwaway Postgres mirror, and never to the platform's tracking server.

## Decision drivers

- **Portability, not physics.** The artefact proves an outsider can reproduce the pipeline. It must
  never be presented as a validation or optimization claim (record-faithful wording, D4).
- **FAIL-LOUD provenance.** No term of the four-tuple may silently mean something else. As amended,
  each hosted term has exactly the meaning it has on the cluster.
- **Like for like.** The hosted run executes the same container bytes, the same case spec and the same
  solver invocation as the cluster, so a reproducibility band compares two machines, not two builds.
- **PLATFORM-NOT-HUB and Principle 2 (compute is fungible).** A local container executor is a
  legitimate backend. It must not leak runner specifics into `aero/` core.
- **Free, fast and pinned.** It runs on `ubuntu-24.04` hosted runners in under about 15 minutes, with
  the container digest and the runtime version pinned.

## Considered options

1. **Do nothing; the crate round trip suffices.** Rejected (operator): it leaves the
   recompute-from-repo gap open.
2. **A hosted runner with Docker running the pinned OCI image directly.** It needs a second command
   builder. Rejected.
3. **A hosted runner with a pinned Apptainer pulling `docker://…@sha256:…`.** Chosen at Stage 21;
   superseded by the amendment (A3): the pulled image is not the cluster's container, so the container
   term would need a third meaning and an Invariant 3 item-3 amendment.
4. **A hosted runner with a pinned Apptainer running the cluster's own SIF**, downloaded and checked
   against `containers/SHA256SUMS`. Chosen by the amendment (operator, 2026-10-21).
5. **Building the SIF on the runner from `containers/openfoam-esi.def`.** Considered at Stage 23 and
   rejected: same recipe, but different bytes, hence a third container meaning.
6. **A self-hosted round trip.** Rejected: it does not close the outsider gap.

## Decision outcome

### D1 — The case and its one number

`blasius_flat_plate` is the registered forward-regime case: a laminar flat plate (Re_L = 1e5,
M = 0.1, OpenFOAM `simpleFoam`, laminar) compared against the analytic Blasius `Cf` law.
- It is steady and laminar, and runs on one CPU (about a minute in the cluster's `vv-smoke`).
- Its reference is the analytic law, tabulated in the **git-tracked**
  `data/references/forward_regime/blasius_flat_plate/cf.csv`, which has no `.dvc` pointer. It
  declares no DVC inputs (ADR-052).
- **The number is `cf_mid`**: the wall `Cf` at the sample whose `x` is nearest `0.5 L` (`x = 1.0`
  for the default `L = 2.0`), among the samples with `0.1 ≤ x ≤ L`
  (`aero/vv/forward_regime/blasius_flat_plate.py:86-100`; the case's `sweep_metric`). It is recorded
  as a float and as `float.hex`.

If the hosted wall time exceeds 15 minutes, a coarser variant is built by the hosted driver, with its
mesh written into this ADR before its first run. It is **not** registered in `aero/vv/stacks.py`
(registering it would add a missing case to the OpenFOAM gate). Its band reference is
then a cluster run of that variant by the same driver, committed before its first hosted run (D5). The
production case is never coarsened in place.

### D2 — Execution

- **A new `LocalContainerExecutor`** in `aero/orchestration/local_container.py`. It runs the command
  with `subprocess` on the current host, with no SSH, and satisfies the existing `Executor` protocol,
  including `transport_error`.
- **Apptainer 1.5.0 comes from the cluster's own pinned release `.deb`** (sha256
  `fbc27204d0ec0440dfa0ae589089e4b2baf192315b4ac22dfae02b78b28981ea`,
  `ansible/roles/aero-apptainer/defaults/main.yml`), checked in the workflow.
- **The container is the cluster's `openfoam-esi.sif`** (`c9d7f329…`, 455.6 MB), published by the
  operator as a release asset under a non-`v` tag with a GPL-3 source note (the OpenFOAM source and
  `containers/openfoam-esi.def`). The job downloads it, checks its sha256 against
  `containers/SHA256SUMS` at the run's `git_sha`, and launches it under ADR-053's guard.

### D3 — The four-tuple off-cluster: the same terms as on the cluster

| Term | Hosted (= cluster, same commit) |
|---|---|
| `git_sha` | `git rev-parse HEAD`; the workflow refuses a dirty tree |
| `config_hash` | sha256 of the canonical case spec, `spec.model_dump(mode="json")` (the `aero vv run` convention, `aero/cli.py:694`): `d1d264c5…` |
| `dvc_input_hash` | ADR-052, scheme `declared-dvc-pointers-md5/v1`: the case declares no inputs, so the canonical empty set `1ef5b7d9a694e703ccb270937035bdcc006487fa5a5b6fd92ac9c10f94453ec3` — never sha256(`{}`), the legacy value |
| `container_sif_sha256` | ADR-053, scheme `sif-sha256-verified-at-launch/v1`: `c9d7f329…`, checked before every launch on the runner |

For the same commit and the same scheme tags, a clean-tree cluster Blasius run and the hosted run
carry the same four terms; a CI V&V run need not, because `tests/vv/conftest.py:196` passes
`allow_dirty=True` and its `git_sha` can carry `-dirty`. No off-cluster meaning and no
`containers/OCI-DIGESTS` file exist.

### D4 — The output: a run record, not a crate, and no platform MLflow

- **The run logs through the cluster's `start_provenance_run`** to a run-local MLflow tracking store
  (sqlite under the runner's temp directory, experiment `aero-hosted-repro`) and a throwaway Postgres
  mirror built with `alembic upgrade head`, so Invariant 3 and Hard Rule 3 hold unchanged. It never
  contacts the platform's tracking server: a hosted run must never become the V&V gate's newest
  Blasius evidence.
- **The output is a typed run record**, uploaded as an artifact and cited by its sha256 in the job
  summary: the run-local MLflow store, the mirror row, the read-back JSON, the canonical config
  bytes (`configs/<config_hash>.json`) and the logs. Anyone can recompute `dvc_input_hash` (from the
  `dvc_inputs` tag) and `config_hash` from it with a stdlib one-liner. Workflow artifacts expire, so the
  citable run's record digest and run URL are committed in the Stage-23 proof record.
- **No result crate this stage.** A crate that is honest about new-semantics runs needs crate format
  v2 (ADR-047 D7): under v1, `rules.py:42-43` forces both old-weakness limitations and the projection
  labels every container `SIFImage`; and the number has no U95, so it could only travel as an
  evidence-only crate. Crate v2 is ledgered.
- **Record-faithful wording.** The number is a CI reproducibility check of the pipeline, not a
  platform result (Invariant 13): release notes may say the check ran and passed, never quote `cf_mid`
  as a result. The Blasius comparison is a diagnostic, never a gated verdict.

### D5 — CI

- **`hosted-repro.yml`** runs on `ubuntu-24.04`. It is non-required, scheduled weekly, runnable by
  `workflow_dispatch`, and runs on PRs that touch `aero/adapters/openfoam/**`, `aero/adapters/_base.py`,
  `aero/provenance/**`, `aero/orchestration/local_container.py`, `aero/vv/_base.py`,
  `aero/vv/forward_regime/**`, `containers/SHA256SUMS`, its driver scripts,
  `ci/hosted-repro/**` or itself. Its actions are SHA-pinned; it holds no secret and declares
  `permissions: contents: read`. It:
  1. installs the pinned Apptainer;
  2. downloads and checks the SIF;
  3. runs the case and logs locally;
  4. reads the run back (`scripts/provenance_readback.py`) and checks the band;
  5. uploads the run record.
- **The gated, pre-registered band.** `|cf_mid_h − cf_mid_c| / |cf_mid_c| ≤ 0.01`, where `cf_mid_c`
  comes from a cluster run of the same driver and case through `LocalSSHExecutor`, on a clean tree, at
  the same `config_hash`, `dvc_input_hash` and container digest and under the same scheme tags (a
  standard `aero vv run` logs `cf_error`, never `cf_mid`: `aero/vv/_base.py:451-468`), recorded in
  `ci/hosted-repro/reference.json` (run id, tags, `cf_mid` as float and `float.hex`) **before the
  workflow's first execution**, so the first hosted run is a test, not its own reference.
  It is **never** compared bitwise (floating-point results legitimately differ across CPUs), and a
  miss fails the workflow loudly. The band is never widened after the fact.
- **The diagnostic.** The pointwise maximum relative error against Blasius over `0.1 ≤ x ≤ L` is
  reported against the case's 5 % tolerance; it gates nothing.
- **A negative step.** A one-byte-flipped copy of the SIF under the same name must exit 86 with
  `AERO-SIF-REFUSED`, and apptainer must never start (ADR-053).
- **Only a `workflow_dispatch` or scheduled run on `main` is citable**; a PR run executes on an
  ephemeral merge ref.

## Consequences

- **Positive:**
  - anyone can recompute one CFD number, with its full provenance, from the public repository and one
    published container on free CI, and compare it with the cluster's number at the same
    `config_hash`, `dvc_input_hash` and container digest (the reference run's `git_sha` is earlier by
    construction);
  - the hosted run exercises ADR-052 and ADR-053 end to end on a machine the platform does not own.
- **Negative:**
  - one new executor;
  - the operator publishes a 455.6 MB GPL-3 container (a network write, with a source note), and an
    outsider downloads a platform-built artefact rather than upstream's image; its digest is anchored
    in `containers/SHA256SUMS`;
  - a weekly hosted CI cost (free for public repositories);
  - no crate until crate format v2.
- **Out of scope:**
  - any physics claim, or any optimizer run on hosted CI;
  - flexible or coupled FSI; coupled restart transparency stays ADR-045 A19 / ADR-046 S5.

## Change history

**2026-10-21, Stage 23 — amended before its first run** (operator decision D5, "Amend: cluster SIF, no
crate"). Each replaced decision, and why:

- **A1 (D3, DVC term).** Was "the sha256 of the canonical empty input set (`{}`)". That value is
  `44136fa3…`, the legacy empty-status digest (an empty `dvc status -c` or an empty stdout; ADR-052)
  carried by 1549 recorded runs, so old and new could not be told apart by value. Now ADR-052's
  domain-separated empty set, `1ef5b7d9…`.
- **A2 (D3, container term).** Was "the OCI manifest digest of the pinned image, recorded in a new
  `containers/OCI-DIGESTS` file and looked up by name". That name lookup is the weakness O-08 removes,
  and the digest (`1ba02114…`) is an OCI image-index digest, not the cluster's container. Now the
  cluster's own SIF, checked at launch (ADR-053).
- **A3 (D2, image source).** Was `docker://opencfd/openfoam-default@sha256:1ba02114…`. That image is not
  byte-identical to the cluster SIF and lacks its bind points and locale, so the run was not like for
  like. Now the published cluster SIF.
- **A4 (D2, runtime pin).** "A pinned release `.deb`" is now the cluster's own Apptainer 1.5.0 pin.
- **A5 (D4, MLflow).** Was "No tracking server is contacted" with `Unavailable(item="mlflow_run")`. That
  conflicts with Invariant 3 and Hard Rule 3. Now a run-local MLflow store and a throwaway Postgres
  through the cluster's own `start_provenance_run`.
- **A6 (D4, crate).** Was a format-v1 crate with a new claim scope `reproducibility-proof`, "an additive
  schema extension". ADR-047 D7 and CONSTITUTION Invariant 13 make any change to the rules or the
  projections format v2 plus an ADR; v1 would force false limitation ids; and a number without U95 is
  evidence-only. Now a typed run record; crate v2 ledgered.
- **A7 (D1/D5, the number and the gate).** The number was never named, and D4's "reported as a
  diagnostic gate, never a gated verdict" contradicted D5's "a miss fails the workflow". Now `cf_mid` is
  named, the 1 % band is the gated criterion, and the Blasius 5 % comparison is the diagnostic.
- **A8 (D5, the reference).** Was "a committed reference value from the first successful run", which
  makes that run its own reference. Now the cluster run at the same `config_hash`, committed before
  any hosted execution.
- **A9 (D1, the fallback).** The coarser `blasius_flat_plate_ci` is no longer "registered", which would
  have added a missing case to the OpenFOAM gate.
- **A10 (drivers, scope, title).** The driver "Each off-cluster term must be named, typed and stated
  as a limitation" is replaced by "each hosted term has exactly the meaning it has on the cluster" (A1,
  A2), and "Like for like" is added. "Out of scope: Changing the cluster's provenance semantics" is
  withdrawn: the hosted run relies on ADR-052 and ADR-053 changing them. The title drops "and a result
  crate" (A6), and the "2 vCPUs" runner figure is dropped.
- **A11 (D3, D5).** D3's refusal of a case that declares DVC inputs, and its sentence forbidding a
  relabel elsewhere, are dropped: the hosted case declares none, and ADR-052's reading rule forbids
  relabelling. D5's PR triggers are widened from "the solver adapter" to the listed paths, and the
  SIF-tamper negative step and the citable-on-`main` rule are added.

## Links

- ADR-004 (four-fold provenance), ADR-047 (result crates), ADR-049 (H-33, O-07, O-08), ADR-051 (row
  23), ADR-052 (`dvc_input_hash`), ADR-053 (the launch guard).
- CONSTITUTION Invariants 3 and 13.
- `containers/openfoam-esi.def`, `containers/SHA256SUMS`, `ansible/roles/aero-apptainer/defaults/main.yml`.
- External review addendum, 2026-10-11 (item B).
- Stage prompt `docs/handoff-bundle/STAGE-23-foundation-provenance.md`; the operator's decision D5
  (2026-10-21): `docs/handoffs/STAGE-23-foundation-provenance-DONE-2026-10-21.md` §2.
