# Stage 20 — the B3 per-wave ceiling: the decision, prepared before the number lands

**Status: INPUT for an operator decision, not a decision.** Written 2026-09-14 while N3 is
still running, so that when its measured rate arrives the choice is a substitution rather
than a fresh analysis. **The one input that decides it does not exist yet.**

## The rule, which is already pre-registered and is not up for renegotiation

ADR-040 B3, verbatim:

> the operator is brought N3's coupled, contended, post-ramp rate and approves the
> **SMALLEST ceiling that fits 20 settled cycles at that rate**, and the approval is taken
> **BEFORE B2 is filled** — so the ceiling is chosen against a measured rate and not
> against a projected campaign length that someone wants to fit.

So this memo does not ask "what ceiling would be convenient". It asks you to read one
measured number off N3 and approve the ceiling that number implies. The ordering matters:
B2's sentinels are filled in the commit AFTER the ceiling is approved, which is what stops
the campaign length from being chosen and the ceiling reverse-engineered to fit it.

## What is already fixed, and is not a function of the rate

The campaign's SHAPE comes from ADR-039 S2's analysis rule, not from how fast the box is.
Derived just now through `size_gated_campaign_040` itself rather than by hand:

| quantity | value | set by |
|---|---|---|
| settled cycles | **20** | ADR-039 S2 (B4's floor is 10, never lower) |
| unconditional discard | **3.0435 s** = 3/f | ADR-039 S2 |
| period | 1.0145 s | ADR-039 S1, prescribed |
| dt | 2e-5 s | ADR-040 N2, the Courant-passing probe's dt |
| **max_time** | **23.3335 s** | discard + 20 cycles, bumped to a `.13e` round trip |
| **n_windows** | **1 166 675** | max_time / dt |

Both arms run concurrently in a wave, so a wave's duration is the **binding (flexible)**
arm's projection, and **two waves are planned**.

## The table you will read the answer off

Smallest ceiling that fits 20 settled cycles, as a function of the binding arm's measured
post-ramp contended rate:

| rate (s/window) | per wave | two waves | where this number would come from |
|---|---|---|---|
| 1.30 | 17.6 d | 35.1 d | the rigid arm's *uncontended* post-ramp rate (§6.48) |
| 2.00 | 27.0 d | 54.0 d | ADR-040's pre-N3 projection |
| 2.56 | 34.6 d | 69.1 d | D-C1 *uncontended* on the adopted stack |
| 3.50 | 47.3 d | 94.5 d | Q1 contended but **ramp-phase** on the adopted stack |
| 4.00 | 54.0 d | 108.0 d | |
| 5.00 | 67.5 d | 135.0 d | |
| 6.00 | 81.0 d | 162.0 d | |

For scale: ADR-039's original 14-day ceiling needs **1.037 s/window**, and even B4's
10-cycle floor needs 1.834 s/window to fit 14 days. **The 14-day ceiling is out of reach at
every rate this campaign has ever measured** — which is why B3 exists as a decision at all.

## The trap in that table, stated plainly

**None of the rates above is N3's answer, and the closest-looking one is the most
misleading.** Q1's 3.50 s/window is *contended*, on the *adopted stack*, and measured
*hours ago* — but it is a **ramp-phase** rate, and ADR-040 N3 is explicit that ramp windows
sit at near-zero plunge and understate the wave. The post-ramp rate is expected to be
**higher**. Meanwhile D-C1's 2.56 and the rigid arm's 1.30 are post-ramp-ish but
**uncontended**, and contention roughly doubled the cost in every paired measurement so far.

So the honest bracket before the measurement is **wide**, and I would rather hand you a wide
bracket than a precise-looking wrong one. N3 exists precisely because this number cannot be
inferred from the numbers we already have.

## What to do when N3 lands

1. `--collect-probe` both arms → the fine-rung I7 probe (alone, after N3) → then
   `--size-040 <flex> <rigid> <fine> --ceiling-s <approved>`.
2. Read the **binding arm's post-ramp seconds-per-window** out of the N3 record.
3. Multiply by 1 166 675 → seconds per wave → round **up** to the smallest ceiling that
   holds it. That is the number to approve.
4. Approve it **before** B2 is filled. The B2 fill commit is the one that also adds
   `data/vv/stage20_n3_confirmation.json` and the four `GATED_040_*`, with
   `test_adr040_budget_is_derived_from_n3.py` re-deriving them — that test is already
   written and was committed *before* any of these numbers existed.

## If the number is bad, the pre-registered order is fixed

ADR-040 B4, in order, and no step may be skipped or reordered:

1. **Cut settled cycles — never below 10.** At 10 cycles the campaign is roughly
   `(3.0435 + 10 × 1.0145) / 2e-5` ≈ **659 750 windows**, about 57 % of the 20-cycle
   campaign, so every duration above scales by ~0.57.
2. **Then a budget NO-GO**, recorded as a result rather than an embarrassment.

And if S3's periodic-steady-state test cannot be satisfied inside whatever ceiling is
approved, the verdict is **NO-GO on periodic steady state — never a re-run with a
hand-picked window**.

## The question this memo cannot answer for you

Even the optimistic end of the bracket is **weeks per wave, twice**, on a single box that
the rest of this platform also needs. That is a scope-and-hardware question rather than a
numerical one, and it sits outside ADR-040's rule: the rule tells you the smallest *honest*
ceiling, not whether to spend it. Worth deciding deliberately once the real rate is in hand,
alongside the option of cutting to 10 cycles at the outset rather than as a fallback.
