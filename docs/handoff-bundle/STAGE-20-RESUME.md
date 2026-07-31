Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). RESUMING a partial stage (2nd resume).

Read first, in order: CLAUDE.md; `.aero-stage` (already 20, do not bump);
`docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` — the work-of-record.
**Read §6.6–§6.9 and §7 items 1 and 1b before writing anything**; they change what you would
otherwise write. Then `docs/handoff-bundle/STAGE-20-flexible-flapping-wing-fsi.md` (original
brief), ADR-016/022/024/030/035/036/038, and
`data/references/fsi/heathcote_gursul_2007/reference.md`. Approved plan:
`/root/.claude/plans/tage-20-flexible-warm-beacon.md` — **stale on `h`; reference.md wins.**

Branch `stage-20-flexible-flapping-wing-fsi`, PR #44 (DRAFT). Auto-mode: proceed without approval
prompts, announce actions; stop only for destructive ops, the burst tier, or non-aero LXCs.

DONE AND VERIFIED — do not redo, do not re-derive

- **CalculiX is in the loop.** Perpendicular-flap smoke, two SIFs, 50/50 windows converged at mean
  2.14 iterations. Re-run in ~35 s: `python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5`.
- **Multi-container provenance** (ADR-038); Postgres `005_container_set` APPLIED and verified.
- **Phase 2b COMPLETE.** `digitization.csv` (208 markers, Figs 5.6a/b/c + 5.9a + 5.13a),
  `hg2007_recomputed.csv` (reference of record), `scripts/stage20_digitize_hg_figures.py`,
  `scripts/stage20_acquire_hg_reference.py`. **R2 passes on all five anchors.**
- **Gated operating point FIXED** (from the reference alone, before any solve):
  **Re = 9000, St = 0.345, flexible `b/c = 0.85e-3` (76.5 µm) vs rigid `b/c = 4.23e-3` (380.7 µm)**
  ⇒ `U = 0.1 m/s`, `f = 0.9857 Hz`, `T = 1.0145 s`; `c = 90 mm`, `a = 17.5 mm`, **`h = 0.194`**,
  water (`rho = 1000`, `nu = 1e-6`), span 300 mm. Reference: `C_T` 1.008 / 0.398 (`ΔC_T` 0.609),
  `η` 0.1753 / 0.0888 (`Δη` 0.0865), pitch amplitude 5.35°.
  Sanity check the numbers hang together: any derived `f` outside the rig's stated 0.3–2.5 Hz
  range means the setup is wrong.
- **Mesh feasibility PASSES.** `CaseSpec.section` (`TeardropPlateSection`) swaps only the surface
  curve inside the existing eight-block C-grid; NACA path pinned byte-identical. Both arms:
  `checkMesh` "Mesh OK", 48 240 cells, skew 2.40, no negative volumes. **The thicker-plate fallback
  is NOT needed.** Suite 359 green (`pytest -q tests/unit tests/stage_20`).

FOUR THINGS THAT WILL BITE YOU IF YOU SKIP THE HANDOFF

1. **`h = 0.194`, not 0.175** (§6.7). 0.175 is the *other two* Heathcote experiments.
2. **No raw PDF digest is reproducible here** (§6.6) — Bath re-wraps the file on every download
   (60 bytes of 12.2 M differ per fetch). Use `pdf_content_sha256` / `page_raster_sha256`.
3. **This thesis's blanket "for all Re" prose is not evidence** (§6.8): the crossover claim misses
   by 12.6 % at the gated Re, while its condition-specific prose reproduces to 0.1 %.
4. **The C-grid's max non-orthogonality has always been ~85**, including 86.5 on the platform's own
   production Stage-05 V&V mesh (§6.9). ADR-024's absolute `≤ 70` applied to I5 would fail on the
   STATIC mesh before any motion. **I5 must gate DEGRADATION against the recorded static
   baseline**, plus absolute skew ≤ 4 and zero negative volumes.

YOUR TASK, IN THIS ORDER

**1. Phase 3A — the `source` seam. LAND THE TWO NON-REGRESSION TESTS ON PRE-REFACTOR CODE FIRST,
see them green, THEN refactor.** Golden values produced by post-refactor code prove nothing. This
is the single most important ordering rule in the stage.
  - `tests/stage_20/test_stage19_materialization_is_byte_identical.py` — fixture tarball through
    the real `_write_case`; assert a literal `{path: sha256}` map, the **golden bytes of
    `aero-manifest.json`**, the exact `DeclaredMutation` tuple; plus a DVC-gated variant on the
    real FSI3 archive.
  - `tests/stage_20/test_stage19_load_path_unchanged.py` — fake `ResultHandle` over committed FSI3
    fixtures; assert the `SolveResult` equals a committed golden (all 20 scalars, `cd is None`).
  - Then: `CoupledCaseSpec.source: TutorialSource | AuthoredSource` (discriminator `kind`);
    `TutorialTree` → `MaterializedTree` (`pin` XOR `authored`); `DeclaredMutation.kind +=
    "authored"`, `before_sha256: str | None`; `select_fluid_mesh(fluid_participant_dir=…)` (kills
    the `case.py:382` hard-code); `_materialize(spec, root)` as a **method** (a free function drags
    the foam writer into `case.py`, which `launcher.py` imports); `CASE_ROOT_DIRNAME = "tutorial"`
    + `_case_dir()` collapse the eight re-derivation sites; **extract** `_assert_status_gate` (K2)
    and `_assert_coupling_converged_over` (K1) so both load paths share ONE gate implementation.
  - **One honest divergence — record it, do not paper over it:** nesting the pin under `source`
    changes FSI3's `config_hash`. Pin the new value with the old in a comment; record both in
    ADR-037. Materialized *bytes* stay identical; the *spec serialization* moved. Different claims.

**2. Phase 3B — authored-case integrity (C-family).**
  - `aero/adapters/precice/calculix.py`: typed `.inp` writer **plus a re-reader**. `C3D8I` on a
    one-element-thick 3-D slab with `*BOUNDARY Nall, 3`; preCICE meshes `dimensions="2"`. NOT plane
    stress. Highest-value assertions: `*CLOAD` on the interface nset exists with dofs {1,2,3} all
    present and all exactly `0.0` (the adapter OVERWRITES it — missing, the run is silently
    force-free); `ALPHA` present and `0.0` (ccx defaults to −0.05 HHT damping, i.e. numerical
    damping inside the gated increment); `DIRECT` present and `dt == time-window-size`; `C3D8I` not
    `C3D8`. A ~20-line `config.yml` reader (no YAML dep — Invariant 1) asserting
    `"N" + patch == interface_nset`, `read-data == [Force]` (**not** FSI3's `Stress`),
    `write-data == [Displacement]`.
  - Geometry: 30 mm aluminium teardrop (max half-thickness 4.8 mm at x ≈ 8.5 mm) + 60 mm steel
    plate, `E = 2.05e11`. **Structural root at x = 30 mm.** Model the teardrop as a **fully
    prescribed (kinematically rigid) region**, not a stiff material — it removes a spurious elastic
    mode and makes the plunge exact. Plunge from the **solid's** LE via `*BOUNDARY` + `*AMPLITUDE`
    with ADR-024's `(1−cos)` ramp (reuse `aero.postprocess.flapping_kinematics`; do not re-derive).
    **The pitch is NOT prescribed** — it arises from the flexibility.
  - `precice-config.xml` = committed template + renderer + re-read + `assert_config`, **not a
    writer**. `templates/SHA256SUMS` verified on every read; assert `found_tokens == _TOKENS`
    exactly before substituting; then check every token is observable in the parsed model.
  - Upstream numerics: `parallel-implicit`, `max-iterations 50`, relative 5e-3 on **both**
    `Displacement` and `Force`, IQN-ILS + QR2, `initial-relaxation 0.5`, `time-windows-reused 15`.
    **Scale the RBF `support-radius`** — upstream's `1.0` is metres on a 0.09 m chord.

**3. Phase 3C — dimensional fluid deck + readout.**
  - `aero/adapters/openfoam/flexible_foil.py`. Do **not** reuse `plunging_airfoil.py`
    (`RHO_INF = U_INF = 1.0`). `preciceDict` in the **perpendicular-flap shape** (single interface,
    `locations faceCenters`, `readData (Displacement)`, `writeData (Force)`) with dimensioned
    `rho … 1000`. `dynamicMeshDict`: `displacementLaplacian` + `diffusivity quadratic
    inverseDistance`. `backward` in `fvSchemes` (add `ddt_scheme=` to `transient_fvschemes`
    additively — `tests/stage_11/test_dynamic_mesh_writers.py:62-63` pins the default byte-exact).
    **`adjustTimeStep no`, fixed `deltaT`** — that is what makes the A-family's bitwise t-grid
    equality reachable at all. `movingWallVelocity` on the moving wall. Name the FOs exactly
    `forces1` / `forceCoeffs1` (`_coefficient_file` / `_maybe_force_file` hard-code those).
  - Promote `_read_force_history`, `_read_coefficient_dat`, `_strictly_increasing_mask` into
    `aero/adapters/openfoam/force_io.py` under public names; re-bind the privates so stages 10–16
    stay green.
  - **Two watch-points** (solid LE and TE), both in `HG2007_EXPECTATION.watch_points` so a
    coordinate typo aborts at `prepare`. LE verifies the prescribed plunge; the pair gives the
    pitch angle. **Kinematics analytic, never differenced** — one sample per window aliases.
  - **Input power three ways, cross-checked:** P1 `−⟨F_y·ẏ_LE⟩` (correct for the rigid arm only),
    P2 a coded OpenFOAM FO integrating `∮(traction·v)dS`, P3 CalculiX reaction power via
    `*NODE PRINT, NSET=Ndriven, TOTALS=ONLY` + `RF` (free, and independent of the fluid solver:
    in periodic steady state `⟨d/dt(KE+U_strain)⟩ = 0`). Pre-register rigid `|P2−P1|/P1 ≤ 0.005`
    and both arms `|P3−P2|/P2 ≤ 0.02`; report `(P1−P2)/P2` on the flexible arm — that IS the bias
    the naive formula would have put inside the gated increment. `η` from **P2**.
    `dynamicCode` works under the existing `setpriv` uid-1000 path; verify with a <60 s probe in a
    **scratch** dir, never the campaign case (I6). Also have the FO write its own `Fx,Fy` solely to
    compare against `forces1` at 1 % — its `fvc::grad(U)` traction is not `devRhoReff`.
  - **ccx `.dat` cadence — do not assume:** classify structurally. `duplicates == 0` ⇒ per-window;
    `duplicates == Σ(iterations) − n_windows` (from the iterations log) ⇒ per-iteration, keep the
    **LAST** row at each time; anything else RAISES. Ignoring this biases the flexible arm.
  - `analyse_limit_cycle`: add optional `period: float | None = None` (default ⇒ FFT, bit-identical
    to Stage 19) + additive `period_source`. New `aero/vv/alignment.py` for the A-family t-grid
    check — `paired_delta_uncertainty` has **no** t-grid check today and `CycleSamples` has no `t0`.

**4. Phase 3D — CLI.** `_build_solver` hard-wires `TUREK_HRON_FSI3_EXPECTATION` into every
`precice` solver — move the expectation onto the source. `stage_str` table + per-case `stage = "20"`
(replaces the hard-code at `cli.py:652`). `_SOLVER_SIF["precice"]` → both SIFs. **The CLI path
never calls `assert_provenance_describes` — a live gap.** Register in **all three** `FSI_CASES`
sites (`vv list` :519, `vv run` :606, `vv report`'s `registered` set :755).

**5. Phase 4 — ADR-037 (authored-case architecture), flip ADR-038 to `accepted`, and ADR-039 (the
gate block) BEFORE any campaign run.** Mirror ADR-036 in form byte-for-byte: pure ASCII, ` - ` not
em-dashes, family headers at column 0, clauses at two-space indent, continuations at five.
Families P/C/I/R/K/S/**A**/D/**M**/X + VERDICT + BUDGET + CONTINGENCIES.
  - **P must be rewritten, not copied** — ADR-036's P3 ("a gated run spanning more than one SIF is
    structurally refused") is now FALSE. Cite `assert_provenance_describes` + the roster + the
    `container_sif_set` tag. CalculiX is **2.20** + adapter v2.20.1 (verified in the SIF).
  - **I5 = degradation vs the recorded static baseline** (gotcha 4). **I6** = the coded-FO probe.
  - **A-family:** bitwise-equal t-grids; the **prescribed** period, bit-identical between arms
    (`paired_delta_uncertainty` compares at `period_rtol = 1e-9` and would correctly refuse two
    FFT-detected periods); one absolute pre-registered discard; ≥20 settled cycles per arm;
    `correlation` / `variance_reduction` reported, never gated.
  - **D-family:** D0 pitch amplitude 5.35°, D1 `C_T` 1.008, D2 `η` 0.1753, D3 `ΔC_T` 0.609,
    D4 `Δη` 0.0865, D5/D6 signs (**no band, cannot be relaxed**), D7 admissibility, **D8 rigid-arm
    pitch ≤ 2°** (HG's exact text-sourced bound — falsifies "our rigid arm is actually rigid"),
    D9/D10 the power identities. **M**: `|C_T,rigid − C_T,rigid,HG| / C_T,rigid,HG ≤ 0.58`,
    ADR-022's measured envelope as a regression bound (not an absolute-thrust validation).
  - Band sizing: `4 × (u95_ref / |value|)`, floored 0.25, capped 0.50. Increment `u95_ref` = RSS of
    the two arms' **reading** terms only — the axis term cancels, and `digitization.csv` shows that
    split per row rather than asserting it. Record the raw multiplier; say when a floor/cap binds.
  - **Record why the selection rule changed**: "largest `ΔC_T`" is degenerate because `C_T ~ St²`,
    so it walks to the figure's right-hand edge; replaced by `Δ(C_T/St²)` inside HG's own
    `0.2 < St < 0.4` band. Note the optimal plate thickness MOVES with St, so plate and St are
    chosen together.
  - **Two improvements on ADR-036:** name EVERY gated clause in the VERDICT line (ADR-036 omitted
    S5 — the clause its own review had just added — and left I4 neither gated nor listed); add
    **shape-7**: every clause identifier appears either in the VERDICT line or the reported-only
    list. Band-parity test compares **ORDERED** `(clause, band)` pairs — a set loses multiplicity.
    ADR-036's regex matches only integer percentages and the literal word "within" — widen it if
    any band is fractional. **Mutation-test the tests**: delete a clause, swap two bands, drop one
    from VERDICT — each must turn a test red.
  - **Both the absolute bands AND the increment sit in the VERDICT line** (operator decision),
    knowing ADR-022 makes a NO-GO on the absolute clause a live outcome. Design the verdict to
    resolve clause by clause so "NO-GO on absolute fidelity, GO on the flexibility increment" is
    expressible. Note §6.8's finding that HG's rig was deliberately nominally 2-D (end plates, gap
    < 3 % chord) — that *weakens* ADR-022's 2-D-vs-3-D root cause here and belongs in the ADR.

**6. Phase 5 — pre-flight**: I1 solverdummy across two SIFs; I3 mesh + counts; I5; I6; **I4
calibrations that COMPLETE ≥200 windows and end `all-exited`, for both arms at every rung**.
**Do not extrapolate a rate from the transient** — Stage 19 was off 3.5-9.6× one way and its B3
diagnostic ~1.8× the other; a run that died after a few windows yields no s/window figure at all.
Pre-register: fixed coupling `time-window-size` across all three rungs, chosen from the FINEST
rung's Courant requirement (else a spatial GCI is contaminated by temporal error, and Courant
drifts toward ADR-030's measured spurious-attractor threshold between Co 4 and Co 8); refine the
solid by the same ratio as the fluid; build the ladder DOWNWARD (e.g. 13k/28k/60k). Pre-flight
FAILS on `Co > 1` rather than silently adjusting.

**7. Phase 6 — launch** 3 rungs × {flexible, rigid} = 6 coupled runs, all launched concurrently on
aero-dev (~12 of 16 cores, ~5 GB each of 32 GB), via `run_long.sh` with unique session names and
`AERO_RUN_LONG_REAP=1`. Then update the handoff (`status: partial`, **no tag, no verdict**).
Phases 7–9 (GCI + paired U95 + clause-by-clause verdict, adversarial review, tag) are a further
session. `compose_improvement(kind="time_averaged", paired=…)`: Stage 20 is its FIRST production
caller — drive it on synthetic per-cycle series in unit tests first, do NOT pass
`baseline`/`improved` (the validator raises), and note `u95_delta_input_frac` multiplies
`|paired.mean_baseline|`, i.e. the RIGID arm's mean.

HARD DON'TS
- Never relax a pre-registered band. Pre-register BEFORE any campaign run.
- Do not cite Stage 19's numbers as Stage 20 evidence (ADR-016).
- Fail loud on non-converged coupling and unreached periodic steady state.
- **NEVER cancel a self-hosted CI job to free a runner** — it strands detached solves. Tell:
  runners `busy=true` while `gh run list` shows nothing `in_progress`.
- **Verify EVERY commit with `git log`.** Run `ruff format && ruff check --fix` before `git add`.
  Changing handoff frontmatter stales the README STATUS block — run `scripts/regenerate_status.sh`.
- `aero/` core is stdlib + numpy + pydantic only; add new modules to `import-platform-only.yml`.
- The multi-hour case is **driver-only**, never in `tests/vv`.
- **Never write a value into a provenance-bearing field you have not actually computed.**

Conventional commits `<type>(stage-20): …`; `.venv/bin` on PATH for pre-commit. Update the existing
Stage-20 handoff as you go rather than writing a second one; flip `status: partial` to `complete`
only when a verdict exists.

LEAVE AN AUDIT TRAIL (the operator will have this session's work reviewed against it)

- **One commit per coherent unit**, each with a body saying *why*, not just *what*. `git log` is
  the primary evidence; a squashed "phase 3 done" commit destroys it.
- **Record every number you measure**, not just the ones that passed — s/window and
  iterations/window per arm per rung (I4), the static mesh-quality baseline (I5), the three power
  routes P1/P2/P3 and their pairwise deltas, the ccx `.dat` cadence classification (K3).
- **Every band in ADR-039 must be traceable to a row in `hg2007_recomputed.csv`** via the stated
  multiplier rule, with the raw multiplier printed beside the applied number.
- **If you deviate from this prompt or the approved plan, say so in the handoff's §3** with the
  evidence that forced it. Deviating is fine; deviating silently is not.
- **If a gate fails, stop and record it.** Never widen a band, never re-pick a window, never
  re-run until it passes. A NO-GO with evidence is a result; a GO obtained by adjustment is not.
- Update `docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` **as you go**.
  Also record the operator's `85e0b32` (`run_long.sh`: a timed-out wait no longer strands the solve
  it was watching) in §4 — it is not yet there, and it matters for a six-run concurrent campaign.
- Final state must be: clean tree, pushed, PR #44 checks green, `pytest -q tests/unit
  tests/stage_20` green, and nothing running on aero-dev that you did not intend to leave running.
