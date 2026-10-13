# JOSS submission (Stage 21 ends at "ready to submit")

The paper is `paper/paper.md` with `paper/paper.bib`. `.github/workflows/joss-draft.yml` builds the
JOSS PDF on every PR that touches `paper/`.

## Gates before submission (the operator submits)

1. **Six months of public history.** The repository has been public since 2026-05-17, so the
   earliest submission is **2026-11-18**.
2. **v0.1.0 is published** as a GitHub Release, not a draft or pre-release, and its Zenodo version
   DOI is recorded in `docs/release/zenodo.md`.
3. **The operator metadata is filled in** (`docs/release/operator-metadata.toml`): ORCID,
   affiliation, funding, the realized research use, and the human-review statement for the AI
   disclosure.
4. **`python3 -I scripts/ai_usage_inventory.py --write --ref origin/main`** has been run and the
   result reviewed. The disclosure is generated from the handoffs and commit trailers, never
   written from memory.
5. **`python3 -I scripts/release_readiness.py --gate joss --online`** prints `READY TO SUBMIT`. It
   also checks the word count (750–1750), the required sections, that every citation key resolves,
   the title and the date format, and that no sentinel is left.

## The rule for review conversations

JOSS forbids AI tools in author–editor and author–reviewer conversation. **Every reply on the JOSS
review issue is written by the operator.** An agent session may prepare code changes that a
review asks for, through the normal PR path. It never drafts, posts or edits review comments.

## Claims

The paper's numbers are tied to the result crates by `docs/release/claims-ledger.toml` and
checked by `tests/unit/test_release_claims_ledger.py`. Changing a number in the paper without
changing the crate fails CI.
