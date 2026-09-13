# ADR-042 — Re-order ADR-041's D-C rungs, and protect the rungs that have not run: family X

- **Status:** accepted — **X1 (as amended by X1a below), X2**. The operator accepted them on 2026-09-07 and
  this commit is that acceptance (the ADR-040 `d5bf381` / ADR-041 `2bbfdd4` pattern).
  **X3 is NOT accepted**: it stands as a recorded diagnosis with no action taken, and
  making the core dump work needs its own operator decision if and when a core is wanted.
  No probe ran before this acceptance.
- **Date:** 2026-09-07
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 20)
- **Stage:** 20
- **Amends:** ADR-041, in two places and nowhere else — the ORDER of D-C's two forms (X1)
  and V1's treatment of a probe that dies before the signature could be observed (X2),
  plus one optional observability clause (X3). **ADR-041's detector bounds (V2), probe
  span and budget cap (V3), Q1 gate (V6), gating fence (V7), verdict vocabulary and
  adoption rule (V1 otherwise) are carried VERBATIM.** No ADR-039 or ADR-040 clause moves
  that ADR-041's header did not already move; in particular the container-SHA
  consequences of a CalculiX bump were already declared there (its header item 3) and are
  not re-opened here, only re-scheduled.

## Why this exists: the ladder was built against a diagnosis that the ladder itself refuted

ADR-041 pre-registered a ladder whose target is the **period-2 parity divergence**, on
§6.49's reading that the ccx heap corruption is *"the final blow it exposes the process
to"*. Two rungs have now run, and that reading did not survive them.

- **D-A (unmitigated, uncontended): RECURRENCE-DETECTED.** Died at w1487 of 8000 with
  attempt 1's exact signature. The divergence is reproducible across runs that share no
  timing, and the detector fired at w1460 — 27 windows of warning, prospectively, on
  bounds fixed before the probe.
- **D-B (serial-implicit, uncontended): DIED-UNDIAGNOSED at w88**, before the detector's
  grid begins.

**Fact 1 — the crash does not need the divergence.** Three deaths, all `corrupted
double-linked list` inside CalculiX 2.20: w1703 (parallel, contended), w1487 (parallel,
uncontended), w88 (serial, uncontended). The first two carried ~150 windows of precursor;
at w88 none could have developed, since the signature has never appeared before ~w1400.
The aborted first D-B submit reached w111 healthy before it was killed, so the death
window varies more than 20x across identical configurations. **This is a timing-sensitive
memory bug that is a first-class failure mode in its own right, not merely the end-state
of a divergence.**

**Fact 2 — serial-implicit is a worse coupling for this case, on two axes.** It costs
1.76x (5.71 s/window against D-A's 3.25), and its solid residuals run two to three orders
of magnitude larger from the start — 496.9 / 316.8 N over windows 41-60 against D-A's
0.215 / 0.198 N. That is the acceleration change preCICE forces under serial coupling
biting: with only `{Displacement}` admissible as IQN-ILS primary data, a high-added-mass
case loses the Force half of its quasi-Newton set. The parity ratio in those windows is
unremarkable (1.09-1.57), so serial may yet suppress the parity split — but at a residual
level and a cost that make it a poor campaign candidate even if it does.

The ladder's remaining rungs are D-C form 1 (ccx `*CONTROLS`/damping deck bytes) and
form 2 (a CalculiX 2.21/2.22 container bump). ADR-041 ordered them cheapest-first, before
either fact existed. Form 1 targets the divergence; form 2 targets the build the crash
lives in.

## X1 — D-C's forms swap order: the container bump runs FIRST

**Decision.** Within D-C, **form 2 (the CalculiX 2.21/2.22 container bump) is attempted
first, and form 1 (the `*CONTROLS`/damping deck change) second.** Everything else about
both forms — their recorded consequences, their commits, ADR-041's requirement that the
operator be consulted before D-C begins, and the rule that both failing V2 exhausts the
ladder and triggers V1's NO-GO — is unchanged.

**Why, in evidence rather than preference:**

1. **Form 2 addresses what is actually ending runs.** 3 of 3 runs across two coupling
   schemes have died of the same glibc-detected corruption inside ccx 2.20. Form 1 cannot
   address it: damping changes the solid's convergence path, not its allocator.
2. **Fact 1 removed form 1's rationale for going first.** Cheapest-first was correct while
   the divergence was believed to be the mechanism and the crash its consequence. It is
   not the ordering the evidence now supports.
3. **Form 1 costs something form 2 does not.** A new field on the solid spec moves EVERY
   digest, which permanently un-reattaches both uncollected N3 attempt-1 records — the
   completed 76 090-window rigid arm among them. Form 2 moves the container SHA, which
   leaves those records reattachable. Spending an irreversible cost on the rung the
   evidence favours least is the wrong way round.
4. **A version bump is a real hypothesis, not a shot in the dark.** The failure is a
   specific, reproducible, glibc-detected heap corruption in one pinned build; upstream
   CalculiX released 2.21 and 2.22 after it.

### X1a — what form 2 actually IS, amended on measurement (accepted 2026-09-07)

**Form 2 is executed as an ADAPTER bump — `calculix-adapter` v2.20.1 → v2.20.2, on
CalculiX 2.20 — and NOT as a CalculiX version bump.** X1 was accepted naming "the CalculiX
2.21/2.22 container bump"; building it showed that change is not available:

- **No adapter exists for CalculiX 2.21 or 2.22.** `precice/calculix-adapter`'s newest tag
  is v2.20.2, its master README reads *"This adapter is based on the source code of
  CalculiX v2.20"*, and its own `docs/calculix-support.md` describes porting as a MANUAL
  source merge into the solver's main loop — copy `nonlingeo.c` from the new CalculiX and
  re-apply the adapter's time-stepping, communication and checkpointing changes, replace
  `ccx_2.<version>.c`, update `CalculiX.h`. Hand-porting coupled-solver C is exactly the
  work whose likeliest by-product is a new memory bug, in a rung whose purpose is to
  remove one.
- **The pinned adapter is 2.5 years stale and the gap is the right one.** The container
  pins `CALCULIX_ADAPTER_REF=v2.20.1` (2024-03-20); v2.20.2 (2026-08-05) is 90 commits
  later and fixes, in the adapter C between CalculiX and preCICE: **uninitialized
  counters** — `numNodes`, `nodeSetID`, `numElements`, `faceSetID` never zeroed in
  `PreciceInterface_Create` (#165), a count read before it is set being a direct route to
  the out-of-bounds write glibc reports as `corrupted double-linked list`; **"memory
  access issues during adapter initialization"** (#154); and two memory leaks (#166).

**Consequences, which are SMALLER than the ones X1 was accepted with.** The rebuild still
moves the SIF digest, its ADR-038 roster row and P1/P3 provenance — the consequence
ADR-041 declared for form 2. But **CalculiX itself does not move, so I9's deck conventions
are NOT re-opened**; ADR-041's header item 3 (ADR-040 U1/U3 giving way) is therefore NOT
exercised by this rung and stands unused unless a true CalculiX bump is ever taken.

**Not proven, and this ADR does not pretend otherwise.** None of those fixes is confirmed
to be our crash. The case for the rung is that it is cheap, that it is the only executable
form-2-shaped change, and that the fixes are in the right component and of the right class.
A near-miss is recorded so a later reader does not mistake it for a smoking gun: the commit
*"Remove an invalid free on nodeIDs"* (#173), which frees a pointer INTO CalculiX's own
`ialset` array, is **not in our build** — introduced after v2.20.1, removed before v2.20.2.

**What form 2 does NOT settle, stated so it is not over-claimed.** V1's adoption rule is
unchanged: a rung is ELIMINATED only if it completes the full 8000-window span AND V2's
detector reports no precursor. **A CalculiX bump that stops the crashes but leaves the
parity divergence intact is RECURRENCE-DETECTED, not an adoption**, and the ladder then
proceeds to form 1, which is the rung that targets the divergence. The two rungs address
two different failure modes and the swap does not merge them.

## X2 — a probe that dies before the signature could be observed may be re-probed once

**Decision.** ADR-041 V1's DIED-UNDIAGNOSED remains terminal, with one bounded exception:
**a probe that ends before window 1400 has produced no information about its rung and may
be re-probed ONCE.** A probe that reaches w1400 or beyond and dies has had the opportunity
to show the signature, and its DIED-UNDIAGNOSED verdict stands as ADR-041 wrote it. The
re-probe counts against V3's 35 h ladder cap like any other, and no rung may be probed
more than twice under any combination of V1(a), V1(b) and this clause.

**Why w1400, fixed from prior data rather than from an outcome:** the earliest the
precursor has ever been *detectable* is w1460 (D-A's parity prong), and the earliest onset
estimate is ~w1557 (attempt 1). 1400 sits below both. A probe that dies before it cannot
have been judged on the signature, so scoring it as a rung verdict records a fact about
the memory bug's timing and calls it a fact about the mitigation.

**Why this matters going forward, which is the actual motivation:** Fact 1 establishes
that the crash can fire arbitrarily early. Under V1 as written, a rung can therefore be
spent by luck rather than by physics, and with two rungs left the ladder could exhaust
itself — reaching a NO-GO on infrastructure — without a single mitigation having been
tested over its span. That is not the failure mode the pre-registration was defending
against.

**The conflict of interest, stated rather than buried:** this clause is proposed *after*
D-B died at w88, and if accepted it would re-open D-B. That is exactly the timing an ADR
regime should be suspicious of. Two things bound it: the threshold is set from D-A's and
attempt 1's numbers, not from D-B's; and **the agent proposing it declines to use it on
D-B** — Fact 2 makes serial-implicit a poor campaign candidate on cost and conditioning
regardless of what a second probe would show, so re-spending 12.7 h of the cap on it is
not recommended. The clause exists to protect the rungs that have NOT run. If the operator
would rather not carry that risk, **X1 can be accepted without X2**: the ladder then keeps
ADR-041's strict rule, D-B stands spent, and a form-2 probe that dies early ends the
ladder in a NO-GO.

## X3 — NOT ACCEPTED (recorded diagnosis only): why the core dump wrote 0 bytes

ADR-041 V5 armed `ulimit -c unlimited`, and D-A produced a **0-byte** `core.31023` owned
by root although the participant runs as uid 1000. The cause is now measured rather than
guessed: **`/proc/sys/fs/suid_dumpable` is `0` on aero-dev**, so the kernel refuses to dump
a process that changed credentials — which the participant does, via `setpriv`. `ulimit`
was necessary and never sufficient, and `setpriv` offers no dumpable option.

Two ways to fix it, and only one is the agent's to take:

1. **`fs.suid_dumpable=2` on aero-dev** — a HOST sysctl change, and therefore an operator
   decision under CLAUDE.md Hard Rule 5. It makes cores for credential-changed processes
   root-owned and written per `core_pattern` (`core`, i.e. into the participant's workdir,
   which is where V5 wanted them). A ccx core at 130 032 cells may be multi-GB; NFS has
   24 T free.
2. **Restore the flag in-process after the drop** — `prctl(PR_SET_DUMPABLE, 1)` inherits
   across `exec`, so a small helper between `setpriv` and the solver would do it without
   touching the host. It adds a moving part to the launch chain that every future coupled
   run would carry.

**Neither was taken, and that was the operator's decision on 2026-09-07.** If form 2 stops
the crashes there is nothing to dump; if it does not, a core becomes worth having and
option 1 is one operator-approved sysctl away. This clause exists so the diagnosis is
recorded and the choice is not re-derived later — **it is not authority to change the host
or the launch chain.**

## What does not change

ADR-041's V2 detector and every bound in it; V3's 8000-window span, the 4000 fallback, the
forbidden 6000, "probes size nothing", and the 35 h aggregate cap (**1.99 h spent** after
D-A and D-B); V4's online detector on every poll; V5's `MALLOC_CHECK_`-on-rungs-only
policy and its reasoning about N3's sizing rate; V6's Q1 re-run on whatever is adopted,
frozen bands verbatim, at its own record path; V7's template-of-record fence. ADR-040's
BUDGET family, N1 stack, L3 ranks, sizing rule, Q1 bands and W contingencies. ADR-039's
gate block, bands and permanently unfilled `<<B2-PENDING-I4>>`.

## Consequences

**Positive.** The next rung tests the failure mode that has ended every run so far, and it
does so without spending the irreversible digest move that form 1 carries. With X2
accepted, the remaining rungs cannot be spent by the memory bug's timing alone.

**Negative / honest limits.** A container bump re-opens the I9 deck-convention checks
against a new binary (already declared in ADR-041's header item 3) and takes a build
before it takes a probe. It may stop the crashes and leave the divergence — which is a
RECURRENCE-DETECTED verdict and another rung, not a win. X2 loosens a rule this regime
deliberately made strict, at a moment that benefits the agent proposing it; X1 stands
without it. And none of this touches the campaign's economics: the parallel stack still
projects ~27 days per wave for 20 settled cycles (~15 at the 10-cycle floor), which is the
B3 conversation ADR-040 pre-registered and which waits on N3's measured rate.

## Links

- Handoff §6.52 (D-A's verdict), §6.53 (D-B's parse gate), §6.54 (the abort and the 1.76x
  cost), §6.55 (D-B's death at w88 and the two facts above).
- Rung evidence on NFS: `adr041-D-A-verdict.json` + `adr041-D-A-solid-residuals.tsv` under
  `runs/hg2007_flexible_foil-20260905-220206/`, and the D-B pair under
  `runs/hg2007_flexible_foil-20260907-122616/`.
- ADR-041 (the ladder this amends), ADR-040 (numerics, budget, L5), ADR-039 (the gate),
  ADR-038 (container roster — where a CalculiX bump's SIF digest lands).
