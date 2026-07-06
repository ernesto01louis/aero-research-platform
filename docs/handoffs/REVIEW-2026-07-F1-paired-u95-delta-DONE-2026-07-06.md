# Review-remediation handoff — F1: computed paired-difference `u95_delta` (2026-07-06)

> **Not a stage handoff.** This is an inter-stage review-remediation note (between Stages 13
> and 14); the Stop-hook keys on `STAGE-13-*-DONE-*.md`, which exists. It follows the handoff
> template's spirit so the next session (Stage 14) reads it alongside the Stage-13 handoff.
> Work of record: `docs/review/2026-07-external-review.md` finding **F1**; design record:
> `docs/adrs/ADR-023-paired-difference-u95-delta.md`.

## What was done (deliverables)

| Deliverable | Status | Note |
|---|---|---|
| External review committed | ✅ | `docs/review/2026-07-external-review.md` (reviewed at v0.0.12) |
| Paired-difference estimator | ✅ | `aero/vv/paired_difference.py` — reuses the Stage-12 NOBM + τ_int machinery on the difference series; records correlation + `variance_reduction` |
| Schema: computed provenance for `u95_delta` | ✅ | `aero/vv/reportable.py` — `DeltaU95 = HandEnteredDeltaU95 \| ComposedDeltaU95` discriminated union; `ImprovementClaim.kind` required; thesis-grade gate refuses hand-entered / zero paired-numerical / unreliable diff estimate |
| `compose_improvement()` | ✅ | `aero/vv/reportable_compose.py`, mirroring `compose_reportable`'s caller-supplies-absolute-GCI seam |
| Known-answer tests | ✅ | `tests/vv/test_paired_difference.py` (17): independent→RSS, correlated→well below RSS (the Invariant-10 prose, measured), AR(1)-diff ESS, all fail-loud paths |
| F1 tripwire in the required gate | ✅ | `tests/stage_12/test_small_signal_gate.py` + committed fixture `tests/stage_12/fixtures/paired_cycle_means.json` (seeded-synthetic; provenance note inside) |
| `small-signal-gate` workflow | ✅ | new test path added; suite green locally (345 passed, slow/cluster skipped) |
| ADR-023 | ✅ | accepted (design); carries the proposed Constitution sentence |
| Constitution micro-PR | ✅ opened | one sentence in Invariant 10's Enforcement paragraph; **72 h window runs from the PR's open time** — merge only after window + operator approval |
| CHANGELOG entry | ⏳ deferred | per operator decision: lands under `[0.0.13]` after PR #24 merges (rebase, then append) — see "Merge order" below |

## Decisions made (and by whom)

- **Operator (2026-07-06, via AskUserQuestion):** (1) Constitution handled as a **parallel
  micro-PR** with the full 72 h amendment window — the code PR does not touch CONSTITUTION.md;
  (2) release train: **merge after PR #24**, rebase, append the F1 entry under `[0.0.13]`
  before v0.0.13 is tagged (explicit nod given, since the Stage-13 handoff frontmatter was
  already committed).
- **Design (two-lens panel + adversarial critique; ADR-023):** discriminated union over a
  `source` tag or an always-computed path; diff-series NOBM over analytic covariance
  composition; signal-scale dead-diff guard; input fraction of `|baseline|` not `|delta|`;
  `cancellation_effective` recorded but NOT gated; reliable-flag enforcement moved into the
  schema gate (the evidence is embedded there — deliberate asymmetry with plain quantities).

## Breaking change + test inventory

`ImprovementClaim(u95_delta=...)` no longer exists → `delta_uncertainty=HandEnteredDeltaU95(...)`
or `compose_improvement(...)`, plus required `kind`. All construction sites were test-only and
updated: `tests/stage_10/test_reportable.py` (7 sites + `_claim()`; `test_zero_u95_delta_rejected`
moved onto the union arm), `tests/stage_12/test_small_signal_gate.py` (2 sites). **No `aero/` or
`scripts/` code constructed a claim** (Stage 15 is unbuilt — this was the cheap moment to break it).

## Gotchas discovered

- The existing estimator already refuses a degenerate batch-means result (`crosscheck_ratio`
  is `gt=0`, so `u95==0` fails construction) — but as a raw mid-construction pydantic
  `ValidationError`. The paired functions wrap per-side `ValidationError` into a typed
  `PairedDifferenceError`; the model keeps a belt-and-braces validator for hand-assembled
  instances.
- `mean(c) - mean(b)` vs `mean(c - b)` differ by float rounding — the consistency validator
  uses `1e-9` relative + `1e-12` absolute tolerance (thrust coefficients cross zero; no
  relative-only tolerance).
- **Practical sample bar:** at 8 common converged cycles the diff's `reliable` flag is
  essentially unreachable (needs τ_int = 0.5 exactly). Plan paired campaigns for **~16–20
  common converged cycles** or the claim stays `validated`. Documented in the module docstring
  and ADR-023 — do not burn cluster time on 8-cycle paired studies.
- **Alignment precondition (prose-only for now):** `CycleSamples` has no `t0`; index-k pairing
  assumes same origin/period/`drop_initial_cycles` — true for the platform's paired drivers.
  `CycleSamples.t0` is ledgered (ADR-023) to make it machine-checkable.

## Merge order (operator playbook)

1. PR #24 (stage-13, v0.0.13) merges first (its 24 h cooling-off).
2. Rebase this branch (`stage-13-f1-paired-u95-delta`) onto the new main; append under
   `[0.0.13]` in CHANGELOG: `### Added — paired-difference u95_delta (review finding F1)`
   (estimator + audit trail; DeltaU95 union + thesis-grade gate; `compose_improvement` +
   expanded `small-signal-gate`).
3. Merge the code PR (all 8 required checks); tag v0.0.13 only after it lands.
4. Constitution micro-PR merges independently after its 72 h window + operator approval.

## Open items (NOT addressed here — the review's remaining findings)

F1 only was in scope. Still open, per the review's prioritized list: **P1b** (-dirty SHA
rejected in the thesis-grade gate — one line, do before Stage 15), **P1d** (input-UQ-skipped
distinguishable from ≈0), **M1** (batch size tied to measured τ_int; multi-seed unbiasedness
tests), **F2** (Stage-13 outcome: documented 2-D-vs-3-D NO-GO, ADR-022 — carried into Stage 14
planning), **F3** (re-sequencing: prove the optimization + delta-UQ loop on a cheap trusted
case before flapping — `compose_improvement` is now ready for exactly that), **P1a/P1c**
(provenance hardening), MPI-before-Stage-14, polish items.

## Pointers for the next session

- Read first: this note, ADR-023, `docs/review/2026-07-external-review.md` (F1 + action list),
  the Stage-13 handoff (unchanged).
- Run first to verify: `pytest tests/vv/test_paired_difference.py
  tests/stage_12/test_small_signal_gate.py -q` and `mypy aero/`.
- Stage-14/15 consumers: build claims via `paired_delta_uncertainty(...)` →
  `compose_improvement(...)`; never construct `ComposedDeltaU95` by hand in drivers.

## Confidence / risk

High confidence in the estimator (known-answer tested, reuses validated machinery) and the
schema gate (tripwire-tested). The known soft spot is inherited, not new: M1 — the error on the
error bar at small N — now applies to the difference series too; the `reliable` gate bounds it
but the review's multi-seed tightening is still worth doing before Stage 15.
