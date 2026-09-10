# ADR-044 — How to read a COMPLETED span with ZERO activation: family Z

- **Status:** proposed — becomes `accepted` on the operator's explicit acceptance, recorded
  in the commit that lands this file. **Nothing is adopted and nothing runs while it is
  proposed. D-C1's verdict of record remains INCONCLUSIVE until and unless this is
  accepted.**
- **Date:** 2026-09-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 20)
- **Stage:** 20
- **Amends:** ADR-041 V1 and V2, by ADDING one adoption path for an outcome the
  pre-registration did not anticipate. **It moves no threshold, no floor, no grid and no
  span.** The parity limit stays 4.0 over two consecutive chunks, the runaway limit 3.0,
  the activation floor 1.0 N, the grids aligned from w101, the span 8000 windows, the cap
  35 h. V3-V7 and ADR-042/043 are untouched.

## The problem, stated as the result that produced it

`hg2007_flexible_foil-20260910-084806` (D-C1, α = -0.05) is **the first flexible coupled
run in this investigation to complete its span**: `stopped_by=all-exited`, both
participants rc=0, **8000 of 8000 windows**, 5.64 h. Its four predecessors died — attempt 1
at w1703, D-A at w1487, D-B at w88, D-C2 at w1996. Its solid is quiet by five orders of
magnitude: p99 = 4.2e-5 N, and exactly **two windows of 8000** above 1.0 N, both inside the
startup transient. D-A's median was **3.23 N and climbing** by w400.

ADR-041 V2's verdict on it is **INCONCLUSIVE**, because 0 of 395 chunks reached the 1.0 N
activation floor and V2(iii) says so: *"the detector is inert here, which is not the same as
health."*

**That is the rule working, not failing.** The parity prong can only compare parities; with
nothing above the floor there is nothing to compare, and a ratio of near-zero quantities is
noise — which V2 says in as many words, and which this session demonstrated by testing the
obvious substitute observable and watching it rank the healthy run above every sick one
(§6.60). **The gap is structural: ADR-041's ladder cannot adopt a mitigation that works,
because success removes the signal its only test consumes.** V1(b)'s re-probe does not
help — it would return INCONCLUSIVE for the same reason, at the same cost.

## Z1 — the adoption path, and why each condition is load-bearing

**A rung is ELIMINATED, in addition to V2's existing path, when ALL of the following hold:**

1. **The probe COMPLETED its full pre-registered span** — every window, `all-exited`, rc=0
   on both participants. No early stop, no ceiling stop, no kill.
2. **The activation fraction over that span is EXACTLY ZERO** — not "low", not "below
   50 %". Zero. A rule keyed to zero cannot be tuned toward a desired answer.
3. **The span covers, with margin, every window at which a run of record carrying the
   signature had already activated.** The runs of record and their first window at ≥ 1.0 N:

   | run | verdict of record | first window ≥ 1.0 N | amplitude there |
   |---|---|---|---|
   | attempt 1 | SICK, died w1703 | **w127** | 0.0015 % |
   | D-A | SICK, died w1487 | **w135** | 0.0017 % |
   | rigid control | healthy, all 76 090 windows | **w72261** | 100 % |

   The required margin is **≥ 10x the latest sick first-activation window**, i.e. the span
   must reach at least w1350. The 8000-window span reaches 59x it.
4. **The detector was armed and functioning over the span** — the series is contiguous and
   the extraction produced a per-window value for every window, so zero activation is a
   measurement rather than a gap. (V2(ii) already requires contiguity; this restates that
   it is a precondition of Z1 and not waived by it.)

**Why this is admissible reasoning and not a rescue.** The calibration in condition 3 was
computed and committed at `95be432` **before D-C1's verdict existed** (§6.61), from the
rigid control and the two sick runs, none of which can have been chosen for their answer.
It establishes a fact ADR-041 did not know when it wrote the floor: **the 1.0 N level does
not separate signal from noise, it separates healthy from sick by four orders of magnitude
of amplitude.** A healthy solid does not reach it until full amplitude; both sick runs were
above it by window ~130. Under that calibration, zero activation across 8000 windows is not
an absence of evidence — it is the healthy control's own behaviour, measured.

**What Z1 deliberately does NOT do.** It does not lower the floor (a lower floor would
compare near-zero quantities, which is the failure §6.60 demonstrated). It does not add an
observable (the candidate was tested and rejected). It does not weaken the parity or
runaway limits, which remain the only way a rung FAILS. A rung that activates and diverges
is RECURRENCE-DETECTED exactly as before.

## Z2 — the second leg, stated separately because it is independent

Completion is itself evidence, and it is evidence of a different kind from the detector's.
**Four of four prior flexible runs died mid-span** — across two coupling schemes and two
adapter versions — and the fifth, differing from the fourth in one deck parameter,
completed. V2(i) already makes completion NECESSARY for elimination; Z2 records that under
this ladder's history it is also *informative*, and that a Z1 adoption rests on both legs
rather than on the detector's silence alone.

## Z3 — what adopting D-C1 would execute

Adoption is not automatic on acceptance of this ADR; it is the operator's step, in a commit
that:

1. executes **ADR-043 Y3's declared moves** — ADR-039 C2's expectation `ALPHA=0.0` →
   `-0.05`, and D10's rationale from exact-by-construction to bounded-by-dissipation, with
   **the 2 % band itself unmoved**;
2. moves `ALPHA_OF_RECORD` to -0.05, which is what lets the mitigated stack pass the
   gating fence (ADR-043's `is_campaign_configuration`);
3. triggers **ADR-041 V6**: Q1 re-runs on the adopted stack, frozen bands verbatim, at its
   own record path, before N3. ADR-040 W4 applies unchanged on rejection.

**The campaign economics improve with it**, which is worth stating because it is a reason
to be careful rather than pleased: D-C1 ran **2.56 s/window** over its last 1000 windows
against D-A's 3.25, so the campaign projection moves from ~27 to **~21 days per wave** for
20 settled cycles. That is still a B3 ceiling conversation, and it still waits on N3's
measured contended rate.

## Consequences

**Positive.** A working mitigation can be adopted on stated evidence rather than on a
verdict the pre-registration cannot reach. The rule that decides it is keyed to zero, to
full-span completion, and to a margin fixed by runs that pre-date the result.

**Negative / honest limits.** This ADR is written after seeing the outcome it would change
the reading of, and no amount of care makes that the same as having written it first. Three
things bound it: the calibration it rests on was committed before the result; it moves no
bound, so no rung that failed can be revisited; and it can only ever ADD an elimination
path, never remove a failure. The operator may reasonably decline it and leave D-C1
INCONCLUSIVE — in which case the ladder is out of pre-registered rungs with no adoption,
and ADR-041 V1's NO-GO on infrastructure is the recorded outcome despite a run that
completed cleanly. That outcome should be chosen deliberately if it is chosen.

Also unresolved and not claimed: **why the crash stopped.** D-C1 did not merely avoid the
divergence, it avoided the heap corruption that killed four runs. §6.58's reading — that
the crash followed the numerics going bad — is consistent with it and still unproven.

## Links

- §6.58 (the ALPHA hypothesis), §6.60 (the substitute observable, tested and rejected),
  §6.61 (the calibration, committed before the verdict), §6.62 (D-C1's completion).
- `runs/hg2007_flexible_foil-20260910-084806/adr041-D-C1-{verdict.json,solid-residuals.tsv}`.
- ADR-041 (V1/V2 and the ladder), ADR-042 (X1/X2), ADR-043 (Y1-Y4 and the alpha knob),
  ADR-039 C2 and D10, ADR-040 W4 and the BUDGET family.
