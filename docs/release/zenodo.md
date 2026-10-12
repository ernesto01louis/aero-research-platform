# Zenodo release & DOI workflow

`aero-research-platform` is archived to [Zenodo](https://zenodo.org) so each
release is citable from external papers, alongside the four-fold provenance
contract (ADR-004).

## Concept DOI vs version DOI

Zenodo issues two kinds of DOI:

- **Concept DOI** — one per project, stable forever, always resolves to the
  *latest* release. This is the DOI in `CITATION.cff`.
- **Version DOI** — one per GitHub release, points at that exact archive.

A concept DOI can be **reserved** before the first release and written into
`CITATION.cff` ahead of time.

## One-time setup (operator)

1. Sign in to <https://zenodo.org> with the GitHub account that owns the repo.
2. **Account → GitHub**: flip the `aero-research-platform` repository switch
   **on**. This installs the Zenodo release webhook.
3. In the repository's Zenodo entry, **reserve the concept DOI** (Zenodo shows
   a reserved DOI before any release exists).
4. Record the reserved concept DOI in `CITATION.cff` under `identifiers:`
   (`type: doi`). Commit it: `docs(stage-NN): record reserved Zenodo DOI`.
5. Validate: `cffconvert --validate`.

## Per-release flow

1. The operator tags the release (`vX.Y.Z`; `tag-handoff-gate` must go green), then creates and
   **publishes** a GitHub Release from the tag, with the artifacts from `release-readiness.yml`
   attached. A draft or a pre-release mints nothing.
2. The Zenodo webhook archives the tarball automatically and mints a **version
   DOI**; the concept DOI updates to point at it.
3. No manual upload step — the GitHub Release is the trigger.

## Notes

- Zenodo only archives **GitHub Releases**, not bare tags — create the Release.
- `.zenodo.json` (repo root, since Stage 21) is **authoritative**: when it exists, Zenodo ignores
  `CITATION.cff`. It deliberately has no `version` or `publication_date`, because those come from
  the tag and the Release. `tests/unit/test_release_metadata_consistency.py` keeps it consistent
  with `CITATION.cff`, `pyproject.toml` and the paper.
- Never print the Zenodo webhook configuration (`gh api .../hooks`): it contains a token.
- The concept DOI reservation is **permanent** — it is requested once, with
  operator `approved`.

## Version DOIs

Each published release gets a version DOI. It is recorded here in the first PR after publication,
and `scripts/release_readiness.py --gate joss` requires it. Concept DOI: `10.5281/zenodo.20292712`.

| Release | Version DOI | Published |
|---|---|---|
| v0.1.0 | *(recorded after the Release is published)* | — |
