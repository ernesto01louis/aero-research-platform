# STAGE-15: Literature Mining & Citation Hardening

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Literature mining" and Pass 1 §"Literature-mining
plane":

- arXiv + Semantic Scholar + OpenAlex ingestion pipeline running on `aero-lit`.
- pgvector-backed retrieval over the ingested corpus.
- A weekly hypothesis-generation cron that surfaces "new papers relevant to
  the platform's active research threads" to the operator (and to the Stage 14
  agent for the `literature_informed_hypothesis` workflow).
- Zenodo deposit workflow exercised: at least one platform tag (e.g.,
  `v0.0.15`) deposited and the DOI verified back-reference in CITATION.cff.
- ORCID integration verified.
- The pre-1.0 ground laid for JOSS submission (paper.md skeleton, test
  evidence index, installation docs).

## ROLE

You are giving the platform a memory of the scientific literature it's
embedded in. Every result the platform produces should be citable forward
(new papers cite us via Zenodo DOI) and backward (we cite the methods we
build on, automatically tracked via the literature pipeline).

## GOAL

1. Provision the literature pipeline on `aero-lit`:
   - Postgres connection (pgvector extension already enabled from Stage 04)
   - Python service running periodic ingestion jobs
2. Author `aero/literature/`:
   - `sources/arxiv.py` — arXiv API client, filtered by category (`physics.flu-
     dyn`, `cs.LG`, `cs.AI` subset relevant to CAE)
   - `sources/semantic_scholar.py` — Semantic Scholar API client (free tier
     suffices for v0.1)
   - `sources/openalex.py` — OpenAlex client for broader coverage
   - `ingest.py` — periodic job: pull new papers, dedupe by DOI / arXiv ID,
     embed via sentence-transformers, store in pgvector
   - `retrieve.py` — semantic-similarity retrieval against a query
   - `hypothesis.py` — weekly job: given the project's active research
     threads (read from a config file), retrieves top-K relevant new papers,
     summarizes them, writes a "weekly digest" markdown to
     `docs/lit-digests/YYYY-WW.md`
3. Wire the `literature_informed_hypothesis` workflow from Stage 14 to use
   the retrieve API: agent queries the corpus for relevant prior work before
   proposing experiments.
4. Author `aero/literature/citations/`:
   - `auto_cite.py` — given a list of MLflow runs, traces the methods used
     (solver versions, surrogate architectures), maps them to citations via
     a curated `aero/literature/citations/index.yaml`, produces a BibTeX file
   - Used by paper-writing workflows: "I ran X cases; auto-generate the
     methods-section citations"
5. Author the Zenodo deposit workflow:
   - GitHub-Zenodo integration already enabled in Stage 04
   - For tag `v0.0.15`, push the tag and verify Zenodo auto-deposits
   - Verify the DOI in CITATION.cff resolves correctly
   - Document the procedure in `docs/release/zenodo.md` (updated from Stage 04)
6. Verify ORCID linking:
   - CITATION.cff has the operator's ORCID
   - Zenodo deposit cross-references ORCID
7. Author the JOSS submission skeleton at `paper/paper.md`:
   - Follow JOSS's paper template (one-paragraph summary, statement of need,
     state of the field, acknowledgments, references)
   - Mark as DRAFT — full submission targets v0.1.0 in Stage 16
   - Cite the same references that auto_cite would produce
8. Add `aero[literature]` extras: `arxiv`, `semanticscholar`, `pyalex`,
   `sentence-transformers`, `pgvector`.
9. Add a `lit-digest` weekly Prefect flow that runs the hypothesis job and
   posts the digest to a configurable channel (Slack, email, or just commits
   to the repo).
10. Author ADR-015 documenting:
    - The three-source ingestion choice (arXiv + Semantic Scholar + OpenAlex
      vs alternatives like Google Scholar or Elsevier)
    - The embedding model choice (specific sentence-transformers checkpoint
      pinned)
    - The hypothesis-generation procedure
    - The Zenodo + JOSS roadmap
11. Update CLAUDE.md with the literature-pipeline conventions.
12. Tag `v0.0.15`.

## WHY

A research platform cut off from the literature is an island. The weekly
hypothesis-generation cron is what keeps the platform's research threads
current — and surfaces opportunities the operator might miss. For the agent
layer (Stage 14), grounding hypothesis-generation in actual literature rather
than parametric guessing is what makes its proposals plausible.

Zenodo + ORCID + CITATION.cff is the citation infrastructure peer review
expects (Pass 3 §8.3). Setting it up at Stage 15 (not later) means v0.0.15
itself gets a DOI, building citation history for the platform.

JOSS submission targets v0.1.0; the paper.md skeleton goes in now so it
evolves with the platform rather than being written from scratch at the end.

auto_cite is what makes "this platform produced this result" auditable in
papers: the BibTeX matches what the platform actually used.

## HOW

- ingest.py: rate-limited per source (arXiv: 1 query / 3 sec; Semantic
  Scholar: per their published limits; OpenAlex: very generous, ~10 / sec).
- Dedup: prefer DOI as the canonical key; fall back to title+author hash.
- Embedding: `sentence-transformers/all-mpnet-base-v2` is the safe default;
  more recent models (e.g., `BAAI/bge-large-en-v1.5`) outperform it but pin
  carefully.
- pgvector index: HNSW for fast retrieval; cosine distance.
- Weekly digest: top-K per research thread, summarized with the agent's LLM
  (each summary <100 words; cite the paper, don't reproduce its abstract verbatim
  — copyright respect).
- For auto_cite's index.yaml: hand-curate the seed list (OpenFOAM, SU2, PyFR,
  NekRS, JAX-Fluids, PhysicsNeMo, DoMINO, Transolver, FIGConvNet, preCICE,
  UQpy, Dakota, NASA TMR, DPW workshops, etc.); extend over time.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-15-literature-mining-and-citation.md` (this file)
- `docs/handoffs/STAGE-14-*-DONE-*.md`
- ADR-004 (Zenodo concept DOI reservation), ADR-014 (agent + literature
  workflow stub)
- Pass 1 §"Literature-mining plane"

## GUARDRAILS — DO NOT

1. Do NOT scrape paywalled content. Use the open APIs only.
2. Do NOT reproduce paper abstracts verbatim in the digests — summarize. The
   digests are committed to a public repo; copyright applies.
3. Do NOT use proprietary indexing services (Web of Science, Scopus) without
   a clear license discussion in an ADR.
4. Do NOT lose the citation chain: every auto_cite output traces back to a
   specific MLflow run via the four-tuple.
5. Do NOT commit the full ingested corpus to git. It lives in Postgres +
   MinIO with periodic dump backups.
6. Do NOT skip the ORCID + Zenodo verification — these are what make the
   platform citable.

## DELIVERABLES

- [ ] Literature ingestion pipeline running on `aero-lit`
- [ ] All three sources actively ingesting; pgvector populated with ≥1000
      papers
- [ ] Semantic retrieval works: `aero lit search "neural operator CFD"`
      returns plausibly relevant results
- [ ] Weekly digest job active; first digest committed to `docs/lit-digests/`
- [ ] auto_cite produces a BibTeX file from a set of MLflow runs
- [ ] Tag `v0.0.15` pushed; Zenodo deposit verified; DOI back-referenced in
      CITATION.cff
- [ ] ORCID in CITATION.cff + Zenodo
- [ ] `paper/paper.md` JOSS skeleton committed
- [ ] `pip install -e .[literature,dev]` works
- [ ] ADR-015 committed
- [ ] CLAUDE.md updated
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.15`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- Pushing tag `v0.0.15` (Zenodo deposit is permanent; verify the CITATION.cff,
  metadata, and the to-be-deposited tag are all consistent before pushing)
- The embedding model pin
- The arXiv categories and Semantic Scholar / OpenAlex filters
- The digest channel (Slack? Email? Repo only? Operator picks)

## POST-STAGE HANDOFF

Required emphases:

- **Zenodo deposit details**: DOI for `v0.0.15`, link to the Zenodo record,
  cross-reference back in CITATION.cff verified.
- **First weekly digest**: paste the digest's top items into the handoff.
- **Corpus stats**: total papers ingested, per-source breakdown, embedding
  index size.
- **Open items for Stage 16**: docs site needs a "Literature" section; JOSS
  submission targets v0.1.0.
- **Gotchas**: API rate-limit edge cases, dedup heuristic misses, embedding-
  model version mismatches.
