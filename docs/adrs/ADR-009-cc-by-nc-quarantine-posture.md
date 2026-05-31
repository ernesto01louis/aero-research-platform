# ADR-009 — CC-BY-NC quarantine posture and structural defences

- **Status:** accepted
- **Date:** 2026-05-31
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 08 follow-up)
- **Stage:** 08 (follow-up)
- **Supersedes:** none. Strengthens ADR-008 §D4.

## Context and problem statement

ADR-008 §D4 codified the three-layer DrivAerNet++ quarantine: structural
separator, constructor guard, and tainted-sample union. Stage 08's first
operator follow-up surfaced the inverse problem: now that the operator has
explicitly approved DrivAerNet++ ingest (CC-BY-NC-4.0) for open-source /
research / portfolio use only, **what additional structural defences
protect the operator against accidental commercial-context contamination
at any point in the future?**

The platform is open source under GPL-3.0. The operator's stated intent is
to keep it that way forever. But:

* A future contributor may not know the licence boundary.
* A future fork may not propagate the structural defences.
* Trained model weights, once published, are easy to copy and re-host
  without their licence label.
* Predictions from a non-commercial model embedded in a downstream
  derivative carry the same obligation; this can be lost in pipeline
  hops.
* If the operator (or anyone) is later employed by a company that uses
  the platform, the boundary between "personal research" and "work
  output" can blur.

The CC-BY-NC-4.0 licence has no time limit, no use-case carve-outs, and
no automatic forgiveness for "we didn't realise." Licensors can pursue
remedies up to and including statutory damages (in jurisdictions with
copyright statutory damages, e.g. the US).

The Stage 08 cert framework (`CertificateOfValidity` with `non_commercial:
bool` and the `non-commercial-fence.yml` CI) already covers accidental
contamination at construction time. This ADR adds the layers that protect
the operator against *intentional or post-fact* contamination: write-once
flags, mandatory citation tracking, structural watermarking, and a
parallel `license-audit.yml` CI workflow.

## Decision drivers

- **Operator-stated intent.** "I want to make sure I'm on the right side
  now and at any point in the future." This rules out "soft" enforcement
  (lint warnings, documentation-only). Every defence must be structural
  and CI-enforced.
- **Open-source posture.** The platform is and will remain GPL-3.0. CC-BY-NC
  obligations stack on top of that; the platform's licence does NOT
  relax them.
- **Reproducibility (Principle 1).** Every cert + run carries the licence
  string and citation chain so auditing a published result decades later
  doesn't require external lookup.
- **No false sense of security.** The defences must be honest about what
  they DO and DON'T cover. Anyone who actively wants to misuse a
  CC-BY-NC artifact can; the defences raise the friction and prevent
  *accidental* misuse, plus document the legal intent.

## Considered options

1. **Status quo (ADR-008 §D4 three-layer defence only).** Accidental
   contamination is well-covered; intentional / post-fact contamination
   is not.
2. **Status quo + author advisory only.** Document the legal posture in
   the README; trust the operator to remember. Cheap but no structural
   teeth.
3. **Full eight-layer defence-in-depth** (this ADR). Cert fields,
   write-once flags, structural watermarking, citation chain on every
   MLflow run, license-audit CI, dataset-LICENSE files, CITATION.cff
   updates, operator-tutorial extension, ADR documentation.

## Decision outcome

Chose **option 3 — full defence-in-depth.** The marginal cost is small
(~200 LoC + a handful of docs); the marginal protection is large. The
operator's stated commitment to permanence justifies the structural
investment.

### The eight layers (cumulative; layers 1–3 are ADR-008's, 4–8 are new)

1. **Structural separator** (ADR-008) — quarantined loader subpackage at
   `aero/surrogates/_common/loaders/non_commercial/`.
2. **Constructor guard** (ADR-008) — `LicenseAcknowledgmentRequired`
   raises without `acknowledge_noncommercial=True`.
3. **Tainted-sample union** (ADR-008) — `TaintedSample` propagates the
   taint into the surrogate's `_non_commercial` flag.
4. **Write-once-True cert flag** (NEW). `CertificateOfValidity.model_copy`
   refuses any update that flips `non_commercial: True → False`. Even
   programmatic re-issuance can't launder the obligation.
5. **Surrogate-name watermark** (NEW). `CertificateOfValidity.new()`
   forces a `_nc` suffix on `surrogate_name` when `non_commercial=True`,
   AND a `model_validator` on the cert refuses manual construction
   without the suffix. The marker is visible in every artifact
   filename, MLflow run name, model-registry entry and directory listing.
6. **Citation chain on every run** (NEW). The new `attribution_required:
   tuple[str, ...]` cert field carries the citation strings every
   publication / artifact / public model description MUST carry. The
   `license_id: str` field carries the SPDX-ish licence identifier.
   `as_mlflow_tags()` writes both onto every MLflow run.
7. **Dataset-LICENSE + DATASET-LICENSES.md** (NEW). Per-dataset LICENSE
   text file under `data/datasets/<name>/LICENSE` (CC-BY-SA-4.0 for
   AhmedML / WindsorML / DrivAerML; CC-BY-NC-4.0 for DrivAerNet++) +
   global overview at `data/datasets/DATASET-LICENSES.md`. The
   `CITATION.cff` `references:` block lists each upstream paper with its
   licence and URL.
8. **license-audit.yml CI workflow** (NEW). On every PR + push to main:
   * scans the diff for any artifact path that crosses the licence
     boundary (e.g. a non-commercial-trained weight file appearing under
     a commercial-output directory)
   * scans new `.json` cert artifacts under `certificates/` for a
     `non_commercial=True` flag that's missing the `_nc` watermark
   * blocks PRs that introduce DrivAerNet++ references outside the
     quarantined subpackage or test fixtures
   * surfaces the result in the GitHub Action summary

### Consequences

- **Positive:**
  - The CC-BY-NC obligation is permanent and visible at every layer.
  - A future contributor (or a future-self after vacation) cannot
    accidentally launder a tainted cert.
  - The publication / commercial-use boundary is structural at the
    artifact-name level — `grep _nc` lists every constrained model.
  - The MLflow run is self-describing: anyone auditing a result years
    later sees the licence + citation without external lookup.
  - The dataset-LICENSE files mean every git clone carries the full
    licence text; no contributor can plead ignorance.

- **Negative:**
  - The `_nc` suffix is mildly ugly. It's intentional — visibility is
    the point.
  - The license-audit CI workflow has false-positive surface around
    legitimate cross-licence operations (e.g. an ablation comparing a
    CC-BY-NC-trained model with a CC-BY-SA-clean one). Mitigation: the
    workflow accepts a `# license-audit: justified` pragma on
    intentionally cross-licence test files (mirrors the
    `non-commercial-fence` pragma pattern).
  - Adding `attribution_required` and `license_id` to the cert is a
    breaking change vs. Stage 08's day-one shape; mitigation: both are
    default-empty so existing tests pass without modification (already
    verified).

- **Neutral / follow-up work:**
  - When Stage 09 trains the first production DoMINO surrogate on
    DrivAerML (CC-BY-SA-only, no taint), the cert will carry
    `license_id="CC-BY-SA-4.0"` + the AhmedML/DrivAerML citations. The
    `_nc` watermark does NOT apply because `non_commercial=False`.
  - When Stage 09 (or later) eventually trains on DrivAerNet++ for an
    NC-flavoured experiment, the cert will be `*_nc` and the publication
    will need the Elrefaie et al. NeurIPS citation.
  - Stage 14's agent layer will read the `attribution_required` tag and
    automatically inject the citation into any public-facing prediction
    response (so a user querying a tainted surrogate gets the obligation
    text alongside the answer).

## Pros and cons of considered options

### Option 1 — Status quo

- Good: zero new code; ADR-008 §D4 covers the common case.
- Bad: any post-fact misuse / drift goes undetected; the operator has to
  remember.

### Option 2 — Author advisory only

- Good: trivial cost; flexible.
- Bad: zero teeth. The README banner becomes invisible after the third
  scroll-past. Future-self in 3 years won't remember the warning was
  there.

### Option 3 — Full defence-in-depth

- Good: structural, permanent, CI-enforced, visible. The operator can
  forget any specific layer because the system keeps the obligation.
- Bad: cumulative complexity. Mitigation: each layer is small and tested
  in isolation; the layers compose by Pydantic field shape, not by
  cross-layer coupling.

## Links

- Stage 08 prompt: `docs/handoff-bundle/STAGE-08-jax-fluids-and-surrogate-plumbing.md`
- Related ADR: ADR-008 §D4 (3-layer quarantine baseline)
- Related handoff: `docs/handoffs/STAGE-08-jax-fluids-and-surrogate-plumbing-DONE-2026-05-30.md`
- Operator tutorial: `docs/handoffs/STAGE-08-operator-tutorial.md` (legal posture section)
- Dataset licences index: `data/datasets/DATASET-LICENSES.md`
- External:
  - CC BY-NC 4.0: https://creativecommons.org/licenses/by-nc/4.0/
  - CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/
  - DrivAerNet++ upstream: https://github.com/Mohamedelrefaie/DrivAerNet
  - Elrefaie et al. 2024 NeurIPS: https://arxiv.org/abs/2406.09624
  - Ashton et al. 2024 AhmedML: https://arxiv.org/abs/2407.20801

## What this ADR does NOT do

* It does not grant a commercial-use waiver.
* It does not waive the citation obligation.
* It does not stop someone with shell access from manually editing a
  cert JSON file. The structural defences live in the Python layer;
  bytes on disk can still be tampered with by a privileged actor. The
  CI fences would catch the result on PR review.
* It does not constitute legal advice. If a specific use case is unclear,
  the operator should consult a copyright attorney or email the dataset
  authors for a written waiver.
