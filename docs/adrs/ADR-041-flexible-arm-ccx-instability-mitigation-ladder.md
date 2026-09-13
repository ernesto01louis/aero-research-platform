# ADR-041 — A pre-registered mitigation ladder for the flexible arm's period-2 solid instability, and a parity-based divergence detector: family V

- **Status:** accepted — the operator accepted this text on 2026-09-05, and that
  acceptance is recorded by the commit that lands this file (the ADR-040 `d5bf381`
  pattern). No ladder probe was submitted before it.
- **Date:** 2026-09-05
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 20)
- **Stage:** 20
- **Supersedes — the full list, stated in the header the operator accepts:**
  1. **ADR-040 B0's scope**, unconditionally on acceptance: B0's text scopes itself to
     "covering L6, Q1 and N3", and this ADR charges the ladder probes and the Q1 re-run
     to it as well, under the aggregate cap in V3. **A budget family moves.**
  2. **ADR-040 U2 (C1 frozen)** and, with it, **the coupling-scheme values ADR-039 C1
     pre-registers** — conditionally, IF AND ONLY IF D-B is adopted under V1, and then
     for the mitigated stack only: `parallel-implicit` → `serial-implicit` **and** the
     IQN-ILS primary-data set from `{Displacement, Force}` to `{Displacement}` (the
     second is FORCED by preCICE, not chosen — see D-B). ADR-039's gate-block **bytes**
     stay byte-identical and digest-pinned; what moves is the expectation value the
     campaign is evaluated against, and this ADR is the record of that move.
  3. **ADR-040 U1 and U3**, conditionally and only if the ladder reaches **D-C form 2**
     (a CalculiX container bump): U1's "P1's SIF pins … are identical" and U3's "I1 I3
     I8 I9 are CITED … and never re-run" both give way — a new binary re-opens the I9
     deck-convention checks.
  4. **ADR-040 L5**, unconditionally on acceptance and in one direction only: L5's five
     inputs stay necessary and none is replaced, but V7 adds ONE conjunctive fence to the
     derivation — the spec's template must be the template-of-record. It can only ever
     refuse. Bundles will therefore carry the ADR-040 gate block's five-input sentence
     (byte-identical, as pinned) beside a `gated` field that is those five inputs AND the
     fence; this ADR is the record of that difference.
  5. The `SHA256SUMS` regeneration note in `aero/adapters/precice/templates/`, in the
     ADD-a-template case only (D-B): it instructs a `RENDERER_VERSION` bump alongside a
     template change, and **`renderer_version` is a hashed field of `AuthoredSource`** —
     bumping it moves EVERY existing spec's `config_hash` and would retro-break both
     uncollected N3 attempt-1 records and both live digest pins. It is not bumped when a
     template is ADDED and no rendered byte of the existing template changes; bundles are
     distinguished by `template`/`template_sha256`.
  Everything else is untouched: every fidelity band D0..D10, every sentinel, the Q1
  bands, the N1 stack, the L3 rank count, the sizing-rate definition, and ADR-040 U10
  (ADR-039's clause-by-clause VERDICT line remains the only verdict this stage takes).

## Naming discipline

Two collisions exist and every reference below qualifies them. **"ADR-039 N3"** is the
wave-1 death contingency (one resubmission, cited by ADR-040 W6); **"N3"** unqualified is
ADR-040's coupled confirmation probe. The ladder rungs are **"D-A" / "D-B" / "D-C"**
(hyphenated, from the endorsed session-13 path); **ADR-039's "D0..D10"** are the fidelity
bands — no unhyphenated "D" id below is a rung. This ADR's own clauses carry a fresh
**V** prefix; it deliberately has **no GATE-BLOCK markers** — it is not a gate
re-registration, ADR-039's block stays byte-untouched and digest-pinned
(`test_adr039_gate_block_digest.py`), and ADR-040's block is not edited.

## Authority for re-opening a frozen clause

ADR-040 U2 froze C1 because "acting on it is what a frozen clause forbids" — a freeze
that binds knob-level action inside the existing pre-registration, not a subsequent
operator-accepted ADR: ADR-040 itself superseded ADR-039's frozen B1/B2 by exactly this
mechanism (U11), and its N4 already records that closing a C1-internal lever "needs a
NEW ADR, not a knob". The handoff queued this exact decision to the operator: §6.49
option (b) — "coupling-scheme/config mitigations (… serial-implicit ordering): C1 is
FROZEN under ADR-040 U2 — same ADR weight as (a)". The admissibility logic is ADR-040
U0's own: **no gated campaign has ever run**, so no number exists for any band or
expectation to be moved toward; this ADR is written, and its rule and bounds fixed,
before any rung probe produces data. (For the record: ADR-040's FORBIDDEN list does NOT
enumerate the coupling scheme — the freeze re-opened here is U2's, and this paragraph,
not the FORBIDDEN list, is the claimed authority.)

## Context and problem statement

At 2026-08-13 01:04 UTC, window **1703 of 76 090** (2.2 %), N3 attempt 1's flexible arm
(`fsi-hg2007_flexible_foil-20260812-230102`) died: `ccx_preCICE` SIGABRT rc=134,
`corrupted double-linked list`, `stopped_by=participant-died` (handoff §6.46). The rigid
control **completed all 76 090 windows** rc=0 and refuted the factorisation-churn crash
candidate (§6.48). Session 12 mined the dead arm's structured records with a pre-stated
precursor test and two adversarial verifiers — both upheld, zero unresolved refutations
(§6.49; tables and the exact parsers preserved at
`/mnt/aero-nfs/runs/stage20-n3-attempt1-mining/`). Verdict under the pre-registered
rule: **MITIGATION-WARRANTED**.

The finding: the abort is not a bolt from the blue. A **period-2, odd-window exponential
instability inside CalculiX** begins ~150 windows before death, invisible to every
interface-side series. An unmitigated resubmission is therefore not a neutral retry, and
— because F-vs-Q1 determinism is DIVERGENT from the first parallel GAMG solve — not a
sharp reproduce/not-reproduce probe either. This ADR pre-registers, BEFORE any probe
runs, the short diagnostic ladder that picks the mitigation, the rule by which a rung is
adopted, and the recorded consequences of each rung, so that no choice is made after the
fact against a number already on the screen.

## The evidence of record (§6.49, re-derived from the primary tables for this ADR)

Every number below was recomputed from `minerB_flexible.tsv` / `minerB_q1.tsv` /
`minerB_rigid_window_table.txt` while writing this ADR; three of §6.49's summary
sentences did not survive that re-derivation and are corrected here, not repeated.

1. **Odd-window absolute residuals grow exponentially from ~window 1557**: 34.83 N →
   1665.37 N (**47.8x**) by w1701, doubling every ~26 windows. Over the same span the
   **even-window maxima move by +6.3 % total**: 17.490 N (w1558) rising monotonically to
   18.586 N (w1662), then sagging 0.7 % to 18.461 N (w1698). §6.49's "even windows
   monotonically DECREASE" is wrong in direction, and an earlier draft of this ADR's
   "within ±3 % of ~18.5 N" was wrong in magnitude however it is centred: the even series
   spans 17.490 → 18.586 N and its minimum sits 5.3 % below its own final value. **The fact that survives, and the only one the detector
   rests on, is the parity split: 47.8x on one branch against 6.3 % on the other**,
   while commanded plunge amplitude grew 1.19x. A symmetric load ramp cannot produce it.
2. **ccx Newton effort escalates in lockstep, odd windows only**: 39 windows with final
   ITER ≥ 8, ALL odd, an unbroken run 1625..1701 escalating 8→14; the fatal window 1703
   aborts at iteration 7.
3. **The residual argmax marches into the death cluster**: strict-cluster share of
   per-window argmax 0 % (w101-1600) → 6 % (1601-1700) → 67 % (1701-1703).
4. **The interface is blind to all of it**: preCICE coupling health clean and improving
   into the death, fluid series clean (death-step Courant 0.1139), interface-force
   sawtooth decaying. The precursor is visible ONLY in `.cvg`/`.sta`/`Solid.log` and the
   elastic-tip watchpoint — **~80 windows of warning that nothing was watching**.
5. **An absolute residual threshold cannot work, because the healthy envelope tracks the
   load.** Excluding the w1 startup transient (1.883 N at window 1, at ~1e-7 % of
   commanded amplitude — not load), the dead arm's healthy per-100-window ceiling climbs
   **0.65 → 2.42 → … → 24.49 N** over w1-1500 as the ramp grows, a 10.1x climb across
   blocks 2-15 alone, while commanded amplitude over those windows grew from ~0 to only
   0.216 % of full. Full campaign amplitude is **464x** the amplitude at w1500, and 16.6x
   the amplitude at this ADR's own probe endpoint (w8000).
   §6.49's sketch of "a 443 N absolute watchdog would have fired ~w1650" is refuted by
   its own table twice over: the first window whose max absolute residual exceeds 443 N
   is **w1683** (474.19 N), 20 windows before death — and any fixed newton threshold that
   is quiet during the ramp is guaranteed to fire on healthy full-amplitude operation.
6. **What does separate sick from healthy, with margin, is PARITY.** Worst 20-window
   odd/even ratio (both parities' maxima ≥ 1.0 N):

   | dataset | span | windows | worst chunk ratio |
   |---|---|---|---|
   | flexible, healthy | w101-1540 | 1 440 | **1.81** |
   | Q1 control, flexible | w101-500 | 400 | **1.53** |
   | **rigid control, COMPLETE run** | w101-76 080 | **75 980** in 3 799 chunks, 182 active | **2.45** |
   | flexible, dying | w1601-1700 | 100 | 3.21 → 5.48 → 10.14 → 21.08 → **76.63** |

   The rigid row is the only healthy coupled data that reaches **full commanded
   amplitude**, and it bounds the healthy parity ratio at 2.45 there. No healthy chunk
   in any dataset reaches 4.0 even once.
7. **Proximate killer vs precursor**: the SIGABRT is CalculiX-2.20-internal heap
   corruption, timing-sensitive (the Q1 control was sicker in coupling health and died
   of nothing). Verbatim from §6.49: *"the 150-window period-2 divergence is the
   mitigation target; the memory bug is the final blow it exposes the process to."*

## Decision drivers

- **The instability set in at 0.23 % of full commanded amplitude, near no kinematic
  extremum** (envelope `0.5(1-cos)` to window 50 725, re-derived here: 0.232 % at the
  w1557 onset; §6.49's "0.27 %" is that envelope at the DEATH window w1703, 0.278 %).
  If odd-window growth is a genuine property of this coupled configuration, the gated
  campaign's 1.17 M windows at FULL amplitude cannot run on the unmitigated stack
  regardless of the memory bug. Observability alone is a coroner, not a cure.
- **Determinism is divergent** (`minerF_determinism.txt`: decks identical except the
  step duration — commanded plunge identical row-for-row — split at the first parallel
  GAMG solve, t=2e-5 s, 15 vs 16 iterations), so recurrence and non-recurrence are both
  weak signals; a rung is judged on the precursor SIGNATURE over a fixed span, not on
  whether an abort happens to fire.
- **Budget**: ADR-040 B0 stands at **134 h remaining**. W6 governs wave-1 solves only,
  and §6.48 item 3 established that an N3 re-run is an ordinary B0 probe; the ladder and
  the Q1 re-run are the scope extension this ADR makes (header item 1), capped at 35 h
  by V3. Worst case that still reaches N3, priced at N3's 96 h ceiling rather than its
  ~82 h projection: 35 + ~1 + 96 = **132 h of the 134**.
- **Q1's ACCEPT was measured on the unmitigated stack** (`data/vv/
  stage20_q1_equivalence.json`). A D-B or D-C adoption moves the configuration that
  verdict certified; a D-A adoption does not (observability moves no spec bytes). V6
  runs the equivalence gate on the adopted stack regardless — one rule for whatever the
  ladder returns, not a per-rung exemption argued after the fact.

## Declared departures from the endorsed session-13 path

The operator endorsed a ladder whose detector was "the solid-side absolute-residual
watchdog (threshold ~10x the baseline ceiling 44.3 N ≈ 443 N)" and whose adoption rule
read "no odd/even residual divergence, stationary envelopes". Three departures, each
forced by the re-derivation above and each stated here so the operator sees them:

1. **The 443 N absolute threshold is replaced by the parity/runaway detector (V2).**
   Reason: evidence items 5-6 — an absolute newton threshold either fires on healthy
   full-amplitude operation or stays silent through the divergence; the counterfactual
   that justified it (fires ~w1650) is refuted by the table (first crossing w1683).
2. **"No odd/even divergence, stationary envelopes" is operationalized with numeric
   tolerances** — parity ratio 4.0 sustained over two consecutive chunks, block growth
   3.0x — rather than as an absolute prohibition. Reason: healthy coupled runs show a
   parity ratio up to 2.45 and block growth up to 1.75x; a literal zero-tolerance rule
   would fail every rung including a healthy one. The margins are measured, not chosen.
3. **The ladder probes and the Q1 re-run are charged to B0** (header item 1), capped.

## The ladder (this ordering IS the cost ordering)

Rungs are attempted in order; "cheapest" in V1 means the FIRST rung whose probe
eliminates the signature.

### D-A — the unmitigated stack, watched

The flexible arm's numerics, deck and coupling exactly as attempt 1 — **but the probe is
uncontended and 8000 windows long, where attempt 1 was contended and 76 090** (V3;
diagnosis needs no partner). That difference is itself a timing perturbation and is
listed among the honest limits below. Plus three observers:

- the **divergence detector** (V2/V4) reading `Solid.log` absolute residuals in newtons
  (NEVER `.cvg` column 6, a percentage normalized by a near-zero early-ramp average
  force);
- **`ulimit -c unlimited`** on the coupled participants, so a recurrence leaves a core
  naming the corruption site (aero-dev's `kernel.core_pattern` is read first; if it
  pipes to a collector the record says where cores actually land — a ccx core at
  130 032 cells can be multi-GB);
- **`MALLOC_CHECK_=3`**, so glibc aborts at detection rather than at the next unlucky
  free — **on ladder rungs only** (V5: it is an unmeasured allocator perturbation and
  must not ride inside any run whose ClockTime is a measurement of record).

**Recorded consequences:** none of the three touches the spec — they live in launcher
command bytes and polling code, and `config_hash` is a digest of the serialized
`CoupledCaseSpec` only (ADR-037), so **config_hash does NOT move**; the launcher's
byte-pinned unit tests move and are updated in the same commit. Honest caveat:
`MALLOC_CHECK_` perturbs allocator behavior — a surviving D-A rung may have *perturbed*
the bug rather than shown its absence, and an earlier abort under it is a *different*
proximate failure than attempt 1's. Both outcomes are evaluated against the precursor
signature (V2), never against abort behavior. Adopting D-A means the campaign runs
unmitigated-but-watched, which §6.49 called a fragile bet — V1 still permits it, because
a clean D-A probe is the evidence that bet needs and the detector stays armed for the
campaign.

### D-B — serial-implicit coupling

The period-2 odd/even split with a perfectly clean interface is the classic
parallel-implicit signature: both participants advance from the same window state, and a
parity oscillation can live in the solid's half-step without the coupling residual ever
seeing it. Serial-implicit ordering (Fluid first, then Solid within each coupling
iteration) removes the mechanism. The rung MEASURES the serial cost from its own
ClockTime — ADR-040 N5 records that I10's 99.42 % fluid-CPU share does **not** transfer
to a parallel run, so no prior cost bound is claimed here; if the measured cost makes N3
or the campaign unaffordable that is a budget conversation under ADR-040's B family,
taken in the open.

**What the change actually is — larger than "rename one element".** preCICE's own
documentation: *"For serial coupling, you can only configure primary data from coupling
data which is exchanged from the `second` to the `first` participant"*, and its
worked FSI example is exactly this case — fluid first, structure second, *"only the
displacements … are accelerated — not the forces"*. The pinned template exchanges
`Force` Fluid→Solid (first→second) and `Displacement` Solid→Fluid (second→first) and
accelerates BOTH. A serial-implicit variant therefore **cannot keep the IQN-ILS
primary-data set `{Displacement, Force}`**; it becomes `{Displacement}`. That is a
second C1 element, it is forced rather than chosen, it changes the quasi-Newton
acceleration itself (not bookkeeping), and it is declared in this ADR's header.
Pre-registered process, because preCICE's parser is the authority and not this text:
**the serial template is rendered and parsed, and the repo's own
`write_precice_config` expectation assertion run, BEFORE the D-B probe is submitted; any
further element the parser forces to change (for instance a convergence measure the
scheme will not accept on first→second data) is recorded as an additional C1 move in
this ADR and shown to the operator before that probe runs.** If the parser forces any change
beyond the two named here, **D-B is BLOCKED**: the additional move needs its own
operator-accepted ADR before that probe runs — this ADR's supersession list is closed at
acceptance and is not amendable afterwards — and the ladder's fixed order is not re-cut
on cost after data exists.

**Mechanics and record consequences.** A SECOND committed template
(`hg2007-precice-config-serial.xml.in`, with a new `SHA256SUMS` row; the parallel
template byte-untouched), selected through the spec's EXISTING
`AuthoredSource.template`/`template_sha256` fields — **no new pydantic field on any spec
model** (a new field serializes into every spec and moves every digest). The selection
path does not exist in code today and is added, behind tests, before any D-B probe: a
scheme→template registry in `template.py` (replacing the module constant),
`hg2007_expectation` parameterized by the scheme (`CouplingSchemeKind` already admits
`"serial-implicit"`), an optional `coupling_scheme` KEYWORD (not a field) on
`hg2007_case_spec`, and a `--coupling` driver argument that writes the scheme
**explicitly into every new submission's `spec_knobs`**. Two rules keep history
readable and make the adoption commit safe:

- **`_reattach` never relies on the builder's default.** It rebuilds with
  `spec_knobs.get("coupling_scheme", LEGACY_COUPLING_SCHEME)` where
  `LEGACY_COUPLING_SCHEME = "parallel-implicit"` is a frozen constant describing
  *history* and never moves. Records written before this ADR — including **both
  uncollected N3 attempt-1 submissions**, one of which is the completed rigid arm —
  therefore keep rebuilding to their original digests no matter what any default does
  later. `RENDERER_VERSION` is not bumped, for a stronger reason than "no rendered byte
  changes": `renderer_version` is a **hashed field of `AuthoredSource`**, so bumping it
  moves every existing spec's `config_hash` and would retro-break both uncollected
  attempt-1 records and both live pins. The templates' `SHA256SUMS` regeneration note is
  amended for the ADD case accordingly (header item 5); the field that distinguishes a
  serial bundle is `template`/`template_sha256`, and bundles are compared on that.
- **The submission schema is NOT bumped to v3.** The v1→v2 bump existed because v1
  records lacked keys `_reattach` needed and would silently rebuild the wrong spec; here
  the missing key has a correct, frozen historical default, so a v2 record still
  rebuilds the configuration that actually ran. Bumping would make every existing v2
  record uncollectable for no gain.

A serial-scheme spec serializes differently and **its config_hash moves — deliberately**
(ADR-037 precedent: the config a run used must be the config its digest names; this is a
*case* move, not a *record* move). **If D-B is adopted**, one commit does all of: makes
the serial template the **template-of-record**; flips `hg2007_case_spec`'s
`coupling_scheme` default so `--submit-040`, which builds its own spec from five
arguments and cannot be handed a scheme, produces the adopted configuration; adds the
EXPLICIT `"coupling_scheme": "parallel-implicit"` key to the pinned knob dicts in
`test_n3_live_submission_digest_is_pinned.py`, which **preserves `bfc60a49…`/`ed1ba571…`
unchanged** — the keyword selects the same template, the spec gains no field, and those
dicts transcribe submissions whose runs really were parallel-implicit (the pins are
REPLACED only when the N3 resubmission on the adopted stack exists and they are
re-transcribed to describe those live submissions, per §6.44's lifecycle — never by
retro-editing the record of a run that already happened); adds serial-cadence fixtures to the `force.dat` / ccx
`.dat` cadence classifiers, whose per-coupling-iteration semantics the scheme changes;
and records the ADR-039 C1 expectation move named in the header.

### D-C — fallback, reached only if BOTH D-A and D-B fail V2

Two pre-registered forms, attempted in THIS order:

1. **ccx `*CONTROLS`/damping deck bytes** (first — cheaper): a new field on the solid
   spec serializes into EVERY spec ⇒ every digest moves ⇒ both live-submission pins
   re-pinned in the same commit (ADR-037 precedent) **and — disclosed here as ADR-040
   disclosed the same consequence for its two I4 submissions — both uncollected N3
   attempt-1 records become permanently unreattachable, the completed rigid arm included,
   because `_reattach` compares against the `spec_sha256` written in the record on disk.
   Anything wanted from those runs is read from their NFS bytes directly, and the rigid
   arm's residual table is already mined and preserved.** The §6.47 `FREQUENCY`-card question
   stays its own ADR question and is not smuggled in here.
2. **CalculiX 2.21/2.22 container bump** (second, only if form 1 fails V2): the heap bug
   lives inside CalculiX 2.20; a new build moves the **container SHA** — new SIF digest
   in the ADR-038 roster style, P1/P3 provenance updated, **and it supersedes ADR-040 U1
   and U3** (header item 3) by re-opening the I9 deck-convention checks against the new
   binary.

Each form is its own commit and its own single probe under V1. **Both forms failing V2
exhausts the ladder and triggers V1's NO-GO.** The operator is consulted before D-C
begins — it is the heavy rung — but the forms, their order and the exhaustion condition
are fixed here.

## The V clauses (pre-registered before any probe runs)

- **V1 — adoption rule.** The campaign takes the CHEAPEST rung that ELIMINATES the
  precursor signature, where cheapest = earliest in the order
  D-A → D-B → D-C(form 1) → D-C(form 2), and elimination is V2's test. One rung at a
  time; a rung is submitted only after the previous rung's verdict is recorded.
  **Each rung receives exactly ONE evaluable probe and its verdict is final.** The
  verdict vocabulary is closed and every outcome maps to exactly one term: **ELIMINATED**
  (V2's four conditions all hold), **RECURRENCE-DETECTED** (a prong fired, whether or not
  the probe then died), **DIED-UNDIAGNOSED** (the probe ended `participant-died` or was
  killed with no prong having fired — terminal for the rung: a death is what the ladder
  exists to prevent, and elimination requires the full span), **INCONCLUSIVE** (the probe
  COMPLETED but V2(ii) or V2(iii) failed, or it was a 4000-window fallback), and
  **UNRESOLVED** (a rung whose one permitted re-probe also returned INCONCLUSIVE).
  ELIMINATED adopts; RECURRENCE-DETECTED, DIED-UNDIAGNOSED and UNRESOLVED are recorded
  rung verdicts and the ladder advances to the next rung. Two bounded exceptions: (a) a
  probe whose failure is attributable to infrastructure unrelated to the solve (evidence
  named and recorded BEFORE the V2 evaluation is run — NFS outage, host OOM kill, a
  hypervisor or power event; **an operator kill in response to the solve's own behaviour
  is NOT infrastructure**) may be resubmitted once; (b) an INCONCLUSIVE probe has not
  spent the rung's verdict and may be re-probed ONCE at the full span, after which a
  second INCONCLUSIVE becomes UNRESOLVED. Any other resubmission is forbidden — with
  divergent determinism, retry-until-clean is the gaming vector this rule exists to close.
  All resubmissions count against V3's aggregate ladder cap. If no rung is ELIMINATED and
  at least one is RECURRENCE-DETECTED or DIED-UNDIAGNOSED, the result is a recorded
  **NO-GO on infrastructure** conversation with the operator — a legitimate outcome, not a
  process failure. A ladder ending with only UNRESOLVED rungs, or truncated by V3's cap
  before every rung has a verdict, is neither an adoption nor a NO-GO: it goes to the
  operator with the budget arithmetic and the verdicts it does have.
  The adopted rung's configuration becomes the campaign configuration ONLY via this ADR
  plus the adoption-commit discipline in D-B/D-C above.
- **V2 — elimination, operationalized (the detector).** Input: the per-window maximum
  absolute residual from `Solid.log`, extracted exactly as session 12's
  `minerB_parse.awk` extracts it (`max_abs_resid`) — that parser is pinned here by content,
  sha256 `0d6eeca9934632a9fc278db9e59f13aba56e1c1a132cf00a042abd67b3f35a2c`, and the
  repo-side implementation is tested against its output, so the normative definition does
  not rest on a mutable file on the NAS. Grids are aligned from w101, so
  startup is excluded by construction: 20-window **chunks** (w101-120, 121-140, …) and
  100-window **blocks** (w101-200, …). A chunk or block is **active** iff BOTH parity
  maxima within it are ≥ **1.0 N** (the activation floor: below it these are ratios of
  near-zero residuals, where a large ratio carries no information — on the flexible arm
  only 2 of 72 healthy chunks fall below it; on the rigid arm most of the run does,
  including 21 536 consecutive POST-ramp windows in which that barely-deforming solid
  never reaches 1.0 N, which is why V2(iii) reads low activation as INCONCLUSIVE rather
  than as health). Only COMPLETE, fully-written units are evaluated.
  Two prongs:
  - **Parity prong (the detector).** PRECURSOR iff **two CONSECUTIVE active chunks each
    have `max(odd,even)/min(odd,even) ≥ 4.0`**, where CONSECUTIVE means adjacent in the
    chunk GRID with both active — an inactive chunk between them breaks the pair and the
    count restarts; inactive chunks are never skipped over. Measured basis: no healthy chunk in any
    dataset reaches 4.0 even once — worst observed 2.45 (rigid, over the COMPLETE
    76 090-window run at full amplitude), 1.81 (flexible healthy), 1.53 (Q1) — so the
    margin to a single crossing is **1.63x** and to the sustained rule larger still. On
    attempt 1 the rule fires at the chunk ending **w1660**: 43 windows before death,
    where the ratio is already 10.1x and the refuted 443 N absolute rule would not fire
    for another 23 windows. Requiring two chunks, rather than one, is deliberate: under
    V1 a single-chunk artifact would otherwise permanently fail a rung.
  - **Runaway prong (the parity-symmetric backstop).** PRECURSOR iff either parity's
    block max is ≥ **3.0x** that parity's max in the **immediately preceding GRID
    block**, evaluated only when BOTH blocks are active; when the preceding block is
    inactive there is no comparison for that pair — growth never accumulates across a gap
    and the nearest earlier active block is never substituted.
    Measured basis: worst healthy same-parity block growth is 1.75x (flexible, w201-300),
    1.70x (Q1), 1.17x (rigid full run) — margin **1.71x**; the dying arm's odd blocks
    jump 32.0x. Startup is excluded twice over: the w101-aligned grid never
    forms a w1-100 block (across whose boundary healthy growth reaches 3.1x flexible and
    3.9x rigid), and the floor screens near-zero comparisons. With the grid alone and no
    floor the worst healthy growth is 2.19x (rigid, w201-300), still below 3.0 — so here
    the floor is belt-and-braces rather than load-bearing.
  A rung **ELIMINATES** the signature iff: (i) every probe window completes, with no
  `participant-died` and no kill — a probe that dies is RECURRENCE-DETECTED if a prong had
  already fired and DIED-UNDIAGNOSED otherwise, and neither is re-probable except under
  V1(a); (ii) on a probe that COMPLETED, the extracted series covers every window
  contiguously — a log gap or truncation there is INCONCLUSIVE, never elimination;
  (iii) at least
  **50 %** of the probe's chunks are active (below that the detector is inert rather than
  discriminating — INCONCLUSIVE); and (iv) neither prong reports PRECURSOR over the full
  span. A rung whose probe dies has NOT eliminated it (subject only to V1(a)).
  Evaluation is reproducible read-only from `Solid.log`; the extracted TSV, the detector
  script and its output are written beside the run on NFS, provenance-noted. Survival is
  evidence, not proof (determinism is divergent) — the detector therefore stays armed
  through Q1, N3 and the campaign (V4). **These bounds do not move: any change to a
  threshold, floor, grid or span is a NEW ADR, not a reinterpretation, and that applies
  equally to a rung that fails on what looks like a false positive.**
- **V3 — probe registration and the ladder's budget cap.** Rung probes are **8000
  windows** (0.16 s at dt 2e-5 — survives the CalculiX `.13e` field-width round trip),
  **flexible arm only, uncontended**, mid rung, adr040-candidate numerics at 4 ranks,
  detached through the ordinary `--probe` path. The span covers 5.1x the observed onset
  horizon (~w1557) and reaches **6.01 % of full commanded amplitude** at w8000 —
  **25.9x** the onset-window amplitude (0.232 %), 21.6x the death-window amplitude
  (0.278 %) — replaying the exact commanded kinematics that produced the instability. The
  V2 grids close exactly on the span: 395 complete chunks (last w7981-8000) and 79
  complete blocks (last w7901-8000). **An ELIMINATION verdict requires the full 8000
  windows.** 4000 windows (0.08 s, round-trips) is the sole pre-authorized fallback, its
  use declared with a recorded reason BEFORE submission; it can return
  RECURRENCE-DETECTED (a prong fires — a real, final rung failure) or INCONCLUSIVE, never
  elimination and never adoption, and an INCONCLUSIVE 4000 does not spend the rung's
  verdict (V1(b)). **6000 does not round-trip and is forbidden.** Probes can NEVER size
  anything — structurally (an 8000-window probe has no post-ramp window, so
  `i7_probe_from_bundle` refuses its bundle) and by record: every rung record carries
  "diagnostic probe under ADR-041; sizes nothing" and names this ADR. Expected ~3-9 h per
  rung. **Aggregate cap: the ladder's total B0 spend, including every resubmission
  permitted by V1, is capped at 35 h.** A probe that would carry the total past 35 h is
  not submitted; the operator takes that budget decision BEFORE the probe runs and
  therefore before its result exists — raising a ceiling in advance is what ADR-040 B0 did
  and required of itself. The cap is sized against N3's CEILING rather than its
  projection: 35 + ~1 + **96** (ADR-040 B0's per-submission ceiling, which W3
  pre-registers N3 as able to reach) = **132 h of the 134 h remaining**; on the ~82 h
  projection the total is ~118 h. The cap can bind before the ladder is exhausted — four
  rungs at the top of the 3-9 h range is 36 h — and that is deliberate: a ladder truncated
  by budget is a decision the operator takes with the verdicts in hand (V1), not one the
  agent takes by spending B0 down to N3's edge.
- **V4 — the online detector (the watchdog).** Repo-side and hash-exempt: reads the run's
  `Solid.log` only (binary-safe, ANSI-escape-tolerant regex parsing per the session-12
  parsers; absolute values of the signed "largest residual force" lines; window
  attribution from the window-marker lines). At every poll it evaluates **the V2
  detector** — one detector, pre-registered once, applied live and post-hoc — over the
  complete chunks and blocks only, **never the trailing partial unit** (a poll can catch
  a window mid-write, and a half-written parity would otherwise fail a rung), and reports
  the running per-parity maxima, the worst chunk ratio, the activation fraction and the
  verdict. Because both prongs are ratios of like quantities the detector is meaningful
  wherever it is *active*; where activation is low it says so rather than reporting
  health (V2(iii)). It OBSERVES AND REPORTS: no automatic kill is pre-registered. During
  a rung probe its verdict IS the rung's V2 result; during Q1, N3 and the campaign it is
  an alarm with, on attempt-1 evidence, ~43 windows of warning, and the operator acts.
  Absent-log semantics are explicit: absent while running = "no data yet"; absent while
  done or failed = loud error.
- **V5 — environment observability.** `ulimit -c unlimited` is injected into the
  participant launch compound (launcher bytes, inside the uid-drop, so a core lands
  writable in the participant workdir) — NOT via the hashed `ParticipantSpec.env` field,
  precisely so config_hash stays still — and stays on for every coupled run from now on;
  its cost is a rlimit call. **`MALLOC_CHECK_=3` is enabled on LADDER RUNGS ONLY and is
  OFF for Q1, N3, the fine-rung I7 probe and the campaign.** Reason, recorded rather than
  assumed: it selects glibc's checking allocator for both participants and its cost is
  unmeasured, and N3's post-ramp ClockTime is the only number ADR-040 permits to size B2,
  against a 96 h ceiling with ~23 % headroom. Enabling it there would put an unmeasured
  perturbation inside the sizing measurement. If a later death makes it wanted on a
  timing run, that is an ADR, not a flag. **Which observability was active is recorded in
  every submission record** (a hash-exempt `observability` block written at submit time),
  so the policy is a fact about the run rather than a discipline a later reader must
  trust.
- **V6 — Q1 re-run on the adopted stack.** Before the N3 resubmission: 500 coupled
  windows, both arms concurrently at 4+4 ranks, on the ADOPTED stack, against the same
  surviving ADR-039-numerics baselines `hg2007_flexible_foil-20260810-144742` /
  `hg2007_rigid_foil-20260810-144747`, ADR-040 Q1's three bands VERBATIM (2 % span-mean;
  5 % of baseline peak-to-peak in max absolute deviation; 5 % on the flexible-minus-rigid
  span-mean difference). The re-run record lands at the NEW path
  **`data/vv/stage20_q1_equivalence_adr041.json`** — the accepted unmitigated record is
  never overwritten (its pin test `test_stage20_q1_equivalence_record.py` stays green
  untouched). It also re-establishes **all six** of ADR-040 L6's checks in the mitigated
  shape: both arms at 4+4; `processor*` count correct on both arms; mpirun inside the uid
  drop in the staged supervisor; both participants exit 0; coupling converged;
  `force.dat` in the case root.
  **On rejection, ADR-040 W4's outcome applies unchanged — the stack is INADMISSIBLE, no
  band widens, no comparison is re-chosen — with one thing W4 could not have anticipated
  stated here.** On a D-B or D-C stack the re-run differs from the ADR-039 baseline in
  *two* variables, so a rejection does not localize (ADR-040 Q2 already says this of the
  one-variable case). The pre-registered response: the operator is brought W4's declared
  alternatives **with the adopted mitigation attached** — the campaign confirmation on
  ADR-039's numerics *carrying that mitigation*, with Q1 re-measured on that pair, or a
  budget NO-GO. **Dropping the mitigation is not among the alternatives**: the ladder's
  verdict stands, and a stack that diverges is not made admissible by a Q1 rejection
  elsewhere.
- **V7 — the gated verdict.** ADR-040 L5's five-input derivation stays, and this ADR adds
  **one conjunctive fence to it, stated plainly rather than described as free**
  (header item 4): a spec is
  gated only if the five inputs match AND its `template_sha256` equals the
  **template-of-record**. The fence is in the spec factory, where `gated` is derived — not
  only at the submission boundary — because `--probe` submits with `gated_intent=False`
  and would otherwise mint a bundle claiming `gated=True` once B2's sentinels are filled.
  It can only ever REFUSE: it cannot make a non-gated configuration gated, and the five
  inputs remain necessary. While the ladder runs the template-of-record is the
  parallel-implicit template, so no serial spec can claim the gated verdict; a D-B
  adoption commit — and only it — moves the template-of-record, after which the adopted
  stack derives gating exactly as any other spec. `--submit-040` additionally refuses a
  spec whose template is not the template-of-record, so a mis-set default is caught before
  a submission, not after. Untouched: ADR-039's gate-block bytes and every test pinning
  them; `<<B2-PENDING-I4>>` (permanently unfilled); ADR-040's N1 stack, L3 rank count,
  sizing-rate definition, Q1 bands, W contingencies and U10. The N3 resubmission runs
  under ADR-040's existing mechanics: an ordinary B0 probe, both arms contended at 4+4,
  the §6.46-item-3 stop rule armed (one arm dies pre-ramp, before window 50 726 ⇒ kill the
  partner, record both). A flexible-arm death on the ADOPTED stack in the resubmission is
  the NO-GO-on-infrastructure conversation, not a quiet third attempt.

## Why this pre-registration can still fail

- **A clean rung is evidence, not proof.** Determinism is divergent and the instability
  is timing-sensitive. The span covers 5.1x the onset horizon and 25.9x the onset
  amplitude, and both prongs are bounded by measured healthy behavior (1.63x and 1.71x
  margins) — but the detector stays armed through the campaign because that is the
  residual risk, not a solved one.
- **The healthy parity bound is load-dependent and thinly sampled.** The flexible
  healthy ratio climbs monotonically (1.36 → 1.81 over w1401-1540) right up to the
  boundary chosen for it, and the only full-amplitude bound (2.45) comes from the RIGID
  arm, which barely deforms and whose chunks are active for just 4.8 % of its run. A
  4.0 threshold is comfortably above every healthy observation that exists; there is no
  healthy *flexible* observation anywhere near full amplitude, and no way to obtain one
  short of the campaign. This is the detector's weakest joint and it is recorded as such.
- **D-B may be bigger than a scheme swap.** The forced acceleration change is already
  known; the parse-first rule exists because more may be forced, and if it is, D-B is
  blocked pending its own ADR rather than quietly reordered.
- **D-B can eliminate the signature and still be unaffordable.** The rung measures the
  serial cost; if it breaks N3's projection or the campaign ceiling that is an open
  budget conversation under ADR-040's B family.
- **Q1 can reject on the adopted stack**, and V6 says what happens — including that the
  rejection will not localize.
- **All rungs can fail V2.** Then the recorded NO-GO is the result. The campaign does not
  run on a stack known to diverge.

## Consequences

**Positive.** The mitigation is chosen by a pre-stated rule against a pre-stated detector
whose thresholds are bounded by measured healthy behavior on three datasets including a
complete 76 090-window run; every future coupled run gains an online detector that would
have reported this instability 43 windows before it killed a two-day solve; a recurrence
under D-A leaves a core and an allocator abort at the corruption site instead of a
mystery.

**Negative / honest limits.** A clean D-A adopts an unmitigated campaign stack on
probabilistic evidence; `MALLOC_CHECK_`, the serial ordering and the uncontended probe
shape each perturb the timing the bug depends on, so cross-rung comparisons are of
signatures, never of abort timings; the detector's full-amplitude healthy bound comes
from the rigid arm only; the ladder can spend up to 35 h of B0 before an N3 that may
run to its 96 h ceiling, leaving ~2 h of margin in that worst case (~16 h on N3's ~82 h
projection); and three of §6.49's summary sentences
(the ~w1650 counterfactual, the even-window "monotonic decrease", and — from this ADR's
own earlier draft — a "±3 %" even-window band) did not survive re-derivation and are
corrected in the evidence section, with a matching correction note in the handoff.

**Neutral / followup.** Everything downstream of a landed contended N3 is unchanged from
the SESSION-12/13 paths: collect both arms → the fine-rung I7 probe → the B3 ceiling
decision BEFORE B2 → `--size-040` → B1/B2/B3 + the four `GATED_040_*` filled in the
add-commit that ADDS `data/vv/stage20_n3_confirmation.json` with
`tests/unit/test_adr040_budget_is_derived_from_n3.py` → wave 1 via `--submit-040`.

## Links

- Handoff §6.46-§6.49 (`docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md`)
  — the death record, the corrections, and the mining verdict of record (plus this ADR's
  three corrections to §6.49, noted there).
- `/mnt/aero-nfs/runs/stage20-n3-attempt1-mining/` — tables and exact parsers
  (`README.md`, `minerB_parse.awk`, `minerB_flexible.tsv`, `minerB_q1.tsv`,
  `minerB_blocks.tsv`, `minerB_rigid_window_table.txt`, `precursor_test.awk`,
  `minerF_determinism.txt`).
- preCICE documentation, acceleration configuration — the serial-coupling primary-data
  constraint quoted in D-B.
- ADR-037 (config_hash over the serialized spec), ADR-038 (container roster / SIF
  digests), ADR-039 (gate pre-registration, frozen; C1), ADR-040 (numerics, U1/U2/U3,
  U10, U11, N4, N5, L5, L6, Q1 bands, W4/W6, BUDGET).
- `aero/adapters/precice/{launcher,template,logs}.py`, `aero/vv/fsi/hg2007_flexible_foil.py`,
  `scripts/stage20_hg2007_flexible_foil.py`,
  `tests/unit/test_n3_live_submission_digest_is_pinned.py`,
  `tests/unit/test_stage20_q1_equivalence_record.py`.
