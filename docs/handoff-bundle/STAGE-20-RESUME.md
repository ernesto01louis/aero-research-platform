Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). RESUMING a partial stage.

Read first, in order: CLAUDE.md; `.aero-stage` (already 20, do not bump);
`docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` — this is the
work-of-record for what is already done, especially §6 (gotchas), §7 (the ordered
resumption path) and §8 (do-not-re-derive). Then the original brief
`docs/handoff-bundle/STAGE-20-flexible-flapping-wing-fsi.md`, then ADR-016/035/036/038,
then `data/references/fsi/heathcote_gursul_2007/reference.md`. The approved plan is at
`/root/.claude/plans/stage-20-flexible-typed-pinwheel.md`.

Branch `stage-20-flexible-flapping-wing-fsi` is checked out and pushed; PR #44 is a DRAFT
with all 10 host-side required checks green. Work continues on that branch and PR.

Auto-mode applies: proceed without approval prompts, announce actions; stop only for
destructive ops, the burst budget tier, or anything touching non-aero LXCs.

WHAT IS ALREADY DONE AND VERIFIED (do not redo, do not re-derive)

- **CalculiX is in the loop.** The perpendicular-flap smoke ran OpenFOAM in `precice-fsi.sif`
  and CalculiX in `calculix-precice.sif`: 50/50 coupled windows converged at mean 2.14
  iterations, both exited 0, tip deflected 0 → 0.1646 m under ~8.6 N. Non-gated; it proves
  plumbing only. Bundle `data/vv/stage20_calculix_smoke.json`. Re-run in ~35 s with
  `python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5`.
- **Multi-container provenance is decided, implemented and applied** (ADR-038): `ProvenanceTuple`
  carries a `containers` roster, strictly additively. Postgres migration `005_container_set` is
  APPLIED and verified (column live, 1280 historical rows intact and NULL, mirror INSERT
  exercised in a rolled-back transaction and byte-identical to the MLflow tag). Stage 19's
  blanket refusal is replaced by `assert_provenance_describes`.
- **The HG2007 reference is acquired to the extent the prose supports**, plus the airfoil
  outline measured off the scale diagram. `u95_input` is MEASURED, not guessed: ±5 % thrust,
  ±10 % efficiency, author-stated.
- Executor rc=255 fail-loud fix; `stage_20` marker; `tests/stage_20/` (45 tests). The full
  suite is 347 green (`pytest -q tests/unit tests/stage_20`).

YOUR TASK, IN THIS ORDER

**1. Finish Phase 2b — digitize Figures 5.6 / 5.9 / 5.13.**
The thesis is NOT committed (licence). Re-fetch to the scratchpad and verify the digest:
`curl -sL -o heathcote_thesis.pdf https://purehost.bath.ac.uk/ws/files/188126105/Samuel_Francis_Heathcote_thesis.pdf`
→ sha256 `fdee2ce497ab39af65aff769f04d858e4a2a3cf10adacc0c1351760f3f74fe10`.
The host has no poppler/pypdf; render with `uv run --no-project --with pymupdf` at 200 dpi.
Figures live at rendered pages: **5.6 → p143 (a,b) + p144 (c)**, **5.9 → p147 (a,b)**,
**5.13 → p152**. Method is already fixed in `reference.md` and is binding:
  - **Figures 5.6 and 5.1 plot `C_T/St²`, NOT `C_T`**, despite Fig 5.6's caption. Multiply by
    `St²` — a factor of 11.1 at St = 0.3. This exact species of error made the repo's *other*
    HG reference wrong by 3-5× for a whole stage.
  - Read each required marker **three times independently**; commit all three readings in
    `digitization.csv` with the tool and version. Reading term = half-range; axis-calibration
    term from tick spacing.
  - **Record the correlated / uncorrelated split explicitly.** The axis-calibration term cancels
    in the flexible-minus-rigid increment (same figure, same axes) and the instrument systematic
    largely cancels too (same gauge, same calibration); only the independent per-marker reading
    term survives. That split is what licenses a tighter band on the increment than on the
    absolutes, and it must be shown, not asserted.
  - **Cross-check against `text_sourced.csv` and STOP on disagreement** — never "prefer whichever
    is closer". The anchors: rigid drag→thrust crossover at St = 0.17 at all three Re;
    `C_T = 0.04` for `b/c = 0.56e-3` at Re = 27000; pitch amplitudes <1° / 6° / 17° at
    Re = 9000, St = 0.56.
Write `scripts/stage20_acquire_hg_reference.py` mirroring `stage19_acquire_fsi_reference.py`'s
five steps, and recompute the reference of record with the platform's own estimators.

**2. Phase 3 — author the coupled case.** The largest chunk. There is no upstream tutorial for
it, and `aero/adapters/precice/config.py` is a READER only.
  - `aero/adapters/precice/calculix.py` — typed, fail-loud `.inp` writer **plus a re-reader** for
    the C-gate. **Element type `C3D8I`** (incompatible-modes hex; cures shear locking in a thin
    bending member) on a **one-element-thick 3-D slab with `*BOUNDARY Nall, 3`**, preCICE meshes
    declared `dimensions="2"`. NOT plane stress — that was the plan's assumption and upstream's
    proven idiom overrides it.
  - Geometry (settled, in `reference.md`): 30 mm aluminium teardrop, ≈9.6 mm max thickness
    (≈0.107c), + 60 mm steel plate, `E = 2.05e11`, `b = (b/c)·90 mm`. **Structural root at
    x = 30 mm**, where the plate is clamped between the two machined LE halves — not at the nose.
  - **`a = 17.5 mm` fixed, so `h = a/c = 17.5/90 = 0.194`. NOT 0.175.** `0.175` belongs to the
    other two Heathcote experiments (the NACA-0012 validation model, and the *spanwise* wing whose
    chord is 100 mm) — same shaker amplitude, different chord. An earlier draft of `reference.md`
    and the approved plan file both carry `0.175`; **`reference.md` is authoritative and the plan
    is stale on this point.** The error is 11 % on plunge amplitude and propagates into the
    frequency-from-Strouhal conversion, the I5 mesh-motion probe and every solve.
  - Sanity check that the numbers hang together: at `Re = 18 000`, `c = 0.09 m`, water ⇒
    `U₀ = 0.2 m/s`; `St = 0.3` ⇒ `f = St·U₀/(2a) = 1.71 Hz`, comfortably inside the thesis's
    stated 0.3-2.5 Hz rig range. If a derived frequency falls outside that band, the setup is wrong.
  - Drive the plunge from the **solid's** leading edge via `*BOUNDARY` + `*AMPLITUDE`, with
    ADR-024's `(1−cos)` ramp. The pitch is NOT prescribed — it arises from the flexibility, per
    the thesis; prescribing it would model a different experiment.
  - Forces reach the solid by the adapter **overwriting a `*CLOAD` block the deck declares as
    zeros** on the interface node set — the deck must declare it or there is nothing to overwrite.
    The adapter's `config.yml` `patch:` name maps to an `*NSET` with an `N` prefix
    (`patch: surface` → `*NSET,NSET=Nsurface`). The calculix-adapter reads **`Force`**, not
    FSI3's `Stress`.
  - `precice-config.xml` is a **committed, digest-verified template + renderer**, not a writer:
    render → re-read with `read_precice_config` → `assert_config` against a pre-registered
    expectation. Upstream's numerics for this class: `parallel-implicit`, `max-iterations 50`,
    relative 5e-3 on BOTH `Displacement` and `Force`, IQN-ILS + QR2 filter,
    `initial-relaxation 0.5`, `time-windows-reused 15`.
  - **The case is DIMENSIONAL.** Do NOT reuse `aero/adapters/openfoam/plunging_airfoil.py`; it
    hard-codes `RHO_INF = U_INF = 1.0` and would silently mis-normalise every coefficient. Write
    `aero/adapters/openfoam/flexible_foil.py`. Use `backward` in `fvSchemes` —
    `transient_fvschemes` is first-order Euler. Needs `preciceDict` with `locations faceCenters`
    and a dimensioned `rho`.
  - **Add the force/power path to the coupled route** — `PreciceCoupledSolver.load()` returns
    `cd=None, cl=None` today. Reuse `_read_coefficient_dat`, `_read_force_history` and
    `_strictly_increasing_mask` from `aero/adapters/openfoam/solver.py`; the last is essential
    (`adjustableRunTime` writes duplicate timestamps and `Signal` requires ascending `t`).
  - **Efficiency is where a silent bias lives.** For a deforming foil `−⟨F_y·ẏ_LE⟩` is NOT the
    actuator power, and the error appears only in the flexible arm — i.e. inside the gated
    increment. Compute interface power `∫(traction·v_surface)dS` via a coded OpenFOAM function
    object (`dynamicCode` works under the existing `setpriv` uid-1000 path). The verification is
    free: on the rigid arm it must reduce to `−⟨F_y·ẏ⟩` within 0.5 % — pre-register that.
  - Extend `CoupledCaseSpec` with a `source: TutorialSource | AuthoredSource` discriminated union
    and refactor `_write_case` into an overridable `_materialize` seam. **Keep the Stage-19 path
    byte-equivalent** — the FSI3 verdict rests on it.
  - Register the new case in **all three** `aero/cli.py` sites (`vv list`, `vv run`, and
    `vv report`'s `registered` set — missing the third means it cannot report `missing`).
  - Unit-test every writer's output **byte-for-byte** (the `render_supervisor_script` precedent),
    and drive `compose_improvement(kind="time_averaged", paired=…)` on synthetic per-cycle series
    — Stage 20 is its first production caller.

**3. Phase 4 — ADR-039, the pre-registered gate block. BEFORE any campaign run.**
Mirror ADR-036 exactly: `<!-- GATE-BLOCK:BEGIN/END -->` around a ```text fence, duplicated
byte-identically as `PREREGISTERED_GATE_BLOCK` in the driver, asserted by a required-CI unit test,
embedded in every bundle. Families P/C/I/R/K/S/**A**/D/**M**/X + VERDICT + BUDGET + CONTINGENCIES.
  - **Both the absolute bands AND the flexible-minus-rigid increment sit in the VERDICT line**
    (operator decision), knowing ADR-022 makes a NO-GO on the absolute clause a live outcome.
    Design the verdict to resolve clause by clause so "NO-GO on absolute fidelity, GO on the
    flexibility increment" is expressible.
  - Size bands from the reference's OWN uncertainty, never from what we expect to achieve, and
    record the raw multiplier alongside the applied number.
  - Two deliberate improvements on ADR-036, both flagged as gaps in its own record: **name every
    gated clause in the VERDICT line** (ADR-036 gated S3 but omitted S5 — the clause its own
    review had just added), and add a **shape-7 test** asserting every clause identifier appears
    either in the VERDICT line or the reported-only list. Band-parity test compares ORDERED
    `(clause, band)` pairs — a set loses multiplicity.
  - **Mutation-test the tests**: delete a clause, swap two bands, drop a clause from VERDICT —
    each must turn a test red.
  - New A-family (alignment): elementwise-equal t-grids, the **prescribed** period (never an
    FFT-detected one — `paired_delta_uncertainty` compares at `period_rtol = 1e-9` and would
    correctly refuse two detected periods), one absolute pre-registered discard, ≥20 settled
    cycles per arm.

**4. Phase 5 — pre-flight, then fix the rung ladder FROM THE MEASUREMENT.**
I1 solverdummy across two SIFs; I3 mesh + counts; **I5 an ADR-024-style motion-only probe**
(`moveDynamicMesh` + `checkMesh` on plunge + 1.5× expected tail deflection, non-ortho ≤ 70,
skew ≤ 4, zero negative volumes) BEFORE any coupled solve; **I4 calibrations that COMPLETE ≥200
windows and end `all-exited`, for both arms at every rung**.
**Do not extrapolate a rate from the transient** — Stage 19 was off 3.5-9.6× one way and its B3
diagnostic ~1.8× the other. Pre-register: fixed coupling `time-window-size` across all three rungs
chosen from the FINEST rung's Courant requirement (else a spatial GCI is contaminated by temporal
error, and Courant drifts toward ADR-030's spurious-attractor threshold); refine the solid mesh by
the same ratio as the fluid; build the ladder DOWNWARD (put the affordable mesh at the top and add
a coarse rung below, e.g. 13k/28k/60k) so the critical path is a rung we can afford.

**5. Phase 6 — launch the campaign**: 3 rungs × {flexible, rigid} = 6 coupled runs, all launched
concurrently on aero-dev (≈12 of 16 cores, ~5 GB each of 32 GB), via `run_long.sh` with unique
session names and `AERO_RUN_LONG_REAP=1`. ~5-7 days wall clock. Then Phase 7 analysis, Phase 8
adversarial review, Phase 9 handoff + tag.

HARD DON'TS
- Never relax a pre-registered band. Pre-register BEFORE any campaign run.
- Do not cite Stage 19's numbers as Stage 20 evidence — different solid solver, different
  reference, ADR-016's whole point.
- Fail loud on non-converged coupling and unreached periodic steady state.
- **NEVER cancel a self-hosted CI job to free a runner** — it strands detached solves. Tell:
  runners `busy=true` while `gh run list` shows nothing `in_progress`.
- **Verify EVERY commit with `git log`.** The ruff-format hook exits 0 having rolled the commit
  back; it happened three times last session. Run `ruff format && ruff check --fix` before
  `git add`.
- `aero/` core is stdlib + numpy + pydantic only; add new modules to `import-platform-only.yml`.
- The multi-hour case is **driver-only**, never in `tests/vv` — that is the FSI3 precedent and it
  is what stops a multi-hour job leaking into `vv-smoke` (which a missing `and not moving` broke
  for 23 days).

Conventional commits `<type>(stage-20): …`, `.venv/bin` on PATH for pre-commit. Update the
existing Stage-20 handoff as you go rather than writing a second one; flip `status: partial` to
`complete` only when a verdict exists.
