# ADR-015 — Constitution Invariants 10 (improvement-exceeds-uncertainty) + 11 (no foreign data)

- **Status:** accepted
- **Date:** 2026-06-10 (proposed); 2026-07-05 (accepted)
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 09 proposed,
  Stage 12 ratified)
- **Stage:** 09 (proposed) / 12 (accepted)
- **Supersedes:** none

> **Ratified (Stage 12, 2026-07-05).** The amendment process is complete: the ≥72 h review
> window elapsed (proposed 2026-06-10, ~a month before ratification), the operator approved, and
> CI is green. Invariants 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) + 11 (NO-SURROGATE-ON-FOREIGN-DATA)
> are constitutional, and their machine enforcement **landed in Stage 12**: the full
> `U95 = RSS(numerical, statistical, input)` composition + the required `small-signal-gate`
> (Invariant 10) and `data-origin-fence` (Invariant 11) CI jobs (ADR-020). CLAUDE.md already
> carried these as Hard Rules 12–13; this ADR promoted the two machine-enforceable ones to
> constitutional invariants.

## Context and problem statement

ADR-013 refocused the platform as an aerodynamic shape optimizer whose product is
*trustworthy CFD-verified improvements*. Two of the six new mission rules are
machine-enforceable and load-bearing enough to belong in the Constitution rather than
only CLAUDE.md:

1. The optimizer must never report an improvement smaller than its own uncertainty —
   and "uncertainty" for an unsteady/optimization quantity is **not** GCI alone.
2. A surrogate that accelerates the optimizer must be certified on the platform's **own
   validated CFD**, never on foreign (e.g. automotive) data — the destination ADR-013
   cut.

The other four mission rules (CFD-VERIFIED-OPTIMUM-ONLY, VALIDATE-AGAINST-EXPERIMENT,
RESULTS-MUST-TRAVEL, SCOPE-GATE) stay at CLAUDE.md hard-rule level for now; two of them
(CFD-verified-optimum, results-must-travel) promote later when their enforcing schemas
land (Stages 15, 20).

## Decision drivers

- **Machine-enforceability.** Both proposed invariants get a concrete pydantic schema +
  CI gate — the bar the Constitution sets for an invariant (cf. Invariants 1, 3, 8, 9).
- **The integrity of the mission.** Improvement-exceeds-uncertainty *is* the optimizer's
  correctness guarantee; no-foreign-data keeps the accelerating surrogate's certificate
  meaningful.
- **Honest UQ.** Verified: GCI/ASME V&V 20 covers discretization only; total U95 must
  RSS in statistical (batch-means / N_eff) and input contributions (Roy & Oberkampf
  2011; Oliver et al. 2014). Encoding the composition in the invariant prevents a
  GCI-only shortcut.

## Considered options

1. **Promote both to constitutional invariants (10 + 11), enforcement landing at named
   stages** — chosen.
2. **Keep both as CLAUDE.md hard rules only** — lighter, but the optimizer's central
   correctness guarantee would lack CI teeth.
3. **Promote only Invariant 10** — leaves the foreign-data prohibition unenforced while
   the own-data surrogate factory (Stage 16) is being built.

## Decision outcome

Chose **Option 1.** Add Invariants 10 + 11 to `CONSTITUTION.md` (text on this branch),
with enforcement that lands at the named stages (the Invariant-5 precedent — "CI tooling
lands at Stage NN"):

- **Invariant 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY):** `aero/vv/reportable.py`
  `ReportableResult` skeleton Stage 10; full `U95 = RSS(numerical, statistical, input)`
  + the `small-signal-gate` required CI job Stage 12; `abs(delta) > k·U95` (k default 2)
  validator on `ImprovementClaim`.
- **Invariant 11 (NO-SURROGATE-ON-FOREIGN-DATA):** `data_origin` field on the `Sample`
  union + cert; `promote_to_validated` refuses `foreign`; `non-commercial-fence` CI
  extended. Lands Stage 12 (reuses the Stage-08 taint machinery).

## Consequences

- **Positive:** the optimizer's two correctness guarantees gain CI teeth; the UQ
  composition is pinned (no GCI-only shortcut); the foreign-data prohibition is
  structural before the own-data factory lands.
- **Negative:** two more required CI gates to maintain; the closed-loop U95 gate is
  nascent in the literature and is real custom development (scoped Stages 12 + 15).
- **Neutral / followup:** CFD-VERIFIED-OPTIMUM-ONLY and RESULTS-MUST-TRAVEL promote to
  constitutional later (Stages 15, 20); this ADR moves to `accepted` when the 72 h
  review elapses, the operator approves, and CI is green.

## Pros and cons of considered options

### Option 1 — promote both (chosen)
- Good: CI-enforced; pins the UQ composition; matches the Constitution's enforceability bar.
- Bad: enforcement is deferred to named stages (proposed-now, teeth-later), like Invariant 5.

### Option 2 — CLAUDE.md only
- Good: no 72 h process; instant adoption.
- Bad: the mission's central guarantee has no CI gate — too weak for a thesis-grade bar.

### Option 3 — Invariant 10 only
- Good: smaller amendment.
- Bad: leaves foreign-data certs possible exactly while the own-data factory is built.

## Links

- Related ADR: ADR-013 (mission refocus), ADR-008/009 (surrogate cert + taint machinery
  reused by Invariant 11), ADR-005 (Invariant-5 "enforcement lands at a stage" precedent)
- Governing scope: `docs/handoff-bundle/00-MISSION-AND-SCOPE.md` §3.4, §8
- Enforcing schema (future): `aero/vv/reportable.py` (Stage 10/12)
- External: Roy & Oberkampf (2011), CMAME 200; Oliver et al. (2014), Phys. Fluids 26,
  035101; ASME V&V 20-2009
