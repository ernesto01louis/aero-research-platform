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

1. Tag and push a release (`v0.0.NN` during the staged build; `v0.x` / `v1.0`
   after Stage 16). Create a **GitHub Release** from the tag.
2. The Zenodo webhook archives the tarball automatically and mints a **version
   DOI**; the concept DOI updates to point at it.
3. No manual upload step — the GitHub Release is the trigger.

## Notes

- Zenodo only archives **GitHub Releases**, not bare tags — create the Release.
- `.zenodo.json` (optional, repo root) overrides Zenodo's metadata extraction;
  until it exists, Zenodo reads `CITATION.cff` and the repo description.
- The concept DOI reservation is **permanent** — it is requested once, with
  operator `approved`.
