Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). RESUMING a partial stage (3rd resume).

Read first, in order: CLAUDE.md; `.aero-stage` (already 20, do not bump);
`docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` — the work-of-record.
**Read §6.10–§6.13 and §7 item 3b before writing anything**; they are session 3's findings and they
change the campaign, the ADR and the next commit you would otherwise write. Then
`docs/handoff-bundle/STAGE-20-flexible-flapping-wing-fsi.md` (original brief),
ADR-016/022/024/030/035/036/038, and `data/references/fsi/heathcote_gursul_2007/reference.md`.
Roadmap: `/root/.claude/plans/stage-20-flexible-cryptic-umbrella.md`. (The older
`stage-20-flexible-typed-pinwheel.md` is superseded — stale on `h`, on the element choice and on
its Phase-6 sizing. The `tage-20-flexible-warm-beacon.md` earlier prompts named never existed.)

Branch `stage-20-flexible-flapping-wing-fsi`, PR #44 (DRAFT). Auto-mode: proceed without approval
prompts, announce actions; stop only for destructive ops, the burst tier, or non-aero LXCs.

DONE AND VERIFIED — do not redo, do not re-derive

- **CalculiX is in the loop.** Perpendicular-flap smoke, two SIFs, 50/50 windows converged at mean
  2.14 iterations. Re-run in ~35 s: `python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5`.
- **Multi-container provenance** (ADR-038); Postgres `005_container_set` APPLIED and verified.
- **Phase 2b COMPLETE.** `digitization.csv` (208 markers), `hg2007_recomputed.csv` (reference of
  record), `scripts/stage20_digitize_hg_figures.py`, `scripts/stage20_acquire_hg_reference.py`.
  **R2 passes on all five anchors.**
- **Gated operating point FIXED** (from the reference alone, before any solve):
  **Re = 9000, St = 0.345, flexible `b/c = 0.85e-3` (76.5 µm) vs rigid `b/c = 4.23e-3` (380.7 µm)**
  ⇒ `U = 0.1 m/s`, `f = 0.9857 Hz`, `T = 1.0145 s`; `c = 90 mm`, `a = 17.5 mm`, **`h = 0.194`**,
  water (`rho = 1000`, `nu = 1e-6`), span 300 mm. Reference: `C_T` 1.008 / 0.398 (`ΔC_T` 0.609),
  `η` 0.1753 / 0.0888 (`Δη` 0.0865), pitch amplitude 5.35°. Any derived `f` outside the rig's
  stated 0.3–2.5 Hz range means the setup is wrong.
- **Mesh feasibility PASSES *geometrically*.** `CaseSpec.section` (`TeardropPlateSection`) swaps
  only the surface curve inside the existing eight-block C-grid; NACA path pinned byte-identical.
  Both arms: `checkMesh` "Mesh OK", 48 240 cells, skew 2.40, no negative volumes. The thicker-plate
  fallback is NOT needed. **But those numbers came from a mesh with `first_cell_height = 2.0e-6 c`
  and are not the campaign mesh — see bite 5.**
- **Phase 3A's two non-regression pins are LANDED (`67d8e82`), on pre-refactor code, alone in their
  commit.** `tests/stage_20/test_stage19_load_path_unchanged.py` (fake `ResultHandle`, 23-scalar
  golden, both K2 endings plus both refusals, gate-C4 negative) and
  `tests/stage_20/test_stage19_materialization_is_byte_identical.py` (tiny committed archive with a
  **two-mutation ordered** ledger, plus a DVC-gated 94-entry golden on the real FSI3 archive).
  Fixtures regenerate with `python scripts/stage20_capture_stage19_golden.py`. Suite **380 green**.
  **Verify the ordering before you trust the refactor**, then record both SHAs in the handoff:

      git log --oneline -- tests/stage_20/fixtures/       # must be exactly 67d8e82
      git merge-base --is-ancestor 67d8e82 <refactor sha> # must be true

SEVEN THINGS THAT WILL BITE YOU IF YOU SKIP THE HANDOFF

1. **`h = 0.194`, not 0.175** (§6.7). 0.175 is the *other two* Heathcote experiments.
2. **No raw PDF digest is reproducible here** (§6.6) — use `pdf_content_sha256` /
   `page_raster_sha256`.
3. **This thesis's blanket "for all Re" prose is not evidence** (§6.8): the crossover claim misses
   by 12.6 % at the gated Re, while its condition-specific prose reproduces to 0.1 %.
4. **The C-grid's max non-orthogonality has always been ~85**, including 86.5 on the platform's own
   production Stage-05 V&V mesh (§6.9). **I5 must gate DEGRADATION against the recorded static
   baseline**, plus absolute skew ≤ 4 and zero negative volumes.
5. **The flexible plate is the campaign's clock, and the default wall spacing is unrunnable**
   (§6.11). `CaseSpec.first_cell_height` defaults to `2.0e-6` chords — 0.18 µm on a 90 mm chord,
   a y+<1 RAS value — and the wake-cut block inherits it, so `Co ≤ 1` would need `dt ≈ 1.7e-6 s`.
   `PlungingAirfoilSpec` already uses **`5.0e-4`**; pre-register that. Then the binding limiter is
   the **flexible arm's blunt-TE base** (76.5 µm across `n_te` cells), giving `dt ≈ 3.5e-4 s` —
   5× tighter than the rigid arm, and the paired A-family forces both arms to share it.
   Also: the C-grid's surface blocks are `simpleGrading (1.0 …)`, i.e. **uniform in arc length**;
   the cosine-spaced control points are shape fidelity, not the cell distribution.
6. **`load()` emits 23 scalars, not 20**, and `_write_case` is `PreciceCoupledSolver._write_case`
   at `solver.py:168-207`, **not** in `case.py`. The `"tutorial"` literal appears at **7 production
   + 2 test** sites, not eight. (Earlier prompts said otherwise; the tests now pin the truth.)
7. **Three silent failure modes in the authored case** (§6.12), from upstream's real `flap.inp`:
   the CalculiX slab's z-thickness must equal the OpenFOAM `span` or the plate is under-loaded
   400× while everything still converges; `*STEP, INC=1000000` or ccx exits **0** mid-run and K2
   *passes*; and `PreciceConfigExpectation` has **no field** for the RBF `support-radius` or any
   acceleration parameter, so the C-family's "every token observable in the parsed model" needs an
   additive extension (`| None = None`) before it can be honoured.

YOUR TASK, IN THIS ORDER

**1. Phase 3A — the `source` seam refactor. The tests are already green; make them stay green.**
Do NOT re-capture the goldens. Do NOT add a `--regenerate` escape hatch. One commit:
  - `CoupledCaseSpec.source: TutorialSource | AuthoredSource` (discriminator `kind`);
    `TutorialTree` → `MaterializedTree` (`pin` XOR `authored`); `DeclaredMutation.kind +=
    "authored"`, `before_sha256: str | None`; `select_fluid_mesh(fluid_participant_dir=…)` (kills
    the `case.py:382` hard-code); `_materialize(spec, root)` as a **method** (a free function drags
    the foam writer into `case.py`, which `launcher.py` imports); `CASE_ROOT_DIRNAME = "tutorial"`
    + `_case_dir()`; **extract** `_assert_status_gate` (K2) and `_assert_coupling_converged_over`
    (K1) so both load paths share ONE gate implementation.
  - **Keep the manifest bytes identical by versioning the SHAPE, not by adding fields.** Extract a
    pure `render_tutorial_manifest_json(...)` (schema v1, dicts built by hand from explicit fields,
    never `model_dump()`) whose docstring states its bytes are a committed golden reproduced in
    every pre-Stage-20 bundle; give authored cases a *separate* emitter. `json.dumps(sort_keys=
    True)` is recursive, so one new optional field on `MaterializedFile` or `DeclaredMutation`
    rewrites all 94 `files` entries and a new top-level key re-sorts the document. Keep `dest` at
    `host_path/CASE_ROOT_DIRNAME` and assert `tree.root.name == CASE_ROOT_DIRNAME` in a validator,
    or `case_dir` and every mutation `path` shift.
  - **Two honest divergences — record them in ADR-037, do not paper over them:** nesting the pin
    under `source` changes FSI3's `config_hash` (pin the new value with the old in a comment,
    record both); and unifying K1 makes the Stage-19 *driver* window-scoped where it was whole-run.
    The latter is **provably a no-op on the tagged record** — `data/vv/stage19_turek_hron_fsi3.json`
    reports `n_nonconverged: 0` over 8000/8000 windows for both participants. Cite that evidence.

**2. Phase 3B — authored-case integrity (C-family).**
  - `aero/adapters/precice/calculix.py`: typed `.inp` writer **plus a re-reader**. `C3D8I` on a
    one-element-thick 3-D slab with `*BOUNDARY Nall, 3`; preCICE meshes `dimensions="2"`. NOT plane
    stress. Highest-value assertions: `*CLOAD` on the interface nset exists with dofs {1,2,3} all
    present and all exactly `0.0` (the adapter OVERWRITES it — missing, the run is silently
    force-free); `ALPHA` present and `0.0`; `DIRECT` present and `dt == time-window-size`; `C3D8I`
    not `C3D8`; **`INC >= 10 * ceil(max_time/dt)`** (bite 7); **slab z-extent == fluid `span`**
    (new clause **C6**). A ~20-line `config.yml` reader (no YAML dep — Invariant 1) asserting
    `"N" + patch == interface_nset`, `read-data == [Force]` (**not** FSI3's `Stress`),
    `write-data == [Displacement]`, and that the mesh name matches the rendered XML's.
  - Geometry: one structured `NX × NY × 1` block over the WHOLE section with y from
    `geometry.hg2007_half_thickness`, so the solid's wetted curve *is* the fluid's — assert that to
    1e-12. No tie constraint at the root. 30 mm aluminium teardrop + 60 mm steel plate,
    `E = 2.05e11`, **structural root at x = 30 mm**. Model the teardrop as a **fully prescribed
    (kinematically rigid) region** (`Ndriven` = every node with `x ≤ 0.030`, dof 1 fixed, dof 2
    driven), not a stiff material. Plunge via `*BOUNDARY` + `*AMPLITUDE` from
    `FlappingKinematics(stroke_plane_deg=90, pitch_amplitude_deg=0)` — ADR-024's `(1−cos)` ramp,
    do not re-derive. `*AMPLITUDE` is **linearly interpolated**: sample it densely and assert
    `max|table − analytic| < 1e-6·a`. `NLGEOM` on (the TE deflects ~9 % of the plate length).
    **The pitch is NOT prescribed** — it arises from the flexibility.
    Note `*BOUNDARY Nall, 3` is plane **strain**: effective modulus `E/(1−ν²) = 2.253e11`, so the
    naive `Eb³/12` hand-check is 10 % off. Record it.
    The prescribed nose **is** part of the preCICE interface (mesh motion needs it, P3 needs it,
    ccx folds its `*CLOAD` into `RF`). With `ALPHA=0` and no damping, `⟨Σ RF·v⟩ = P2` exactly —
    that is what makes D10 a closure check *and* a check that `ALPHA=0` held. Put it in the ADR.
  - `precice-config.xml` = committed template + renderer + re-read + `assert_config`, **not a
    writer**. `templates/SHA256SUMS` verified on every read; assert `found_tokens == _TOKENS`
    exactly before substituting; then check every token is observable in the parsed model — which
    **requires the additive `PreciceConfigExpectation` extension** (bite 7).
  - Upstream numerics: `parallel-implicit`, `max-iterations 50`, relative 5e-3 on **both**
    `Displacement` and `Force`, IQN-ILS + QR2, `initial-relaxation 0.5`, `time-windows-reused 15`.
    **Scale the RBF `support-radius`** — upstream's `1.` is metres on a 0.09 m chord.
    `nearest-projection` + `nodes-mesh-with-connectivity` is the declared contingency.

**3. Phase 3C — dimensional fluid deck + readout.**
  - `aero/adapters/openfoam/flexible_foil.py`. Do **not** reuse `plunging_airfoil.py`
    (`RHO_INF = U_INF = 1.0`). `preciceDict` in the **perpendicular-flap shape** (single interface,
    `locations faceCenters`, `readData (Displacement)`, `writeData (Force)`) with dimensioned
    `rho … 1000`. `dynamicMeshDict`: `displacementLaplacian` + `diffusivity quadratic
    inverseDistance` (already a free string — no signature change). `backward` in `fvSchemes` (add
    `ddt_scheme=` to `transient_fvschemes` additively; the default must still render the exact
    existing bytes — `tests/stage_11/test_dynamic_mesh_writers.py:62-63`). **`adjustTimeStep no`,
    fixed `deltaT`** — that is what makes the A-family's bitwise t-grid equality reachable.
    `movingWallVelocity` on the moving wall. Name the FOs exactly `forces1` / `forceCoeffs1`.
    **Pre-register `first_cell_height = 5.0e-4 c` and `n_te` per rung** (bite 5).
  - Promote `_read_force_history`, `_read_coefficient_dat`, `_strictly_increasing_mask` into
    `aero/adapters/openfoam/force_io.py` under public names; re-bind the privates — three external
    consumers: `tests/stage_10`, `tests/stage_11`, `scripts/stage16_urans_cert.py`.
  - **Two watch-points** (solid LE and TE), both in `HG2007_EXPECTATION.watch_points` so a
    coordinate typo aborts at `prepare`. The LE one is **not tautological** about what actually
    breaks (the `*AMPLITUDE` interpolation, units/scale, the vertex snap, `dt` == window size, the
    ramp) but it *is* tautological about the fluid mesh — so add a `patchProbes` at the LE on the
    moving `airfoil` patch and pre-register `max|y_probe − y_LE,solid| ≤ 1e-6 m` as a C-clause.
    The LE/TE pair gives the pitch. **Kinematics analytic, never differenced.**
  - **Input power three ways, cross-checked:** P1 `−⟨F_y·ẏ_LE⟩` (rigid arm only — and reconcile
    the phase convention: `MotionKinematics` is `A sin(ωt)` with no ramp, `FlappingKinematics` is
    `a·e(t)·cos(ωt)`), P2 a coded OpenFOAM FO integrating `∮(traction·v)dS`, P3 CalculiX reaction
    power via `*NODE PRINT, NSET=Ndriven, TOTALS=ONLY` + `RF` with `v` analytic. Pre-register rigid
    `|P2−P1|/P1 ≤ 0.005` and both arms `|P3−P2|/P2 ≤ 0.02`; report `(P1−P2)/P2` on the flexible arm
    — that IS the bias the naive formula would have put inside the gated increment. `η` from **P2**.
    `dynamicCode` works under the existing `setpriv` uid-1000 path; verify with a <60 s probe in a
    **scratch** dir, never the campaign case (I6). Also have the FO write its own `Fx,Fy` solely to
    compare against `forces1` at 1 %.
  - **ccx `.dat` cadence — do not assume:** classify structurally. `duplicates == 0` ⇒ per-window;
    `duplicates == Σ(iterations) − n_windows` ⇒ per-iteration, keep the **LAST** row at each time;
    anything else RAISES. Then a third assertion the earlier prompt omitted:
    `len(kept) == round(max_time/dt)` **and** `kept_times == watchpoint.t` bitwise.
  - `analyse_limit_cycle`: add optional `period: float | None = None` (default ⇒ FFT, bit-identical
    to Stage 19) + additive `period_source`; `fundamental_frequency` must become `1/period` on the
    prescribed path. New `aero/vv/alignment.py` for the A-family: bitwise-equal raw `t` over the
    paired window, bit-identical prescribed periods, **bitwise-equal segmentation anchors**, and
    re-indexing to the first prescribed cycle boundary at or after the discard —
    `paired_delta_uncertainty` pairs by index off each arm's *own* anchor and nothing raises today.

**4. Phase 3D — CLI.** `_build_solver` hard-wires `TUREK_HRON_FSI3_EXPECTATION` into every
`precice` solver — move the expectation onto the source. `stage_str` table + per-case `stage = "20"`
(replaces the hard-code at `cli.py:652`). `_SOLVER_SIF["precice"]` → both SIFs, and **pass
`extra_container_sifs=`** — the gap is two-part, and fixing only the assertion would make every
two-SIF CLI run fail with an empty roster. **The CLI path never calls
`assert_provenance_describes`.** Register in **all three** `FSI_CASES` sites (`vv list` :519,
`vv run` :606, `vv report`'s `registered` set :755 — note a registered case with no run reports
`missing` and denies ALL GREEN, so registration and execution are coupled). Add
`aero.vv.alignment` and `aero.adapters.openfoam.force_io` to `import-platform-only.yml`.

**5. Phase 4 — ADR-037 (authored-case architecture), flip ADR-038 to `accepted`, and ADR-039 (the
gate block) BEFORE any campaign run.** Mirror ADR-036 in form byte-for-byte: pure ASCII, ` - ` not
em-dashes, family headers at column 0, clauses at two-space indent, continuations at five.
(Measured target shape: 150 lines, ~10.4 k chars, indents ∈ {0, 2, 5}, max width 90.)
Families P/C/I/R/K/S/**A**/D/**M**/X + VERDICT + BUDGET + CONTINGENCIES.
  - **P must be rewritten, not copied** — ADR-036's P3 ("a gated run spanning more than one SIF is
    structurally refused") is now FALSE. Cite `assert_provenance_describes` + the roster + the
    `container_sif_set` tag. CalculiX is **2.20** + adapter v2.20.1 (verified in the SIF).
  - **I5 = degradation vs the recorded static baseline** (bite 4). **I6** = the coded-FO probe.
    **I7 (new) = a MEASURED max-Courant probe**, run *before* this ADR freezes, so the B-family is
    pre-registered against a measurement and not against arithmetic. Pre-flight FAILS on `Co > 1`.
  - **A-family:** bitwise-equal t-grids; the **prescribed** period, bit-identical between arms;
    bitwise-equal anchors; one absolute pre-registered discard; the settled-cycle ladder below;
    `correlation` / `variance_reduction` reported, never gated.
  - **D-family:** D0 pitch amplitude 5.35°, D1 `C_T` 1.008, D2 `η` 0.1753, D3 `ΔC_T` 0.609,
    D4 `Δη` 0.0865, D5/D6 signs (**no band**), D7 admissibility, **D8 rigid-arm pitch ≤ 2°**,
    D9/D10 the power identities. **M**: `|C_T,rigid − C_T,rigid,HG| / C_T,rigid,HG ≤ 0.58`,
    ADR-022's measured envelope as a regression bound, **above the 0.50 cap by construction** —
    say in the M header that it is a different rule, or a reader reads 0.58 as a relaxed D.
    Consider **M2**, the same regression bound on the *increment*, so the record separates
    "outside reference uncertainty" from "outside the platform's own known error envelope".
  - **The bands are already computed** (§6.13): D0 0.25 (floor), D1 0.25 (floor), D2 0.40,
    D3 0.25 (floor), D4 0.25 (floor). The cap never binds; the floor binds four of five.
    **Say plainly that for D3/D4 the 4× rule is decorative and 0.25 is a policy number**, and that
    ADR-022's −28 %/+58 % envelope makes a NO-GO on D3 at least as likely as one on D1. Note the
    asymmetry (the rigid arm's absolutes sit in M, not D) explicitly, or it reads as cherry-picking.
  - **Record why the selection rule changed**: "largest `ΔC_T`" is degenerate because `C_T ~ St²`;
    replaced by `Δ(C_T/St²)` inside HG's own `0.2 < St < 0.4` band. The optimal plate thickness
    MOVES with St, so plate and St are chosen together.
  - **Two improvements on ADR-036 + the regex fix:** name EVERY gated clause in the VERDICT line
    (ADR-036 omitted S5 and left I4 neither gated nor listed); add **shape-7** (every clause id is
    in the VERDICT line or the reported-only list, **and the two sets are disjoint** — that second
    half is exactly the I4 gap); add **shape-8**, ORDERED `(clause, band)` parity plus an ordered
    band-less registry. ADR-036's regex `r"^\s+(D\d) [^\n]*within (\d+) %"` has three defects:
    `D\d` matches **`D10` as `D1`**, `(\d+) %` cannot express D9's 0.5 %, and `^\s+` also matches
    five-space continuations. Anchor at exactly two spaces, `[A-Z]\d{1,2}`, fractional percents,
    `(no band)` as an alternative, and guard that no clause line carries two band tokens.
    **Mutation-test the tests** in-process on a mutated copy of the block string, not by editing
    the ADR: delete a clause id, swap two bands, drop one from VERDICT, give a band to a no-band
    clause — each must turn a parity assertion red.
  - **Both the absolute bands AND the increment sit in the VERDICT line** (operator decision).
    Design the verdict to resolve **clause by clause** — write it so `GO(D3,D4,D6,D7,D9,D10) /
    NO-GO(D1,D2)` is expressible *in the bundle*, not just in prose. Note §6.8's finding that HG's
    rig was deliberately nominally 2-D (end plates, gap < 3 % chord): that *weakens* ADR-022's
    2-D-vs-3-D root cause and therefore makes a D1 NO-GO harder to explain away. It belongs in the
    ADR before the run, not in the post-hoc discussion.
  - **B-family — operator decisions, both departures from earlier prompts (§6.11):**
    * **Settled-cycle ladder:** ≥20 settled cycles on the rung carrying the paired increment,
      ≥10 on the GCI-only rungs (`DEFAULT_MIN_SAMPLES` is 8, so 10 is a declared margin, and a GCI
      needs converged *means*, not tight variances).
    * **Two launch waves:** wave 1 = coarse + mid (4 runs), wave 2 = fine (2 runs). The 7-day
      ceiling applies **per wave**. Removes contention and gets the headline increment out first.
    * **Pre-register the sizing RULE, not the numbers.** Commit A = ADR-039 complete and final with
      B2 carrying the rule plus a `<<B2-PENDING-I4>>` marker. Commit B = the I4/I7 record
      (`data/vv/stage20_i4_calibration.json`) with its own four-fold tuple and clean-tree git_sha.
      Commit C = fills the marker **only**. Land a committed **pure sizing function** in commit A,
      tested there against synthetic I4 records, plus
      `tests/stage_20/test_adr039_budget_is_derived_from_i4.py` which re-applies it to the real I4
      JSON and asserts equality — so the numbers are an output, not a decision. The driver refuses
      a gated run unless `git merge-base --is-ancestor <ADR-039 first commit> <I4 record>` holds,
      with the first-commit SHA obtained at run time from
      `git log --reverse --format=%H -- docs/adrs/ADR-039-*.md | head -1`, never hard-coded.
      Record the full `git log --format="%H %ct %s" -- docs/adrs/ADR-039-*.md` in the bundle.

**6. Phase 5 — pre-flight**: I1 solverdummy across two SIFs; I3 mesh + counts (**re-measure with
`first_cell_height = 5.0e-4 c`; the spike's 48 240 / skew 2.40 are from the 2e-6 mesh**); I7; I5
static baseline + degradation probe; I6; then **I4 calibrations that COMPLETE ≥200 windows and end
`all-exited`, for both arms at every rung**. **Do not extrapolate a rate from the transient** —
Stage 19 was off 3.5-9.6× one way and its B3 diagnostic ~1.8× the other; a run that died after a
few windows yields no s/window figure at all. Pre-register: fixed coupling `time-window-size`
across all rungs, chosen from the FINEST rung's Courant requirement (else a spatial GCI is
contaminated by temporal error, and Courant drifts toward ADR-030's measured spurious-attractor
threshold between Co 4 and Co 8); refine the solid by the same ratio as the fluid; build the ladder
DOWNWARD.

**7. Phase 6 — launch wave 1** (coarse + mid, 4 coupled runs) concurrently on aero-dev via
`run_long.sh` with unique session names and `AERO_RUN_LONG_REAP=1`. Then update the handoff
(`status: partial`, **no tag, no verdict**). Phases 7–9 (wave 2, GCI + paired U95 +
clause-by-clause verdict, adversarial review, tag) are further sessions.
`compose_improvement(kind="time_averaged", paired=…)`: Stage 20 is its FIRST production caller —
drive it on synthetic per-cycle series in unit tests first, do NOT pass `baseline`/`improved` (the
validator raises), and note `u95_delta_input_frac` multiplies `|paired.mean_baseline|`, i.e. the
RIGID arm's mean.

HARD DON'TS
- Never relax a pre-registered band. Pre-register BEFORE any campaign run.
- Do not cite Stage 19's numbers as Stage 20 evidence (ADR-016).
- Fail loud on non-converged coupling and unreached periodic steady state.
- **Do not re-capture the Phase-3A goldens.** They are the pre-refactor record; re-capturing them
  after the refactor destroys the only evidence the refactor was non-regressive.
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

- **One commit per coherent unit**, each with a body saying *why*, not just *what*.
- **Record every number you measure**, not just the ones that passed — s/window and
  iterations/window per arm per rung (I4), the measured Courant (I7), the static mesh-quality
  baseline (I5), the three power routes P1/P2/P3 and their pairwise deltas, the ccx `.dat` cadence
  classification (K3).
- **Every band in ADR-039 must be traceable to a row in `hg2007_recomputed.csv`** via the stated
  multiplier rule, with the raw multiplier printed beside the applied number.
- **If you deviate from this prompt, say so in the handoff's §3** with the evidence that forced it.
  Deviating is fine; deviating silently is not.
- **If a gate fails, stop and record it.** Never widen a band, never re-pick a window, never
  re-run until it passes. A NO-GO with evidence is a result; a GO obtained by adjustment is not.
- Update `docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` **as you go**.
- Final state must be: clean tree, pushed, PR #44 checks green, `pytest -q tests/unit
  tests/stage_20` green, and nothing running on aero-dev that you did not intend to leave running.
