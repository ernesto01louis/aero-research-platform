# ADR-045 — Checkpoint/restart for the coupled flexible arm: family R

- **Status:** proposed. **Nothing in this ADR is implemented, nothing is submitted, and no
  B0 hour is spent until the operator accepts this text.** R6 makes adoption conditional on
  the sanitizer hunt that is running as this is written, precisely so that the expensive
  parts are not built if the crash turns out to be fixable.
- **Date:** 2026-09-15
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 20)
- **Stage:** 20
- **Amends:** ADR-036's no-restart rule, by adding a SECOND and narrower deviation beside
  ADR-040 N3's "resubmit once, from scratch". It moves no band, no floor, no grid, no span
  and no ceiling. ADR-039 and ADR-040's FORBIDDEN lists carry over intact; ADR-041 V7's
  NO-GO remains the recorded outcome unless R3 passes.

## The problem, stated as the arithmetic that produced it

N3 attempt 2 died at window 21 897 of 76 090 with the solid quiet for its last 7 698
windows: the adopted α = -0.05 damping eliminated the period-2 divergence, and the heap
corruption killed the run anyway. On the adopted stack the flexible arm has now run
**37 897 windows for one death**. A wave is **1 166 675 windows**. That is **~31 expected
deaths per wave, and ~17 even at B4's 10-cycle floor** (handoff §6.71).

Every lever tried so far changes the *numerics* and none of them changes that arithmetic,
because the arithmetic is mean time to crash. Exactly two things do: removing the bug
(the sanitizer hunt, §6.72) or surviving it (this ADR). **Checkpoint/restart fixes
nothing.** It converts 31 fatal deaths into 31 restart discontinuities inside the analysis
window, and the entire question this ADR has to answer honestly is whether a discontinuity
is cheaper than a death **in V&V terms**, not in wall-clock terms.

## What already exists — measured on disk, not assumed

**F1 — the fluid already checkpoints, and nobody planned it.** The generated
`system/controlDict` carries `writeControl timeStep; writeInterval 2000; purgeWrite 2`. In
the completed control run `hg2007_flexible_foil-20260912-161321`, `processor0/0.12` and
`processor0/0.16` each hold a full restartable dump — `U p phi Uf cellDisplacement
pointDisplacement meshPhi polyMesh uniform/time` — including the **deformed** `polyMesh`,
which is what a moving-mesh restart actually needs. Cadence 2000 windows, two generations
retained. Half the mechanism is already in the case.

**F2 — the fluid's restart is state-exact, and only because of one line.** `fvSchemes` says
`ddtSchemes { default Euler; }`. Euler needs ONE old time level, so a restart from a written
time directory loses nothing. Under `backward` it would need two, the second is not written,
and the first restarted step would silently drop to first order. **This is a property of the
current scheme, not of OpenFOAM** — if the numerics are ever re-opened, this fact expires
with them.

**F3 — but the write is lossy.** `writeFormat ascii; writePrecision 12`. Twelve significant
digits is not a double; the restart is perturbed at ~1e-12 relative. The fix is one word
(`binary`, or `writePrecision 17`) and it belongs in the same commit as anything else here.

**F4 — the solid checkpoints nothing to disk.** `nonlingeo_precice.c` at v2.20.2 contains
the string `restart` **zero** times. The adapter's `Precice_WriteIterationCheckpoint`
(called at `nonlingeo_precice.c:1685`, read back at `:3764`) is in-memory only and saves
just `(theta, dtheta, v)`; the mechanical history is restored by CalculiX's own
`vini/veini/accini` copies through the existing cutback path, which the adapter drives by
incrementing `icutb`. The consequence that matters: **the complete window-start state is
already assembled in named arrays at exactly the point where a disk checkpoint would be
written.** We are serializing a snapshot the adapter already takes, not inventing one.

**F5 — CalculiX's own restart is the wrong tool, twice.** `restartwrite` is called only at
the END of a step (`ccx_2.20.c:1795-1797`, guarded by `jrstrt` — a counter of *steps*), and
this case is ONE `*STEP ... INC=400000`, so native restart would write once, at the end we
never reach. And it saves less than we need: `accold` occurs **zero** times in both
`restartwrite.f` and `restartread.f` (it is allocated fresh at `ccx_2.20.c:1041` and freed
at step end), as does the HHT α force history.

## R1 — the mechanism: a purpose-built state dump, not CalculiX's restart

The write point is `nonlingeo_precice.c:1685`, inside `if (icutb == 0)`, where the state is
the converged end of the previous coupling window. The read point is the equivalent
position at step start, before the first `Precice_AdjustSolverTimestep`.

| Carried | Size | Why |
|---|---|---|
| `vold` | `mt*nk` | displacements — the thing everyone remembers |
| `veold` | `mt*nk` | velocities — second-order system |
| `accold` | `mt*nk` | accelerations — **native restart does not carry this** |
| `fini`, `fextini`, `cvini`, `fnextini` | `neq[1]` ×3 + `mt*nk` | HHT α weights t_n's forces; without these the first restarted increment is a different equation |
| `sti`, `eme` | `6*mi[0]*ne` ×2 | stress/strain history |
| `ener`, `enerini` | `mi[0]*ne` ×2 | only if `nener` |
| `xstate` | `nstate_*mi[0]*ne` | empty for this linear-elastic deck; carried anyway, because "empty today" is how silent breakage starts |
| `ttime`, `theta`, `dtheta`, `iinc`, `qaold` | scalars | time and the convergence-norm history |

**Why not plumb `restartwrite`.** About fifteen of its arguments are simply not in
`nonlingeo_precice`'s scope — `nalset`, `namtot`, `ne1d`, `ne2d`, `nlabel`, `iplas`,
`ncs_`, `nodebounold`, `ndirbounold`, `iponor`, `xnor`, `knor`, `offset`, `iponoel`,
`inoel`, `rig`, `infree`. Reaching them means widening the CalculiX call chain, which is a
patch against code we do not maintain, to obtain a checkpoint that carries **less** state
than the table above. The model itself does not need serializing: it is re-read from the
deck in seconds (10 380 equations).

**The amplitude trap, which would otherwise be a silent catastrophe.** `plunge.amp` opens
`*AMPLITUDE, NAME=PLUNGE` with no `TIME=` parameter, and CalculiX's default is STEP time. A
restart that begins a new `*STEP` at step-time 0 would **replay the plunge from the
beginning** while the solid carried the displacement field of window 40 000 — and it would
not error, it would produce numbers. The fix is `*AMPLITUDE, TIME=TOTAL TIME` (parsed at
`amplitudes.f:72`) plus the restored `ttime`. That moves deck bytes and therefore
`config_hash`, so it lands with a same-commit re-pin; but it **cannot** move any number in a
non-restarted run, because with a single step starting at `ttime = 0`, step time and total
time are the same quantity. That is a testable claim and R3 is where it gets tested, not
asserted.

**And `precice-run/` must be removed before the relaunch**, or the new participants attach
to a dead rendezvous.

## R2 — cadence and retention

The solid checkpoints every **2000 windows**, matching the fluid's existing cadence exactly,
and keeps **two** generations, matching `purgeWrite 2`. A restart resumes from the newest
window index present in BOTH participants; a checkpoint with no partner is not a checkpoint.

Worst-case rework is one full interval: 2000 windows ≈ **1.9 h** at N3's measured contended
3.50 s/window. At ~31 deaths that is **≈60 h of rework per wave**. That number belongs in
the B-band sizing as a line item. It is not overhead to be waved away, and a wave that
cannot absorb it is not rescued by this ADR.

## R3 — the restart-transparency experiment, pre-registered before it is run

**Control — already bought and already completed.** `hg2007_flexible_foil-20260912-161321`:
flexible, mid rung, α = -0.05, parallel-implicit, dt 2e-5, 4 ranks, uncontended,
**8000/8000 windows**, 8001-line trailing-edge watchpoint intact on NFS. No new control is
purchased.

**Treatment.** The identical submission with one deliberate checkpoint-restart at window
4000.

**Acceptance — all four required, any one failing ⇒ restart is not transparent:**

- **(a)** cycle-averaged lift, thrust and interface power over windows 4001-8000 lie within
  the **frozen Q1 bands (2 % / 5 % / 5 %)** of the control's same windows. The bands are
  reused verbatim and are not widened for this purpose.
- **(b)** the trailing-edge watchpoint difference **decays**: `max|Δ|` over windows
  4001-4200 strictly exceeds `max|Δ|` over 7801-8000. A restart may inject a transient; it
  may not inject a shift.
- **(c)** the ADR-041 divergence detector returns ELIMINATED on the treatment, on the same
  grid and the same bounds.
- **(d)** coupling iterations per window return to within ±1 of the control's mean inside 30
  windows of the restart. This is the clause that bounds the IQN-ILS loss in R4.3, and it is
  the one most likely to fail.

**Cost:** one 8000-window uncontended probe, ≈3 h of B0. **It sizes nothing** — the same
fence every ladder probe carries.

## R4 — what a restart loses, so nobody has to rediscover it

1. **`accold`.** Without a carried value CalculiX re-derives it by the initial-acceleration
   procedure (`nonlingeo.c:1397` ff., recognisable by the deliberate sentinel
   `dtime = 1.235711130e-20`). That is *consistent*, not *identical*: it re-solves
   `M a = f_ext - f_int` at the restart state, so the difference is the previous increment's
   equilibrium residual. R1 carries it and the question does not arise.
2. **HHT α force history.** Same: carried by R1, and one perturbed increment if it is not.
3. **IQN-ILS history — NOT recoverable, at any price.** preCICE 3.4.1 has no
   simulation-level restart, and the config reuses 15 time windows of quasi-Newton
   information. After a restart the first ~15 windows converge without it. Coupling converges
   to a tolerance and not to machine zero, so this perturbs the converged state at the
   tolerance level and costs extra iterations. **This is the loss the checkpoint cannot fix**,
   and R3(d) is the only thing standing between it and the campaign.
4. **Fluid ASCII truncation** (F3). Removed by one word.

## R5 — the hazard nobody would think of until it had already happened

The checkpoints that matter are the ones written **shortly before a heap-corruption death**.
Corrupted allocator metadata does not politely confine itself to allocator metadata; an
invalid write large enough to poison a chunk header can equally have landed in `vold`. A
restart from such a checkpoint resumes from garbage **and does not fail** — it produces
numbers, in a campaign whose entire product is trustworthy numbers.

Pre-registered guard, **validate on read**: every value finite; `|displacement|` bounded by a
fixed multiple of the prescribed plunge amplitude; kinetic + internal energy inside the
control run's observed band; the solid's window index matching the fluid's. A failed
validation steps back one generation; a second failure **refuses the restart and records the
run as a death**. Standing rule on top: after a crash, **prefer generation N-1** — written
2000 windows before the death — over the newest one.

## R6 — the adoption rule, conditional on the sanitizer hunt

This clause exists so that ~300 lines of C against a solver we do not maintain are not
written for nothing.

- **If the ASan hunt names a line we compile** (the adapter's own C — upstream fixed a
  *different* invalid free in that file three weeks ago) **and a patch removes the crash:**
  the bug is FIXED. R1-R3 become optional insurance and may be deferred with no prejudice
  and no further B0 spend.
- **If it names CalculiX Fortran we do not maintain, or returns no report at all:** the
  crash is survivable-only, and R1-R3 are the path — **but only if R3 passes.**
- **If R3 fails:** the recorded outcome is ADR-041 V7's **NO-GO on infrastructure**,
  unchanged and unrescued. A campaign whose restarts are not transparent is not made valid
  by being made completable.

## R7 — provenance and gating

A restarted solve is not one continuous integration and must never silently claim to be.

- The submission/collection record gains `restart_generations: int` and the restart window
  indices; the exported bundle carries them (RESULTS-MUST-TRAVEL).
- `is_campaign_configuration` is **not** extended. A restart is not a configuration change:
  the deck, the container, the numerics and the coupling are identical, and adding a fourth
  conjunct would wrongly imply otherwise.
- The gate derivation gains one condition instead: a gated wave-1 solve may carry restarts
  **only** if R3 passed and the count is recorded. `restart_generations > 0` with no passing
  R3 on record derives `gated=False` unconditionally, by the same L5 mechanism that already
  refuses a non-default coupling scheme.
- Everything ADR-039 and ADR-040 forbid stays forbidden. This ADR buys completion, not
  latitude.

## Consequences

**Positive.** The only lever that changes mean-time-to-crash arithmetic without touching the
science, built on a snapshot the adapter already takes, at a write point that already exists,
against a fluid side that is already checkpointing every 2000 windows with the deformed mesh.
The state we would carry is strictly richer than CalculiX's own restart. And R6 means the
work is not started until the cheaper answer has had its chance.

**Negative / honest limits.** This is real engineering effort — a C patch to the adapter, a
deck change that moves `config_hash`, a container rebuild, driver-side relaunch and
bookkeeping, and tests for all of it — spent on **surviving a bug we do not understand**
rather than fixing it. R5 is not a theoretical concern: restarting from a checkpoint written
by a process with known-poisoned heap metadata is the single most dangerous thing proposed in
this stage, and the validation guard bounds it without eliminating it. R4.3 is unfixable at
any effort. And the deepest limit is the one R6 states plainly: **if R3 fails, nothing here
helps**, and the NO-GO stands exactly where ADR-041 V7 put it.

## Links

- Handoff §6.71 (the death arithmetic), §6.72 (the sanitizer hunt); RESUME §6w.
- `runs/hg2007_flexible_foil-20260912-161321/` — the R3 control, completed 8000/8000.
- `nonlingeo_precice.c` v2.20.2 `:1684-1685` (checkpoint write), `:3762-3764` (read).
- CalculiX 2.20 `ccx_2.20.c:1041` (`accold` allocation), `:1795-1797` (`jrstrt`),
  `nonlingeo.c:1397` (initial-acceleration procedure), `restartwrite.f` / `restartread.f`
  (zero occurrences of `accold`), `amplitudes.f:72` (`TIME=TOTALTIME`).
- ADR-036 (no-restart), ADR-039/040 (the frozen bands and FORBIDDEN lists), ADR-041 V7
  (the NO-GO this ADR is trying to avoid and may not).
