# ADR-047 — RESULTS-MUST-TRAVEL: the `aero-result-crate` format v1, and Hard Rule 16 → CONSTITUTION Invariant 13

- **Status:** proposed. Ratification is a separate constitution micro-PR. It needs a ≥72 h window
  counted from this ADR's date and the operator's sign-off (CONSTITUTION "Amendment process"). The
  code lands without waiting; the ADR-027 two-track precedent applies.
- **Date:** 2026-10-12
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 21)
- **Stage:** 21 (ADR-046 S1 moved the promotion here from Stage 20)
- **Supersedes:** none. It promotes CLAUDE.md Hard Rule 16.

## Context and problem statement

Hard Rule 16 (RESULTS-MUST-TRAVEL) says every exported result is a self-describing bundle
(`CaseSpec` + four-tuple + U95 envelope + validity context) usable in a thesis without the
cluster. No such bundle exists. The stage-open audit (2026-10-11; stage prompt "Why this stage")
measured why the existing records cannot travel:

1. **The platform's own serialization does not round-trip.** `model_dump_json()` writes the 12
   computed fields of the `ReportableResult` tree, and `_STRICT` (`extra='forbid'`,
   `aero/vv/reportable.py:52-57`) rejects them on load. None of the 9 committed `ReportableResult`
   JSONs in `data/vv/` reloads as written. Once computed keys are stripped, the Stage 12/15/16/17
   records reload and their recomputed values match bit for bit. The four Stage-13 records do not:
   they predate the `u95_input_basis` validator (`reportable.py:164-175`). That is schema drift.
2. **The CaseSpec cannot be re-derived from today's code.** `config_hash`
   (`aero/provenance/four_fold.py:267-279`) is a digest of whatever payload the producer passed,
   and CaseSpec has gained fields since then. Stage 17 at HEAD hashes to `c1a92546…`, while the
   record says `72e3e030…`; dropping Stage 20's `section` key reproduces the recorded value. A
   bundle must carry the exact as-hashed bytes.
3. **The reader cannot be core-only today.** `aero.vv.reportable` drags in loguru through
   `aero/vv/__init__.py:15 → aero/vv/_base.py:24 → aero/adapters/_base.py:37` and
   `aero/orchestration/local_ssh.py:18`.
4. **Two provenance fields are weaker than their names suggest.** `dvc_input_hash` is a digest of
   the `dvc status -c` sync state: one constant across all 74 occurrences in `data/vv`.
   `container_sif_sha256` is a basename lookup in `containers/SHA256SUMS` (review item P1c).
5. **"Validity context" exists only as prose** (`docs/vv/output-validity-bar.md` §5).

## Decision drivers

- **Same numbers.** Read-back must be bit-for-bit, not approximately equal.
- **Portability.** A crate must be verifiable without the cluster, the DVC remotes, MLflow or the
  repository.
- **PLATFORM-NOT-HUB.** The reader imports only stdlib + numpy + pydantic.
- **FAIL-LOUD.** No silent coercion, no `null` for a non-finite number, no unknown members.
- **Honesty is structural.** A crate cannot claim more than its content supports. The limitations
  its own content makes mandatory are machine-checked.
- **Standards alignment** (00-MISSION §3.7). RO-Crate and W3C PROV consumers get real value.
- **Small blast radius.** No change to the constitutional-gate schemas beyond closing holes; no
  vv-required churn.

## Considered options

1. **Ad-hoc JSON records with `model_dump_json`**, the status quo. Rejected: they do not reload
   (fact 1).
2. **A minimal directory format**: `SHA256SUMS` + the typed result + configs, plus an RO-Crate file
   with inline PROV-O only. This is smaller, but it has no run-crate profile, no PROV document an
   external tool can parse, and no container entity.
3. **A standards-faithful result crate.** RO-Crate 1.3 + Process Run Crate 0.6 + a PROV-JSON
   sidecar, all generated deterministically from one typed envelope that the reader re-derives.
   This is **chosen**, slimmed by option 2's mechanisms: the lossless-subset rule for computed
   fields, one-shot era recipes kept out of platform code, and Stage 14 as an evidence-only crate.
4. **ro-crate-py / prov as runtime dependencies.** Rejected: PLATFORM-NOT-HUB. They are used only
   as CI-side validators.

## Decision outcome

Chose **option 3**. The bundle is an **`aero-result-crate`, format version 1**, written and read
only by the core package **`aero/crate/`** (stdlib + numpy + pydantic). The word "bundle" stays in
prose that quotes Hard Rule 16; in code it is already taken by the Stage-20 evidence dicts, the
precice manifest and the Stage-17 corpus.

### D1 — Members (closed set)

A crate is a directory `crates/<crate_id>/` (`crate_id` matches `^stage\d{2}-[a-z0-9-]{3,60}$`), or
a deterministic ZIP_STORED archive of it. The archive is the RO-Crate *Attached Package* form, with
the metadata file at its root.

| Member | Content |
|---|---|
| `SHA256SUMS` | `<64hex>  <path>\n`, path-sorted, LF, every member except itself. The **crate digest** is `sha256(SHA256SUMS)`. |
| `aero-crate.json` | The typed envelope (`CrateManifest`), the single source of truth. |
| `result.json` | The `ReportableResult`, including computed fields. Absent for an evidence-only crate. |
| `configs/<config_hash>.json` | The exact as-hashed config preimage: `json.dumps(cfg, sort_keys=True, separators=(",",":"))` as ASCII with no newline, so `sha256(file)` is the recorded `config_hash`. |
| `evidence/<name>` | Verbatim copies of source records (opaque bytes; hash-pinned). |
| `ro-crate-metadata.json` | RO-Crate 1.3 + Process Run Crate 0.6 JSON-LD. A deterministic projection of the envelope. |
| `prov.json` | W3C PROV-JSON. A deterministic projection of the envelope. |

Member names are lowercase, at most two path segments deep and at most 128 characters long. The
reader refuses:
- `..`, absolute paths, backslashes, NUL, duplicates and case-fold collisions;
- symlinks and non-regular files;
- the ADR-045 basenames;
- more than 64 members, a member over 4 MiB, or more than 16 MiB in total.

### D2 — Byte rules

- Document JSON is written as `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True,
  allow_nan=False) + "\n"`. Every document must be a fixed point of that encoder.
- Pydantic payloads are re-encoded through the stdlib, so pydantic-version-specific float tokens
  never reach disk.
- Parsing is strict: duplicate keys, `NaN` / `Infinity` / `1e999` tokens, a BOM, CR characters and
  invalid UTF-8 are all refused. Validation uses `model_validate` on the strictly parsed object,
  never `model_validate_json`.
- The one legal non-finite value, `StatisticalUncertainty.crosscheck_ratio = inf`, travels as the
  string `"Infinity"`.

### D3 — Verification (`verify_crate`)

1. **Fixity first.** The member set is closed and matches `SHA256SUMS`. Every member is hashed
   before any parse, and an optional `expect_digest` is checked.
2. **Envelope.** `aero-crate.json` must be strict-parsed, valid as a `CrateManifest`, a byte-identical
   re-dump, and consistent with `SHA256SUMS` in its member table.
3. **Payload.** `result.json` validates as a `ReportableResult` under the **lossless-subset rule**:
   - every leaf in the file exists in the model's own re-dump with the same type and value, with
     floats compared through `float.hex`;
   - every computed field is present and recomputes bit for bit;
   - keys present only in the re-dump must be listed, with their exact defaults, in an ADR-governed
     `ADDED_FIELDS` allowlist (initially `provenance.containers = []`,
     `optimization.cfd_verified.containers = []`, and `u95_input_basis = "skipped"` where
     `u95_input == 0`).
4. **Configs.** Each stem equals `sha256(bytes)` and equals `four_fold.config_hash(parsed)`. A
   config is **never** validated into a HEAD CaseSpec.
5. **Legacy replay.** Where the source record is embedded as evidence, a legacy import of it must
   equal `result.json`. This proves the result was derived from the committed record, not hand-edited.
6. **Validity rules (D4)** hold.
7. **Projections.** `ro-crate-metadata.json` and `prov.json` regenerate byte for byte.

The reader never fetches a JSON-LD context, never executes, unpickles or imports anything named by
crate content, and never touches the network. The `python -I -m aero.crate verify` entry point runs
under an audit-hook sandbox that denies sockets, subprocesses and writes.

### D4 — The validity context (the concrete definition of Hard Rule 16's "validity context")

`ValidityContext` carries:
- `claim_tier`: `none | smoke | validated | thesis-grade`. It equals `result.validation_tag`, or
  `none` for evidence-only crates.
- `claim_scope`: `optimization | forward-capability | uq-reference`, plus `flagship_domain`.
- `verdicts`: typed `GateVerdict`s. Each records the verbatim criterion, comparator, threshold,
  observed value, `passed` (re-derived on read), whether it was **gated** (pre-registered, with a
  reference to where) or a reported **diagnostic**, and the overall GO / NO-GO.
- `design_space` / `conditions`: the applicability bounds.
- `certificate_expiry`, where a surrogate certificate is cited.
- `limitations`: from a closed vocabulary. Each quotes its source verbatim and references it.

**Required limitations** follow from content and are machine-checked:

| Content | Required limitation |
|---|---|
| any skipped input UQ | `input-uq-skipped` |
| no passing experiment anchor | `no-experiment-anchor` |
| any NO-GO verdict | `nogo` |
| any diagnostic | `diagnostic-not-gate` |
| any unavailable provenance | `provenance-unavailable` |
| a non-public commit | `provenance-sha-not-public` |
| any available four-tuple | `dvc-input-hash-sync-state` and `container-digest-by-lookup` |
| a cited certificate | `certificate-expiry` |
| an optimization outside the flagship domain | `not-flagship-domain`, quoting ADR-046 S3 |

Other structural rules:
- An **evidence-only** crate (`payload = none`, `claim_tier = none`) must declare every missing core
  component. It can carry no GO verdict.
- Exactly one run is the record of provenance; its four-tuple must equal `result.provenance`.
- An optimization crate must have a CFD-verification run whose four-tuple equals
  `optimization.cfd_verified`.
- `CodeIdentity` records whether the run's commit is publicly resolvable and how it relates to the
  stage tag (`is-tag-commit | code-trees-identical | code-trees-differ | not-established`). CI
  checks both directions.

### D5 — Standards projection

- **`ro-crate-metadata.json`.** `@context` is the RO-Crate 1.3 context plus the Workflow Run Crate
  context. The root `conformsTo` lists RO-Crate 1.3 and Process Run Crate 0.6
  (`https://w3id.org/ro/wfrun/process/0.6`).
- **Runs.** Each run with available provenance is a `CreateAction` (also typed `prov:Activity`) with:
  - an `instrument` `SoftwareApplication` (`prov:SoftwareAgent`) at the run's git SHA;
  - a `containerImage` (`SIFImage`, sha256);
  - `object` set to the config `File` plus the four-tuple as `PropertyValue`s;
  - `result` set to the U95 terms as `PropertyValue`s.
- **Export action.** Every crate also has one export `CreateAction`, so even an evidence-only crate
  satisfies the profile's MUSTs.
- **`prov.json`** is the PROV-JSON projection of the same graph, following the Leo et al. (2024)
  RO-Crate↔PROV-O mapping.
- **Validation.**
  - PROV-O is the normative W3C target; PROV-JSON is a W3C Member Submission chosen because
    `prov` 3.2.2 (MIT, CI-only) parses it offline.
  - The MUSTs of RO-Crate 1.3 and Process Run Crate 0.6, plus PROV equivalence, are checked
    in-repo with the stdlib.
  - `roc-validator` 0.12.2 validates the 1.3 base in a non-required CI job. Its Process Run Crate
    profile is still 0.5, for RO-Crate 1.1.

### D6 — Licence

Crate content (the platform's own results and metadata) is **CC-BY-4.0** (operator decision D3,
2026-10-11). Third-party reference values appear only as cited scalars inside validation anchors and
gates, never as copied datasets. Reference data is referenced by DOI and sha256, not embedded. The
software stays GPL-3.0-or-later.

### D7 — Producers, legacy and immutability

- **Producer contract (Stage 22 on).** Keep the exact `resolved_config` passed to
  `compute_provenance`, and call `aero.crate.write_crate` with it.
- **The five v0.1.0 crates.** Stages 12, 14, 15, 16-relaxed and 17 are built once by
  `scripts/stage21_export_crates.py` from an explicit record-of-record registry that never globs.
  Its era recipes reconstruct each as-hashed config and must reproduce the recorded hash before
  anything is written.
- **CI never re-runs the recipes.** It re-reads and rewrites the committed crates and requires byte
  equality, so a future CaseSpec field cannot turn CI red.
- **Stage 13** is refused (schema drift), not migrated.
- **Stage 14** has no four-tuple, U95 or CaseSpec in its record. It ships as an **evidence-only**
  crate and carries no claim.
- **Format v1 is frozen at ratification.** Any change to the member set, the rules or the
  projections is format v2 plus an ADR, and readers keep the v1 path. Payload models may evolve
  additively only through the `ADDED_FIELDS` allowlist.
- **Published crates are immutable from v0.1.0.** A result is cited by crate digest plus its
  four-tuple.
- **Nothing is ever written under `data/vv/`.** The writer refuses such destinations and the
  ADR-045 basenames.

### D8 — Enforcement and the draft Invariant 13

**Enforcement:**
- the round-trip, tamper, archive-safety, import-isolation and committed-crate tests in `tests/unit`
  (required context `pytest unit (py3.12)`);
- the new required context **`crate round-trip — Invariant 13`**. Crates are written on one runner,
  moved, and verified on fresh Linux, macOS and Windows runners that hold only the built wheel,
  numpy and pydantic, with no repository checkout. The same numbers are compared bitwise against an
  independent stdlib oracle built from the committed source records.

**Draft CONSTITUTION Invariant 13 — RESULTS-MUST-TRAVEL** (text final at the micro-PR):

> Every result the platform reports outside the repository is a self-describing result crate
> (`aero-result-crate` format v1, ADR-047). It carries the exact as-hashed CaseSpec bytes of every
> run it cites, the four-fold provenance tuple (Invariant 3), the U95 envelope (Invariant 10) and its
> validity context: claim tier, pre-registered gate verdicts and reported diagnostics, applicability
> bounds, and the limitations its own content makes mandatory. It is verifiable, and reads back to
> the same numbers, without the cluster, the DVC remotes, MLflow or the repository. A result that
> cannot carry its four-tuple, U95 or CaseSpec travels only as an evidence-only crate that declares
> each missing component and carries no claim. **Enforcement:** `aero/crate/` (stdlib + numpy +
> pydantic) is the one writer and reader. Required checks `pytest unit (py3.12)` and `crate
> round-trip — Invariant 13`. Published crates are immutable.

### Consequences

- **Positive:**
  - Results become citable and checkable away from the cluster at three levels:
    - coreutils `sha256sum -c`;
    - any RO-Crate or PROV tool;
    - the full semantic check with only numpy and pydantic installed.
  - The Invariant-10 non-finite hole and the libm-dependent RSS are closed as prerequisites (ADR-049).
- **Negative:**
  - The format is strict and frozen, so any change needs an ADR.
  - The era recipes encode three historical CaseSpec canonicalisations, once.
  - Stage 14, the flagship domain's only validation, travels without a claim. That is the honest
    state of its record.
- **Follow-up:**
  - Crates for Stages 18–20 need a later ADR.
  - A content-addressed `dvc_input_hash` is a post-v0.1.0 ADR, because it changes four-tuple
    semantics.

## Links

- CLAUDE.md Hard Rule 16; ADR-046 S1; `docs/vv/output-validity-bar.md` §5;
  `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` §3.7.
- ADR-015 (the invariant bar: a schema plus a CI gate), ADR-023, ADR-027 (the promotion precedents),
  ADR-038 (the container roster), ADR-048 (licence), ADR-049 (release governance and hardening).
- RO-Crate 1.3 (https://w3id.org/ro/crate/1.3); Process Run Crate 0.6
  (https://w3id.org/ro/wfrun/process/0.6); W3C PROV-O (https://www.w3.org/TR/prov-o/); PROV-JSON
  (https://www.w3.org/submissions/prov-json/); Leo et al. 2024, "Recording provenance of workflow
  runs with RO-Crate", PLOS ONE (arXiv:2312.07852).
