# ADR-052 — A content-addressed `dvc_input_hash`: the declared `.dvc` pointers a case reads, and a typed tuple that names each term's semantics

- **Status:** **accepted in two steps.** (1) Its definitions — D1, D2 and D4, with the frozen
  scheme, tag and column names, the preimage bytes and the golden values — were **accepted by the
  operator on 2026-10-21** ("Two-step"), after deciding the three questions at the Stage-23 plan
  review (D1 "Class declaration, run-bound", D2 "Pointer md5+size, prefixed", D4 "Typed V2 tuple,
  scheme tags"); that acceptance is recorded by the commit that lands this ADR. Any later change to a
  frozen computation mints a new scheme name. (2) The CONSTITUTION Invariant 3 text below is ratified
  by the merge of the PR that implements O-07 and amends it, after the ≥72 h amendment window and the
  operator's recorded approval (CONSTITUTION "Amendment process").
  - **Boundaries on `main`** (D4, "interim states are labelled, never absent"): `6cfa401` (#79,
    2026-10-22) is the first commit whose tuples carry scheme tags, both terms v0
    (`repo-sync-state/v0`, `sha256sums-lookup/v0`).
- **Date:** 2026-10-21
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 23)
- **Stage:** 23 (Foundation II, ADR-051 row 23)
- **Supersedes:** none
- **Amends on acceptance:** ADR-004 term 2 (`dvc_input_hash`); CONSTITUTION Invariant 3 item 2 and its
  Enforcement paragraph. ADR-004's decision text is not edited; on acceptance a dated amendment note
  under its Status line (the ADR-046 pattern) points term 2 here. This ADR is the definition of record
  for runs that carry the new scheme tag.
- **Closes:** ADR-049 O-07. Together with ADR-053 (O-08) it retires H-33's documented weakness for
  every run recorded under the new schemes.

## Context and problem statement

Every result carries `(git_sha, dvc_input_hash, container_sif_sha256, config_hash)` (Invariant 3).
CONSTITUTION Invariant 3 item 2 defines the DVC term over "all `.dvc`-tracked inputs **the case
touches**". The implementation since Stage 04 (`aero/provenance/four_fold.py:229-247` at `0c96e45`)
is:

```python
def dvc_input_hash(repo_root: Path) -> str:
    proc = _run([_dvc_executable(), "status", "-c", "--json"], cwd=repo_root)
    if proc.returncode != 0:
        raise ProvenanceError(...)
    try:
        status = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProvenanceError(...) from exc
    canonical = json.dumps(status, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

It takes no case: it hashes the **whole repository's** `dvc status -c` against DVC's `core.remote`
(`aero-minio`), on whichever machine computes it, and an empty stdout silently becomes `{}`. Measured
read-only on 2026-10-21 (MLflow `aero-provenance`: the 2502 runs with the tuple started before 08:29
UTC):

| Recorded value | Where |
|---|---|
| `44136fa3…` = sha256(`{}`) | 1549 runs (2026-05-19 to 10-16) |
| `618b8fed…` | 386 runs: every CI run of every case since 2026-07-30 |
| `7ec8590f…` | 108 runs (2026-06-15 to 07-26); all 74 tuples in `data/vv` (28 files), the Stage-17 corpus and every committed crate tuple |
| 8 other values | 459 runs |

So the value is a function of the checkout, its DVC cache, the remote's contents and the
credentials on that machine; the same value is shared by every case run at the same moment; and it
never identifies an input. It also cannot be computed off the cluster: a hosted runner has no remote
credentials (ADR-050). Stage 22 found that the inputs live on several remotes (DrivAerML on
`aero-nfs`, the small assets on `aero-minio`), so a bare `dvc pull` can never succeed in this
repository and a sync-state digest cannot be made honest by scoping alone.

**Erratum (record-faithful; nothing is relabelled).** `7ec8590f…` is not sha256(`{}`), so by the
code's own construction every `data/vv` record and every committed crate tuple was recorded while the
repository-wide `dvc status -c` reported something. The sentence "It shows the inputs were in sync
with the remote at run time" — in the committed crates (from
`scripts/stage21_export_crates.py:239-242`) and SECURITY.md:67-69 — is therefore not supported by the
record. What the status contained is unknown without a `dvc` read on that checkout. A value of
sha256(`{}`) means an empty status **or an empty stdout** (`four_fold.py:243`), so ADR-004:49-51's
reading of it ("inputs are exactly the published versions", also the docstring at
`four_fold.py:233-235`) holds only when the stdout was not empty. The committed crates are immutable
and keep their text; SECURITY.md is corrected, and scoped to runs without scheme tags, by a later
Stage-23 PR.

Who actually reads a DVC-tracked file today (read-only survey, 2026-10-21): of the 25 registered
cases, `turek_hron_cfd2` and `turek_hron_cfd3` read `cylinder_flag.stl`, `turek_hron_fsi3` reads the
preCICE FSI3 tutorial tarball, and the frozen `onera_m6` reads its SU2 mesh. The other 21 read
no DVC-tracked file; two of them, the frozen PyFR cases `taylor_green_p3_32` and `periodic_hill_2d`,
read files that are in neither git nor DVC and are absent from the checkout. Three of the four read
and hash their file while building the spec
(`aero/vv/external_geometry/turek_hron_cfd.py:58-80`, `aero/vv/fsi/turek_hron_fsi3.py:119-136`), so
the set cannot be derived from spec fields on a machine without the data.

Two constraints shape the marker that tells old from new:

- **Crate format v1 is frozen** (ADR-047 D7). The crate envelope embeds the full `ProvenanceTuple`
  and must re-dump byte for byte (`aero/crate/reader.py:126-129`), so **any** new field on
  `ProvenanceTuple`, even a defaulted one, makes every committed crate unreadable. `rules.py:42-43`
  also forces the two old-weakness limitations on every crate with a tuple.
- **Pydantic narrows subclasses silently.** A subclass of `ProvenanceTuple` placed in a
  `ProvenanceTuple`-typed field validates and loses its extra fields on serialisation (verified on
  pydantic 2.13.4); an unrelated class is refused with `model_type`.

## Decision drivers

- **Invariant 3's meaning**: the term identifies the inputs the case touches.
- **Recomputable from the repository alone**: a third party with git at `git_sha` and no data, cache
  or credentials can recompute the value.
- **No dependence on machines or remotes**: the same case at the same commit has the same value on
  the cluster, on CI and on a hosted runner, whichever remote holds the bytes.
- **Fail loud**: an undeclared read, a byte mismatch or an unsupported output is refused, never
  recorded.
- **Never relabel**: no recorded run, record or crate changes; old values stay interpretable.
- **One object**: the declaration that is hashed is the declaration that is enforced.

## Considered options

D-numbers are the operator's plan-review decisions; D3 is ADR-053's and D5 is ADR-050's.

- **D1 (how a case declares its inputs):** (a) a required class declaration, bound to the run;
  (b) a central table keyed by case name (rejected: optimizer designs and refined grids have no
  registry key); (c) a field on the hashed spec (rejected: it moves every `config_hash` and breaks the
  N3 digest pin); (d) derivation from the spec's path fields (rejected: 3 of the 4 DVC-reading cases
  cannot build their spec without the data).
- **D2 (what is hashed):** (a) the declared pointers' `(path, md5, size)`, domain-separated; (b) the
  same plus a git-tracked sha256 sidecar (rejected: see "Why not the sidecar sha256" below); (c) a
  case-scoped `dvc status -c` (the literal Invariant-3 wording; rejected: still remote- and
  cache-dependent); (d) sha256 of the staged bytes (rejected: not recomputable from git).
- **D4 (telling old from new):** (a) a typed, non-subclass `ProvenanceTupleV2` with per-term schemes;
  (b) scheme tags beside an unchanged tuple (rejected: tuples persisted outside MLflow would carry no
  marker); (c) one semantics-version tag (rejected: it cannot express one term changed and the other
  not); (d) new tag names beside the old ones (rejected: the old term would need the remote forever).

## Decision outcome

Chose **D1 (a), D2 (a), D4 (a)** (operator, 2026-10-21).

### D1 — Each case declares the `.dvc` pointers it reads; the run carries the declaration

- **The declaration.** `BenchmarkCase` (the Protocol in `aero/vv/_base.py`) gains a required member
  `dvc_inputs: tuple[str, ...]`: repo-relative POSIX paths of the git-tracked `.dvc` pointer files the
  case reads. It has no default; a case that reads none writes `()`. The optimizer's case classes
  carry it too. It is not part of the hashed spec, so no `config_hash` moves.
- **The call.** `compute_provenance` takes `dvc_inputs` as a required keyword with no default, at every
  call site (34 today: 32 in `aero/` and `scripts/`, plus `tests/vv/conftest.py:192` and
  `tests/stage_04/test_four_fold.py:222`). A missing declaration is a type error, and
  an AST test covers the untyped `scripts/`.
- **The binding.** The tuple carries the resolved inputs. `BenchmarkRunner` refuses a tuple whose
  inputs differ from its case's declaration, and the tuple is bound to the case directory, so staging
  checks the declaration of **this run**, not a class attribute the hash never saw.
- **The one read path.** `aero/provenance/dvc_inputs.py` (a core module: stdlib + pydantic) provides
  `read_declared_input(repo_root, path, *, declared) -> bytes`. Every platform read of a DVC-tracked
  file goes through it — spec-time reads with the class declaration, staging reads with the run's —
  and it returns the verified bytes from one read. It refuses: a DVC output not in the declaration; a
  file that is neither git-tracked nor a declared output (an absolute path outside the checkout is
  covered by neither `git_sha` nor `dvc_input_hash`); a member of a `.dir` output; bytes whose md5 or
  size differ from the pointer; a declared pointer whose bytes differ from `HEAD`, even under
  `--allow-dirty` (or the value would not be recomputable from git).
- **Detection, besides the refusals.** A golden table of the 25 declarations; an audit-hook test that
  building, staging and reading the reference of every case that needs no data opens no undeclared
  DVC output; an AST test that every `compute_provenance` call passes `dvc_inputs`.

The declarations at acceptance:

| Case | `dvc_inputs` |
|---|---|
| `turek_hron_cfd2`, `turek_hron_cfd3` | `("data/references/fsi/turek_hron_fsi3/cylinder_flag.stl.dvc",)` |
| `turek_hron_fsi3` | `("data/references/fsi/turek_hron_fsi3/precice-tutorials-turek-hron-fsi3.tar.gz.dvc",)` |
| `onera_m6` (frozen, SU2) | `("data/meshes/su2/onera_m6.su2.dvc",)` |
| the other 21 registered cases | `()` |

`data/references/naca0012/naca0012.csv` is read by no code and is declared by no case.

### D2 — The hash: the declared pointers' content addresses, domain-separated

```text
PREFIX    = b"aero.dvc-inputs/v1\n"
inputs    = sorted by "path": {"hash": "md5", "md5": <outs[0].md5>,
                               "path": posixpath.join(posixpath.dirname(<pointer>), outs[0].path),
                               "size": int(<outs[0].size>)}
canonical = json.dumps({"inputs": inputs}, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True).encode("ascii")
dvc_input_hash = sha256(PREFIX + canonical).hexdigest()
```

- `path` is the output's repo-relative POSIX path
  (`data/references/fsi/turek_hron_fsi3/cylinder_flag.stl`), never the bare `outs[0].path`
  (`cylinder_flag.stl`, which gives `d50592a6…` for `turek_hron_cfd2`) nor the `.dvc` path; `size` is
  a JSON integer. The golden values below are computed this way.
- The values come from the git-tracked pointer files at `git_sha`. No `dvc` binary, no remote, no
  cache, no credentials. Every read of a declared file checks its md5 and size against the pointer.
- **The pointer parser is strict and stdlib-only** (core modules may not load `yaml` or `dvc`). It
  accepts exactly one `outs` entry with the keys `hash`, `md5`, `path`, `size` and an optional
  `remote`, which is excluded from the preimage, so moving bytes between remotes changes no digest.
  It refuses: `hash` other than `md5` (DVC-2 pointers used md5-dos2unix, a different function); a
  `.dir` md5 or an `nfiles` key (a directory output); any other key; a second output; a path that
  escapes the pointer's directory. `dvc.lock` stage outputs are not declarable.
- **Golden values** (pinned by unit tests):

| Declared set | `dvc_input_hash` |
|---|---|
| none (`{"inputs":[]}`) | `1ef5b7d9a694e703ccb270937035bdcc006487fa5a5b6fd92ac9c10f94453ec3` |
| `turek_hron_cfd2` / `cfd3` | `70b49f18e2fd314d3ec305433d74b4a2be494581fc05453f23b74cd66245e000` |
| `turek_hron_fsi3` | `5234c4dd598c00381ba4732930bef80a42729986d22f0619675ab0ee45c21659` |
| `onera_m6` | `25b590aae4b2757b8597f8724297d84ed91a0bbf890ec558a44793fc07557c7f` |

- **Disjoint from every old value by construction.** Every legacy preimage is the canonical JSON of a
  `dvc status` object and begins with `{`; every new preimage begins with `aero.dvc-inputs/v1`. The
  empty set is `1ef5b7d9…`, never `44136fa3…`. A unit test asserts that the golden values are not
  among the recorded legacy values.
- **Why not the sidecar sha256 (D2 (b)):** the active inputs' sha256 already enters `config_hash`
  (`surface_sha256` in the external-geometry spec, `archive_sha256` in the tutorial pin) and is
  re-checked at staging (`aero/adapters/openfoam/external_geometry.py:529-537`,
  `aero/adapters/precice/case.py:724`). A sha256-based scheme can be added later under a new scheme
  name.
- **Out of scope, stated:** `dataset_hash` (`aero/surrogates/_common/loaders/__init__.py:91-118`) and
  the certificate's `training_dataset_dvc_hash` keep their sync-state meaning. They back the
  Invariant-9 data gate of the Stage-17 certificate (expires 2027-01-20); changing them needs its own
  ADR. `.dir` and `dvc.lock` outputs (DrivAerML, AhmedML, WindsorML: frozen surrogate data, ADR-013)
  are refused, so `aero surrogate train` and DoMINO training refuse loudly until a later scheme covers
  them.

### D4 — A typed tuple that names each term's semantics

- **`ProvenanceTupleV2`** (in `aero/provenance/four_fold.py`) is a new frozen, `extra="forbid"` model
  and **not** a subclass of `ProvenanceTuple`. It carries the four terms in their existing shapes, the
  roster (`containers`), `container_sif_name` (the container of record's basename),
  `dvc_inputs` (the resolved inputs; `None` under `repo-sync-state/v0`, which uses no declaration),
  and the required `schemes`:

| Term | Scheme names (frozen) |
|---|---|
| `dvc_input_hash` | `repo-sync-state/v0` (the ADR-004 computation, `four_fold.py:229-247` at `0c96e45`, except that an empty stdout raises `ProvenanceError` instead of hashing `{}`); `declared-dvc-pointers-md5/v1` (this ADR) |
| `container_sif_sha256` | `sha256sums-lookup/v0` (the ADR-004 lookup, `four_fold.py:250-264` at `0c96e45`, unchanged); `sif-sha256-verified-at-launch/v1` (ADR-053) |

  Its validators recompute `dvc_input_hash` from `dvc_inputs` under `declared-dvc-pointers-md5/v1`
  (where `dvc_inputs` is required, possibly empty), and require `dvc_inputs` to be `None` under
  `repo-sync-state/v0`, so a v0 run never reads as "declared no inputs".
- **MLflow tags.** `as_mlflow_tags()` emits the four keys exactly as before, `container_sif_set` for a
  multi-container run as before, and `container_sif_name`, `dvc_input_hash_scheme`,
  `container_sif_sha256_scheme`, and, under `declared-dvc-pointers-md5/v1` only, `dvc_inputs` (the
  canonical inputs JSON, e.g. `{"inputs":[]}`; refused, never truncated, above MLflow's 8000-character
  tag limit). Every MLflow path takes its tags from
  this method, including the surrogate paths that bypass `start_provenance_run`, and
  `start_provenance_run` accepts only a `ProvenanceTupleV2`.
- **The Postgres mirror.** Migration `006_provenance_schemes` adds nullable `TEXT` columns
  `dvc_input_hash_scheme`, `container_sif_sha256_scheme` and `dvc_inputs`, with a CHECK
  (`provenance_schemes_consistent`) that the two scheme columns are both NULL or both set, and that
  `dvc_inputs` is set exactly when the DVC scheme is `declared-dvc-pointers-md5/v1`. It has no
  DEFAULT, no UPDATE and no INSERT, so no historical row changes. The operator applies it before the first PR that writes the new columns is
  pushed, because PR CI writes to the shared mirror.
- **Legacy stays legacy.** `ProvenanceTuple` is unchanged and byte-identical; it is the only tuple that
  crate format v1 and the payload models (`ReportableResult`, `OptimizationResult.cfd_verified`,
  `CorpusRow`) accept, and a `ProvenanceTupleV2` there is refused. In-memory consumers
  (`BenchmarkResult`, `MeshSweep`, the optimizer objective) take a discriminated union, and committed
  `data/vv` records reload as legacy.
- **Interim states are labelled, never absent.** The first implementing PR ships the type with both
  terms at `…/v0`; the O-08 PR flips the container term to v1; the O-07 PR flips the DVC term to v1.
  Each boundary is the merge commit that first produces a scheme on `main`, and the Status line of
  the ADR concerned records it.

**The reading rule.** A run, mirror row or record **without** scheme tags was recorded by code that
predates `ProvenanceTupleV2` (Stage-23 runs before the first implementing PR's merge included): its
`dvc_input_hash` is the ADR-004 sync-state digest (the erratum above applies) and its
container digest a lookup. A run **with** them carries exactly the semantics its tags name. Old runs
are never backfilled, and their values cannot be recomputed (they depended on remote state).

### The Invariant 3 text this ADR's implementing PR applies

Item 2 becomes:

> 2. `dvc_input_hash` — sha256 of the line `aero.dvc-inputs/v1` (with its line feed) followed by the
>    canonical JSON `{"inputs":[{"hash":"md5","md5":…,"path":…,"size":…},…]}`, sorted by `path`, of
>    the `.dvc`-tracked inputs the case **declares**: each output's repo-relative path, md5 and size,
>    read from its git-tracked pointer at `git_sha` (scheme `declared-dvc-pointers-md5/v1`; the
>    byte-exact definition and golden values are in ADR-052). Every platform read of a DVC-tracked
>    file goes through one reader, which checks the bytes against the declared pointer and refuses a
>    file the run did not declare. A case with no DVC-tracked input records the canonical empty set.
>    A run whose `dvc_input_hash_scheme` tag is absent or is `repo-sync-state/v0` carries the
>    repository-wide `dvc status -c` digest (ADR-004); such runs are never relabelled.

The same amendment brings the rest of Invariant 3 up to date in the same window, so it never has to
reopen: item 3's roster sentence names `ProvenanceTupleV2.containers` (the roster is unchanged), and
the Enforcement paragraph names `ProvenanceTupleV2`, the scheme tags, the mirror columns and ADR-053's
launch guard (`build_apptainer_exec`; exit 86 → `ProvenanceError`), and says that `ReportableResult`
and format-v1 crates carry the legacy `ProvenanceTuple` until a crate-format-v2 ADR.

## Consequences

- **Positive:**
  - the term means what Invariant 3 says, is identical on every machine, and is recomputable from git
    alone; key rotation or a moved remote can no longer break a solve's provenance;
  - the first content check of `onera_m6.su2`'s bytes; workspace edits to declared data are refused;
  - every new record says which semantics produced each term, in MLflow, the mirror and the type.
- **Negative:**
  - churn: 18 case classes, 2 optimizer classes, 6 adapter staging sites, 34 call sites, ~10 type
    annotation sites;
  - capability: until a crate-format-v2 ADR, no new-semantics `ReportableResult`,
    `OptimizationResult` or `CorpusRow`, and no crate of a new-semantics run; `aero surrogate train`,
    DoMINO and the historical stage drivers refuse loudly (each ledgered);
  - an Invariant 3 amendment with its ≥72 h window sits on the release path.
- **Neutral / follow-up:** a crate format v2 (and Invariant 13's "format v1"); a DVC scheme for `.dir`
  and `dvc.lock` outputs; `dataset_hash`'s own ADR before the Stage-17 certificate is renewed; whether
  the V&V report filters or only displays schemes (Stage 24).

## Links

- ADR-004 (four-fold provenance), ADR-011 (DVC remotes), ADR-038 (multi-container roster), ADR-047
  (result crates, format v1), ADR-049 (O-07, H-33), ADR-050 (the hosted case), ADR-051 (row 23), ADR-053
  (O-08).
- CONSTITUTION Invariants 3, 9 and 13.
- `aero/provenance/four_fold.py`, `aero/provenance/mlflow.py`, `aero/provenance/db.py`,
  `db/migrations/005_container_set.sql`.
- Stage prompt `docs/handoff-bundle/STAGE-23-foundation-provenance.md`; the operator's decisions D1, D2
  and D4 (2026-10-21): `docs/handoffs/STAGE-23-foundation-provenance-DONE-2026-10-21.md` §2.
