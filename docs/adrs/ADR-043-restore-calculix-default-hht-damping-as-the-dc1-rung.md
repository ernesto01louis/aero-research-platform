# ADR-043 — D-C form 1, pinned: restore CalculiX's own HHT damping default: family Y

- **Status:** accepted — the operator authorised this rung and its pinned value on
  2026-09-10, and this commit is that acceptance (the ADR-041 `2bbfdd4` / ADR-042
  `6ec293a` pattern). The α value below was fixed BEFORE the probe was submitted.
- **Date:** 2026-09-10
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 20)
- **Stage:** 20
- **Amends:** ADR-041's D-C form 1, by pinning what it changes and to what value (Y1),
  and by declaring one consequence ADR-041 and ADR-042 both promised would not occur —
  **a gated band's RATIONALE moves if this rung is ADOPTED** (Y3). Everything else in
  ADR-041 and ADR-042 is carried verbatim: V1's vocabulary and adoption rule, V2's
  detector and bounds, V3's span and 35 h cap, V4-V7, and ADR-042 X1/X2.

## Why this rung, and why it is no longer the leftover one

Three rungs have run. The divergence appears in **3 of 3 parallel runs that lived long
enough** — attempt 1 (onset ~w1557), D-A (detector fired w1460), D-C2 (fired w1820) — and
it survived a coupling-scheme change (D-B) and an adapter change (D-C2). A failure robust
to the coupling software and to the adapter version is a property of the CASE, and the
deck names the mechanism:

```
*DYNAMIC, ALPHA=0.0, DIRECT
```

At α = 0 the HHT-α integrator degenerates to Newmark average-acceleration: unconditionally
stable and **exactly zero dissipation at every frequency, including Nyquist**. The Nyquist
mode of a window-stepped solve is a **period-2, window-alternating oscillation** — which is
the signature ADR-041's detector was written to catch, and which has now been observed
three times. An undamped Nyquist mode is not a defect in anyone's code; it is what this
integrator does with this parameter.

Two independent corroborations, both from the runs rather than from theory:

- **The diverging parity is not fixed.** attempt 1 and D-A diverged on the ODD branch;
  D-C2 diverged on the **EVEN** branch (odd 2.370 N against even 11.080 N at w1801-1820).
  Parity is only a label for which sub-step the mode happened to start on. A Nyquist
  oscillation does that; a systematic odd-window code path does not.
- **D-C2 diverged later and more gently at far lower residuals and still crashed** — the
  adapter bump moved the timing and left the mechanism untouched.

## Y1 — what changes, pinned before the probe

**`ALPHA = 0.0` → `ALPHA = -0.05` on the solid deck's `*DYNAMIC` card, and nothing else.**

The value is not chosen by taste: **-0.05 is CalculiX's own default**, read from the
pinned source this container is built from —
`CalculiX/ccx_2.20/src/dynamics.f:73`, `alpha(1)=-0.05d0`, with the same file clamping the
admissible range to `[-1/3, 0]` (lines 106-113). ADR-039 C2's `ALPHA=0.0` was therefore a
deliberate override of upstream's default to **the single value in the permitted range
with exactly zero high-frequency dissipation**. This rung reverts that override; it does
not invent a damping level.

What that buys, computed at this case's `dt = 2e-5 s`, where the algorithmic damping ratio
for small `ωΔt` is `ξ ≈ (γ - ½)·ωΔt/2 = 0.025·ωΔt` at α = -0.05:

| mode | ωΔt [rad] | ξ_num | energy lost per cycle |
|---|---|---|---|
| flapping, 0.986 Hz | 1.24e-4 | 3.1e-6 | **3.9e-5** |
| a 50 Hz structural mode | 6.3e-3 | 1.6e-4 | 2.0e-3 |
| a 500 Hz mode | 6.3e-2 | 1.6e-3 | 2.0e-2 |
| **Nyquist, 25 kHz** | π | 7.9e-2 | **~0.99** |

The physical flapping mode loses 0.004 % of its energy per cycle; the Nyquist mode is
essentially annihilated. Against the observed growth — the odd branch doubling every ~26
windows, a per-window factor of 1.027 — a per-step Nyquist decay of this order turns
growth into decay with a very wide margin. That is the whole hypothesis, and V2's detector
is what will decide it.

## Y2 — the probe changes nothing gated, and that is what makes it runnable now

An ADR-041 rung probe carries `gated=False`, sizes nothing, and evaluates **no D band**.
D10 is a band of the gated campaign, read off a campaign run that has never happened. So
this probe touches no fidelity band, no sentinel and no verdict: it renders a deck with a
different `*DYNAMIC` card, runs 8000 windows, and is judged by V2 exactly as D-A and D-C2
were. Nothing in Y3 below applies to it.

**Record consequences of the probe itself**, which do land now: the solid spec gains an
`hht_alpha` field, and because `config_hash` is a digest of the serialized spec, **every
spec's digest moves**. For any spec at the default α = 0.0 the DECK BYTES ARE IDENTICAL,
so that is a *record* move rather than a *case* move — the distinction ADR-040 drew for
the serialised `mpi_ranks` null. Consequently, and as ADR-041 declared for this rung,
**both uncollected N3 attempt-1 records become permanently unreattachable**, the completed
76 090-window rigid arm included. That cost is accepted with its mitigation stated: those
runs' bytes are on NFS and readable directly, the rigid arm's per-window residual table is
already mined and preserved at `stage20-n3-attempt1-mining/`, and nothing downstream reads
them through `_reattach`. The live digest pins are re-pinned in the same commit.

## Y3 — what ADOPTION would move, declared now and decided later

If this rung is ELIMINATED under V1 and becomes the campaign configuration, two ADR-039
clauses move, and the second is the one ADR-041 and ADR-042 both promised would not:

1. **C2's expectation**, `ALPHA present and 0.0` → `ALPHA present and -0.05`. Same weight
   and same mechanism as ADR-041's C1 move: ADR-039's gate-block bytes stay byte-identical
   and digest-pinned; what moves is the expectation the campaign is evaluated against.
2. **D10's RATIONALE — a GATED band.** D10 reads: *"the interface-power closure |P3-P2|/P2
   within 2 % — a genuine identity: with ALPHA 0 and no damping the cycle-mean reaction
   power over the prescribed region equals the interface power exactly, and holding also
   proves ALPHA=0 held."* With α = -0.05 the identity is **no longer exact by
   construction**: algorithmic dissipation is a power sink. **The 2 % BAND DOES NOT MOVE
   and D10 stays gated** — what changes is the claim underneath it, from an exact identity
   to one holding within the dissipation of the modes that carry the energy: 3.9e-5 per
   cycle at the flapping frequency, 500x inside the band; ~2e-3 for a 50 Hz mode; and
   reaching the band only for content near 500 Hz, which this ADR does NOT claim to have
   bounded. **That residual uncertainty is the honest cost of this rung** and it is stated
   here rather than discovered when D10 is read.
   D10's SECONDARY role — *"holding also proves ALPHA=0 held"* — is voided, and is
   replaced by something stronger and direct: the deck self-check already parses
   `dynamic_alpha` out of the written deck and asserts it against the spec, so the value
   is verified from the bytes that ran instead of inferred from a power balance.

**Neither of these is decided by this ADR.** They are declared so that an adoption commit
is a recorded step rather than a discovery, exactly as ADR-041 handled D-B's C1 move. If
the rung fails V2, none of it happens.

## Y4 — this is the LAST pre-registered rung

D-A: RECURRENCE-DETECTED. D-B: DIED-UNDIAGNOSED (ADR-042 X2 permits one re-probe; declined
on the record, serial being a poor campaign candidate on both cost and conditioning).
D-C2: RECURRENCE-DETECTED. **If D-C1 fails V2, ADR-041 V1's ladder is exhausted and the
result is a recorded NO-GO on infrastructure**, which is a legitimate outcome and not a
failure of process. Ladder spend stands at 3.89 h of V3's 35 h cap.

## Consequences

**Positive.** The rung tests a mechanism rather than a suspicion: a named parameter, a
documented default that was deliberately overridden, a mode structure that matches the
observed signature including its parity flip, and a quantified margin between the
dissipation the physical modes see and the dissipation the Nyquist mode sees.

**Negative / honest limits.** It costs the reattachability of both attempt-1 records, now,
for a rung that may still fail. If it succeeds, D10's identity weakens from exact to
bounded, with the bound unquantified for content near 500 Hz. And a rung that eliminates
the divergence still says nothing directly about the heap corruption: the crash would have
to stop as a consequence of the numerics staying sane, which is the reading §6.58 favours
but has not proven.

## Links

- Handoff §6.52 (D-A), §6.55 (D-B and its softened Fact 1), §6.58 (D-C2 and the ALPHA
  hypothesis). Rung evidence under each run's `adr041-*-verdict.json` on NFS.
- `CalculiX/ccx_2.20/src/dynamics.f:73` (`alpha(1)=-0.05d0`) and :106-113 (the clamp) in
  the source tarball this container pins, sha256 `63bf6ea0…`.
- ADR-039 C2 and D10; ADR-040 (numerics, budget, L5); ADR-041 (the ladder, V1-V7);
  ADR-042 (X1 re-order, X1a the adapter bump, X2 the early-death re-probe).
