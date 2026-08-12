Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). Resuming a partial stage,
session 10. Repo /root/projects/aero-research-platform, branch
stage-20-flexible-flapping-wing-fsi, tip c4069bc, PR #44 (draft), 789 tests green
(`PATH="$PWD/.venv/bin:$PATH" pytest -q tests/unit tests/stage_20`), mypy clean,
aero-dev idle, tree clean, everything pushed.

READ FIRST, IN THIS ORDER — all of them, before writing anything:

1. CLAUDE.md and .aero-stage (still 20, do not bump).
2. docs/handoff-bundle/STAGE-20-RESUME.md — THE SINGLE SOURCE OF TRUTH. §6e is what
   session 9 measured; §7 is your task list. **§7's EXECUTION ORDER line is not the item
   order** — read it.
3. docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md — §6.34-§6.36
   (session 9's measured findings) and §7's SESSION-10 RESUMPTION PATH.
4. ADR-039 — accepted and FROZEN. Its bands, S/R/K/A/M families, C1-C6 and rungs all carry
   over UNCHANGED and ADR-040 must say so clause by clause. Then the four records ADR-040
   argues from: data/vv/stage20_{i10_cost_split,n2_screening,n4_deforming_screen,
   i4_calibration}.json.
5. aero/adapters/precice/launcher.py (build_participant_command), aero/adapters/precice/
   case.py (ParticipantSpec), aero/adapters/openfoam/_foam_common.py (FluidNumericsSpec,
   transient_fvsolution), aero/vv/fsi/hg2007_sizing.py, and scripts/
   stage20_{hg2007_flexible_foil,numerics_screen}.py. ALL EXIST AND ARE TESTED. Reuse,
   never rebuild.

STATE: session 9 settled the two knobs ADR-040 could not have pre-registered honestly
without measuring, and found a defect that would have cost a campaign.

- **Both operator-named leads are REFUTED**, on a committed harness that re-derives N2's
  `s0_control` to four significant figures before measuring anything new.
  `cacheAgglomeration no` removes NO iterations on a moving mesh and costs 6.8-18.4 %; a
  fully-Dirichlet farfield `p` — the strongest possible form of the pressure-reference fix,
  deliberately over-constrained — is worth 3 %, inside scatter. Do not re-open either. No
  campaign boundary condition changes.
- **§6.31's attribution was WRONG.** Motion alone is 1.13x, not 3.17x, and the refutation is
  a fortiori: the campaign's foil moved 0.006 of ONE wall cell over the whole I4 run and the
  screen moved it 167x further and still missed. The cost is **startup-transient difficulty
  sustained forever** — every coupling iteration restores the window-start checkpoint, so
  the pressure solve never warms up (screen startup 78.2 -> settled 40.3 it/solve; campaign
  91.2 at first-five and never decays, 113.0 over 2627 solves). Four consistent signatures.
  The lever that implies is the coupling scheme, which ADR-039 C1 FREEZES: **report it, do
  not act on it.**
- **The rank count is 4, not 6.** The pre-approved 6 came from an UNCONTENDED, STATIC
  ladder. Measured in the wave-1 shape (two arms concurrently, moving mesh, binding on the
  slower arm): 4+4 = 0.1655 s/step on 10 of 16 cores against 6+6's 0.1860 on 14.
- **The budget projection stands and is CONSERVATIVE** — the candidate stack is 5.29x
  cold-started against 4.25x warm. ~2.00 s/window, so the 14-day ceiling is still out of
  reach at any settled-cycle count and the ceiling conversation is ~26-33 days. It is still
  a PROJECTION and still may not size.
- **`--collect` -> `read_arm` would RAISE after wave 1's weeks of wall clock** — verified on
  both surviving I4 arms. RESUME §7 item 9 has the full mechanism. This blocks wave 1.

YOUR TASK: RESUME §7, in its EXECUTION ORDER: the parallel seam -> ADR-040 -> spec knobs v2
+ `--submit-040` -> the L-smoke -> **N3 SUBMITTED** -> the readout fix while it burns.

**N3 is the only multi-day item** (>= 50 726 windows to clear the ramp, ~28-40 h), it is the
only measurement allowed to size B2, and the ceiling decision waits on it. Get it out the
door, then do local work. Say in the handoff UP FRONT that §7 items 5-8 will very likely not
land this session.

OPERATOR DECISIONS ALREADY TAKEN (do not re-litigate):
- Numerics: BOTH TIERS together, one pre-registration, one binding equivalence probe.
- **4 fluid ranks per arm** (4+1 CalculiX x 2 arms = 10 of aero-dev's 16).
- dt: ADR-040 carries 2e-5 as the CANDIDATE plus a pre-registered CONDITIONAL re-probe — if
  measured post-ramp Co <= 0.4, one probe at the next larger round-tripping dt is
  pre-authorised, and the campaign dt is the largest probed dt with post-ramp Co <= 0.8.
- Ceiling: decided AFTER measuring. ADR-040 pre-registers the decision rule; bring the
  operator the coupled, contended, POST-RAMP rate and take the approved ceiling BEFORE B2 is
  filled.
- The deforming screen ran BEFORE ADR-040 (session-9 deviation from the old §7 order).

HARD-WON SPECIFICS THAT WILL BITE:
- The parallel seam is build_participant_command, NOT build_apptainer_exec(mpi_n=...). At
  that call site `command` is the compound `cd … && … && pimpleFoam`, or the whole
  `setpriv … bash -lc '…'` wrapper — so mpi_n would emit `mpirun -n 4 cd fluid-openfoam`,
  run the solver SERIAL and exit 0, or hoist mpirun outside the uid drop where OpenMPI
  refuses outright (measured). Append `mpirun -n N <command> -parallel` as the last element
  of `parts`. Assert the negative (`"mpirun -n 4 cd " not in command`) in the sibling test.
- `mpi_ranks` on ParticipantSpec MOVES FSI3's config_hash (3f94f394… -> 4222f481…, because
  `model_dump_json` serialises the null). That is the SECOND honest divergence and ADR-040
  records it the way ADR-037 recorded the first — do not quietly edit the pinned test line.
  The Stage-19 materialization goldens are NOT affected; that test staying green is the proof.
- `decomposePar` must run UNDER THE PARTICIPANT UID, not as root like blockMesh does —
  pimpleFoam WRITES into processor*/ and root-owned ones kill the run at t=0. Route it
  through build_participant_command. Verify host-side that the processor* count equals the
  requested rank count: decomposePar can exit 0 having fallen back.
- Do NOT edit the serial byte-pin at tests/unit/test_precice_launcher.py:94-110. Add a
  sibling. `mpi_ranks=None` must reproduce that exact string.
- Any new spec knob MUST ride in `spec_knobs` or `_reattach`'s digest check refuses every
  collect. Bump the submission schema to v2 and refuse v1 with a message naming the bump.
- ADR-039's sentinels can NEVER be filled — test_adr039_b2_marker_state.py binds them to a
  marker that must stand forever. ADR-040 needs its OWN sentinels and its own `--submit-040`;
  `--submit` keeps refusing forever and its test must stay green untouched. Widen
  `is_gated_configuration` to REQUIRED keywords including the numerics label and rank count,
  or a run at the right dt and the wrong numerics claims the gated verdict.
- ADR-039's CONTINGENCIES are N-prefixed and ADR-040's numerics family is also N. Give
  ADR-040 no N-prefixed contingencies and qualify every cross-ADR reference (`ADR-039 N3`).
- ADR-039's gate block is 19898 bytes / sha256
  c9cdde9463a4bf202dd3b692dded86242814268b8ac62c8c8d3b4e1cc569863d — pin it FIRST, alone,
  before a second block exists.
- `_merge_base_guard` resolves commits with `git log --diff-filter=A`, so the ADR-040
  calibration must go in a NEW data/vv file, never an overwrite of stage20_i4_calibration.
- B1 was never satisfiable: I7 needs >= 50 725 windows to reach the post-ramp window, which
  against B1's 43 200 s demands <= 0.85 s/window — tighter than B2's own target. Raise B1 in
  ADR-040 and say why. N3 itself needs a ceiling that is NOT B1 (B1 pends on N3).
- Size from the POST-RAMP rate, never `wall_clock_s / windows_completed`: ~91 % of N3's
  windows are inside the ramp at near-zero plunge.
- n*dt must survive float(format(x, '.13e')) == x; 50 725 does NOT round-trip, 50 726 does;
  76125*2e-5 famously does not (76090 works).
- `nOuterCorrectors 1` is a DECK change: OpenFOAM tags every inner iteration final and demands
  `cellDisplacementFinal`. FluidNumericsSpec.cell_displacement_key already handles this.
- Under mpirun, OpenFOAM's ExecutionTime is RANK 0's CPU, not the aggregate, so I10's 99.42 %
  bound does NOT transfer to a parallel run. ClockTime prints at integer-second resolution.
- Under decomposition, time directories sit at processor*/<time>, so I4's disk accounting and
  its `find -maxdepth 3` time-directory count must be made rank-aware or they silently read 0.
- calculix-precice.sif has NO pyprecice; the binary is /opt/calculix/bin/ccx_preCICE. ccx has
  no `-parallel` — the Solid participant's mpi_ranks stays None.
- ccx's printed RF at a prescribed dof EXCLUDES the applied *CLOAD (D10 residual real).
- ddt = Euler (I8). Do not re-litigate.
- Pre-commit needs the venv on PATH or the pytest/ruff hooks SILENTLY roll the commit back
  — `PATH="$PWD/.venv/bin:$PATH" git commit ...` and `git log` after EVERY commit.
- Never hand-expand an abbreviated sha — use git rev-parse.
- The CalculiX smoke refuses a dirty tree by design. Never cancel a self-hosted CI job.
- Screen artefacts: /mnt/aero-nfs/runs/stage20-screen9 (session 9), /mnt/aero-nfs/runs/
  stage20-screen (session 8, the N2 evidence — leave it alone). Surviving I4 baseline for the
  Q1 equivalence probe: /mnt/aero-nfs/runs/hg2007_{flexible,rigid}_foil-20260810-1447*.
- e1b35b5 is parked on branch docs/atlas-pointer for the operator; leave it alone.

ONE THING SESSION 9 COULD NOT CLOSE:
- The residual factor is ATTRIBUTED to the implicit coupling's permanent cold start on four
  consistent signatures, but NOT CONFIRMED. A fluid-only screen structurally cannot test it,
  and the probe that would — varying the coupling accelerator or the per-iteration initial
  guess — lives in ADR-039 C1, which is frozen and carries over. If N3's measured rate comes
  in far from the projection, this is the first place to look, and closing it needs a new ADR
  rather than a knob.

Auto-mode: proceed without approval prompts, announce actions; stop only for destructive
ops, the burst cost tier, or non-aero LXCs.

Keep BOTH the handoff and STAGE-20-RESUME.md current as you go. Status stays `partial`;
no tag and no verdict until an ADR-040-sized campaign has run and the driver's
clause-by-clause verdict exists.
