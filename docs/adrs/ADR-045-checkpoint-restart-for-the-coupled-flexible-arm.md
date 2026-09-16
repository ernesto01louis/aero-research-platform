# ADR-045 — Checkpoint/restart for the coupled flexible arm: family R

- **Status:** accepted — **as amended by A1–A10 below.** The sanitizer hunt landed on
  2026-09-15 with no report (handoff §6.76: `no-report-died`, CalculiX's own divergence
  stop, NOT exoneration), so R6's second bullet is the operative clause and no patchable
  line exists. The operator chose option (1) of session 14's memo (handoff §6.77) on
  2026-09-15 — *"id go with your rexommendation"* — and this commit is that acceptance
  (the ADR-044 `d702b57` pattern). **Acceptance implements nothing and spends nothing:**
  R1–R7 land as suite-green commits in clause order, the R3 scorer exists and passes the
  control against itself BEFORE the treatment is submitted, and the first B0 hour is that
  ~3 h treatment, behind the B0 stop gate. R3 fails ⇒ ADR-041 V7's NO-GO, unrescued.
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
`amplitudes.f:72`) plus the restored `ttime`. That moves deck bytes; the RECORD moves
through the `RENDERER_VERSION` bump (amendment A1 — a deck byte alone moves no digest), so
it lands with a same-commit re-pin; but it **cannot** move any number in a
non-restarted run, because with a single step starting at `ttime = 0`, step time and total
time are the same quantity. That is a testable claim and R3 is where it gets tested, not
asserted.

**And `precice-run/` must be removed before the relaunch**, or the new participants attach
to a dead rendezvous — the supervisor already does this on every launch (amendment A3).

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
- **(d)** the IQN-ILS history refills. `precice-Solid-iterations.log` carries a `QNColumns`
  column, which **is** the quasi-Newton history depth, so this clause measures the quantity
  itself rather than a proxy: `QNColumns` returns to the control's windows-4001-8000 mean,
  and `Iterations` to within ±1 of the control's mean, both inside **30 windows** of the
  restart. This is the clause that bounds the unrecoverable loss in R4.3, and it is the one
  most likely to fail.

**Every clause was checked against the control run before this ADR was written** — the
ADR-041 round-1 lesson was a pre-registered clause that could not be evaluated. (a) fluid
`postProcessing/forces1/0/force.dat` + `forceCoeffs1/0/coefficient.dat`, and the
`aeroInterfacePower <t> <power> <fx> <fy>` lines the coded function object writes into
`Fluid.log`; (b) `precice-Solid-watchpoint-Trailing-Edge.log`, 8001 lines; (c)
`adr041-D-C1-solid-residuals.tsv` beside the run, produced by the detector already in code;
(d) `precice-Solid-iterations.log`, 8000 rows carrying `Iterations` and `QNColumns`. Nothing
in R3 needs an artefact that does not exist.

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
control run's band **at the same window index** (amendment A5 — the global band spans 3.7
decades and would pass anything); the solid's window index matching the fluid's. A failed
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
  R3 on record refuses the gated verdict unconditionally — at the boundary where the
  submission record is read back (amendment A4: the spec-side `gated` cannot see a value
  that must stay out of the spec), with the same one-way force as the L5 fence.
- Everything ADR-039 and ADR-040 forbid stays forbidden. This ADR buys completion, not
  latitude.

## Amendments at acceptance (A1–A10) — measured in session 14, handoff §6.75; A11–A17 added as built (sessions 14–15)

Every item below was read off disk or source before acceptance, so the corrections are
part of the text being accepted rather than discoveries made while implementing it. **None
moves a band, a floor, a grid, a span or a ceiling.** Clause numbers refer to the sections
above.

| # | clause | as proposed | as accepted |
|---|---|---|---|
| A1 | R1, F3 | the `TIME=TOTAL TIME` deck edit "moves deck bytes and therefore `config_hash`" | `config_hash` digests the serialized SPEC only (`aero/adapters/precice/case.py:586-606`); a deck byte moves nothing. The record moves by bumping `RENDERER_VERSION` (`aero/adapters/precice/template.py`, "bumped whenever a rendered byte changes") in the same commit as the deck edit and F3's `writePrecision`, with the same-commit re-pin of every live digest |
| A2 | Links | `ccx_2.20.c:1041` / `:1795-1797` | those are CalculiX's pristine file; the file compiled into `ccx_preCICE` is the adapter's copy `/src/calculix-adapter/ccx_2.20.c` (`:1121` / `:2146-2149`). Ownership of a line is decided by its PATH, never its basename |
| A3 | R1 | "`precice-run/` must be removed before the relaunch" | already done by the supervisor on every launch (`launcher.py:306`); no new work |
| A4 | R7 | `restart_generations > 0` without a passing R3 "derives `gated=False` … by the same L5 mechanism" | `gated` is derived inside `hg2007_case_spec` from spec fields only, and `restart_generations` must stay OUT of `spec_knobs` (they are passed verbatim to the factory by `_reattach`; a new key is a TypeError and moves the digest). The refusal therefore sits where the record is read back — `_reattach` / `--collect-probe` / `--verdict` — reading the record's top-level `restart_generations` and the R3 record at `data/vv/stage20_adr045_r3.json`; one-way, like the L5 fence |
| A5 | R5 | "kinetic + internal energy inside the control run's observed band" | `nener=1` unconditionally for implicit `*DYNAMIC` and `Solid.log` prints the energies every converged window — but over the control run the sum spans 3.7 decades (1.6e-11 → 7.7e-8 J), so a global band is vacuous. The guard compares against the control run's value **at the same window index**, within a factor of 10 either way, plus finiteness, the displacement bound and the window-index match |
| A6 | (silent) | no restart precedent in the repo | `scripts/stage16_urans_cert.py` is one: `patch_controldict_for_restart` (`startFrom latestTime`), `read_concat_series` across segments, `restart_continuation: True` in provenance. Reused where it fits |
| A7 | (silent) | the clocks of a restart segment | three clocks, not one: the fluid's `startTime`/`endTime` are ABSOLUTE (start at the checkpoint time, keep `endTime` = full `max_time`); preCICE has no restart and starts at 0, so the rendered `<max-time>` is the REMAINING time; CalculiX's `*DYNAMIC` second field is a STEP PERIOD, so it is the remaining time too, with `INC` covering the remainder. Only `max_time` is a spec field and it tracks the fluid, so the digest does not move on the clock's account |
| A8 | (silent) | relaunch mechanics | `_prepare_and_submit` allocates a FRESH run_id and `decomposePar -force` deletes every `processor*/` — the fluid's checkpoints. A restart relaunches INTO the existing case root through a dedicated driver path that skips prepare/mesh/decompose, rotates `Fluid.log`, `Solid.log`, `coupled-status.json` and every `precice-*.log` to a `.seg<n>` name first (the supervisor truncates the logs; `WatchpointTrace` refuses a non-monotonic Time column), and records the generation in the submission record's top level |
| A9 | R3(b)/(d) | the readers exist | `read_iterations_log` keeps the QN column NAMES only; no lift series exists on the coupled path; no window-range selector exists. Added additively in the scorer commit; segment-2 rows map onto global windows by the restart offset (preCICE's `TimeWindow` and watchpoint `Time` restart at zero) |
| A10 | R3(a) | "the frozen Q1 bands (2 % / 5 % / 5 %)" on lift, thrust, interface power | Q1 as coded is Q1a 2 % span-mean on fx, Q1b 5 % of peak-to-peak in max deviation, Q1c 5 % on the two-arm increment. Single-arm, Q1c has no meaning. **Fixed in the scorer commit (`a2fb4ce`) from the control's own numbers over windows 4001–8000:** Q1a applies where the control's `|mean| / peak-to-peak ≥ 1` — thrust 1.48 (yes), lift 0.017 and interface power 0.023 (no: a relative band on a near-zero mean is meaningless); Q1b applies to all three. No band is widened |
| A11 | R3(b) | "strictly exceeds" | a treatment identical to the control has no transient and no shift; `max|Δ| = 0` in both windows reads as transparent, because the clause exists to refuse a SHIFT. Δ is the magnitude of the trailing-edge displacement-vector difference |
| A12 | R3, R2 | "the identical submission with one deliberate checkpoint-restart at window 4000" | realised WITHOUT changing the submission: segment 1 is the identical 8000-window submission, stopped deliberately (`run_long.sh kill`, recorded rc=143) once the solid's `aero-checkpoint-w4000.bin` and the fluid's `0.08` dump exist; segment 2 relaunches into the same case root from them. The windows segment 1 ran past 4000 are recomputed by segment 2, which wins them in every reader (`7b30bd9`) |
| A13 | A7, A6 | the stage-16 precedent's `startFrom latestTime` | never here: the force function objects leave a field-less stub time directory at EVERY step, so `latestTime` after a crash selects a stub. The relaunch patches an explicit `startTime <checkpoint time>`; `endTime` is inert under the coupled adapter (it sets `endTime` to GREAT and preCICE alone ends the run) |
| A14 | A7, R1 | "CalculiX's `*DYNAMIC` second field is a STEP PERIOD, so it reduces too, with `INC` covering the remainder" and "the read point is before the first `Precice_AdjustSolverTimestep`" | the solid re-enters the SAME step at `theta = t_r / tper` with `iinc` and `qam` resumed: no reduced period, no new `*STEP`, the deck byte-identical (the `TIME=TOTAL TIME` pin stays as insurance for any future new-step restart). The write point is the END of the `icutb == 0` prologue, reading the LIVE arrays (`vold veold accold f fext cv fnext sti eme ener xstate`): at the ADR's line 1685 the `*ini` copies are one window stale, and `prediction()` later rewrites `veold`/`accold`. The restore point is AFTER the initial-acceleration procedure (which then runs at rest exactly as in the control, so the mass matrix, `energyref` and `emax` are the control's) and BEFORE `Precice_Setup`, which registers the coupling mesh at `co + vold`. `ttime` is 0 for the whole single step; `qaold` is a step-entry constant — the running norms are `qam`; `dtheta` is overwritten by preCICE one call later and is carried inert |
| A15 | R5 | "validate on read: finite; bounded; energy band; window match" | as implemented (`adapter/AeroCheckpoint.c`): magic, format version, array sizes against THIS deck, an FNV-1a checksum over every byte, finiteness of every value, `|displacement| ≤ 3 ×` the largest prescribed plunge up to that window, `E_int + E_kin` within ×10 either way of the reference run's value at the same window, and the window the driver asked for; a refusal prints `*ERROR aero-checkpoint` and exits 202 — the driver steps back a generation or records a death; nothing produces numbers from a rejected file |
| A16 | R3, R1 | "the identical submission" | the control ran the UNPATCHED image (`calculix-precice.sif`, `ac0805d6…`); R1 rebuilds the solid container, so the treatment runs the patched one of record (`calculix-precice-adr045.sif`, `ca1937f7…`, built and signed 2026-09-16). The R3 shape check compares every knob except the container, refuses a treatment on the unpatched image, and writes both names into the record |
| A17 | R3(a), R3(b), R3 cost | "the frozen Q1 bands (2 % / 5 % / 5 %)", "(b) … strictly exceeds", "≈3 h of B0" | **Accepted by the operator 2026-09-16 ("Option 2 as stated in §6.82"), pre-registered BEFORE the treatment, after the calibration below showed the as-written (a)/(b) cannot be passed by any treatment.** A restart is transparent when the restarted run is indistinguishable from another fresh draw of the same submission. The **reference draw** is D-C1, `hg2007_flexible_foil-20260910-084806` (8000/8000, 2026-09-10); the control is its re-probe. **(a)** per quantity (thrust, lift, interface power) over windows 4001–8000: RMS(treatment − control) ≤ **2×** RMS(reference − control), and \|mean(treatment) − mean(control)\| ≤ max(Q1a's 2 % of \|mean(control)\|, 2× \|mean(reference) − mean(control)\|); the as-written Q1a/Q1b numbers are computed and recorded informationally, never gate. **(b)** over windows 7801–8000 RMS\|Δ_TE\|(treatment − control) ≤ 2× RMS\|Δ_TE\|(reference − control); the early-window (4001–4200) transient is recorded, not gated. (c) and (d) verbatim. The factor 2 is a judgment stated in advance — a restart that doubles the natural run-to-run scatter is a shift. **The yardstick, measured (`data/vv/stage20_adr045_r3_calibration.json`, control against itself with D-C1 as the reference):** thrust RMS 7.79e-6 N (span-mean limit 1.99e-6 N), lift 4.11e-4 N (limit 2.59e-5 N), power 1.97e-6 W (limit 1.03e-7 W), late trailing-edge RMS 1.09e-5 m (limit 2.18e-5 m). **(e) the episode rule, decided before the run (the operator's second addition):** the two reference draws differ by a ~1e-5 N floor everywhere plus two localised bursts of 1–2e-3 N (windows 201–400 and ~1376). If (a) fails ONLY through one isolated episode far from the restart — exactly one contiguous span (gaps under 50 windows merged) of windows where the treatment's deviation exceeds 10× the reference RMS for that quantity, at most 400 windows long, starting ≥ 1000 windows after the restart (≥ w5000), not touching windows 7801–8000, and (a) passing with that span excised from both deviations — and (b), (c), (d) pass, the verdict is **`inconclusive-episode`**: neither pass nor fail, because the episode is indistinguishable from the draw noise the reference pair shows and the test cannot attribute it. Exactly one re-probe (the identical treatment, same restart window, same container) is then permitted, at the same cost; its reading is final, and a second `inconclusive-episode` is UNRESOLVED and ADR-041 V7's NO-GO stands. Any other failure of (a) or (b), a second episode, an episode inside the clearance, or one touching the late window is a plain `fail`. **The limit of what a pass says (the operator's first addition):** windows 4001–8000 lie at **1.3–3.3 % of the full plunge amplitude** (0.0175 m), inside the **first sixth** of the 1.0145 s startup ramp (0.16 s = 15.8 %); a pass is evidence that a restart is transparent THERE and is not evidence about restarts in settled full-amplitude cycles. **Cost corrected:** the control ran at 2.60 s/window, so 8000 windows is ≈ 5.8 h, not ≈ 3 h; the treatment (segment 1 to the w4000 checkpoint, then 4000 restarted windows) is ≈ 5.9 h of B0, and a re-probe the same again. The restart window stays 4000 (option 3, w400, was refuted by its own calibration: 96 % / 153 % of peak-to-peak — handoff §6.82). Scorer `aero/vv/fsi/hg2007_r3.py`, driver `--score-r3 CONTROL TREATMENT --r3-reference D-C1`, verdict vocabulary `pass` / `fail` / `inconclusive-episode`; every number above is re-derived by the scorer and written into the record, never typed in |
| A18 | R4.3, R5, R3 | "restarting from a checkpoint ... is the single most dangerous thing" and R4.3's coupling-state loss "unfixable at any effort" | **session 15, discovered by running the treatment (handoff §6.85).** The SOLID mechanism is sound: R5 validated the w4000 restore, the state came back bit-identical (E_int+E_kin 5.024052e-08 on both write and restore), the step re-entered at theta 0.5. But the coupled restart died in 31 s. A fresh preCICE instance initialises read-data to ZERO; from rest that is correct, but on a restart the fluid mesh is already at the w4000 deformation, so being handed a zero Displacement it snapped its interface back to undeformed in one 2e-5 s window -> a ~O(10^2 m/s) spurious mesh velocity -> a 2.32e8 N force (against the from-rest control's 0.36 N) -> the solid diverged to a 6.15 m displacement and segfaulted. **Fix: `initialize="true"` on every `<exchange>` in the restart's precice-config**, so the solid writes its restored Displacement and the fluid its restored Force before preCICE initialises (the CalculiX adapter already does this at `precicec_requiresInitialData()`, no C change). It is INERT for the from-rest control -- implicit coupling converges to the same fixed point regardless of the initial guess -- so it lives ONLY on the restart path (`rewrite_for_restart`, a second declared mutation beside A7's max-time) and the base template is untouched; segment 1 stays byte-identical to the control. This fixes R4.3's DATA continuity; the quasi-Newton HISTORY is still lost (as R4.3 said) and shows as a first-window transient, which is exactly what R3(b)/(d) measure. `exchange_initialize` was added to the parsed config model so the "nothing else moved" check can SEE the flag (it was previously blind to it) |

The acceptance commit records A1–A11; A12–A15 are the implementation's own findings, recorded
in `7b30bd9`; A16 is the rebuild's. Each lands in code in the clause-order commits (handoff §6.78 onward). R6 is spent: the hunt's reading is on the record and cannot
be re-read to a different bullet.

**R3 calibration finding (session 14, `a2fb4ce`, `data/vv/stage20_adr045_r3_calibration.json`) —
put to the operator before any treatment was submitted; resolved by A17.** The control against itself
passes all four clauses. But the same submission run TWICE — D-C1 on 2026-09-10 and its
re-probe, the control, on 2026-09-12, both 8000/8000 — differ over windows 4001–8000 by
**35 % of the control's thrust peak-to-peak and 51 % of its lift peak-to-peak** in max
deviation (the thrust difference is a smooth ~1e-5 N offset, lag-1 autocorrelation 0.96; the
lift difference is window-to-window noise), and their trailing-edge displacements differ by
**~1.5e-5 m early against ~1.3e-5 m late** (the control's own displacement there is
~1.2–2.0e-4 m). Q1b's 5 % band is therefore BELOW the two-draw noise floor at these windows:
the force signals are nearly flat there (thrust peak-to-peak 6.7e-5 N against a 1e-4 N mean),
so the peak-to-peak normalisation that made Q1 discriminating on the I4 startup transient
(peak-to-peak 0.69 N) collapses. **As written, R3(a) cannot be passed by any treatment,
transparent or not, and R3(b) sits at the noise floor.** The pre-registration checked every
clause against the control's files but not against two draws of it. This is not a band
being relaxed after a result: no treatment has run. It is a test found unable to resolve its
question, found by the scorer it required, before the B0 hour it protects. **Resolved by A17
(session 15, handoff §6.83): the operator chose the two-draw yardstick (option 2 of handoff
§6.82), with the amplitude limit and the episode rule recorded above before the treatment was
submitted. The restart window stays 4000; option 3 (w400) was refuted by its own calibration.**


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
- CalculiX 2.20 `ccx_2.20.c:1041` (`accold` allocation), `:1795-1797` (`jrstrt`) — the
  PRISTINE file; the adapter's compiled copy has them at `:1121` / `:2146-2149` (A2),
  `nonlingeo.c:1397` (initial-acceleration procedure), `restartwrite.f` / `restartread.f`
  (zero occurrences of `accold`), `amplitudes.f:72` (`TIME=TOTALTIME`).
- ADR-036 (no-restart), ADR-039/040 (the frozen bands and FORBIDDEN lists), ADR-041 V7
  (the NO-GO this ADR is trying to avoid and may not).
