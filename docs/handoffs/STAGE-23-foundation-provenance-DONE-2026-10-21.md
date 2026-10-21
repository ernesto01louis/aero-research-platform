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
| 2 | O-07, a content-addressed `dvc_input_hash` | ❌ | not started — ADR-052 (D1, D2, D4), `aero/provenance/dvc_inputs.py`, tests; amends Invariant 3 item 2 (≥72 h) |
| 3 | O-08, the SIF re-hashed at launch | ❌ | not started — ADR-053 (D3), the launch guard in `build_apptainer_exec`, fake-executor tests |
| 4 | The end-to-end proof | ❌ | not started — ADR-050 as amended (D5) on a hosted runner, plus `blasius_flat_plate` and `turek_hron_cfd2` on the cluster, read back |
| 5 | The lock refresh for the pip-audit advisories | ❌ | not started — targeted `uv lock -P`, licence refresh, one ignore, locked V&V installs, FULL run |
| 6 | The close: `v0.1.2` | ❌ | release PR, then the operator cuts the tag (by 2026-12-21 UTC, the Stage-17 certificate margin) |

(✅ = done, ⚠️ = partial, ❌ = not done / blocked)

**PR map** (planned; one merge per main movement, each with all 12 required contexts green):

| PR | What | FULL `vv-required` | Operator action before merge |
|---|---|:-:|---|
| 1 | open the stage; moving-vv dispatch-input guard | — | — |
| 2 | lock refresh (deliverable 5); self-hosted V&V jobs install from the lock | yes | review any licence-exception move |
| 3 | ADR-052, ADR-053, ADR-050 amended (names and golden values frozen) | — | accept ADR-053 and ADR-050 |
| 4 | migration `006_provenance_schemes` | — | `alembic upgrade head` before PR 5's first push |
| 5 | `ProvenanceTupleV2` with per-term schemes (v0 labels), scheme tags and mirror columns | yes | — |
| 6 | O-08: the SIF re-hashed before every launch | yes | read-only digest check of the preCICE/CalculiX SIFs |
| 7 | O-07 + the Invariant 3 item-2 amendment (open ≥72 h) | yes | approve the amendment after the window |
| — | two cluster solves, read back (no PR) | — | approve the two verification-scale solves |
| 8 | ADR-050 hosted run (`hosted-repro.yml`) | — | publish `openfoam-esi.sif` (c9d7f329…) |
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
- **Invariant 3 item 2 must be amended.** Its text names `dvc status -c` outputs, so O-07 is a
  redefinition: the O-07 PR carries the CONSTITUTION change and stays open ≥72 h for the operator's
  approval. O-08 fits item 3 as written.
- **Deliverable 4 produces no result crate** (D5): a v1 crate of a new-semantics run would have to
  carry the two old limitation ids (`aero/crate/rules.py:42-43`), and the hosted number has no U95.
- **The FULL run for the lock** is evidence only because the V&V jobs install from the lock and
  `uv.lock` joins the FULL filter (PR 2).
- **"Ride-alongs only if 1–6 are done"** cannot hold literally: H-34/H-35 change code paths the tag
  gate compares, so any ride-along merges before the release PR's bump commit.

## 4. Environment / dependency / schema changes

- None yet. Planned: migration `006_provenance_schemes` on `aero_provenance` (LXC 202; additive,
  nullable, no backfill, applied by the operator), the targeted lock refresh, a new core module
  `aero/provenance/dvc_inputs.py`, `aero/orchestration/local_container.py`.

## 5. CI/CD changes

- None yet. PR 1's second commit fixes moving-vv's dispatch-input guard.
- Planned: locked installs in the self-hosted V&V jobs; `uv.lock` in the FULL filter; the pip-audit
  ignore; provenance-completeness fails instead of skipping; `hosted-repro.yml`; MinIO keys only in
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
- **The hermetic provenance suites (`tests/stage_04`, `tests/stage_20`) run in no CI job**;
  `tests/stage_04/test_provenance_logging.py:87` is stale (5 insert parameters, `db.py` sends 6).

## 7. Open items for the next stage (and beyond)

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

## 10. Confidence / risk

- **High confidence:** the measured state in §1 (two independent read-only MLflow reads; the SIF
  hashes on aero-build).
- **Risks:** the ≥72 h amendment window and the operator's approvals sit on the path to the
  2026-12-21 tag deadline; the hosted runner's Apptainer behaviour is unmeasured until its first
  PR run; the self-hosted queue paces every PR (45–60 min per cycle).
