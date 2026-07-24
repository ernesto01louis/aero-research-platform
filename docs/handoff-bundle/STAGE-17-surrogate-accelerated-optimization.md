# STAGE 17 — Surrogate-Accelerated Optimization (own-data)

> Stage 15 built and proved the direct-CFD optimization loop (turbulent optimum m≈0.0727,
> p≈0.2045: L/D 21.7→46.3, +113% at Re=5e5, robustly positive at every grid). NOTE: the
> earlier "+47% thesis-grade GO" that once headlined this prompt was RETRACTED by the
> Stage-15 audit; Stage 16 then pursued grid-converged certification on a graded
> (fixed-mapping) mesh family — the steady path closed with an honest NO-GO (resolved
> unsteadiness at the finest grid; ADR-028) and certification moved to the URANS /
> independent-U95 path (ADR-029). **Read the Stage-16 handoff for the certification verdict
> before citing any improvement number.** Stage 17 makes the loop **cheaper**: train a
> surrogate on the platform's OWN validated CFD, use it to propose candidates, but keep every
> reported optimum CFD-verified. The generality engine is the platform's own-data flywheel —
> never foreign data (Invariant 11).

> **RECONCILE FIRST (branch coordination):** an inter-stage **ADR-025 anti-surrogate-exploitation
> stack** was authored concurrently on `feat/stage-14-anti-surrogate-exploitation` (`aero/surrogates/
> _common/{ensemble,calibration,trust_region,infill}.py` + a surrogate-stage DRAFT prompt + the audit
> reconciliation `docs/review/2026-07-audit-reconciliation.md`). It is the intended substrate for
> THIS stage. Merge/reconcile that branch to `main` before/at Stage-17 start, and ratify-or-amend its
> DRAFT against this prompt (a Stage-15 handoff obligation, carried through Stage 16). Do NOT rebuild
> what ADR-025 already lands.

## BEFORE YOU START — READ

1. `CLAUDE.md` — esp. Invariant 9 (surrogate certificate gate), Invariant 11 (NO-SURROGATE-ON-
   FOREIGN-DATA), Hard Rule 14 (CFD-verified-optimum-only → Invariant 12, ADR-027).
2. `.aero-stage` (→ `17`). `docs/handoffs/STAGE-16-*-DONE-*.md` (the certification outcome) and
   `docs/handoffs/STAGE-15-*-DONE-*.md` (the optimizer + the CFD corpus).
3. ADR-026 (the direct-CFD optimizer), ADR-008 (Surrogate protocol + CertificateOfValidity),
   ADR-025 (the anti-surrogate-exploitation stack — ensemble/calibration/trust-region/infill).
4. `.claude/rules/optimization-integrity.md`, `docs/vv/output-validity-bar.md`.

## Why this stage

Direct-CFD BO (Stage 15) costs one CFD solve per candidate. A surrogate trained on the accumulating
Stage-15 CFD corpus can propose better candidates per solve and shrink the loop — the "own-data
factory" that makes the optimizer scale to more design variables / harder geometries. The risk is
surrogate exploitation (the optimizer chasing a surrogate artifact); ADR-025's ensemble uncertainty
+ trust-region + uncertainty-routed infill are the guards, and Invariant 12 keeps every reported
optimum CFD-verified.

## Deliverables

1. **A surrogate of the objective trained on the platform's OWN Stage-15 CFD data** (the airfoil
   L/D-vs-shape corpus; expand it). Invariant 11: foreign datasets cannot certify. The surrogate is
   a `Surrogate` subclass with a `CertificateOfValidity` (ADR-008) extended with the ADR-025
   `UncertaintyCalibration` evidence (held-out ±k·std coverage).
2. **Surrogate-in-the-loop optimization** wired through the ADR-025 stack: `EnsembleSurrogate`
   (epistemic std), `TrustRegionPolicy` (expand/shrink on the CFD-verified outcome), uncertainty-
   routed `infill` (high-uncertainty candidates → CFD, retrain → re-certify). The `aero/optimize`
   loop (Stage 15) is the host; the surrogate proposes, CFD disposes.
3. **Every reported optimum still CFD-verified** (Invariant 12) — a surrogate-predicted optimum is
   re-evaluated by ground-truth CFD before it is reported; `OptimizationResult.surrogate_predicted`
   records the surrogate's role, `cfd_verified` the ground-truth four-tuple, held-out + n_candidates
   for selection bias. The improvement delta still clears k·U95 (Invariant 10).
4. **Demonstrate the speed-up** honestly: surrogate-accelerated vs direct-CFD BO to the same
   CFD-verified L/D delta, at a recorded reduction in CFD evaluations (with the surrogate's
   certificate + calibration evidence). ADR + handoff + Stage-18 prompt + tag `v0.0.17` (→ v0.1.0
   milestone territory).

## GO / NO-GO

**GO** = a surrogate-accelerated run reaches a CFD-verified thesis-grade improvement delta in fewer
ground-truth CFD evaluations than direct-CFD BO, with a valid (in-window, calibrated) surrogate
certificate. **NO-GO** = if the surrogate cannot be certified (poor held-out coverage / drift) or
its accelerated optimum does not CFD-verify, fall back to direct-CFD BO and document — never report
a surrogate optimum unverified (Invariant 12), never train on foreign data to inflate accuracy
(Invariant 11).

## Infra + conventions

Serial OpenFOAM (MPI blocked), 16-core aero-dev, detached driver, concurrent independent serial CFD
evals; surrogate training is CPU-light (the corpus is small) — a GPU is not required (the DoMINO/
RunPod path stays frozen, ADR-013). Clean-tree provenance for thesis-grade runs. Conventional commits
`<type>(stage-17)`; branch + PR; the four-layer memory/handoff discipline.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-17-*-DONE-*.md` (frontmatter + 10 sections). Emphasize the own-data
surrogate + its certificate/calibration, the CFD-verified accelerated optimum, and the measured
speed-up. Confirm the Stage-18 prompt exists (arbitrary-geometry ingestion + robust meshing). Tag
`v0.0.17`.
