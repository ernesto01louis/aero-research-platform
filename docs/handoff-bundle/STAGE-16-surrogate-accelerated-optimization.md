# STAGE 16 — Surrogate-Accelerated Optimization (Own-Data Factory)

> **STATUS: DRAFT — pending Stage-15 handoff ratification (ADR-025).** This prompt was
> authored at Stage 14 (inter-stage, ADR-025) so the anti-surrogate-exploitation
> primitives it consumes could be designed and tested against a concrete consumer. The
> "each handoff authors the next stage's prompt" rule (README-handoff) is honored as a
> **ratify-or-amend obligation**: the Stage-15 post-stage handoff MUST either ratify
> this draft or amend it with what Stage 15 actually learned — corpus size and shape,
> per-evaluation CFD cost, the pinned BO backend, which case (cylinder / plunging foil /
> flapping wing) carries the loop — and record the diff. Handoff-discipline §7's
> "confirm the next prompt exists" is satisfied by this file **only after ratification**.

> Stage 15 closed the loop with direct CFD and banked the first thesis-grade delta — and
> generated, as a side effect, a corpus of platform-validated CFD evaluations over the
> design space. Stage 16 is the **data flywheel**: train a surrogate on that own corpus
> (`data_origin="platform-validated"` by construction — Invariant 11 satisfied
> structurally, no foreign data anywhere), then run the optimization loop *through the
> surrogate* with every accepted step still verified by ground-truth CFD. The prize is
> CFD-calls-saved at equal trustworthiness; the risk is **surrogate exploitation**, and
> the ADR-025 stack exists to contain it.

## BEFORE YOU START — READ

1. `CLAUDE.md` (auto-loaded) — esp. Hard Rules 12/13/14 (IMPROVEMENT-EXCEEDS-UNCERTAINTY,
   NO-SURROGATE-ON-FOREIGN-DATA, CFD-VERIFIED-OPTIMUM-ONLY) and the ADR-025 bullet.
2. `.aero-stage` (flip to `16` as this stage's first commit).
3. `docs/handoffs/STAGE-15-*-DONE-*.md` — the optimizer, the pinned BO backend, the
   evaluation cost per case, the corpus this stage trains on, and this draft's
   ratification/amendment record.
4. **ADR-025** + the four modules it landed (`aero/surrogates/_common/{ensemble,
   calibration,trust_region,infill}.py`) — the primitives this stage wires into the loop.
5. ADR-008 (Surrogate ABC + certificate), ADR-013 (own-data mission constraint),
   ADR-023 (delta-UQ), `.claude/rules/optimization-integrity.md`,
   `docs/vv/output-validity-bar.md`.

## Why this stage

A direct-CFD BO campaign spends one full CFD solve per candidate. A trustworthy
surrogate collapses most of those to milliseconds — but an *untrustworthy* surrogate
steers the optimizer into its own blind spots (the audit's #1 failure mode; see
`docs/review/2026-07-audit-reconciliation.md`). The platform's answer is structural:
train only on own validated CFD (Invariant 11), certify with **uncertainty-calibration
evidence** (ADR-025), bound the search with a **trust region** updated by CFD-verified
outcomes (Hard Rule 14), and when the region collapses, spend the budget on
**uncertainty-routed infill** instead of more optimization.

## Phase A — the own-data surrogate factory

1. **Harvest the Stage-15 corpus** into a `Sample` stream: features = the design vector,
   normalized to the unit cube `[0, 1]^d` (the convention `trust_region.py` expects — the
   caller owns the physical↔normalized mapping; Stage 15 defines the physical variables),
   targets = the objective + any gated QoIs; `data_origin="platform-validated"`,
   `case_id` = the run's provenance pointer.
   Every sample traces to a four-tuple-logged CFD run — the data-origin fence is
   satisfied by construction, and the corpus is DVC-tracked so the certificate data
   gate can see it drift.
2. **Train an `EnsembleSurrogate`** (3–5 members; per-member seeds are automatic).
   Member architecture: start with the cheapest thing that fits the corpus (the
   MLP-baseline pattern on a ≲10-dim design vector); the corpus is O(10–100) points,
   not O(10⁵) — this is a small-data GP/MLP regime, not a field-surrogate regime.
3. **Certify with the calibration gate.** The cert carries `ensemble_size` +
   `uncertainty_calibration` (ADR-025). Promotion `smoke → validated` requires BOTH:
   held-out error below the bar the Stage-15 handoff sets (objective-scale, e.g.
   p95 error < the objective's U95 — a surrogate less accurate than the CFD noise floor
   accelerates nothing), AND empirical ±2·std coverage in **[0.85, 0.99]** (ratify or
   amend this band). Under-coverage = over-confident = exploitation fuel;
   1.0-with-huge-stds = useless. A collapsed ensemble cannot certify at all
   (`CalibrationError` — by construction).

## Phase B — surrogate-in-the-loop with trust-region + infill

The loop (each piece already exists; this stage wires them):

1. `TrustRegionPolicy.bounds(state)` constrains the acquisition search
   (`aero/surrogates/_common/trust_region.py`; start from the Stage-15 incumbent).
2. The acquisition (Stage-15's backend) proposes a candidate **inside the region**
   using `predict_with_uncertainty` (ensemble mean + epistemic std).
3. The candidate is **CFD-verified** (Hard Rule 14 — every accepted step, not just the
   final optimum; the run enters the corpus).
4. `TrustRegionPolicy.update(...)` consumes the verification: accept-expand /
   accept-hold / reject-shrink. Log every `TrustRegionUpdate` to MLflow (it is frozen
   pydantic — serialize as-is).
5. On `surrogate_distrusted` (reject-floor): STOP optimizing. `rank_infill_candidates`
   routes a batch (exploit + reserved explore fraction) to CFD; the new runs join the
   corpus; the ensemble **retrains**; the old cert **fails its data gate automatically**
   (`assert_current` — the corpus DVC hash changed; Invariant 9 closes the loop);
   re-certify (calibration gate again) and resume with a reset region.
6. The final optimum is verified on a **held-out** CFD evaluation, `n_candidates`
   recorded (`OptimizationResult` enforces both), and the improvement composed via
   `compose_improvement()` — `delta > k·U95` (k=2) exactly as in Stage 15. The
   surrogate changes the *search cost*, never the *evidence bar*.

## Deliverables

1. **The surrogate-accelerated loop** in `aero/optimize/` (extending Stage 15's package;
   core stays stdlib+numpy+pydantic; the ADR-025 modules import cleanly — core-to-core).
2. **The map-row gate result:** a surrogate-accelerated optimum that **matches the
   Stage-15 direct-CFD optimum within tolerance** (ratify the tolerance from Stage-15's
   U95), CFD-verified, under a valid current calibrated certificate.
3. **CFD-calls-saved accounting:** direct-CFD evaluations in Stage 15 vs Stage 16
   (optimization + infill + verification — count everything; a surrogate that saves
   nothing is a finding, not a failure).
4. **ADR** for the loop configuration (trust-region config, calibration band, infill
   batch size / explore fraction, retrain cadence); **post-stage handoff**; author the
   **Stage-17 prompt** (arbitrary-geometry ingestion — inherit ledger §6's autogen
   template item); tag `v0.0.16`.

## The GO/NO-GO gate

**GO** = the surrogate-accelerated optimum matches the direct-CFD optimum within the
ratified tolerance, CFD-verified, valid calibrated cert, and the loop's every accepted
step carries its `TrustRegionUpdate` audit trail.

**NO-GO paths (report honestly; Principle 4 — fall back to validated physics):**
- **Miscalibrated ensemble** (coverage outside the band after retraining + infill):
  the surrogate is not trustworthy enough to steer; fall back to direct CFD (Stage 15's
  loop still works) and report the calibration evidence as the finding.
- **Persistent trust-region floor** (distrust streak survives infill rounds): the
  design-space region of interest is beyond the corpus's reach; report the infill
  history and the honest conclusion that this problem, at this corpus size, does not
  yet benefit from surrogate acceleration.
- Never relax the calibration band or the matching tolerance to pass; never report a
  surrogate-predicted optimum (Hard Rule 14); never let an uncalibrated/expired cert
  predict (Invariant 9 — `UncertifiedSurrogate`/`CertExpired` are gates, not nuisances).

## Infra + conventions

Budget tier: sustained/burst per the README-handoff map row — the infill batches are
CFD campaigns; budget them and get operator sign-off before large batches (cost-cap
Invariant 8 applies to any cloud arm). Serial-OpenFOAM / detached-driver conventions
carry over from Stages 14–15. Clean-tree provenance for anything thesis-grade. Branch +
PR, squash, 24 h cooling-off, Conventional Commits `<type>(stage-16)`.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-16-*-DONE-YYYY-MM-DD.md` (full frontmatter + 10 sections).
Emphasize: the calibration-gated certificate lifecycle observed in practice (how many
retrain/re-certify cycles fired); the trust-region trajectory; CFD-calls-saved; the
match-vs-direct-CFD verdict. Confirm the **Stage-17 prompt exists**. Tag `v0.0.16`.
