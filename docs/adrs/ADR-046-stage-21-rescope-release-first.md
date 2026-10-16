# ADR-046 — Stage 21 re-scoped: release-first (bundles, hardening, licence scan, JOSS/Zenodo, v0.1.0), flexible-flapping optimization deferred past v0.1.0

- **Status:** **accepted** — drafted 2026-09-21 and **accepted by the operator on 2026-10-10**, and
  that acceptance is recorded by the commit that lands this change (the ADR-041 `d5bf381` pattern).
  The operator also settled the open question below by choosing **option (i)**: v0.1.0 ships with
  the flagship limitation documented. `README-handoff.md` row 21 and `00-MISSION-AND-SCOPE.md` are
  updated in that same commit, per S6.
- **Date:** 2026-09-21
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 20 close-out)
- **Stage:** 21 (scoped from Stage 20's close-out)
- **Amends on acceptance:** `README-handoff.md` row 21; `00-MISSION-AND-SCOPE.md`'s v0.1.0 framing.
  It moves **no** pre-registered band, gate or budget clause. ADR-039/040's FORBIDDEN lists and all
  four B-sentinels are untouched and stay permanently unfilled (ADR-041 V7 FIRED).

> **Errata (2026-10-12, Stage 21; ADR-049 H-29).** Two typos are noted here; the decision text
> is unchanged.
> 1. The Status line cites "the ADR-041 `d5bf381` pattern". `d5bf381` is **ADR-040's** acceptance
>    commit; ADR-041's is `2bbfdd4`. The pattern (acceptance recorded by the commit that lands
>    the change) is the same.
> 2. The `## Decision (proposed)` heading below predates acceptance. The decision is accepted, as
>    the Status line says.

> **Amendment (ADR-051, accepted 2026-10-16).** The scheduling below ("the rigid-flapping
> optimization is therefore scheduled as the **first post-v0.1.0 stage**") is superseded. The
> post-v0.1.0 stages 22–26 build the foundation first, and the rigid-flapping optimization follows
> them. The decision, S1–S6 and option (i) are unchanged.

## Context and problem statement

Stage 21 is currently defined (`README-handoff.md:46`) as **"Flexible-Flapping Optimization +
Portable Bundles + Hardening + v0.1.0"** — optimization over flexible-flapping (surrogate + FSI),
the RESULTS-MUST-TRAVEL bundle with RO-Crate/W3C-PROV, licence-scan CI, JOSS/Zenodo, release.

**Stage 20 ended in a recorded NO-GO on infrastructure** (ADR-041 **V7 FIRED**, 2026-09-20; handoff
§6.88–§6.89; `data/vv/stage20_nogo_infrastructure.json`). The gated flexible-arm campaign cannot be
run on this stack: the flexible arm survives ≈37 900 windows per death against 1 166 675 per wave,
and both levers that could change that are exhausted — the AddressSanitizer hunt found no patchable
line, and ADR-045's checkpoint/restart could not produce a coupled restart in two attempts.

**Therefore the flexible-flapping FSI capability has no validated verdict**, and Stage 21 as written
would optimize over an unvalidated capability. That is precisely what **Hard Rule 14**
(CFD-VERIFIED-OPTIMUM-ONLY), **Hard Rule 15** (VALIDATE-AGAINST-EXPERIMENT) and **Invariant 9**
forbid. Stage 21 cannot proceed as specified, and v0.1.0 is behind it.

## What the record actually supports — stated precisely, because the re-scope depends on it

The claim "the optimizer is demonstrated" must be sized to the evidence, not to the roadmap.

| Evidence | Status of record | What it does and does not establish |
|---|---|---|
| **Stage 15** — CFD-in-the-loop airfoil shape optimizer | **Built and works**; an earlier "+47 % thesis-grade" claim was **RETRACTED** after an adversarial audit; thesis-grade certification **not** achieved | The optimizer exists and finds real, large improvements on an **airfoil** case |
| **Stage 16** — grid-converged certification | **HONEST NO-GO by one gate**: observed order **0.465** against the pre-registered **0.5** asymptotic-range floor (floor committed before the campaign, not adjusted); `validation_tag=validated` | The certification machinery is hardened and the delta is monotone; the certification gap is **one order estimate wide** |
| **Stage 17** — surrogate-accelerated optimization | Deliverables 1–3 **GO**: a `gp_bootstrap` ensemble **PROMOTED to `validated`** (held-out ±2·std coverage 0.90) drove a propose/dispose loop to a **surrogate-proposed, CFD-verified** L/D 46.372 > corpus best 46.337. The pre-registered **speed-up is a documented DEGENERATE NO-GO** | A CFD-verified surrogate-accelerated improvement exists, on the **airfoil** case; single-run acceleration is **not** demonstrated |
| **Stage 14** — rigid flapping-wing validation | Rotation-timing **trend VALIDATED** (advanced 0.577 > symmetrical 0.467 > delayed 0.137, the Dickinson signature; LEV capture textbook). Stroke-averaged **mean lift is a documented NO-GO** — 46 % off the WBD experiment, band **not** relaxed, root-caused to overset wake-capture dissipation | A **forward capability** in the flagship domain, validated **for trend only** |
| **Stage 20** — rigid FSI arm | Completed 76 090/76 090 windows as the **partner arm** of a paired campaign that never produced a gated verdict | **Carries no verdict of its own and cannot stand in for a validated rigid-flapping-FSI capability** |

**Two corrections this ADR must not paper over.**

1. **The optimizer has never been run on a flapping case.** Stages 15–17 optimize an **airfoil**;
   Stage 15 was an explicit operator pivot away from flapping. So "the optimizer demonstrated on
   Stage 14's rigid flapping" is not available as written — Stage 14 is a *forward-physics*
   validation, not an optimization demonstration. What v0.1.0 can honestly ship is **an optimizer
   demonstrated on the airfoil case (15/16/17), plus a trend-validated rigid flapping forward
   capability (14)**.
2. **Neither Stage 16 nor Stage 17 is an unqualified "certified optimization."** Stage 16 is a NO-GO
   by one gate at `validated`; Stage 17's optimization deliverables are GO with a `validated`
   surrogate certificate, while its speed-up claim is a NO-GO. "Certified" in this ADR means
   **`validated`-tier, gate-honest**, never thesis-grade.

This matters because the mission brief names **flapping as the single flagship demonstration
domain**. Under this re-scope v0.1.0 ships with the flagship represented by a trend-validated
forward capability and no flapping *optimization*. That limitation is real and is carried openly in
the release notes rather than smoothed over.

## Decision drivers

- Hard Rules 14/15 and Invariant 9 forbid optimizing over, or claiming, an unvalidated capability.
- The release-side deliverables (bundles, hardening, licence scan, JOSS/Zenodo) are **independent**
  of the flexible-flapping outcome and are already the majority of Stage 21's content.
- A v0.1.0 gated behind an infrastructure NO-GO would never ship.
- The project's own discipline: a NO-GO is a result to record and route around, not to retry.
- Honesty over completeness — shipping with a documented limitation beats shipping a claim the
  evidence does not carry.

## Considered options

1. **Proceed with Stage 21 as written.** Rejected: optimizing over flexible-flapping FSI is
   impossible (no campaign) and would violate Hard Rules 14/15 even if attempted.
2. **Block v0.1.0 until flexible-flapping is validated.** Rejected: the blocking condition is an
   unresolved infrastructure defect with no owner and no estimate; it makes the release hostage to
   a bug that ADR-041 V7 already declared a NO-GO.
3. **Substitute Stage 20's rigid FSI arm as the flagship validation.** Rejected on the record: that
   arm carries no verdict of its own (see the table above).
4. **Re-scope Stage 21 to release-first and defer flexible-flapping optimization past v0.1.0, with
   an explicit re-entry condition.** **Proposed.**

## Decision (proposed)

**S1 — Stage 21 becomes release-first.** Its deliverables are: the RESULTS-MUST-TRAVEL
self-describing bundle (+ RO-Crate / W3C-PROV) and its round-trip CI; hardening; licence-scan CI;
JOSS paper + Zenodo deposition; and the **v0.1.0** release. Hard Rule 16's constitutional promotion
rides on the bundle landing here, which is where it always was.

**S2 — The optimizer's demonstration for v0.1.0 is the airfoil case.** Stage 15's optimizer, Stage
16's certification machinery and Stage 17's `validated` surrogate-accelerated, CFD-verified
improvement. Each ships with its gate-honest status verbatim, including Stage 16's one-gate NO-GO
and Stage 17's degenerate speed-up NO-GO.

**S3 — The flagship domain ships as a forward capability only.** Stage 14's rigid flapping, carried
with its validated trend **and** its documented mean-lift NO-GO. **No flapping optimization claim is
made in v0.1.0.** The release notes and the JOSS paper state this limitation in the body, not a
footnote.

**S4 — Flexible-flapping optimization moves past v0.1.0**, to a stage numbered at re-entry. It is
deferred, not cancelled, and not silently dropped: `README-handoff.md` gains a deferred row on
acceptance.

**S5 — The re-entry condition, explicit and testable.** Flexible-flapping optimization may be
re-opened only when **(R-a) or (R-b)**, **and** R-c and R-d, all hold:

- **R-a — the crash rate stops mattering.** A demonstrated flexible-arm mean-time-to-crash giving
  **fewer than one expected death per pre-registered wave** (i.e. ≳ 1.17e6 windows per death against
  the 1 166 675-window wave), measured on ≥ 2 independent runs, **or** the CalculiX heap corruption
  root-caused and fixed with the fix identified by file and line.
- **R-b — or a restart that is demonstrably transparent.** A coupled restart passing an
  R3-equivalent transparency test — ADR-045 R3 clauses (a)–(e) **as amended by A17**, scored by the
  existing scorer `aero/vv/fsi/hg2007_r3.py`, on a run that actually advances windows past the
  restart. (Both 2026-09-16/17 attempts advanced **zero**; see ADR-045 A19.)
- **R-c — declared pins.** The evidence is produced on a stack whose pins are declared in the new
  ADR. ADR-039/040's bands, floors, grids, spans and ceilings are **frozen**; moving any of them
  needs its own ADR and may not be bundled into the re-entry.
- **R-d — the operator's explicit word**, plus a re-derived B0 that carries the restart-rework line
  item (handoff §6.87) and settles the unresolved box-time vs sum-of-submissions reading.

**S6 — What acceptance changes, and nothing before it.** On acceptance: `README-handoff.md` row 21
is rewritten and a deferred flexible-flapping row added; `00-MISSION-AND-SCOPE.md`'s v0.1.0 framing
is updated to match S2/S3. **Until then both files stand as they are.**

## Consequences

**Positive.** v0.1.0 becomes shippable on evidence that already exists and is gate-honest. The
release-side work is unblocked immediately. The flagship deferral is written down with a testable
re-entry condition instead of decaying into an unstated omission. No band moves.

**Negative / honest limits.** The flagship demonstration domain ships **without an optimization
result** — the mission brief's headline ("flapping is the single flagship demonstration domain") is
weaker at v0.1.0 than the roadmap promised, and a reviewer will notice. The optimizer's evidence is
a 2-D airfoil problem, which is also where Stage 17's speed-up claim degenerated. Hard Rule 16's
promotion rests on a bundle whose only flagship content is forward-physics. Deferral has a way of
becoming abandonment: R-a/R-b are deliberately strict, and if neither is ever met the honest future
record is that flexible-flapping optimization was **not achieved**, not that it is pending forever.

## Open question — SETTLED 2026-10-10: option (i)

**Does v0.1.0 ship with the flagship represented by forward physics only? — YES.** The operator
chose **option (i)**: accept S3 and carry the limitation openly in the release notes and the JOSS
paper. The reasoning recorded with the choice: v0.1.0's purpose is portability, citability and
hardening, none of which depends on flapping; adding a rigid-flapping optimization would cost a
fresh campaign on an overset moving mesh, and holding the release for new compute is the pattern
that consumed Stage 20. The rigid-flapping optimization is therefore scheduled as the **first
post-v0.1.0 stage**, beside the deferred flexible-flapping work, where its claim can be scoped
properly against Stage 14's mean-lift bound.

The three options as they stood, for the record: **(i)** accept S3 and document the limitation in
the release notes and JOSS paper; **(ii)** add a **rigid**-flapping *optimization* demonstration to
Stage 21 — the optimizer over Stage 14's validated-trend capability — which would cost a campaign
and inherits Stage 14's mean-lift NO-GO as a stated bound on any claim; **(iii)** re-word the
flagship claim for v0.1.0 so the brief and the release agree. **(i) was chosen.**

## Links

- ADR-041 **"V7 — FIRED"**; ADR-045 **"R6 — EXECUTED"** + A19; handoff §6.88–§6.89;
  `data/vv/stage20_nogo_infrastructure.json`; CHANGELOG `[0.0.20]`.
- ADR-013 (optimizer refocus), ADR-016 (two solid solvers; its application-fidelity delegation to
  Stage 20 went unmade), ADR-027 (Hard Rule 14), ADR-028/029/030 (Stage 16), ADR-031/032 (Stage 17).
- `docs/handoff-bundle/README-handoff.md:46`; `docs/handoff-bundle/00-MISSION-AND-SCOPE.md`;
  `docs/vv/output-validity-bar.md`.
