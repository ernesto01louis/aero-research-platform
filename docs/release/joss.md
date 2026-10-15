# JOSS submission (Stage 21 ends at "ready to submit")

> **Status: DEFERRED (operator decision, 2026-10-15).** JOSS's pre-review screening has a must-meet
> item: "There must be evidence that the software is being used for research"; "Aspirational
> statements about future use are not sufficient"; a submission that fails it "will receive a desk
> rejection" (JOSS submitting guide, read 2026-10-15). The paper's research-impact statement is,
> honestly, "used for testing so far", with no external users. So a submission now would be refused.
>
> The project builds its foundation first (ADR-051, proposed). **Resume when** there is evidence of
> research use: a publication or an analysis that uses the platform, or an external adopter. Then
> rewrite the research-impact statement from that evidence, and run the procedure below. The prepared
> metadata (submission date, conflicts of interest: none) is on the branch `joss-submission`
> (closed PR #68); its date and AI disclosure must be redone at that time.

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
   written from memory. The block names the commit it was generated at. `--check` regenerates at
   that commit and allows it to be at most one commit behind, which is the PR that wrote it.
5. **`python3 -I scripts/release_readiness.py --gate joss --online`** prints `READY TO SUBMIT`. It
   also checks the word count (750–1750), the required sections, that every citation key resolves,
   the title and the date format, and that no sentinel is left.
6. **Conflicts of interest.** JOSS asks every author to disclose potential conflicts of interest in
   the manuscript. The statement is the operator's own words, like the AI human-review statement.
   It goes in the paper's Acknowledgements, next to the funding sentence.

The Stage-17 surrogate certificate expires 2027-01-20, and the release checks inside the JOSS gate
require at least 30 days of validity. So the gate passes only through **2026-12-21**. After that the
certificate is re-certified first (compute; a new ADR), or the expiry stands as a stated
limitation and the gate's margin is an operator decision. With the submission deferred, this
decision comes with the resumption.

## Submission day (on or after 2026-11-18)

**1. The repository: one PR, merged before submitting.** Put the operator's date in
`docs/release/operator-metadata.toml`, and the paper's `date:` in `%e %B %Y` form:

```sh
cd /root/projects/aero-research-platform
git fetch origin && git switch -c joss-submission origin/main
# edit docs/release/operator-metadata.toml: submission_date = "YYYY-MM-DD"
# edit paper/paper.md front matter:        date: DD Month YYYY
python3 -I scripts/ai_usage_inventory.py --write --ref origin/main
git diff paper/paper.md            # review the regenerated disclosure
```

Commit (`docs(stage-NN): JOSS submission metadata`), open the PR, and merge it once the required
checks are green. Merge nothing else before submitting: `--check` allows exactly one commit after
the one the block names.

**2. The gate, on main after the merge:**

```sh
git switch main && git pull --ff-only
GH_TOKEN=$(gh auth token) python3 -I scripts/release_readiness.py --gate joss --online
```

It must print `READY TO SUBMIT to JOSS`.

**3. The submission (operator only).** Open <https://joss.theoj.org/papers/new> and log in with
ORCID (0009-0004-8145-8319). The form's exact labels may differ; expect at least:

| Field | Value |
|---|---|
| Repository | `https://github.com/ernesto01louis/aero-research-platform` |
| Branch | leave empty (`paper/paper.md` is on `main`) |
| Software version | `v0.1.0` |
| Title, description | from `paper/paper.md` |

Before submitting, read the built PDF: the `joss-paper` artifact of the `JOSS paper draft` check on
the PR from step 1. After acceptance, JOSS asks for a tagged release and its
archive DOI. If the review changed the software, that is a new release (`v0.1.x`) with its own
Zenodo version DOI, recorded in `docs/release/zenodo.md`.

## The rule for review conversations

JOSS forbids AI tools in author–editor and author–reviewer conversation. **Every reply on the JOSS
review issue is written by the operator.** An agent session may prepare code changes that a
review asks for, through the normal PR path. It never drafts, posts or edits review comments.

## Claims

The paper's numbers are tied to the result crates by `docs/release/claims-ledger.toml` and
checked by `tests/unit/test_release_claims_ledger.py`. Changing a number in the paper without
changing the crate fails CI.
