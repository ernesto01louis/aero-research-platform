# ADR-040 — Re-pre-registered campaign numerics, the parallel fluid seam, and a resized budget: families U, N, L, Q and BUDGET

- **Status:** accepted
- **Date:** 2026-08-12
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 20)
- **Stage:** 20
- **Supersedes:** — (ADR-039 remains the pre-registration of record for the physics; only
  its B1 and B2 budget clauses are superseded, and its gate block is untouched and
  digest-pinned)

## Context and problem statement

ADR-039 pre-registered the Heathcote-Gursul gates and then, working exactly as designed,
**refused to size its own campaign**. Session 7's pre-flight measured the candidate time
step failing Courant at the first window (max Co 9.61), re-probed at `dt = 2e-5` s, and
measured the Courant-passing window at **16.08 s/window (flexible)** and **9.12 (rigid)**
in the wave-1 contention shape. The committed sizing rule then said, in its own words:
*"flexible projects 18762387s > 1209600s, rigid projects 10640030s > 1209600s"* — **217
and 123 days against a 14-day per-wave ceiling**, still 7.8x and 4.4x over at the 10-cycle
last resort. `<<B2-PENDING-I4>>` stayed, the sentinels stayed `None`, and no wave ran.

That is the whole reason this ADR can exist. **No gated campaign has ever run, so no
verdict exists, and the only thing this stage has ever seen from the pre-registered
configuration is a cost — never a result.** ADR-039's FORBIDDEN list binds changes made
*after* a campaign, when a band could be moved toward a number already on the screen. Its
P4 mechanism — sentinels `None`, `gated` DERIVED, `--submit` structurally refusing — is
precisely what kept that from becoming possible. Every change below is chosen against a
measured **cost** or a refuted **hypothesis**, and **not one fidelity band moves**.

Three sessions of measurement stand behind the numerics chosen here, and two of them
mostly consist of things that turned out to be false:

- **Session 8** bounded the cost. 99.42 % of the flexible arm's wall clock is fluid
  participant CPU and 90.8 % of that is the pressure solve, at 961 GAMG iterations per
  step. Every I/O-shaped lever is capped at 0.58 % by that bound and fluid subcycling at
  ~6.6 %; both were named as leads and both are dead. One token — `smoother
  GaussSeidel` → `DICGaussSeidel` — is worth **2.22x**.
- **Session 9** killed the two remaining operator-named leads on a committed harness that
  reproduces the previous record's control to four significant figures before measuring
  anything new. `cacheAgglomeration no` removes **no** iterations on a mesh that moves and
  costs 6.8–21.4 %; a fully-Dirichlet farfield pressure — the strongest and deliberately
  over-constrained form of the pressure-reference fix — is worth 3 %, inside scatter.
- **Session 9 also corrected the previous record's attribution.** The residual 3x is not
  the deforming mesh: the campaign's foil had moved **0.006 of one wall cell** over its
  whole run, and a screen that moved it 167x further reproduced almost none of the cost.
  It is the implicit coupling's **permanent cold start** (N4) — which lives inside C1, and
  C1 is frozen, so it is reported and not acted on.

The rank count moved too, and for a reason worth stating: the standing decision of six
fluid ranks per arm came from an **uncontended** ladder on a **static** mesh. Re-measured
in the shape wave 1 actually runs in — two arms concurrently, moving mesh, binding on the
slower arm — **4+4 beats 6+6** while leaving four more cores free.

What none of that produces is a number allowed to size B2. Every rate above comes from a
fluid-only screen or from the ADR-039 numerics. **N3** is this ADR's one expensive
measurement and its only sizing input, and getting it out of the door is the reason the
rest of this document exists.

<!-- GATE-BLOCK-040:BEGIN -->
```text
THE ADR-040 GATE BLOCK (ADR-040 is the source of record for the campaign numerics, the
parallel seam and the budget; the campaign driver's PREREGISTERED_GATE_BLOCK_040 is the
operational copy, embedded in every ADR-040 bundle beside ADR-039's; required unit tests
assert byte-identity, shape and marker state. ADR-039's block is NOT touched and is
digest-pinned by test_adr039_gate_block_digest.py)

U - what ADR-039 carries over UNCHANGED, clause by clause (ADR-039 remains the
  pre-registration of record for everything not named in N, L, Q or BUDGET below; where
  a clause is re-run rather than cited, it is re-run against the SAME criterion)
  U0 why changing anything is admissible at all: NO GATED CAMPAIGN EVER RAN. The only
     thing this stage has ever seen from the pre-registered configuration is a COST -
     217 and 123 projected days against a 14-day ceiling - and never a RESULT. ADR-039's
     FORBIDDEN list binds changes made after a campaign, when a band could be moved
     towards a number already seen; its own P4 mechanism (sentinels None, gated DERIVED)
     is what kept that from happening. Everything below is chosen against measured COSTS
     and refuted HYPOTHESES, with every fidelity band untouched.
  U1 P1 P2 P3 P4 P5 unchanged. P1's SIF pins, the adapter commit and the roster contract
     are identical; the only difference is that the fluid participant now runs under
     mpirun (L3). P4's derivation gains two required inputs and is otherwise the same
     mechanism - see L5.
  U2 C1 C2 C3 C4 C5 C6 unchanged, and C1 is FROZEN in particular: parallel-implicit,
     max-iterations 50, relative convergence 5e-3 on both Displacement and Force,
     IQN-ILS with QR2 filter limit 1e-2, initial-relaxation 0.5, max-used-iterations 100,
     time-windows-reused 15. N4 below names a lever that lives inside C1. It is REPORTED
     and NOT acted on, because acting on it is what a frozen clause forbids.
  U3 I1 I3 I4 I5 I6 I7 I8 I9 unchanged as clauses. I1 I3 I8 I9 are CITED from their
     existing data/vv records and never re-run - none of them is a function of the linear
     solver. I4 I5 I7 are re-run under the ADR-040 stack, against the same criteria,
     because a rate, a mesh-motion trace and a Courant number are all properties of the
     numerics that produced them.
  U4 R1 R2 R3 unchanged. The reference of record stays hg2007_recomputed.csv and no
     reference row moves.
  U5 K1 K2 K3 unchanged, including K1's window-scoped range and K3's repeat-cadence
     classification, which RAISES on any repeat the iterations log does not account for.
  U6 S1 S2 S3 S4 S5 unchanged: the prescribed period T = 1.0145 s, the unconditional 3/f
     discard, the fundamental-anchored convergence test, at least 20 settled cycles on
     the paired rung and 10 on the GCI rungs, the last-checkpoint rule, and the
     cumulative per-signal bound.
  U7 A1 A2 A3 A4 A5 unchanged. A4 - matched numerics by construction - now additionally
     requires that both arms share the numerics label and the fluid rank count, which L5
     makes structural rather than a matter of discipline.
  U8 D0 D1 D2 D3 D4 D5 D6 D7 D8 D9 D10 unchanged, every band verbatim: 25 %, 25 %, 40 %,
     25 %, 25 %, (no band), (no band), (no band), 2 deg, (no band), 2 %. NO BAND MOVES,
     the gated set is the same set, D9 stays reported-only and D10 stays gated. The
     ordered (clause, band) parity against CLAUSE_BANDS is ADR-039's test and stays green.
  U9 M1 M2 M3 M4 unchanged, and the X diagnostics list is unchanged.
  U10 ADR-039's VERDICT line IS the stage verdict, verbatim and clause by clause.
     ADR-040 introduces no gated physics clause and cannot change the outcome of one.
  U11 ADR-039 B3 and B4 carry over; ADR-039's contingencies N1 N2 N3 N4 carry over
     verbatim. ADR-039 B1 and B2 are SUPERSEDED by the BUDGET section below, and
     ADR-039's <<B2-PENDING-I4>> marker STANDS UNFILLED PERMANENTLY: the campaign it
     would have sized was measured infeasible and will never run, so its sentinels stay
     None and its --submit mode refuses forever. That is a state, not an oversight, and
     test_adr039_b2_marker_state.py keeps it true.

N - the campaign numerics, re-pre-registered (measured in the data/vv records
  stage20_i10_cost_split.json, stage20_n2_screening.json and
  stage20_n4_deforming_screen.json; every rejected lever below is rejected on a
  measurement rather than on an argument)
  N1 the fluid linear-solver stack, by token, label adr040-candidate: p solver GAMG;
     p smoother DICGaussSeidel; p tolerance 1e-6; p relTol 0.01; pcorr tolerance 0.02;
     no GAMG controls; nOuterCorrectors 1; nCorrectors 2; nNonOrthogonalCorrectors 1.
     Measured 3.73x serial static and 4.36x on a mesh that moves, against the ADR-039
     stack. The single token DICGaussSeidel is worth 2.22x of that and drops GAMG
     iterations per step from 302 to 51: the coarse-grid correction was not working
     under a plain Gauss-Seidel smoother at cell aspect ratios near 310.
     nOuterCorrectors 1 is a DECK change, not a knob - OpenFOAM then tags every inner
     iteration final and demands cellDisplacementFinal, and a deck carrying only
     cellDisplacement dies with FOAM FATAL IO ERROR on the first time step.
  N2 what is deliberately NOT changed, each refuted by measurement: cacheAgglomeration
     no leaves the pressure solve at 41.3 iterations per solve against 40.3 with the
     cache on - no reduction at all - and costs 6.8 percent, 21.4 percent on this stack;
     pinning the ENTIRE farfield pressure, the strongest and deliberately
     over-constrained form of the pressure-reference fix, is worth 3 percent, inside
     scatter, so NO CAMPAIGN BOUNDARY CONDITION CHANGES; forces1 write scheduling and
     fluid subcycling are both bounded away by I10's 99.42 percent fluid-CPU share
     (0.58 percent and about 6.6 percent respectively); PCG+DIC is 1.07x and stays
     rejected; the time scheme stays Euler per I8; dt stays the candidate 2e-5 s subject
     to W5.
  N3 THE COUPLED CONFIRMATION - the only measurement in this stage permitted to size B2.
     Both arms concurrently at the gated rung, 4 fluid ranks each (L3), the N1 stack,
     dt 2e-5 s, 76090 windows = 1.5218 s. The (1-cos) ramp ends at window 50725, so this
     covers 25364 post-ramp windows = one full half-stroke, over which the plunge speed
     runs 0 -> peak -> 0 and the phase coverage of |v| is complete by symmetry.
     THE SIZING RATE IS THE POST-RAMP RATE, over a whole number of post-ramp
     quarter-cycles, and never wall_clock_s / windows_completed: two thirds of these
     windows sit inside the ramp at near-zero plunge and would understate the wave. A
     ramp-phase rate may not size; a fluid-only screen may not size; an uncontended run
     may not size.
  N4 REPORTED, NEVER ACTED ON - where the residual cost is. The campaign's pressure
     solve is permanently cold-started: under implicit coupling every iteration restores
     the window-start checkpoint, so the solve never inherits a converged iterate. The
     screen's own first five steps cost 78.2 iterations per p solve from uniform fields
     and decay to 40.3 by step five; the campaign's first five sit at 91.2 - the screen's
     STARTUP number, not its settled one - and never decay, running 113.0 over 2627
     solves. Four consistent signatures: present from the first solve, flat across
     position in the window (987 on iteration 1 against 977 on iteration 3), flat in
     time, and untouched by both refuted knobs. This is an ATTRIBUTION, not a
     confirmation - a fluid-only screen structurally cannot test it. The lever it implies
     is the per-iteration initial guess, which lives in C1, which is frozen (U2). If N3's
     measured rate lands far from the projection this is the first place to look, and
     closing it needs a NEW ADR, not a knob.
  N5 the caveats parallelism carries into every downstream number, stated so they are
     not rediscovered as anomalies: under mpirun OpenFOAM's ExecutionTime is RANK 0's
     CPU, not the aggregate, so I10's 99.42 percent bound does NOT transfer to a parallel
     run and the post-ramp rate is read from ClockTime; ClockTime prints at
     integer-second resolution, which is ample over a run of hours and useless over one
     of seconds; under decomposition time directories sit at processor*/<time>, so I4's
     disk accounting and its time-directory count are rank-aware or they read zero.

L - the live MPI ladder and the parallel seam (L1 and L2 already PASSED and are cited
  from data/vv/stage20_n2_screening.json; L3 is measured in
  data/vv/stage20_n4_deforming_screen.json)
  L1 PASSED: mpirun is REFUSED outright by OpenMPI when it runs as root, and works under
     the setpriv uid drop (4 ranks, Open MPI 4.1.6). So the seam is
     build_participant_command and never build_apptainer_exec(mpi_n=...), which would
     hoist mpirun outside the drop or emit mpirun -n 4 cd fluid-openfoam - a solver that
     runs SERIAL and exits 0.
  L2 PASSED: at 2, 4, 6 and 8 ranks postProcessing/forces1/0/force.dat lands in the CASE
     ROOT, never under processor*/, so the readout needs no change under decomposition.
  L3 the fluid rank count is 4 PER ARM, pre-registered with no free knob, 10 of
     aero-dev's 16 cores with the two CalculiX participants. Measured in the wave-1 shape
     - two arms concurrently, moving mesh, binding on the SLOWER arm because the wave is
     not done until both are: 4+4 gives 0.1655 s/step against 6+6's 0.1860 on 14 cores,
     medians over repeats. The uncontended moving-mesh ladder agrees and is sharper,
     pressure iterations per solve rising monotonically 5.6 / 9.2 / 11.4 / 18.4 / 36.1
     across 1 / 2 / 4 / 6 / 8 ranks - an iteration count is a far more robust witness
     than a wall clock on a shared box. The standing 6-rank decision came from an
     UNCONTENDED ladder on a STATIC mesh and is superseded.
  L4 decomposePar runs UNDER THE PARTICIPANT UID, not as root like blockMesh: pimpleFoam
     writes into processor*/ every time step and root-owned directories kill the run at
     t=0. The processor* count is COUNTED on the host and must equal the requested rank
     count before any submit - decomposePar exits 0 having fallen back to fewer
     subdomains, and that is a different configuration wearing this one's clothes.
  L5 gated is DERIVED by is_gated_configuration_040 from FIVE required inputs - rung,
     time-window-size, max-time, numerics label AND fluid rank count - never passed in.
     Two of those are new because without them a run at the right dt with the wrong
     numerics, or at the wrong rank count, would claim the gated verdict. ADR-039's
     is_gated_configuration is left untouched and returns False permanently (U11).
  L6 the L-SMOKE: a short coupled run through the real driver path, both arms at 4+4,
     must PASS before N3 is submitted - processor* count correct on both arms, mpirun
     inside the uid drop in the staged supervisor, both participants exit 0, coupling
     converged, force.dat in the case root. Two minutes to de-risk two days.

Q - equivalence against the ADR-039-numerics baseline (the band and the REJECTION
  outcome are fixed here, before the probe runs; the baseline side costs nothing because
  the surviving I4 bytes are on disk)
  Q1 500 coupled windows at the I4 shape, both arms concurrently, under the N1 stack at
     4+4 ranks, against the surviving ADR-039-numerics I4 runs
     hg2007_flexible_foil-20260810-144742 and hg2007_rigid_foil-20260810-144747. Three
     pre-registered comparisons, all of which must hold: (a) the span-mean streamwise
     interface force per arm within 2 percent of the baseline's span-mean; (b) the
     per-window trace within 5 percent of the baseline trace's peak-to-peak amplitude in
     maximum absolute deviation - an absolute band scaled by a MEASURED amplitude,
     because a relative bound is undefined at a zero crossing; (c) the flexible-minus
     -rigid difference of the span-means within 5 percent of the baseline difference,
     stated separately so that a common-mode shift is not read as an increment failure
     and an anti-symmetric one is not read as a pass.
  Q2 what Q1 does NOT establish, stated rather than left to be assumed. The I4 shape
     sits inside the ramp: over its whole 0.01 s the foil moved 2.6e-07 m, 0.006 of ONE
     wall cell. So Q1 certifies that the stack reproduces the ADR-039 numerics' forces IN
     THAT REGIME, not post-ramp. And it compares the configuration AS DELIVERED - N1's
     numerics and the 4-way decomposition together - so a rejection does not localize;
     the declared localizing follow-up is a serial run at the N1 numerics.

VERDICT: ADR-040 has NO verdict of its own over the physics. ADR-039's clause-by-clause
VERDICT line stands verbatim and is the only verdict this stage will ever take (U10).
ADR-040's own outcomes are four, each a recorded result either way: L6 passes or N3 is
not submitted; Q1 accepts or the N1 stack is inadmissible (W4); N3 measures a post-ramp
rate or FAILS (W3); and B2 is then either filled from that rate through the committed
sizing rule or the stage records a budget NO-GO. A budget NO-GO is a result. No band is
relaxed under any circumstance, and no number below is chosen after seeing a rate.

BUDGET (pre-declared): aero-dev only, no cloud spend, 4 fluid ranks per arm, two waves.
  B0 the ADR-040 PROBE ceiling: 259200 s (72 h) per submission, 432000 s (5 d) total,
     covering L6, Q1 and N3. This clause exists because N3 cannot be ceilinged by B1:
     B1 is an OUTPUT of N3. At the pessimistic end of the projection N3's 76090 windows
     cost 59.2 h, so 72 h carries about 22 percent headroom and still clears the ramp
     alone at up to 5.1 s/window.
  B1 pre-flight ceiling: <<B1-PENDING-N3>>
     ADR-039's B1 - 43200 s per submission - was NEVER SATISFIABLE, and saying so is part
     of the record. I7 must reach the post-ramp window, which needs at least 50725
     windows; against 43200 s that demands 0.85 s/window, TIGHTER than the 1.037
     s/window B2 itself needed for 20 settled cycles in 14 days. A pre-flight ceiling
     that binds harder than the campaign it is a pre-flight for cannot be met by any run
     that would justify the campaign. The replacement is an OUTPUT of N3's measured
     post-ramp rate, re-derived by a required test, and is filled in the same commit as
     the N3 record.
  B2 gated campaign: <<B2-PENDING-ADR040>>
     The sizing RULE is pre-registered now and the numbers are an output of the N3 record
     through aero/vv/fsi/hg2007_sizing.py:size_gated_campaign_040, re-derived by a
     required test. The gated rung is mid, both arms; the time-window-size is the
     Co-passing probe's dt verbatim, never scaled from a measurement at another dt;
     max-time is the smallest exact multiple of dt covering the S2 discard plus 20
     settled cycles, bumped to the first value for which n*dt survives a .13e round trip;
     the projection uses N3's CONTENDED POST-RAMP seconds-per-window; dt is FIXED across
     all three rungs so temporal error is common-mode (I8), which is why I7 must also
     pass on the fine rung.
  B3 per-wave ceiling: <<B3-PENDING-CEILING>>
     ADR-039's 14-day per-wave ceiling is MEASURED out of reach at any settled-cycle
     count: 20 cycles need 1.037 s/window and 10 need 1.834, against a projection of
     about 2.00. The DECISION RULE is pre-registered here and only the number is pending:
     the operator is brought N3's coupled, contended, post-ramp rate and approves the
     SMALLEST ceiling that fits 20 settled cycles at that rate, and the approval is taken
     BEFORE B2 is filled - so the ceiling is chosen against a measured rate and not
     against a projected campaign length that someone wants to fit.
  B4 reaching a ceiling is a RECORDED OUTCOME, not a failure, exactly as in ADR-039. The
     declared last resorts, in order: cut settled cycles (never below 10), then a budget
     NO-GO. If S3 cannot be satisfied within the ceiling the verdict is NO-GO on periodic
     steady state - never a re-run with a hand-picked window.

CONTINGENCIES - MECHANISM (allowed, declared in advance) vs GATE (forbidden); items are
  W-prefixed because N is a numerics family here AND ADR-039's own contingencies are
  N-prefixed, so every cross-ADR reference in this document is qualified (ADR-039 N3)
  W1 if the L-smoke (L6) fails, N3 is NOT submitted. The seam is fixed and the smoke
     re-run; a failed smoke is recorded and never bypassed, because the thing it proves
     is the thing a two-day run would otherwise discover at hour 40.
  W2 if the processor* count does not equal the requested rank count, the run is
     REFUSED, before submit. There is no fallback rank count: L3 pre-registers one.
  W3 if N3 reaches B0 before completing one whole post-ramp quarter-cycle, N3 FAILS,
     B2 stays pending and the record says so. If it reaches B0 having completed at least
     one whole post-ramp quarter-cycle, the rate is taken over the largest whole number
     of post-ramp quarter-cycles completed and the record states the phase coverage.
  W4 if Q1 rejects, the N1 stack is INADMISSIBLE and N3's rate may not size B2 even if
     N3 itself succeeded. The declared alternatives, in order: re-run the campaign
     confirmation on ADR-039's numerics under the B3 ceiling, or record a budget NO-GO.
     The band is not widened and the comparison is not re-chosen.
  W5 the CONDITIONAL dt re-probe, pre-authorised here and nowhere else: if N3's measured
     post-ramp max Courant is at most 0.4, ONE probe at the next larger round-tripping dt
     is permitted, and the campaign dt is the largest probed dt whose post-ramp max
     Courant is at most 0.8. Any dt that is not itself a passing probe's dt is refused,
     and n*dt must survive a .13e round trip or the CalculiX field width rejects the deck.
  W6 if a wave-1 solve ends participant-died, ADR-039 N3 applies unchanged: one
     resubmission, both arms, new run ids, both bundles shipped, and a second death is a
     NO-GO on infrastructure.
  FORBIDDEN: everything ADR-039's FORBIDDEN list names - any D band, any convergence
  limit, max-iterations, the S2 discard, the settled-cycle minima, the analysis window,
  the reference row, M3's motion margin - and, after the N3 record exists: the N1 stack,
  the L3 rank count, the definition of the sizing rate, and the Q1 bands. Any of these
  requires a NEW ADR, and the original verdict stands on the record.
```
<!-- GATE-BLOCK-040:END -->

### Why this pre-registration can still fail

- **Q1 can reject.** `nOuterCorrectors 1` and a `p` tolerance loosened by a decade are
  genuine accuracy changes, not just speed. The band is 2 % on a span-mean against a
  baseline that already exists on disk, and W4 says plainly what happens if it does not
  hold: the stack is inadmissible and N3's rate may not size B2 *even if N3 succeeded*.
- **N3 can fail outright.** W3 makes a run that reaches B0 inside the ramp a FAILURE, not
  a rate with a caveat. ~67 % of N3's windows are ramp windows at near-zero plunge, and a
  rule that let them average into the sizing rate would produce a comfortable number and
  an unaffordable campaign.
- **B2 can still refuse.** The projection is ~2.00 s/window against the 1.037 that 20
  settled cycles need inside 14 days; the 14-day ceiling is already measured out of reach
  at *any* settled-cycle count. B3 exists because the honest response is a bigger ceiling
  taken deliberately, not a smaller campaign taken quietly — and B4 keeps a budget NO-GO
  on the table as a result rather than an embarrassment.
- **N4 is attributed, not confirmed.** If N3's measured rate lands far from the
  projection, this is the first place to look, and closing it needs a new ADR rather than
  a knob.

### The two honest divergences this ADR records

**FSI3's `config_hash` moved a second time, `3f94f394…` → `4222f481…`.** Adding
`mpi_ranks` to `ParticipantSpec` changes the spec's *serialization*, and `config_hash` is
a digest of exactly that. The counter-intuitive part is worth stating: **FSI3 uses no MPI
and neither of its participants sets the field** — what moved the digest is
`model_dump_json` serialising the `null`. A field that is absent and a field that is
present-and-null are the same configuration and a different record. This is recorded the
way ADR-037 recorded the first move, and the proof that it is a *record* move and not a
*case* move is that `test_stage19_materialization_is_byte_identical.py` stays green with
goldens untouched since `67d8e82`.

**The two committed I4 submissions no longer reattach.** `spec_config_digest` is what
`_reattach` compares against `spec_sha256`, so the digest move correctly invalidates
`c0eae20a…` and `86121b82…`. That is the guard doing its job — the code *did* move under
those records — and it costs nothing: `--collect-cost` reads the I4 record directly, and
the Q1 baseline and the readout-fix proof read the surviving NFS bytes directly.

### Consequences

**Positive.** The campaign numerics are pinned by token in a document that predates every
run they will produce, the rank count has no free knob, and `is_gated_configuration_040`
makes a run at the right time step with the wrong numerics or the wrong rank count
structurally unable to claim the gated verdict. The sizing rate is defined as a post-ramp
rate in the pre-registration rather than discovered to be one afterwards. Two of the three
pending numbers (B1, B3) are pending on a *measurement* and one (B2) on a *rule that is
already committed as code*.

**Negative (honest limits).** Q1 compares the configuration as delivered — numerics and
4-way decomposition together — so a rejection does not localize, and it compares it inside
the ramp, where the foil barely moves (Q2). The N4 attribution rests on four consistent
signatures and no controlled experiment. And B3 leaves the campaign's headline ceiling
genuinely undecided until N3 lands: this ADR pre-registers the decision *rule* and defers
the *number*, which is weaker than pre-registering both and is the honest shape given that
every rate available today comes from a screen.

**Neutral / followup.** If N3 or Q1 sends the campaign back to ADR-039's numerics (W4),
the confirmation has to be re-run there, and the ceiling conversation happens anyway. The
`<<B1-PENDING-N3>>` / `<<B2-PENDING-ADR040>>` / `<<B3-PENDING-CEILING>>` markers each carry
the same three-commit discipline ADR-039 B2 established — rule now, record next, numbers
last — enforced by `test_adr040_marker_state.py`.

## Links

- ADR-039 (the pre-registration of record for the physics; untouched, digest-pinned by
  `tests/unit/test_adr039_gate_block_digest.py`), ADR-037 (the first `config_hash`
  divergence, and the precedent for recording one), ADR-038 (the multi-container roster),
  ADR-016 (why coupling correctness and application fidelity never blur), ADR-024 (the
  `(1-cos)` ramp that puts 50 725 windows in front of the first usable measurement).
- `data/vv/stage20_i10_cost_split.json` — the 99.42 % bound and the pressure-solve share.
- `data/vv/stage20_n2_screening.json` — the twelve-variant token sweep, the strong-scaling
  ladder, and the L1/L2 MPI ladder cited by the L family.
- `data/vv/stage20_n4_deforming_screen.json` — N4/N5 refuted, the corrected attribution,
  and the contended rank ladder behind L3.
- `data/vv/stage20_i4_calibration.json` — the ADR-039-numerics baseline Q1 compares
  against, and the record whose sizing refusal is quoted above.
- `aero/vv/fsi/hg2007_sizing.py` — `size_gated_campaign_040`, the committed rule B2's
  numbers are an output of; `aero/vv/fsi/hg2007_flexible_foil.py` — `NUMERICS_STACKS`, the
  ADR-040 sentinels and `is_gated_configuration_040`.
- `scripts/stage20_hg2007_flexible_foil.py` — the operational copy of the block below and
  the `--submit-040` mode.
- `tests/unit/test_adr040_*.py` — byte-identity, shape and marker-state tests (in
  `tests/unit/` because `tests/stage_20` is not in CI).
