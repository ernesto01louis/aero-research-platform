---
stage: 23
stage_name: "Stage 23 — Foundation II: Provenance You Can Trust"
status: partial
date_started: 2026-10-21
date_completed: 2026-10-21
session_duration_hours: 3
claude_code_version: "2.1.150 (Claude Code)"
model: "claude-opus-5-5"
git_sha_start: 0c96e45d41a8a9a13fa4c00af69d562ea9a13544
git_sha_end: 0c96e45d41a8a9a13fa4c00af69d562ea9a13544
stage_tag: v0.1.2
next_stage: 24
next_stage_name: "Stage 24 — Foundation III: Run the Registry"
---

# Stage 23 — Foundation II: Provenance You Can Trust — PARTIAL (opened 2026-10-21)

> **Stage 23 is `partial`.** This file is kept current from the first commit to the close.
> `git_sha_end` is the `main` commit the stage opened on until the release PR's bump commit
> replaces it.
>
> - **The prompt of record** is `docs/handoff-bundle/STAGE-23-foundation-provenance.md`.
> - **The charter** is ADR-051 row 23: `dvc_input_hash` content-addresses the inputs a case
>   touches (O-07), the SIF is re-hashed at launch (O-08), each change has its own ADR, and
>   ADR-050's hosted run is the end-to-end proof. D6 keeps that order (§2).
> - **Verification-scale compute only** (ADR-051 D3): the hosted run plus two cluster solves. Never
>   relax a tolerance. Stage 20 stays closed. PR #21 is left alone.
> - **Nothing recorded is relabelled**: no MLflow run, `data/vv` record, Stage-17 corpus row or
>   committed crate.

## 1. Deliverables status

| # | Deliverable (verbatim from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | Bookkeeping (first commit) | ✅ | `.aero-stage` 23, Dependabot prefix `ci(stage-23)`, this handoff, README regenerated; moving-vv's H-09 guard fixed in the same PR (Stage-22 left-over 1) |
| 2 | O-07, a content-addressed `dvc_input_hash` | ✅ | ADR-052 accepted 2026-10-21 (D1/D2/D4); built in PR 7 (#81) with the CONSTITUTION Invariant 3 amendment; **merged 2026-10-23 05:38 UTC by the operator (squash `3b02461`), with the recorded approval but 39 h into the ≥72 h window** (§3; re-affirmation after 2026-10-24 14:38 UTC pending) |
| 3 | O-08, the SIF re-hashed at launch | ⚠️ | ADR-053 accepted 2026-10-21 (PR 3); the guard is built and tested (PR 6, `stage-23-o08-guard`: 1661 unit tests, mypy strict clean), not yet merged; from its merge every tuple's container term is `sif-sha256-verified-at-launch/v1` |
| 4 | The end-to-end proof | ⚠️ | ADR-050 accepted as amended 2026-10-21. **Cluster solve 1 of 2 done (2026-10-23): `turek_hron_cfd2` on clean `main` `3b02461`, PASS, read back with every check passing (§4, E2E-1)**. Still to do: the Blasius cluster reference through the hosted driver, after #82, and the hosted run (needs the published SIF) |
| 5 | The lock refresh for the pip-audit advisories | ⚠️ | PR 2 open: re-measured 2026-10-21 at 179 rows = 116 advisories in 21 packages; after `uv lock -P` on the 20 fixable packages only diskcache's PYSEC-2026-2447 (no fix) remains, waived with a dated rationale; licence scan 302 packages, 0 FAIL, no exception change; self-hosted V&V jobs install from the lock; the PR's FULL run is the evidence |
| 6 | The close: `v0.1.2` | ❌ | release PR, then the operator cuts the tag (by 2026-12-21 UTC, the Stage-17 certificate margin) |

(✅ = done, ⚠️ = partial, ❌ = not done / blocked)

**PR map** (planned; one merge per main movement, each with all 12 required contexts green):

| PR | What | FULL `vv-required` | Operator action before merge |
|---|---|:-:|---|
| 1 | open the stage; moving-vv dispatch-input guard | — | — |
| 2 | lock refresh (deliverable 5); self-hosted V&V jobs install from the lock | yes | review any licence-exception move |
| 3 | ADR-052, ADR-053, ADR-050 amended (names and golden values frozen) | — | accept ADR-053 and ADR-050 |
| 4 | migration `006_provenance_schemes` | — | `alembic upgrade head` before PR 5's first push |
| 5 (#79) | `ProvenanceTupleV2` with per-term schemes (v0 labels), scheme tags and mirror columns — **merged 2026-10-22 09:04 UTC by the operator, squash `6cfa401`** (ADR-052 D4's first boundary) | yes | — |
| 6 (#80) | O-08: the SIF re-hashed before every launch — **merged 2026-10-22 16:02 UTC by the operator, squash `07937a4`** (ADR-053's boundary; FULL run on `ef8f81c`: 3 passed, 1 xfailed) | yes | read-only digest check of the preCICE/CalculiX SIFs (done 2026-10-21, all match) |
| 7 (#81) | O-07 + the Invariant 3 item-2 amendment — **merged 2026-10-23 05:38 UTC by the operator, squash `3b02461`** (both terms v1 from here); opened 2026-10-21 14:38 UTC, so 39 h into the ≥72 h window | yes | approval recorded 05:38 UTC; re-affirm after 2026-10-24 14:38 UTC |
| — | two cluster solves, read back (no PR) | — | approve the two verification-scale solves |
| 8a | ADR-050's executor and driver: `LocalContainerExecutor`, `scripts/hosted_repro.py`, the runner's `log_scalars` | yes | — |
| — | the cluster reference: `hosted_repro.py run --executor local-ssh` on clean `main` after 8a, then `reference` | — | — |
| 8b | `ci/hosted-repro/reference.json` and `hosted-repro.yml`; its PR run is the first execution | — | publish `openfoam-esi.sif` as `sif-openfoam-esi-c9d7f329` (pre-release) |
| 9 | MinIO keys only in steps that `dvc pull` | — | rotate the keys (open item) |
| 10 | SECURITY.md erratum, ledger, proof record | — | — |
| 11 | release `v0.1.2` and the Stage-24 prompt | yes | cut the tag |

### The two terms at open (the definitions being replaced)

**`dvc_input_hash` (ADR-004; `aero/provenance/four_fold.py:229-247` at `0c96e45`).** The sha256 of
the canonical JSON of `dvc status -c --json`, run at the repository root with no targets, against
DVC's `core.remote` (`aero-minio`). An empty stdout is silently read as `{}`. It never takes the
case as an argument, so it is a digest of the whole repository's cache/remote sync state on the
machine that computed it, not of the inputs a case touches.

**`container_sif_sha256` (ADR-004; `four_fold.py:250-264` at `0c96e45`).** The first two-token line
of the submitting checkout's `containers/SHA256SUMS` whose second token equals the SIF's basename.
The SIF file is never opened.

Measured read-only on 2026-10-21 (MLflow `aero-provenance`: 2505 runs, 2502 carrying the tuple, all
`solver_version = OpenFOAM-ESI v2412`):

| Recorded value | Where | What the old code says it is |
|---|---|---|
| `dvc_input_hash = 44136fa3…` = sha256(`{}`) | 1549 MLflow runs, 2026-05-19 to 10-16 | an empty `dvc status -c` output (or an empty stdout) |
| `dvc_input_hash = 618b8fed…` | 386 MLflow runs: every CI run of every case since 2026-07-30 | a non-empty status on the CI checkout |
| `dvc_input_hash = 7ec8590f…` | all 74 `data/vv` records, the Stage-17 corpus, every committed crate tuple | a non-empty status on the control-host checkout |
| 8 other `dvc_input_hash` values | 459 MLflow runs | sync states of other checkouts and dates |
| `container_sif_sha256 = c9d7f329…` | all 2502 runs | the `openfoam-esi.sif` line of SHA256SUMS, looked up by name |

So the value depends on which checkout, cache and remote computed it, and the same value is shared
by every case run at the same time. Because `7ec8590f…` is not sha256(`{}`), the sentence "it shows
the inputs were in sync with the remote at run time" (the committed crates, SECURITY.md:67-69,
ADR-004) is not supported by the record; what that status contained is unknown without a `dvc`
read. The crates are immutable and keep their text; the correction goes into ADR-052 and
SECURITY.md. The live `openfoam-esi.sif` on aero-build does hash to `c9d7f329…` (2.19 s), and so does
`pyfr.sif` to its entry (19.1 s): the recorded container digests are consistent but were never
measured at launch.

## 2. Decisions made

All taken by the operator on 2026-10-21, before any ADR or provenance code (plan review).

- **D1 — the declaration: a class declaration, bound to the run.** Every `BenchmarkCase` class
  declares `dvc_inputs` (repo-relative `.dvc` pointers; `()` written out for none) as a required
  member; `compute_provenance` takes a required `dvc_inputs` at all 33 call sites; the tuple carries
  the declaration into the case directory, where one read helper verifies md5 and size and refuses
  any DVC-tracked file the run did not declare. Rejected: a central table (optimizer designs and
  refined grids have no registry key), a hashed spec field (moves every `config_hash` and breaks the
  N3 digest pin), deriving inputs from spec paths (3 of the 4 DVC-reading cases cannot build their
  spec without the data).
- **D2 — the hash: the declared pointers' md5 and size, domain-separated.** sha256 of the line
  `aero.dvc-inputs/v1` followed by the canonical JSON `{"inputs":[{hash, md5, path, size}, …]}`
  (sorted by path; the `config_hash` JSON convention), read from the git-tracked pointers at
  `git_sha`. No `dvc` binary, remote or credentials. The empty set is `1ef5b7d9…`, never
  `44136fa3…`. `.dir` and `dvc.lock` outputs, and pointers without `hash: md5`, are refused; a
  pointer's `remote:` key is allowed and excluded. Rejected: adding sidecar sha256s (the active
  inputs' sha256 already enters `config_hash` via `surface_sha256`/`archive_sha256`), a scoped
  `dvc status -c` (still remote- and cache-dependent), hashing staged bytes (not recomputable from
  git).
- **D3 — the SIF: a guard before every launch.** `build_apptainer_exec` requires the expected digest
  from the run's own tuple and prefixes every command with a `sha256sum --check` on the solve host;
  a mismatch exits 86 before apptainer starts and surfaces as `ProvenanceError`. No digest cache.
  Rejected: a probe before and after the run (misses launches in between and outside the runner),
  probe plus guard (no extra guarantee), re-hashing on the control host (does not bind the executed
  file).
- **D4 — telling old from new: a typed `ProvenanceTupleV2`.** A new class (not a subclass) with
  required per-term schemes; new runs carry `dvc_input_hash_scheme` and
  `container_sif_sha256_scheme` tags and nullable mirror columns (migration 006, no backfill).
  A run without scheme tags was recorded before Stage 23. The legacy `ProvenanceTuple` stays
  byte-identical and is the only tuple crate format v1 and the payload models accept. Rejected:
  tags beside an unchanged tuple (tuples persisted outside MLflow would carry no marker), one
  version tag (cannot express one term changed and the other not), new tag names (the old term would
  need the remote forever).
- **D5 — ADR-050: amended, then accepted.** The hosted run uses the cluster's own
  `openfoam-esi.sif` (`c9d7f329…`, published by the operator) under the same launch guard, logs to a
  run-local MLflow store and a throwaway Postgres (so Invariant 3 and Hard Rule 3 hold unchanged),
  reports `cf_mid`, and is gated at 1 % against a cluster run committed before any hosted run; the
  Blasius 5 % comparison is a diagnostic only. No crate this stage: a crate that is honest about new
  semantics needs format v2 (ledgered). Rejected: building the SIF from the def (a third container
  meaning plus an Invariant 3 item-3 amendment), crate v2 now (the largest risk to the tag deadline),
  deferring (leaves ADR-051 row 23's proof unmet).
- **ADR acceptances (2026-10-21, after the adversarial review of the drafts):** ADR-053 "Accept as
  written"; ADR-050 "Accept as amended"; ADR-052 "Two-step" — its definitions (frozen names,
  preimage bytes, golden values) are accepted now, and only the CONSTITUTION Invariant 3 text waits
  for PR 7's ≥72 h window. Any later change to a frozen computation mints a new scheme name.
- **Taken while writing the ADRs** (no operator decision needed): under `repo-sync-state/v0` the
  tuple carries no `dvc_inputs` (NULL in the mirror), so a v0 run never reads as "declared no
  inputs"; the Invariant 3 amendment also brings item 3's roster sentence and the Enforcement
  paragraph up to date, so the window never has to reopen; `sha256sums-lookup/v0` is the unchanged
  lookup (the strict `SHA256SUMS` parser rides with O-08).
- **D6 — the 23↔24 reorder clause lapsed unused.** If the provenance work blocks, Stage 23 closes
  `partial` and Stage 24 waits; no campaign is recorded under the old semantics.
- **Deliverable 5:** targeted `uv lock -P` for the 19 packages with a fix; an explicit, dated
  `--ignore-vuln PYSEC-2026-2447` (diskcache 5.6.3 via dvc-data, no fixed version); the self-hosted
  V&V jobs install with `uv sync --locked` (extends ADR-049 H-15), so the FULL run tests the lock.
- **The cluster proof:** `blasius_flat_plate` (empty input set) and `turek_hron_cfd2` (one declared
  input, `cylinder_flag.stl`).
- **moving-vv** keeps both default cases: it re-measures the cylinder weekly and fails honestly when
  `plunging_airfoil_hg2007` hits the 14400 s ceiling (~5.5 h of runner time); Stage 24's compute plan
  owns hg2007.
- **Operator items:** the MinIO keys printed on 2026-10-16 are **not rotated yet**;
  `.dvc/config.local` was mode 0644 and is now 0600 (permission only, never read); a GitHub Release
  for v0.1.1 is decided at the v0.1.2 close.

## 3. Deviations from the stage plan

- **moving-vv's fix is stronger than the brief's `printf '%s\n'`.** That one-liner accepts the empty
  scheduled input, but would still let `' '` run zero cases green and `$'\n-h'` record "-h: PASS". The
  guard is a whole-string `[[ =~ ]]` check, each word is checked against the known cases, and zero
  cases fails the job (PR 1).
- **Corrections to the brief:** 4 of the 5 committed crates state both weaknesses (stage14 is
  evidence-only); there are 33 `compute_provenance` call sites (`tests/vv/conftest.py` is the 33rd);
  hashing a multi-GB SIF is not "seconds" (19.1 s for 4.25 GB over NFS; the active stack is < 1 GB);
  "inputs were in sync" was never shown (§1).
- **The lock refresh upgrades 20 packages, not 19.** `certifi` 2026.4.22 gained an advisory
  (PYSEC-2026-4320) after the 2026-10-19 schedule. `uv lock -P` takes the newest compatible release,
  not the minimum fix (mlflow 3.12.0 → 3.17.2, which is what the unlocked V&V jobs already ran), and
  `anyio` is pinned to 4.14.2 because `-P anyio` forked it (4.15.1 only for Python ≥ 3.15) and the
  licence scanner refuses a package locked twice.
- **Invariant 3 item 2 must be amended.** Its text names `dvc status -c` outputs, so O-07 is a
  redefinition: the O-07 PR carries the CONSTITUTION change and stays open ≥72 h for the operator's
  approval. O-08 fits item 3 as written.
- **Deliverable 4 produces no result crate** (D5): a v1 crate of a new-semantics run would have to
  carry the two old limitation ids (`aero/crate/rules.py:42-43`), and the hosted number has no U95.
- **The FULL run for the lock** is evidence only because the V&V jobs install from the lock and
  `uv.lock` joins the FULL filter (PR 2).
- **O-08 as built (PR 6), against ADR-053's text.** The binding is the `CaseDir` itself: it carries
  the run's `ProvenanceTupleV2`, and `CaseDir.pin(sif_path)` returns the `SifPin` (refusing a basename
  the tuple does not name) and counts the launch; there is no separate `ContainerBinding` class. The
  preCICE plan's `sif_paths` became `sif_pins`, one pin per SIF, each filed under its own basename.
  A coupled refusal is read from the participant log's first 4 KiB: rc 86 without the
  `AERO-SIF-REFUSED` line is a solver's own exit, not a refusal. `JaxFluidsSolver.differentiable_run`
  is "refused" structurally: it records no tuple, so it claims no container (a test pins that
  `JaxGradientResult` has no such field). Two refusals the ADR did not list:
  `scripts/stage20_numerics_screen.py` (launches with no tuple) and the hg2007 driver's ADR-045
  restart (`_launch_tuple`, refused before anything is rotated; its rotation tests replace the seam).
- **PR 8 is two PRs.** ADR-050 D5 needs the cluster reference committed **before the workflow's
  first execution**, and that reference is a run of the same driver on a clean, reachable commit.
  So 8a lands the executor and driver on `main`, the cluster reference runs there, and 8b adds the
  reference and the workflow, whose PR run is its first execution. The SIF's release tag is
  `sif-openfoam-esi-c9d7f329`, published as a pre-release, which mints no Zenodo version.
- **The Invariant 3 amendment merged 33 h before its review window ended.** #81 merged on 2026-10-23
  at 05:38 UTC, 39 h after it opened (2026-10-21 14:38 UTC), with the operator's recorded approval
  and all 12 contexts green on the merged head. CONSTITUTION's Amendment process asks for ≥72 h. The
  operator kept the merge and re-affirms after the window. A revert would have added two semantics
  boundaries on `main` for a window whose only reviewer had already approved. ADR-052's Status line
  records it.
- **"Ride-alongs only if 1–6 are done"** cannot hold literally: H-34/H-35 change code paths the tag
  gate compares, so any ride-along merges before the release PR's bump commit.

## 4. Environment / dependency / schema changes

- **The lock** (PR 2): `uv lock -P` for aiohttp, anyio (=4.14.2), asyncssh, certifi, cryptography,
  dulwich, fsspec, gitpython, hydra-core, mlflow, multidict, pillow, pyasn1, pydantic-settings,
  setuptools, sqlparse, starlette, urllib3, virtualenv and werkzeug; transitively distlib,
  mlflow-skinny, mlflow-tracing, packaging, python-discovery, s3fs and yarl moved. None of the four
  packages with reviewed licence exceptions moved. `ci/licence/metadata-snapshot.json` refreshed. The
  `stage_23` pytest marker is registered in `pyproject.toml`.
- **Migration `006_provenance_schemes`** (PR 4; `db/migrations/006_provenance_schemes.{sql,py}`, the
  005 pattern): nullable `TEXT` columns `dvc_input_hash_scheme`, `container_sif_sha256_scheme` and
  `dvc_inputs`, and the CHECK `provenance_schemes_consistent` (the scheme columns both-or-neither;
  `dvc_inputs` set exactly under `declared-dvc-pointers-md5/v1`); no DEFAULT, UPDATE or INSERT.
  `tests/unit/test_migration_006_additive.py` pins it; `alembic upgrade head --sql` renders 004→006.
  **Applied 2026-10-21** on `aero_provenance` (LXC 202) by the agent with the operator's approval
  ("Run it for me (approved)"), after #78 merged: `alembic upgrade head` 005 → 006, `alembic current`
  = `006_provenance_schemes (head)`; the three columns are nullable with no default, the CHECK
  `provenance_schemes_consistent` exists, and all 2527 historical rows have NULL in every new column.
- **The typed tuple** (PR 5): `aero/provenance/four_fold.py` gains `TermSchemes`, `DeclaredInput`, the
  ADR-052 digest (`dvc_inputs_digest`, `EMPTY_DVC_INPUTS_DIGEST`), `ProvenanceTupleV2` (not a subclass
  of `ProvenanceTuple`) and the `AnyProvenanceTuple` union; `compute_provenance` returns a V2 tuple
  labelled `repo-sync-state/v0` / `sha256sums-lookup/v0`; the v0 DVC term refuses an empty stdout.
  `start_provenance_run` takes only a V2 tuple; the mirror insert writes 9 columns. In-memory
  consumers (`BenchmarkResult`, the runner, `MeshSweep`, the optimizer objective, the preCICE check,
  `SurrogateProvenanceTags`) take the union; `ReportableResult`, `OptimizationResult`, the corpus and
  the crate model stay legacy-only. `SurrogateProvenanceTags.log_to_mlflow(run_id)`, which had no
  caller and could set tags on any existing run, is deleted.
- **The runner refuses a tuple of another spec** (PR 5): `BenchmarkRunner.run`/`measure_scalar` check
  `config_hash` against the case's spec, and `MeshSweep.run` takes `provenance_of(case)` and builds one
  tuple per grid; until now a sweep logged its refined grids under the finest grid's `config_hash`.
  `tests/vv/conftest.py` and `aero vv run --mesh-sweep` pass the case.
- **19 historical drivers refuse** (PR 5; ledger, Stage 23): they predate the typed tuple and call
  `refuse_unported_driver` (exit 4) before recording anything. Ported: `stage11_moving_vv`,
  `stage18_turek_hron`.
- **The launch guard** (PR 6, ADR-053): `aero/adapters/_base.py` gains `SifPin`, `sif_guard`,
  `raise_if_container_refused`, `assert_launches_guarded` and the sentinel (exit 86,
  `AERO-SIF-REFUSED` / `AERO-SIF-VERIFIED`); `build_apptainer_exec` takes a required
  `expected: SifPin` (no `sif_path`) and a structural `no_home` flag (commit 1, byte-identical to the
  three old `.replace` splices); `Solver.prepare(spec, *, provenance)` binds the tuple to the
  `CaseDir`. Every adapter launch (OpenFOAM, SU2, PyFR, NekRS, JAX-Fluids, the preCICE fluid mesh,
  decompose and participants) is pinned from the tuple and checked; the robust-mesh ladder takes
  `provenance_of(rung_spec)` (each rung its own tuple) and pins `checkMesh`; the preCICE supervisor
  exits 86 ahead of its other exit rules and `read_coupled_status` raises `ProvenanceError`; the V&V
  runner and `aero run` refuse a record whose launches were not guarded or were pinned from another
  tuple. `containers/SHA256SUMS` is parsed strictly (`read_sha256sums`: `#`/blank skipped, 64-hex,
  no duplicate name) and must equal HEAD's (`sha256sums_at_head`), even under `--allow-dirty`.
  `compute_provenance` labels the container term `sif-sha256-verified-at-launch/v1`. Refused, exit 4
  (ledger, Stage 23): `aero run|vv run --executor runpod`, `aero surrogate train`, the numerics screen,
  the hg2007 restart. Tests: `tests/unit/test_sif_launch_guard.py` (local bash + fake `apptainer` +
  temp SIF: a match launches once; a same-name swap or a missing file exits 86 and apptainer never
  starts; a SIF the tuple does not name is refused before any command), the supervisor's refusal
  tests, and `tests/unit/_launch_fixtures.py` (tuples at the committed digests) for every
  `CaseDir` a test builds, including the hermetic `tests/stage_*` suites. **Read-only digest check
  before PR 6 (2026-10-21, on aero-build):** `sha256sum` of the five active-stack SIFs in
  `/opt/aero/containers/` (2.45 GB, 13 s over NFS) equals `containers/SHA256SUMS` for every one:
  `openfoam-esi.sif` `c9d7f329…`, `precice-fsi.sif` `ce795873…`, `calculix-precice.sif`
  `ac0805d6…`, `calculix-precice-adr045.sif` `ca1937f7…`, `su2-v8.sif` `7b0dc25c…`.
- **The declared inputs** (PR 7, ADR-052): a new core module `aero/provenance/dvc_inputs.py`
  (stdlib + pydantic; registered in `test_core_import_isolation.py` and `import-platform-only.yml`)
  with the strict pointer parser, `resolve_declared` (pointers read at `HEAD`; a working copy
  that differs is refused even under `--allow-dirty`) and `read_declared_input`, the one read
  path. Every case class (18 V&V, 2 optimizer) declares `dvc_inputs` (ADR-052's table: the
  Turek-Hron CFD pair the STL, FSI3 the tutorial archive, `onera_m6` its mesh, the rest `()`);
  `compute_provenance(..., dvc_inputs=...)` is required and returns both terms v1; the
  repository-wide `dvc status` digest (`four_fold.dvc_input_hash`) is deleted. `Solver.prepare`
  hands the run's resolved inputs to `_write_case(..., declared=...)`, and the six staging sites
  (external-geometry STL, preCICE tutorial archive, SU2/PyFR/JAX-Fluids mesh files, NekRS case
  directory) and the two spec-time reads (`_gated_stl`, the FSI3 archive) go through the reader.
  The runner refuses a tuple whose inputs are not the case's declaration. CONSTITUTION Invariant 3
  item 2, item 3's roster sentence and the Enforcement paragraph are amended; ADR-004 carries a
  dated amendment note; CHANGELOG `[Unreleased]`. Tests: `tests/unit/test_dvc_inputs.py` (the
  declaration table and goldens, the parser against `yaml.safe_load` on every committed pointer,
  every refusal, the read path in a temp checkout, the AST check of every call site, and an
  audit-hook test that no case opens an undeclared DVC output).
- **The hosted check's executor and driver** (PR 8a, ADR-050):
  - `aero/orchestration/local_container.py`: `LocalContainerExecutor` runs each command in a local
    `bash`, with no SSH, under the `Executor` contract. Long jobs merge stderr into stdout, as a
    detached job's `output.log` does. A timeout is rc 124 and kills the whole process group, and a
    shell that can't start is a `transport_error`.
  - `BenchmarkRunner.run(..., log_scalars=("cf_mid",))` logs named scalars of the solve in the same
    MLflow run, and refuses a name the solve did not produce before logging anything.
  - `scripts/hosted_repro.py` has four subcommands:
    - `run`: one Blasius solve through the platform's runner and `start_provenance_run`. A
      `local-container` run may only log to a run-local sqlite or file store. The record's number
      and tags are read back from the logged run, and it writes the config preimage.
    - `band`: the gated 1 % comparison on `float.hex`, with the same terms and v1 schemes on both
      sides and clean commits.
    - `reference`: accepts only a clean `local-ssh` record.
    - `negative`: a one-byte-flipped copy of the SIF exits 86 and apptainer never starts, proved
      with a `PATH` shim. It passed on the real 455.6 MB SIF on 2026-10-22, in 2.5 s.
  - The Blasius `config_hash` is `d1d264c5…`, as ADR-050 D3 states.

- **E2E-1, cluster solve 1 of 2 (2026-10-23 10:35 UTC, operator-approved).** The run was
  `aero vv run --case turek_hron_cfd2 --executor local-ssh` in a clean worktree at `main`
  `3b02461`, the #81 squash, so both terms are v1. Its MLflow run is
  `95401ce5f6ad482fbcd7165831fbac7c` and its case directory
  `turek_hron_cfd2-20261023-103515-45e2f1`.
  - **Result: PASS.** Cd error 0.385 % (tolerance 5 %), Cl error 0.243 % (tolerance 10 %).
  - **Read back** with `scripts/provenance_readback.py --mirror --config-json`, which does not
    import `aero`: all 14 checks pass.
    - `git_sha` `3b0246193c90…` is a clean commit.
    - `dvc_input_hash` `70b49f18…` is ADR-052's golden value, recomputed from the `dvc_inputs` tag,
      and the STL's md5 and size match its pointer at `git_sha`.
    - `container_sif_sha256` `c9d7f329…` is the `SHA256SUMS` entry at `git_sha`.
    - `config_hash` `47f3fef6…` is recomputed from the spec.
    - The mirror row is byte-equal to the tags.
  - **The launch guard:** one `AERO-SIF-VERIFIED sha256=c9d7f329… path=/opt/aero/containers/openfoam-esi.sif`
    line in each of the two launches' `output.log` (mesh and `simpleFoam`), and no refusal.
  - **Caveat:** the `config_hash` embeds the worktree's absolute STL path, the ledgered Turek-Hron
    `surface_source` issue, so it differs between checkouts of one commit.

## 5. CI/CD changes

- **moving-vv** (PR 1): the dispatch input is read only by a new, secret-less step, "Validate the
  dispatch input", which checks it as one string (`[[ "$CASE_INPUT" =~ ^[a-z0-9_ ]*$ ]]`, the
  `release-readiness.yml` precedent), splits it into words, runs the two default cases when there
  are none, writes a summary line before any `exit 2`, and hands the validated list to the run step
  through `GITHUB_ENV`. The run step fails when that list is empty. `tests/unit/test_workflow_hygiene.py`
  runs both scripts under `bash -e`: `''`, `' '` and valid keys are accepted; `a;b`, `x;id`,
  `$(id)`, `` `id` ``, `-h`, `$'\n-h'`, `$'ok\n;evil'`, a trailing newline, upper case and a tab are
  refused with exit 2 and nothing passed on; zero cases exits 1 without calling the driver; the
  defaults are registered `UNSTEADY_CASES`; only the validation step reads the input, and it holds
  no secret. Proof on the cluster: the Sunday 2026-10-25 schedule.
- **Locked V&V installs** (PR 2): vv-required, vv-smoke, vv-transonic, vv-scale-resolving (both jobs),
  moving-vv and provenance-completeness install with `uv sync --locked --python 3.12 --extra …`
  (ADR-049 H-15, dated scope note); `uv.lock` triggers a FULL `vv-required` run; the pip-audit job
  waives exactly PYSEC-2026-2447 until 2027-01-31 (`PIP_AUDIT_WAIVER_REVIEW_BY`). Hygiene tests pin
  all three: no `uv pip install`/`uv venv` in a self-hosted job, `uv.lock` in the filter, one waiver id
  that fails the test after its review date.
- **provenance-completeness** (PR 5) reads back the scheme tags, `container_sif_name`, the digest's
  membership in `containers/SHA256SUMS` and the mirror's eight columns byte for byte, and with
  `AERO_PROVENANCE_REQUIRE_CLUSTER=1` fails instead of skipping when MLflow or the mirror is
  unreachable. The provenance contract now has a gated home: `tests/unit/test_provenance_v2.py`.
- Planned: `hosted-repro.yml`; MinIO keys only in
  the steps that pull.

## 6. Gotchas discovered

- **Any new `ProvenanceTuple` field breaks every committed crate**: the envelope must re-dump byte
  for byte (`aero/crate/reader.py:126`), and it embeds the tuple. A pydantic subclass is silently
  narrowed to the parent's fields when placed in a `ProvenanceTuple` field (pydantic 2.13.4), so the
  new type must be unrelated.
- **PR-branch CI writes to the shared MLflow and Postgres** (vv-smoke and provenance-completeness on
  pull requests), so scheme names are frozen in the ADRs before the first implementing PR, and
  migration 006 must be live before the writer PR's first push.
- **`grep -q` accepts a multi-line input if any line matches**, so a pipe-to-grep input check is
  not a whole-string check.
- **The three `--no-home` sites rewrite the first `apptainer exec `** with `str.replace(..., 1)`
  (`precice/launcher.py:369`, `precice/solver.py:564`, `scripts/stage20_numerics_screen.py:310`); a
  guard prefix must not contain that literal.
- **The licence scanner refuses a forked resolution** (one package locked at two versions for
  different Python markers), and `uv lock -P <pkg>` can create one; pin the package
  (`-P anyio==4.14.2`) instead.
- **No cluster run has ever logged `cf_mid`.** A standard `aero vv run` logs `<metric>_error` and
  measured scalars only (`aero/vv/_base.py:451-468`), and Blasius' only metric is the pointwise `cf`.
  The hosted band's reference is therefore a cluster run of the hosted driver itself.
- **The Turek-Hron specs embed an absolute checkout path** (`surface_source`, `archive_path`), so
  their `config_hash` differs between checkouts of one commit. The proof records the path; the fix
  (it moves `config_hash`) is ledgered.
- **Both `vv` runners solve on the one aero-build.** PR #79's first FULL `vv-required` run lost
  `cylinder_strouhal_re100` to the executor's 30-min ceiling (rc 124 at t = 149.7) while main's
  `vv-smoke` shared the host. The rerun of only the failed job, with the host idle, passed: the
  case took 27 min 45 s (run 39601984722, attempt 2; 3 passed, 1 xfailed). PR 6 raises the V&V
  ceiling to 45 min. Until the shared host is fixed, start a FULL run only when no other
  self-hosted job is running.
- **The self-hosted workflows run only for pull requests into `main`** (`vv-required`, `vv-smoke`,
  `provenance-completeness`), so a PR stacked on a feature branch costs no cluster time. That is
  why PR 6 (#80) and PR 7 (#81) were opened stacked: #81's 72 h window runs while its CI waits.
- **The auto-mode classifier denied the agent's `gh pr merge 79 --squash`** on 2026-10-21, after all
  12 required contexts were green (#76 to #78 had merged earlier the same day). SECURITY.md
  names merging a PR, tagging and publishing a Release as operator acts, which is what the
  classifier enforced. The operator merges (#79 at 09:04 UTC on 2026-10-22).
- **Run ids collided across concurrent jobs.** A run id was `<case>-<UTC second>`. On #80's first run,
  `vv-required` and `vv-smoke` started `blasius_flat_plate` in the same second (09:42:41), so both
  wrote and meshed the one NFS case directory, and the second `simpleFoam` submit was refused as
  a duplicate `run_long.sh` session (rc 1, run 39757494577). The bytes were identical (same spec,
  deterministic `blockMesh`), but two runs shared one directory. Fixed in PR 6: the id carries a
  random 6-hex suffix, and an existing run directory is refused, never reused.
- **The hermetic provenance suites (`tests/stage_04`, `tests/stage_20`) run in no CI job**;
  `tests/stage_04/test_provenance_logging.py:87` is stale (5 insert parameters, `db.py` sends 6).

## 7. Open items for the next stage (and beyond)

- **Operator, from 2026-10-24 14:38 UTC:** re-affirm the CONSTITUTION Invariant 3 amendment on #81
  (merged early, §3), e.g. "Re-affirmed after the full 72 h amendment window: no change."
- **Operator:** rotate the MinIO keys for aero-minio (LXC 212) and aero-nas, then update
  `.dvc/config.local` and the `AERO_DVC_*` repo secrets; verify with `ls` and one targeted
  `dvc status -c data/meshes/su2/onera_m6.su2.dvc`. After O-07 the four-tuple no longer touches the
  DVC remote.
- The Stage-24 prompt (`docs/handoff-bundle/STAGE-24-foundation-run-the-registry.md`) is written
  before the close.

## 8. Pointers for the next session

- **Read first:** this file, the Stage-23 prompt, ADR-051 row 23, ADR-050, ADR-047 D7, CONSTITUTION
  Invariant 3.
- **Run first:** `PATH=.venv/bin:$PATH pytest -q tests/unit`; `bash scripts/check_handoff_exists.sh`;
  `scripts/regenerate_status.sh --check`; `gh run list --status in_progress`.

## 9. Artifacts produced

- This handoff.
- ADR-052, ADR-053 and the amended ADR-050 (PR 3).

## 10. Confidence / risk

- **High confidence:** the measured state in §1 (two independent read-only MLflow reads; the SIF
  hashes on aero-build).
- **Risks:** the ≥72 h amendment window and the operator's approvals sit on the path to the
  2026-12-21 tag deadline; the hosted runner's Apptainer behaviour is unmeasured until its first
  PR run; the self-hosted queue paces every PR (45–60 min per cycle).
