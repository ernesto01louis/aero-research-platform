Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul). RESUMING a partial stage (session 7).

**THIS FILE IS THE SINGLE SOURCE OF TRUTH FOR STAGE 20.** Six sessions have run and each left a
resume prompt behind; the earlier ones are superseded and must not be followed. If you find
instructions anywhere else that contradict this file, this file wins. In particular:

- `/root/.claude/plans/stage-20-flexible-typed-pinwheel.md` — SUPERSEDED (session 1). Stale on `h`,
  on the element choice, on the Phase-6 sizing.
- `/root/.claude/plans/stage-20-flexible-cryptic-umbrella.md` — SUPERSEDED (session 3).
- `/root/.claude/plans/stage-20-flexible-refactored-aurora.md` — session 4's roadmap. Still USEFUL:
  it carries the commit-by-commit sequence referenced below and a costed pre-flight ordering. Read
  it second.
- `tage-20-flexible-warm-beacon.md` — a path some earlier prompts named. Ignore it.

---

## 1. Where this stage sits

Stage 19 (`v0.0.19`, GO) built `aero/adapters/precice/` and verified it on the *supported upstream*
Turek-Hron FSI3 tutorial — OpenFOAM fluid + Nutils solid, **one container**, 8000/8000 windows
converged, all five displacement bands passed. That claim is **coupling correctness**.

Stage 20's claim is **application fidelity**, and ADR-016 requires the two never blur: a
chordwise-flexible plunging foil, OpenFOAM fluid + **CalculiX** solid across **two** containers,
validated against **experiment** (Heathcote & Gursul 2007). Different solver, different physics,
different reference. **Do not cite Stage 19's numbers as Stage 20 evidence.**

It is the last physics stage before the v0.1.0 checkpoint.

## 2. What the four sessions actually did

| session | date | commits | what landed |
|---|---|---|---|
| 1 | 2026-07-30 | `4fb6ce2`..`40503e6` (8) | opened the stage; rc=255 made loud; **ADR-038** multi-container provenance + Postgres migration `005`; perpendicular-flap acquired and the **CalculiX smoke PASSES on two containers**; HG reference acquired (text-sourced only); partial handoff |
| 2 | 2026-07-31 | `a161903`..`4765683` (11) + operator `85e0b32` | migration verified against 1280 rows; **figure digitization COMPLETE** (208 markers) and `hg2007_recomputed.csv` written, R2 passes; **operating point FIXED**; `TeardropPlateSection` in the C-grid, mesh spike passes; operator fixed `run_long.sh` stranding solves |
| 3 | 2026-08-01 | `30aa126`..`a007689` (4) | **the two non-regression pins** (`67d8e82`) on pre-refactor code — the stage's most important ordering rule, done right; found the campaign does not fit its ceiling (§6.11), proposed **I7**, found `PreciceConfigExpectation` needs extending (§6.12), computed the bands (§6.13) |
| 4 | 2026-08-04 | `1bd7011`..`b4bc801` (4) | **the `source` seam refactor**, the **`PreciceConfigExpectation` extension**, the **`transient_fvschemes` byte pin**; four operator decisions taken; **I3/I5 static baseline measured**; three corrections to the work-of-record (§6.14-§6.16) |
| 5 | 2026-08-05 | `397af1c`..`b9f317f` (10) | **EVERY WRITER AND READER THE AUTHORED CASE NEEDS** — config template + renderer, CalculiX deck writer/re-reader, dimensional fluid deck, interface-power FO, force_io, `ddt_scheme=`, per-cycle limit-cycle objects, `alignment.py`, `.dat` reader. Pre-flight **S1, I6 and I3 pulled forward and PASSED**. Host rebooted mid-session; nothing lost |
| 6 | 2026-08-06 | `227ffed`..`d6f0b99` (7) | **THE AUTHORED CASE MATERIALIZES, HAS A V&V OBJECT, AND IS WIRED.** `_materialize`/`_render_manifest`/`load` all dispatch on the source; 18 files written and re-read; `aero/vv/fsi/{hg2007_flexible_foil,hg2007_readout}.py`, both arms registered; Phase 3D closed ADR-038's residual. **Two silent-wrong-number defects fixed** (§6.22, §6.23), one from the adversarial review. **ADR-037 written, ADR-038 accepted.** Smoke re-passed at HEAD |

Suite 348 (Stage-19 close) → 380 (s3) → 418 (s4) → 581 (s5) → **672** (session 6). Branch
`stage-20-flexible-flapping-wing-fsi`, PR **#44** (DRAFT), clean tree, pushed, aero-dev idle.

## 3. DONE AND VERIFIED — do not redo, do not re-derive

- **CalculiX is genuinely in the loop.** Two SIFs, 50/50 windows converged at mean 2.14 iterations,
  both participants rc=0. Re-verify in ~35 s:
  `python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5`
- **Multi-container provenance** (ADR-038); migration `005_container_set` APPLIED and verified.
- **The HG2007 reference of record is complete.** `digitization.csv` (208 markers, Figs 5.6a/b/c +
  5.9a + 5.13a), `hg2007_recomputed.csv`, and the two acquisition scripts. **R2 passes on all five
  anchors.**
- **The gated operating point is FIXED** from the reference alone, before any solve:
  **Re = 9000, St = 0.345, flexible `b/c = 0.85e-3` (76.5 um) vs rigid `b/c = 4.23e-3` (380.7 um)**
  ⇒ `U = 0.1 m/s`, `f = 0.9857 Hz`, `T = 1.0145 s`; `c = 90 mm`, `a = 17.5 mm`, **`h = 0.194`**,
  water (`rho = 1000`, `nu = 1e-6`), rig span 300 mm. Reference: `C_T` 1.008 / 0.398
  (`dC_T` 0.609), `eta` 0.1753 / 0.0888 (`d_eta` 0.0865), pitch amplitude 5.35 deg.
  Any derived `f` outside the rig's stated 0.3-2.5 Hz range means the setup is wrong.
- **Phase 3A is COMPLETE.** The two pins landed alone at `67d8e82` on pre-refactor code; the
  refactor landed at `1bd7011`. The ordering held and is checkable:

      git merge-base --is-ancestor 67d8e82 1bd7011                   # true
      git diff --stat 67d8e82 1bd7011 -- tests/stage_20/fixtures/    # EMPTY
      git diff --stat 67d8e82 1bd7011 -- tests/stage_20/test_stage19_load_path_unchanged.py
                                                                      # EMPTY

  **Do NOT re-capture the goldens.** They are the pre-refactor record.
- **`PreciceConfigExpectation` is extended** (`10fcb70`): 15 additive fields, all defaulting to
  "do not check", each driven with a wrong value in a parametrized test.
- **`transient_fvschemes` is byte-pinned** (`c682671`): laminar 781 B / `1df84e21...`,
  kOmegaSST 886 B / `4edd1332...`, kOmegaSSTLM 958 B / `3703fe5c...`.
- **The I3/I5 static baseline is MEASURED** at the pre-registered `first_cell_height = 5.0e-4 c`
  (handoff §6.16). Cell counts **45 682 / 77 240 / 130 032** — uniform refinement ratio 1.30.

## 4. WHAT DOES NOT EXIST — verified with `ls`, not inferred from prose

*Sessions 5 and 6 built every writer, the materializer, the readout and the V&V case object.
What is left is the CLI wiring, the ADRs, the pre-flight and the campaign.*

    docs/adrs/ADR-039-*.md                     (the gate block — NOTHING may run before it)
    scripts/stage20_hg2007_flexible_foil.py    (the campaign driver)
    tests/unit/test_adr039_*.py                (the binding tests — tests/unit, NOT stage_20)
    data/vv/stage20_i4_calibration.json        data/vv/stage20_i3_mesh.json

**No campaign has run. No verdict exists and none may be made, because ADR-039 does not
exist** — and, since session 6, that is also STRUCTURAL: `GATED_TIME_WINDOW_S` and
`GATED_MAX_TIME_S` in `hg2007_flexible_foil.py` are `None` until ADR-039 B2 records the I7 and
I4 measurements, `is_gated_configuration` returns `False` while they are, and `gated` is
DERIVED. No configuration can claim the gated verdict before the pre-flight has run.

**These now EXIST and are tested — do not rebuild them:**

    aero/adapters/precice/template.py          aero/adapters/precice/templates/
    aero/adapters/precice/calculix.py          aero/adapters/precice/ccx_dat.py
    aero/adapters/openfoam/flexible_foil.py    aero/adapters/openfoam/force_io.py
    aero/vv/alignment.py
    aero/vv/fsi/hg2007_flexible_foil.py        aero/vv/fsi/hg2007_readout.py

**The authored case materializes end to end** (`227ffed`). `PreciceCoupledSolver._materialize`,
`_render_manifest` and `load` all dispatch exhaustively on `source.kind`; an authored spec
writes 18 files under `<root>/<case_dir_name>/`, every one re-read, with a schema-v2 manifest
whose `spec_sha256` is computed by CALLING `config_hash`. The **physical spec rides on
`AuthoredSource`** (ADR-037): `config_hash` covers the geometry, and the two arms — which
differ in one number — no longer hash identically.

**Both arms are registered V&V cases** (`21840e0`). `metrics()` carries only what ONE arm can
measure; the D3/D4 increment needs both and belongs to the campaign driver, so **it has no V&V
dashboard row and ADR-039 must say so**. D5/D6/D7 live in a band-less `predicates()` registry
carrying a literal `(no band)` token; D7 raises, D5/D6 report.

## 5. NINE THINGS THAT WILL BITE YOU IF YOU SKIP THE HANDOFF

1. **`h = 0.194`, not 0.175** (§6.7). 0.175 is the *other two* Heathcote experiments.
2. **No raw PDF digest is reproducible here** (§6.6) — use `pdf_content_sha256` / `page_raster_sha256`.
3. **This thesis's blanket "for all Re" prose is not evidence** (§6.8): the crossover claim misses
   by 12.6 % at the gated Re, while its condition-specific prose reproduces to 0.1 %.
4. **I5 must gate DEGRADATION against the recorded static baseline**, never an absolute threshold
   (§6.9 + §6.16). Measured: checkMesh reports "Non-orthogonality check OK" at 85.23; the one
   failing check is **aspect ratio**, and it is byte-identical (1884.4471) on the platform's own
   stock NACA 0012. So **M1 ("Mesh OK") and M2 (non-ortho) are both unusable as absolute gates** —
   they fail the platform's own production airfoil mesh. Gate degradation + absolute skew <= 4 +
   zero negative volumes.
5. **The flexible plate is the campaign's clock** (§6.11). `first_cell_height` defaults to `2.0e-6`
   chords and is unrunnable; **`5.0e-4` is pre-registered**. The binding limiter is then the
   flexible arm's blunt-TE base, ~5x tighter than the rigid arm, and the paired A-family forces
   both arms to share it.
6. **`load()` emits 23 scalars, not 20**; `_write_case` is `PreciceCoupledSolver._write_case`.
7. **Three silent failure modes in the authored case** (§6.12): the CalculiX slab's z-thickness
   must equal the OpenFOAM `span` or the plate is under-loaded 400x while everything converges;
   `INC` must be **computed** (`>= 10*ceil(max_time/dt)`), never copied, or ccx exits **0** mid-run
   and K2 *passes*; and the RBF `support-radius` must be scaled (upstream's `1.` is one metre on a
   0.09 m chord) — now assertable thanks to `10fcb70`.
8. **A nullable XOR pair is forgeable** (§6.14). `model_copy(update=...)` bypasses
   `@model_validator(mode="after")`, and `case.py` uses that idiom twice. This is why
   `MaterializedTree` carries ONE `source` field. Generalise it: any invariant expressed only as an
   after-validator is bypassable here.
9. **ADR-036's band regex silently DROPS `D9` and `D10`** — it needs a literal space after the id,
   so `D10 ` never matches. The phantom pair comes from `^\s+` matching **five-space continuation
   lines**, and greedy `[^\n]*` reports the **last** band on a line mentioning two. Earlier prompts
   and §6.13 say "D\d matches D10 as D1"; that is wrong, and silent omission is strictly worse for
   a parity test. The replacement must anchor at exactly two spaces, use `[A-Z]\d{1,2}`, accept
   fractional percents and `\(no band\)`, be **non-greedy**, and guard one band token per line.

## 6. OPERATOR DECISIONS — settled, do not re-litigate

From sessions 1-3 (handoff §2, §7):

- Plunge driven from the **solid's** leading edge; **the pitch is NOT prescribed** — it arises from
  the flexibility. Prescribing it would model a different experiment.
- CalculiX **3-D slab of `C3D8I`, dof 3 suppressed**, not plane stress (§6.1).
- Solid geometry settled: 30 mm aluminium teardrop + 60 mm steel plate, `E = 2.05e11`,
  **structural root at x = 30 mm**. The teardrop is a **fully prescribed (kinematically rigid)
  region**, not a stiff material.
- The rigid control is the **same coupled path with a stiffer plate** (`b/c = 4.23e-3`), which HG
  measured — so both ends of the increment carry an experimental anchor.
- **Both the absolute bands AND the increment sit in the VERDICT line**, knowing ADR-022 makes a
  NO-GO on the absolute clause a live outcome. The verdict must resolve **clause by clause** so
  "NO-GO on absolute fidelity, GO on the flexibility increment" is expressible *in the bundle*.
- The paired path segments on the **prescribed** period, never an FFT-detected one.
- **Settled-cycle ladder**: >=20 settled cycles on the rung carrying the paired increment, >=10 on
  the GCI-only rungs. **Two launch waves.**
- **Pre-register the sizing RULE, not the numbers**: ADR-039 commit A carries B2 with a
  `<<B2-PENDING-I4>>` marker and a committed pure sizing function; commit B is the I4 record;
  commit C fills the marker only.

From session 4:

- **Time scheme: `backward` IF AND ONLY IF checkpoint fidelity is proved, else `Euler`.** Every
  preCICE OpenFOAM tutorial uses `Euler`; second order under *implicit* coupling needs the adapter
  to checkpoint `U.oldTime().oldTime()` every coupling iteration and nothing establishes it does.
  Build the probe as a **reusable pre-flight clause I8** in `aero/vv/` — 5 windows implicit vs the
  same 5 at `max-iterations 1`, comparing window-start field state. Either way the claim is
  measured. If it fails, `Euler` is defensible: a fixed coupling time-window-size across rungs makes
  temporal error common-mode, so it does not contaminate the spatial GCI.
- **`NLGEOM` ON unconditionally.** B2 is sized for whatever it costs; I4 must report the multiplier.
- **D9 is REPORTED-ONLY; D10 stays gated.** D8 admits 2 deg of rigid-arm pitch, worth 12 % TE
  velocity, and P1 assumes a single rigid-body velocity — D8 and D9 could not both be satisfiable.
  Report `(P1-P2)/P2` on **both** arms as the measured bias the naive formula would have injected.
- **Budget fallback: raise the ceiling, do not degrade the evidence.** Per-wave ceiling **14 days**,
  and **wave 1 is the rung carrying the paired increment (both arms)**; wave 2 is the two GCI-only
  rungs. Cutting settled cycles and accepting a budget NO-GO are the last resorts, in that order,
  and only if 14 days per wave is also exceeded.

## 6b. FIVE MORE THINGS MEASURED IN SESSION 5 (handoff §6.17-§6.21) — do not re-derive

1. **CalculiX truncates every numeric field at 20 characters.** A deck written at `%.16e`
   (22 chars) made ccx 2.20 reject EVERY numeric card with rc=201 before a single increment.
   `%.13e` works. A double needs 17 significant digits and does not fit, so chosen values
   (dt, max_time, span) are required to be exactly representable and derived ones are
   asserted to 1e-12 m.
2. **A 70 005-row `*AMPLITUDE` table reads fine** (rc=0, ~2.9 s). Per-window sampling stays.
3. **The `.dat` is a four-line record with a SEVEN-significant-digit time**, not a table.
   Ten real records are committed as a fixture. Under implicit coupling a time repeats per
   ITERATION — classified structurally, never assumed.
4. **The coded interface-power FO compiles under `setpriv --reuid 1000`** and its force sum
   matches `force.dat` to 12 significant figures; on a stationary mesh its power is −4.3e-18,
   which proves it reads the WALL velocity.
5. **At `farfield_extent_chords = 20` all six decks pass checkMesh outright.** Cell counts
   reproduce §6.16 exactly (45 682 / 77 240 / 130 032) and non-ortho to four significant
   figures, but aspect ratio is 309.9 not 1884.4, so `Mesh OK` PASSES. §6.16's argument still
   stands; Stage 20's own mesh simply has no pre-existing failing check. Still a
   measurement, not a record — the I3/I5 pre-flight must re-run it into `data/vv/`.

## 6c. FOUR THINGS SESSION 6 FIXED OR FOUND — do not re-derive (handoff §6.22-§6.25)

1. **The fluid and solid readers kept DIFFERENT coupling iterates.** `force_io` kept the
   FIRST row at a repeated time, `ccx_dat` the LAST; under implicit coupling `force.dat`
   repeats per iteration, so `C_T` came from the accelerator's first guess and `P2`/`P3` from
   the converged solve. Invisible to every downstream check, and **the bias differs between
   arms**, so it landed in `dC_T` and `d_eta`. Fixed additively — `repeats="first"` is still
   the default so no Stage-10/11/13 record moves; the coupled readout passes `"last"` and
   `classify_repeat_cadence` proves the repeat count against the iterations log, RAISING on
   anything unexplained.
2. **`align_arms` could attest to a time base it never compared** (adversarial review, six
   refuter votes). The raw-time check needed BOTH arrays; `n_samples` was derived from one.
   Now all-or-nothing, `n_samples` is `int | None` bound to `time_base_checked`, and **the
   segmentation-anchor clause is unconditional** — `t_start - converged_from_cycle * period`
   recovers the post-discard origin from fields both analyses already carry, so no raw times
   are needed. Equal `discard_s` does NOT imply equal origins.
3. **`tests/stage_20` is not in CI.** `test.yml` runs `pytest -q tests/unit` only, so 664
   green is not 664 enforced. **ADR-039's binding tests must go in `tests/unit/`**, beside
   `test_stage19_gate_block_sync.py`. Corollary: FSI3's `config_hash` embeds absolute host
   paths, so `3f94f394...` is a property of THIS checkout — ADR-037 must say so.
4. **`forces1` writes its registered fields every time step** (`writeFields yes` at
   `writeControl timeStep; writeInterval 1`), which `purgeWrite 2` does not track. `writeFields`
   is REQUIRED — the interface-power object looks the field up — so **I4 must count the time
   directories and `du` them before B2 is sized.** A full NFS four days into a 14-day wave is
   the failure mode.

## 7. YOUR TASK, IN THIS ORDER

Each commit must leave `pytest -q tests/unit tests/stage_20` green. The full commit-by-commit
sequence with rationale is in `/root/.claude/plans/stage-20-flexible-refactored-aurora.md`;
session 5's own plan, which that sequence was executed from, is
`/root/.claude/plans/stage-20-flexible-logical-kay.md`.

**START HERE (session 7): ADR-039, then the campaign driver, then pre-flight, then wave 1.**
Phases 3A/3B/3C, the V&V case object and Phase 3D are all DONE (sessions 4-6), and **ADR-037
and ADR-038 are both `accepted`**. What is left is the pre-registration, the driver that
byte-duplicates it, the I-clauses and the campaign.

Three things make ADR-039 cheaper than it looks, and one makes it safer:

- the ORDERED band registry already exists as `hg2007_flexible_foil.CLAUSE_BANDS`, with
  `(no band)` as a first-class value — shape-8 has a real object to compare against;
- shape-7's property (gated XOR reported-only, disjoint and exhaustive) is already asserted
  against that registry by `test_the_gated_and_reported_only_sets_are_disjoint_and_exhaustive`;
  what is missing is the ADR side;
- **the binding tests go in `tests/unit/`** — `tests/stage_20` is not in CI (§6c item 3), so a
  parity test living there would never run;
- **`GATED_TIME_WINDOW_S` / `GATED_MAX_TIME_S` are already `None`** and
  `is_gated_configuration` returns False while they are, so no configuration can claim the
  gated verdict until the pre-flight fills them. The "pre-register before any campaign run"
  ordering is structural now, not a rule to remember.

**Phases 3B and 3C below are DONE except where noted** — kept for the rationale, which is
still the specification the code was written against.

**Phase 3B — authored-case integrity (DONE, `397af1c` + `460d972`).**

- **C3 `precice-config.xml` template + renderer.** Committed template under
  `aero/adapters/precice/templates/` + `SHA256SUMS` verified on every read + renderer + re-read +
  `assert_config`, **not a writer**. Assert `found_tokens == _TOKENS` exactly before substituting,
  then check every token is observable in the parsed model — which `10fcb70` finally makes
  possible. Upstream numerics: `parallel-implicit`, `max-iterations 50`, relative 5e-3 on **both**
  `Displacement` and `Force`, IQN-ILS + QR2 (`limit 1e-2`), `initial-relaxation 0.5`,
  `max-used-iterations 100`, `time-windows-reused 15`. **Scale the RBF `support-radius`.**
  `nearest-projection` + `nodes-mesh-with-connectivity` is the declared contingency.
- **C4 `aero/adapters/precice/calculix.py`** — typed `.inp` writer **plus a re-reader**, and a
  ~20-line `config.yml` reader (no YAML dep — Invariant 1). Highest-value assertions: `*CLOAD` on
  the interface nset exists with dofs {1,2,3} all present and all exactly `0.0` (the adapter
  OVERWRITES it — missing, the run is silently force-free); `ALPHA` present and `0.0`; `DIRECT`
  present and `dt == time-window-size`; `C3D8I` not `C3D8`; `NLGEOM` on;
  **`INC >= 10*ceil(max_time/dt)`**; and **new clause C6: the slab z-extent equals the emitted
  `blockMeshDict` span**. The reader must assert `"N" + patch == interface_nset`,
  `read-data == [Force]` (**not** FSI3's `Stress`), `write-data == [Displacement]`, and that the
  mesh name matches the rendered XML's.
  One structured `NX x NY x 1` block over the WHOLE section with y from
  `geometry.hg2007_half_thickness`, so the solid's wetted curve *is* the fluid's — assert to 1e-12.
  Plunge via `*BOUNDARY` + `*AMPLITUDE` from `FlappingKinematics(stroke_plane_deg=90,
  pitch_amplitude_deg=0)` — ADR-024's `(1-cos)` ramp, do not re-derive; the table is **linearly
  interpolated**, so sample densely and assert `max|table - analytic| < 1e-6*a`.
  `*BOUNDARY Nall, 3` is plane **strain**: effective modulus `E/(1-nu^2) = 2.253e11`, so the naive
  `Eb^3/12` hand-check is 10 % off. The prescribed nose **is** part of the preCICE interface; with
  `ALPHA=0` and no damping, `<Sum RF.v> = P2` exactly, which is what makes D10 a real closure check.

**Phase 3C — dimensional deck + readout (DONE except the V&V case object,
`e229ecf`..`b9f317f`).** Every point below is implemented and tested; they are kept because
they are the reasons the code looks the way it does. What is NOT done: the V&V case object
(`hg2007_flexible_foil.py` + `hg2007_readout.py`), which needs the authored materialization
above first.

- **The `controlDict` MUST carry the preCICE adapter function object** —
  `libs ("libpreciceAdapterFunctionObject.so")` + a `preciceAdapterFunctionObject`. No earlier
  prompt mentions it. Without it pimpleFoam runs a happy **uncoupled** solve to `endTime`, exits 0,
  and the Solid blocks to the ceiling.
- **The HG section emits TWO wall patches** (`airfoil` + `airfoil_te`), and all four of these must
  list both: every `0/` `boundaryField`, both force FOs' `patches`, the `preciceDict` interface, and
  the mesh-motion `moving_patch`. Dropping `airfoil_te` from the force FOs biases `C_T` on **one arm
  only** — straight into the gated increment. One test should parse the rendered `blockMeshDict`
  boundary block and assert the wall-patch set equals all four.
- **Do NOT route P1 through `propulsive_metrics`.** `MotionKinematics.velocity` is `Aw*cos(wt)`;
  the solid's plunge velocity is `-aw*sin(wt)` post-ramp — exactly 90 deg out of phase, so `p_in`
  becomes a quadrature integral ~ 0 and `C_P ~ 0`. Compute P1 from
  `FlappingKinematics.evaluate(t)["vy"]` directly.
- **`analyse_limit_cycle` must additionally expose `cycles: CycleSamples` and
  `convergence: CycleConvergenceReport`.** It currently discards both, and they are exactly the two
  arguments `paired_delta_uncertainty` needs — so the paired path cannot be called at all today.
  Worse, the two arms' tails are anchored at different `converged_from_cycle`, so naive index-`k`
  pairing is silently phase-shifted. `aero/vv/alignment.py` must assert bitwise-equal raw `t`,
  bit-identical prescribed periods and **bitwise-equal segmentation anchors**.
- **`eta` is a ratio of means, not a mean of ratios** — per-cycle `eta_k` needs its own helper
  before D2/D4 can go through the paired path.
- **`kept_times == watchpoint.t` bitwise is NOT achievable** across an ASCII round trip between two
  independent accumulators; reserve bitwise for the A-family's cross-arm watch-point comparison.
  Also set **`timePrecision 12`**: at `timePrecision 6` consecutive force rows collapse to the same
  string and `_strictly_increasing_mask` deletes them **silently**. Have `read_force_history` return
  `n_dropped` and raise on non-zero.
- ccx `.dat` cadence classified **structurally**: `duplicates == 0` ⇒ per-window;
  `duplicates == sum(iterations) - n_windows` ⇒ per-iteration, keep the **LAST** row at each time;
  anything else RAISES.

**Phase 3D — CLI (1 commit). START HERE.** Two of these are live faults, not tidying:

- **`_SOLVER_VERSIONS["precice"]` says `"... + Nutils 9.2"`** (`cli.py:47-51`) and
  `stage_str = "19"` for every precice run (`cli.py:650-659`). Both ride into MLflow tags, so a
  Stage-20 bundle would claim a **Nutils solid** and Stage-19 provenance. Key both by CASE
  (`_CASE_STAGE` + a per-case solver version), not by solver name — a table, not a Protocol change.
- **`assert_provenance_describes` still has ZERO call sites.** Without it a two-container run
  logs an empty roster and silently omits CalculiX: the ADR-038 residual this stage opened with.
  Derive `container_sif` + `extra_container_sifs` FROM THE SPEC (both are already properties on
  `CoupledCaseSpec`); do NOT widen `_SOLVER_SIF`, which is `dict[str, str]` feeding a single-SIF
  `compute_provenance`. Call it immediately after `compute_provenance`, before anything runs.
- Move the expectation off the `cli.py:115-121` hard-wire into a name-keyed registry with
  `Field(exclude=True)` so it stays out of `config_hash`. **Note the HG expectation is DERIVED
  from the spec** — `hg2007_expectation(spec.source.coupling_values())` — not a module constant
  like FSI3's, so the registry holds a callable or the solver builds it per case.
- The three `FSI_CASES` sites and `import-platform-only.yml` are **already done** (session 6:
  both arms registered, and the fence names the six new modules).

**Phase 3D is DONE** (`7f1d584`). Both faults above are closed and pinned by
`tests/stage_20/test_cli_coupled_provenance.py`.

**Phase 4 — ADRs, BEFORE any campaign run.** ADR-037 (authored-case architecture; record the two
honest divergences — FSI3's `config_hash` moved `c524faff...` → `3f94f394...`, and the driver's K1
became window-scoped, provably a no-op at `n_nonconverged: 0` over 8000/8000 windows); ADR-038 →
`accepted`; **ADR-039** (the gate block). Mirror ADR-036's form byte-for-byte: pure ASCII, ` - ` not
em-dashes, family headers at column 0, clauses at two spaces, continuations at five (measured
target: 150 lines, ~10.4 k chars, indents in {0, 2, 5}, max width 90). Families
P/C/I/R/K/S/**A**/D/**M**/X + VERDICT + BUDGET + CONTINGENCIES. **P must be rewritten, not copied**
— ADR-036's P3 ("a gated run spanning more than one SIF is structurally refused") is now FALSE.
CalculiX is **2.20** (verified live) + adapter v2.20.1. **B1 must be >= 21600 s**, not ADR-036's
3600 s: six I4 calibrations of >=200 windows do not fit an hour.

Bands are already computed (§6.13): D0 0.25 (floor), D1 0.25 (floor), D2 0.40, D3 0.25 (floor),
D4 0.25 (floor). **Say plainly that for D3/D4 the 4x rule is decorative and 0.25 is a policy
number.** Add shape-7 (every clause id is in the VERDICT line or the reported-only list, **and the
two sets are disjoint**) and shape-8 (ORDERED `(clause, band)` parity plus a band-less registry),
and **mutation-test the tests** in-process on a mutated copy of the block string.

**Phase 5 — pre-flight.** **S1, I6 and I3 are DONE** (session 5, §6b) but have no `data/vv/`
record with a four-fold tuple, so they are measurements and must be re-run into `data/vv/`
before ADR-039 cites their numbers. Ordered by leverage, not clause number: **I7 first**
(measured max-Courant
— Courant on a moving mesh uses the RELATIVE flux, so §6.11's wall-cell arithmetic is probably
conservative by a large factor, and `dt` decides the whole campaign), then I8, I6, I1, I3, I5, and
finally **I4 calibrations that COMPLETE >=200 windows and end `all-exited`, both arms, every rung**.
**Never extrapolate a rate from a transient.** Pre-flight FAILS on `Co > 1`; it never adjusts.

**Phase 6 — launch wave 1** (the paired-increment rung, both arms) via `run_long.sh` with unique
session names. **SUBMIT DETACHED; do NOT hold an owning `wait` across the session boundary.**
`AERO_RUN_LONG_REAP=1` makes `wait` the OWNER of the job's lifetime — on timeout or
SIGTERM/SIGINT/SIGHUP it kills the remote tmux session — which is right for CI and wrong for a
14-day campaign launched from a session that will end. Submitting is unaffected by the flag.
Poll with `run_long.sh status|logs` only, and record the session names and the poll commands in
the handoff so the next session resumes by polling. (Operator decision, session 6.) Then update
the handoff (`status: partial`, no tag, no verdict).

## 8. HARD DON'TS

- Never relax a pre-registered band. Pre-register BEFORE any campaign run.
- Do not cite Stage 19's numbers as Stage 20 evidence (ADR-016).
- Do not re-capture the Phase-3A goldens.
- Fail loud on non-converged coupling and unreached periodic steady state.
- **NEVER cancel a self-hosted CI job to free a runner** — it strands detached solves. Tell:
  runners `busy=true` while `gh run list` shows nothing `in_progress`.
- **Verify EVERY commit with `git log`.** Run `ruff format && ruff check --fix` before `git add`.
  Changing handoff frontmatter stales the README STATUS block — run `scripts/regenerate_status.sh`.
- `aero/` core is stdlib + numpy + pydantic only; add new modules to `import-platform-only.yml`.
- The multi-hour case is **driver-only**, never in `tests/vv`.
- **Never write a value into a provenance-bearing field you have not actually computed.**

## 9. AUDIT TRAIL

One commit per coherent unit, each with a body saying *why*. Record every number you measure, not
just the ones that passed. Every band in ADR-039 must be traceable to a row in
`hg2007_recomputed.csv` with the raw multiplier printed beside the applied number. If you deviate
from this file, say so in the handoff's §3 with the evidence that forced it — deviating is fine,
deviating silently is not. **If a gate fails, stop and record it.** A NO-GO with evidence is a
result; a GO obtained by adjustment is not.

Update `docs/handoffs/STAGE-20-flexible-flapping-wing-fsi-DONE-2026-07-30.md` **as you go**, and
keep **this file** current — it is what stops session 6 being as confused as session 5 would
otherwise be. Flip `status: partial` to `complete` only when a verdict exists.

Final state each session: clean tree, pushed, PR #44 required checks green,
`pytest -q tests/unit tests/stage_20` green, nothing running on aero-dev you did not intend.

*(Note: `vv-smoke` is NOT a required check and has been intermittently red from a `pimpleFoam`
rc=124 timeout on `cylinder_strouhal_re100` on aero-build. It is green on `main`. Treat it as
contention unless it fails on `main` too.)*
