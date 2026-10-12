# STAGE 21 — Release: Portable Bundles + Hardening + v0.1.0 (release-first, ADR-046)

> **Stage 20 is CLOSED.** It ended in a recorded NO-GO ON INFRASTRUCTURE (ADR-041 "V7 — FIRED",
> 2026-09-20), is `status: complete` with that NO-GO as its verdict, and is tagged `v0.0.20`.
> Do not reopen it, retry any of its levers, or re-argue this stage's scope: **ADR-046 (accepted
> 2026-10-10) defines this stage.**
>
> **The limitation this release carries (ADR-046 S2/S3, operator option (i)).** At v0.1.0 the
> optimizer is demonstrated on the **airfoil** case only (Stages 15/16/17: `validated`-tier and
> gate-honest, including Stage 16's one-gate NO-GO and Stage 17's degenerate speed-up NO-GO).
> **The optimizer has never been run on a flapping case.** The flagship flapping domain ships as
> Stage 14's forward capability: its rotation-timing ordering is reproduced, and its stroke-averaged
> mean lift is a documented NO-GO. **No flapping optimization claim is made at v0.1.0.** This goes
> in the **body** of the release notes and the JOSS paper, never a footnote. Rigid-flapping
> optimization is the first post-v0.1.0 stage (Stage 22). Flexible-flapping optimization is
> DEFERRED (ADR-046 S4); re-entry needs ADR-046 S5 and a NEW ADR.
>
> **No compute.** There is no compute campaign and no budget in this stage. The "burst" tier in
> `README-handoff.md` row 21 is superseded. Any solve or campaign needs a new ADR and the operator.

## BEFORE YOU START — READ

1. `CLAUDE.md` (Hard Rule 16 now says Stage 21; Principle 5 and Hard Rule 10 are amended by this
   stage's constitution PR) and `.aero-stage` (→ `21`).
2. **ADR-046** S1–S6; `docs/handoff-bundle/README-handoff.md` row 21 and the DEFERRED row under it;
   `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` roadmap item 11.
3. `docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` §0, §6.88–§6.89, §7 —
   context only. `data/vv/stage20_nogo_infrastructure.json`.
4. The substrate the crate builds on: `aero/vv/reportable.py`, `aero/vv/reportable_compose.py`,
   `aero/provenance/four_fold.py`, `aero/optimize/report.py`, `docs/vv/output-validity-bar.md`.
5. Governance: `CONSTITUTION.md` (amendment process at the end of the file); ADR-015, ADR-023,
   ADR-027 (the promotion precedents); `scripts/check_handoff_exists.sh`,
   `scripts/regenerate_status.sh`, `.github/workflows/tag-handoff-gate.yml`.
6. ADR-047 / ADR-048 / ADR-049 once they land (this stage writes them).

## Why this stage

v0.1.0's purpose is portability, citability and hardening, and none of it depends on flapping. An
audit at stage open (2026-10-11) found that the release is not shippable as the repository stands:

- **Results do not travel.** No committed `ReportableResult` JSON reloads into its own model:
  default `model_dump_json()` writes the computed fields (`u95_total`, `delta`, `u95_delta`,
  `required_margin`), and `extra='forbid'` rejects them on load. No record embeds its CaseSpec, and
  `config_hash` cannot be re-derived from today's models (Stage 17 at HEAD hashes to `c1a92546…`; the
  record says `72e3e030…`; dropping the Stage-20 `section` key reproduces it).
- **A FAIL-LOUD hole in a constitutional gate.** `ImprovementClaim(baseline=nan)` constructs and
  composes into a thesis-grade `ReportableResult` (`reportable.py:413` compares `delta <=
  required_margin`, which is False for NaN), and the default `ser_json_inf_nan='null'` then writes an
  unreadable record.
- **The reader cannot be core-only.** `aero.vv.reportable` cannot be imported with only stdlib +
  numpy + pydantic: loguru arrives via `aero/vv/__init__.py:15 → aero/vv/_base.py:24 →
  aero/adapters/_base.py:37` and `aero/orchestration/local_ssh.py:18`.
- **Provenance does not resolve.** The Stage-17 run SHAs (`30595a39`, `e2ec52bb`, `41f1f468`) exist
  only on an unpushed local branch; the Stage 12/15/16 SHAs only on deletable remote branches.
  `dvc_input_hash` is a sync-state digest (one constant across all 74 occurrences in `data/vv`), not
  a content address.
- **The release tag is ungated.** `tag-handoff-gate.yml` fires only on `v0.0.*`.
- **Outside readers arrive with v0.1.0.** `pip install aero` installs an unrelated 2011 PyPI package;
  three self-hosted jobs can be triggered by fork pull requests on this public repo; every action
  is on a mutable tag; `ubuntu-latest` moves to Ubuntu 26 on 2026-10-19.

## Operator decisions recorded at stage open (2026-10-11)

| # | Decision | Choice |
|---|---|---|
| D1 | Dependency licence policy (ADR-048; Invariant 5 rewording) | GPL-3.0-compatible allowlist, scoped. Reviewed exact-version exceptions. Base install and supported extras proprietary-free. NVIDIA proprietary CUDA wheels only in the frozen GPU extras `jax-fluids`, `surrogate-smoke`, `physicsnemo-cu12` (ADR-010 precedent). **dvc stays in the base dependencies**; grandalf, pygit2 and zc-lockfile become reviewed exceptions. |
| D2 | Claim wording | **Record-faithful** wording in the release notes, the JOSS paper, `CITATION.cff`, `.zenodo.json` and the crates (table below). ADR-046 stays exactly as accepted. |
| D3 | Licence of the result crates' content | **CC-BY-4.0** for the platform's own results and metadata. Third-party reference values appear only as cited scalars, never as copied datasets. |
| D4 | Evidence tags | Yes. After a clean gitleaks scan of the newly published range, push annotated, non-release `stage-NN-evidence-*` tags for the Stage 12/15/16/17 provenance SHAs (the `stage-20-evidence-2026-09-20` pattern). This publishes the 37 Stage-17 commits. |

### Record-faithful wording (D2): what the records support

| Topic | Do not write | Write (source) |
|---|---|---|
| Stage 14 ordering | "rotation-timing trend VALIDATED" (unqualified) | The ordering advanced 0.577 > symmetrical 0.467 > delayed 0.137 is **reproduced — a pre-registered, non-gated diagnostic** (`docs/vv/stage14-preregistration.md:51-56`); advanced and delayed magnitudes miss experiment by 38 % and 64 % (`data/vv/stage14_flapping_nogo.json`). |
| Stage 14 mean lift | — | Gated symmetrical mean lift misses the WBD 2004 experiment by 45.7 % against a pre-registered ±25 % band — a documented NO-GO; the band was not relaxed. |
| Stage 14 cause | "root-caused to overset wake-capture dissipation" | Overset wake-capture dissipation is **the leading hypothesis** (Stage-14 handoff :153-155). |
| Stage 15 | "+113 %", "+47 %", "large improvements" | The optimum's matched delta 24.66 did **not** exceed its own U95 of 25.37; not grid-converged; the "+47 %" claim was retracted (CHANGELOG [0.0.15]). |
| Stage 16 | — | Honest NO-GO by one pre-registered gate: observed order 0.465 vs the 0.5 floor; shipped `validated`. |
| Stage 17 loop | "the validated ensemble drove the loop" | The loop's proposals came from **smoke-tier, in-loop retrained ensembles** (by design, ADR-032); every proposal was CFD-verified; the `validated` certificate is a separate fit (`data/vv/stage17_arm_surrogate_explore.json`). |
| Stage 17 optimum | "46.372 > corpus best 46.337" as an improvement | 46.372 exceeds the corpus best by 0.035, inside that quantity's U95 of 7.03, and is not claimed. The claim that clears 2·U95 is vs the **baseline** (24.70 > 4.15 under a 2-grid GCI, capped at `validated`). "Held-out" means a deterministic same-grid re-solve. The speed-up is a degenerate NO-GO. |
| Airfoil forward model | "validated against experiment" | No experiment anchor (`anchors = []` in every Stage 15–17 record). The only thesis-grade record is Stage 12's lock-in cylinder. Mission publish-bar criterion 2 is not met. |
| Four-tuple | "the four-tuple identifies the inputs" | `dvc_input_hash` is a DVC sync-state digest, not a content address; `container_sif_sha256` is a basename lookup in `containers/SHA256SUMS`, not a re-hash of the SIF that ran. Crates add content digests. |

The required sentence, verbatim in the paper's Summary and limitations section, the release notes,
the `CITATION.cff` abstract and the `.zenodo.json` description: **"The optimizer has never been run
on a flapping-wing case, and v0.1.0 makes no flapping-wing optimization claim."**

## Deliverables

1. **Bookkeeping (PR-01).** `.aero-stage` → 21; this prompt; `CLAUDE.md` Hard Rule 16 says Stage 21
   (substance unchanged); the handoff template's inline comments moved to their own lines (they broke
   the Stop-hook parser); a `status: partial` Stage-21 handoff from the first commit on.
2. **Result crates — the RESULTS-MUST-TRAVEL bundle (ADR-047).** A new core package `aero/crate/`
   (stdlib + numpy + pydantic only; outside the vv-required path filter; "bundle" is already taken in
   the code base). A crate is a directory (or a deterministic STORED zip) holding:
   - `aero-crate.json` — the typed envelope (`CrateManifest`): runs with `ProvenanceAvailable |
     ProvenanceUnavailable`, a concrete `ValidityContext` (claim tier, pre-registered gate verdicts
     and reported diagnostics, applicability bounds, required limitations quoted verbatim), the
     member table, the licence (CC-BY-4.0);
   - `result.json` — the `ReportableResult` including computed fields, verified by a lossless-subset
     rule (every computed value recomputed and compared bit for bit);
   - `configs/<config_hash>.json` — the exact as-hashed CaseSpec preimage, so `sha256(file)` **is**
     the recorded `config_hash`; never re-derived from HEAD models;
   - `evidence/…` — verbatim source records;
   - `ro-crate-metadata.json` (RO-Crate 1.3 + Process Run Crate 0.6, PROV-O typed) and `prov.json`
     (PROV-JSON) — deterministic projections that the reader regenerates and compares byte for byte;
   - `SHA256SUMS` — coreutils format; the crate digest is `sha256(SHA256SUMS)`.

   The reader hashes every member before parsing it, refuses unsafe or unknown members, duplicate
   keys and non-finite numbers, never fetches a JSON-LD context and never executes content. The
   v0.1.0 set is five committed crates under `crates/`: Stage 12 (thesis-grade UQ reference), Stage
   14 (evidence-only: provenance unavailable, carries no claim), Stage 15, Stage 16 (relaxed, the
   record of record) and Stage 17. Stage 13 is refused (schema drift) rather than migrated. Nothing is
   ever written under `data/vv/`.
3. **Round-trip CI (`crate-roundtrip.yml`).** Crates are written and packed on one runner, moved,
   and verified on fresh Linux, macOS and Windows runners with **no checkout**, holding only the
   built wheel, numpy and pydantic (plus a dependency-floor leg and a Python 3.13 leg). The same
   numbers are compared bitwise against an independent stdlib oracle built from the committed source
   records. One aggregator job, **`crate round-trip — Invariant 13`**, becomes a required context
   after its first green run on main.
4. **Dependency licence scan (ADR-048).** `scripts/licence_scan.py` (stdlib, `python3 -I`) over
   `uv.lock`, using hash-verified PEP 658 metadata from a committed snapshot, so the required job is
   offline and deterministic. The policy and exceptions files live under `ci/licence/`. Required
   context **`dependency licence scan — Invariant 5`**. Separately, `license-audit.yml` (the
   certificate watermark, which today scans zero files) is repaired.
5. **Hardening — a closed list.** IN items H-01 … H-36 and OUT items O-01 … O-24 are recorded in the
   stage plan and ADR-049. P0: release-tag gate (H-01), the non-finite hole and IEEE-exact RSS
   (H-02/03), version single-sourcing (H-04), install text (H-05), verifiable "all required CI
   green" (H-06), evidence tags (H-07), CI supply chain — SHA pins, `ubuntu-24.04`, permissions,
   step-scoped secrets — **before 2026-10-19** (H-08), shell injection (H-09), vv-transonic REAP +
   concurrency (H-10), fork-PR exposure (H-11), import isolation (H-12). Anything newly found goes
   to `docs/operator/deferred-work-ledger.md` under "Stage 21" unless it blocks GO. OUT includes the
   PSS backfill, the mesh ladder, the bowtie check, 3-D geometry, the fair-test speed-up, the 393²
   rung, any moving-vv compute fix, PyPI, a docs site, and Claude hook/config changes.
6. **JOSS + Zenodo — ends at "ready to submit".** `paper/paper.md` + `paper/paper.bib` (750–1750
   words; sections Summary, Statement of need, State of the field, Software design, Research impact
   statement, AI usage disclosure, Acknowledgements, References), a non-required draft-PDF workflow,
   a refreshed `CITATION.cff` (0.1.0 at release, `GPL-3.0-or-later`, gate-honest abstract),
   `.zenodo.json` (authoritative for Zenodo, which then ignores CITATION.cff) with a consistency
   test, and release notes carrying the limitation in the body. Operator-only metadata (ORCID,
   affiliation, funding, evidence of research use, the AI human-review statement) stays as
   `<<OPERATOR-…>>` sentinels until supplied. **JOSS submission is the operator's, on or after
   2026-11-18** (the repo must be public for more than six months), and **AI must not be used for
   conversations with JOSS editors or reviewers**.
7. **Governance, then v0.1.0 last.** ADR-047 (crates + Invariant 13), ADR-048 (licence policy +
   Invariant 5) and ADR-049 (release governance and CI hardening; Hard Rule 10 extended to release
   tags) land as `proposed`. One constitution micro-PR then waits at least 72 h for the operator's
   sign-off before merging (`CONSTITUTION.md` amendment process). The release PR bumps to 0.1.0,
   completes this handoff (`stage_tag: v0.1.0`, `next_stage: 22`) and authors the Stage-22 prompt.
   The operator tags v0.1.0 and publishes the GitHub Release, which mints the Zenodo version DOI. A
   follow-up PR refreshes the README STATUS block, because the tag must exist first.

## GO / NO-GO

**GO** requires all of:
- (a) `crate round-trip — Invariant 13` is green on the release commit (clean machines, same
  numbers bitwise, same digests);
- (b) all required contexts are green there, checked by the readiness script rather than assumed —
  `enforce_admins` is false and PR #45 merged with a red check;
- (c) Invariant 13 is ratified;
- (d) this handoff is `complete` with `stage_tag: v0.1.0`, and the Stage-22 prompt exists;
- (e) the operator has tagged v0.1.0 and `tag-handoff-gate` is green on it.

**NO-GO**: no tag; the handoff stays `partial` and names what is missing. Never relax a band. No
flapping claim of any kind.

## Infra + conventions + inherited notes

- **vv-required.** It runs the full ~34-min self-hosted suite when a PR touches `aero/adapters/**`,
  `aero/vv/**`, `aero/geometry/**`, `conf/case/**` or `pyproject.toml`. Batch those edits; exactly two
  FULL runs are planned (the core-hardening PR and the release PR). Its concurrency group cancels in
  progress: **never push while a FULL run is in flight**, and never cancel a self-hosted job. Even the
  trivial path needs an online `[self-hosted, vv]` runner (`aero-build-vv`, `aero-build-vv-2`).
- **Hard don'ts.**
  - Never create `data/vv/stage20_adr045_r3.json` or `data/vv/stage20_n3_confirmation.json`.
  - Never fill `<<B1-PENDING-N3>>`, `<<B2-PENDING-ADR040>>`, `<<B3-PENDING-CEILING>>` or
    `<<B2-PENDING-I4>>`.
  - Never delete `stage-20-evidence-2026-09-20`.
  - Never write under `data/vv/`, and never derive file names by stem-stripping.
  - Never `run_long.sh wait`.
  - Never print the Zenodo webhook config; it contains a token.
- **Stop gates.** The v0.1.0 tag, the GitHub Release, the JOSS submission, the constitution sign-off,
  repo settings and anything in `.claude/settings.json` are the operator's. Any compute or Stage-20
  lever needs a new ADR. Destructive, provisioning or non-aero-LXC actions are propose-first with the
  literal `approved`.
- **Commits.** `<type>(stage-21): …`, header ≤ 100 chars (commit-lint is required); quotes via
  heredoc; `.venv/bin` on PATH; `git log -1 --stat` after every commit, because the ruff-format hook
  can roll a commit back silently.
- **The Stop hook.** Once `.aero-stage` is 21, the hook exits 2 until a single
  `docs/handoffs/STAGE-21-*-DONE-*.md` exists in the working tree with five valid frontmatter
  fields. Keep exactly one Stage-21 handoff file: the hook picks the newest-mtime file, while the
  README generator picks the lexicographically last.
- **README STATUS.** `docs-sync.yml` needs `fetch-depth: 0`. A tag must be pushed before the README
  can claim it, so the tagged tree reads `v0.1.0 (not yet tagged)` and the refresh is the first PR
  after the tag.
- **pydantic.** CI resolves dependencies fresh (it got pydantic 2.14 against the locked 2.13.4).
  Crate serialization never relies on pydantic's own JSON tokens.
- **PR #21** is unrelated; leave it.
- **Ledger items carried forward:** Stage-11 PSS S3/S5; the mesh fallback ladder; the bowtie check;
  3-D external geometry; the fair-test speed-up; the 393² rung; moving-vv red since 2026-09-13
  (`plunging_airfoil_hg2007`, rc=124 at the 4 h ceiling), recorded as known-failing. Two ledger
  items are already fixed (`bc1384a`): README STATUS "complete, not yet tagged" and the
  `select_fluid_mesh` hard-code. Close them in the ledger.

## POST-STAGE HANDOFF (mandatory)

`docs/handoffs/STAGE-21-release-portable-bundles-DONE-2026-10-12.md` — one file, kept from stage open
to close (frontmatter + 10 sections). Emphasize:
- the crate format and the round-trip evidence (runner legs, digests);
- the required-context changes;
- the licence policy and its exceptions;
- the hardening disposition table;
- the constitution ratification record;
- where the limitation wording lives;
- the release facts: tag SHA, Release URL, version DOI;
- JOSS readiness and the remaining operator sentinels.

Frontmatter at close: `status: complete`, `stage_tag: v0.1.0`, `next_stage: 22`,
`next_stage_name: "Stage 22 — Rigid-Flapping Optimization"`. Confirm that
`docs/handoff-bundle/STAGE-22-rigid-flapping-optimization.md` exists: the optimizer over Stage 14's
rigid prescribed-kinematics capability, with claims bounded by its mean-lift misses, a new
pre-registration ADR, and a compute-campaign ADR that the operator approves before any run.
