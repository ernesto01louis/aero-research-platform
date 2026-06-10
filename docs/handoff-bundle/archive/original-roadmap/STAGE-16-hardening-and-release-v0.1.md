# STAGE-16: Hardening & Release v0.1.0

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Versioning & release cadence" and Pass 3 §8.3
(citation, FAIR, JOSS):

- mkdocs documentation site live (via the project's docs LXC or GitHub Pages).
- README's `## Status` block fully wired and verified (auto-regeneration
  hooks from Stage 01 working correctly across all 15 prior stages).
- JOSS submission prepared: `paper/paper.md` complete, software-archive Zenodo
  deposit verified, automated tests documented, installation docs
  comprehensive.
- First conference paper template at `paper/conference-template/` for AIAA
  SciTech or APS DFD — operator picks the venue; the template skeleton is
  generic.
- v0.1.0 release tag — first stable platform release.
- Final post-stage handoff that doubles as the "what's-next" research-not-
  platform roadmap.

## ROLE

You are polishing a working platform into a releasable one. The build is done;
this stage is hardening, documentation, citation infrastructure, and the
release ceremony. After this stage, the platform is stable and the operator
shifts from platform-building to research.

## GOAL

1. Author the mkdocs site at `docs/`:
   - `mkdocs.yml` with the Material theme
   - `mkdocstrings` plugin pointed at `aero/` for auto-generated API reference
   - Nav structure: Quick Start, Architecture, Solvers, Surrogates, V&V, UQ,
     Orchestration, Agentic, Literature, Provenance, ADRs, Handoffs (the
     post-stage handoffs, public), Citation, License
   - Deploy via GitHub Actions to GitHub Pages (or self-host on the docs LXC
     behind VPN, operator picks)
2. Verify the README `## Status` auto-regeneration:
   - Run the regen on the latest handoff (Stage 16's, written at the END of
     this stage)
   - Verify the marker-delimited block updates correctly
   - Verify the docs-status-sync CI check from Stage 01 still works
3. Complete `paper/paper.md` for JOSS:
   - Statement of Need (the field has commercial CAE and a fragmented OSS
     ecosystem; this platform unifies + adds provenance, surrogates, agentics)
   - State of the field (cite Pass 2 SOTA findings)
   - Summary of features (one paragraph per layer)
   - Reproducibility and citation
   - Acknowledgments (NVIDIA PhysicsNeMo, OpenFOAM, SU2, preCICE, etc.)
   - References (BibTeX file in `paper/refs.bib`)
4. Run the JOSS pre-submission checklist:
   - Open-source license (verified: GPL-3 or AGPL-3 from Stage 01)
   - Software has a clear research application (verified)
   - Substantial scholarly effort (16 stages of opinionated build)
   - Documentation: installation, examples, API reference (just built)
   - Automated tests with results visible (CI green)
   - Community guidelines: CONTRIBUTING.md (exists), issue templates (add now)
5. Author the conference-paper template at `paper/conference-template/`:
   - LaTeX skeleton for AIAA (uses `aiaa.cls`) or generic ACM/APS style
   - Auto-cite integration: a one-liner that pulls citations from a list of
     MLflow runs the paper draws on
   - Reproducibility statement template (the four-tuple per result)
6. Final hardening pass:
   - All ADRs cross-referenced from the appropriate handoffs
   - All CI workflows green
   - All optional extras documented in pyproject.toml and the docs
   - All Apptainer SIF SHAs in SHA256SUMS verified and signed
   - SECURITY.md updated for the full v0.1.0 surface
   - CHANGELOG.md complete with all 16 stage tags
7. Add GitHub issue templates at `.github/ISSUE_TEMPLATE/`:
   - Bug report (require the four-tuple of the failing run)
   - V&V regression (require the failed case + tolerance band)
   - Feature request (require justification + which layer it touches)
   - Documentation gap
8. Add a `.github/PULL_REQUEST_TEMPLATE.md` that prompts the four-tuple, test
   evidence, ADR link, handoff link if mid-stage.
9. Verify all stage tags `v0.0.1` through `v0.0.16` (this stage's tag) have
   corresponding post-stage handoffs.
10. Author the final handoff `docs/handoffs/STAGE-16-hardening-and-release-
    DONE-YYYY-MM-DD.md` with a "What's Next" section that's a research
    roadmap, not a platform roadmap:
    - First conference paper: candidate topics drawn from the platform's
      capabilities
    - Bio-inspired drag-reduction studies (riblets, vibrating skins)
    - Flapping-wing aerodynamics
    - Hypersonic + reacting-flow with SU2-NEMO + Mutation++
    - New surrogate architectures (the platform supports adding them)
    - New V&V contributions (could publish the V&V harness itself)
11. Tag `v0.1.0`.
12. Push the v0.1.0 tag. Verify Zenodo auto-deposits the v0.1.0 release; the
    CITATION.cff DOI now resolves to this version.
13. Submit to JOSS (or mark ready-to-submit and let the operator pull the
    trigger).

## WHY

A research platform without docs is unusable. A research platform without a
DOI is uncitable. A research platform without a release tag is a moving
target nobody can build on. Stage 16 makes the platform usable, citable, and
stable.

JOSS submission is the formal recognition that this is research software
worth peer-reviewing. It also pulls a permanent citation into the academic
record.

The conference-paper template is the on-ramp to the operator's actual
research output. After v0.1.0, every paper drawn from the platform starts
from this template + auto-cite + the four-tuple reproducibility statement.

The handoff's "What's Next" section is deliberately not platform work — the
platform is done. Stage 16 closes the platform-building project and points
the operator toward research.

## HOW

- mkdocs Material is well-documented; mkdocstrings auto-generates API docs
  from docstrings — verify the project's docstrings are sufficient first
- For JOSS, follow the editor checklist precisely; the review is rigorous
  but constructive
- For the conference template, AIAA's `aiaa.cls` is the most common starting
  point for aerospace; APS DFD uses RevTeX. Operator picks.
- For the v0.1.0 Zenodo deposit: verify all the metadata one more time before
  pushing; this is the citation people will use forever.
- Don't rush this stage. The temptation is to ship and move on; instead,
  treat it as the operator's final QA pass on the whole project.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-16-hardening-and-release-v0.1.md` (this file)
- All previous handoffs (Stage 01 through Stage 15) — this is the one stage
  where the prior handoffs are read in full, because Stage 16's job is to make
  sure the whole story holds together
- All ADRs (002 through 015)
- `paper/paper.md` skeleton from Stage 15

## GUARDRAILS — DO NOT

1. Do NOT tag v0.1.0 with any failing CI check, missing handoff, or expired
   surrogate certificate. v0.1.0 must be entirely green.
2. Do NOT submit to JOSS without the operator's explicit go-ahead. Mark
   ready-to-submit; let the operator click submit.
3. Do NOT skip the v0.1.0 Zenodo metadata QA pass.
4. Do NOT hand-edit the README's `## Status` block. Use the regen.
5. Do NOT introduce new features in this stage. Hardening only. If a feature
   gap appears, file an issue for v0.1.1.

## DELIVERABLES

- [ ] mkdocs site builds and renders all sections
- [ ] Site deployed (Pages or self-hosted)
- [ ] README `## Status` regenerated from the Stage 16 handoff
- [ ] `paper/paper.md` complete and JOSS pre-submission checklist green
- [ ] Conference-paper template at `paper/conference-template/`
- [ ] All 15 prior handoffs verified to exist with valid frontmatter
- [ ] All ADRs cross-linked
- [ ] All CI workflows green
- [ ] Issue + PR templates committed
- [ ] CHANGELOG.md complete
- [ ] Tag `v0.1.0` pushed
- [ ] Zenodo v0.1.0 deposit verified; DOI resolves
- [ ] Final handoff written with research roadmap (not platform roadmap)
- [ ] JOSS submission marked ready (operator-gated)

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- Pushing `v0.1.0` (permanent, propagates to Zenodo)
- Submitting to JOSS
- The conference paper venue (AIAA SciTech, APS DFD, others) for the template
- The docs hosting choice (GitHub Pages public, VPN-only self-hosted)

## POST-STAGE HANDOFF

This is the **final** post-stage handoff. Required emphases:

- **The full deliverable list across all 16 stages**: a single
  table for posterity.
- **Total resource investment**: cumulative $-spend on cloud compute,
  estimated total operator + Claude Code hours.
- **The "What's Next" research roadmap** (NOT platform roadmap):
  - First conference paper candidate topics
  - Bio-inspired drag reduction (riblets, vibrating skins)
  - Flapping-wing aerodynamics
  - Hypersonic + reacting flow
  - New surrogate architectures
  - V&V harness as a publishable artifact on its own
- **The v0.1.0 DOI** for the operator's CV / ORCID profile.
- **A "thanks" section**: the platform stands on OpenFOAM, SU2, PyFR, NekRS,
  JAX-Fluids, PhysicsNeMo, preCICE, UQpy, Dakota, NASA TMR, AIAA DPW/HLPW,
  ERCOFTAC. Acknowledge them.
- **Gotchas**: any final caveats the operator should remember when they pick
  the platform up for research in week 2 post-release.

After this handoff is committed and v0.1.0 is tagged: **the platform-building
project is complete**. The operator (and any future contributors) shift to
using the platform for science.
