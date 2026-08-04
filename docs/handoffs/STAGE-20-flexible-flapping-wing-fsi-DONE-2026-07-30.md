---
stage: 20
stage_name: "Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul)"
status: partial
date_started: 2026-07-30
date_completed: 2026-08-01
session_duration_hours: 10
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5[1m]
git_sha_start: 42ebb55e984f6762e982d358678c443c857b6dce
git_sha_end: 67d8e8226b651890529f96a6a498f34b8d5c6c67
stage_tag: v0.0.20
next_stage: 21
next_stage_name: "Stage 21 — Release (v0.1.0)"
---

# Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul) — PARTIAL 2026-07-30

> **Read this first. Status: PARTIAL, and deliberately so — no tag.** The foundation phases are
> done and verified; the authored case, the pre-registration and the campaign are not started.
> **No gated claim has been made and none may be, because ADR-039 does not exist yet.** Nothing
> here is a Stage-20 verdict.

## 0. The one-paragraph version

The two hard structural problems are solved. **CalculiX is genuinely in the loop**: the
perpendicular-flap smoke ran OpenFOAM in `precice-fsi.sif` and CalculiX in
`calculix-precice.sif`, 50/50 coupled windows converged at a mean of 2.14 iterations, both
participants exited 0, and the flap tip deflected 0 → 0.1646 m under a real fluid force of
~8.6 N. That is two-way FSI across two containers, which nothing before this had shown — Stage 19
put both participants in one image. And **the multi-container provenance question is decided**
(ADR-038): `ProvenanceTuple` carries a `containers` roster, strictly additively, so a gated
two-SIF run is now expressible; Stage 19's blanket refusal is replaced by
`assert_provenance_describes`, which enforces the property that actually matters. The
Heathcote-Gursul reference is acquired to the extent the prose supports exactly, including
author-stated measurement uncertainties. What remains is the largest single chunk — authoring the
coupled case — plus the pre-registration and a multi-day campaign.

## 1. Deliverables status

| # | Deliverable (verbatim from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | CalculiX in the loop — `.inp` writer, adapter `config.yml`, element choice | ⚠️ | Smoke **PASSES** on two containers; the *writers* are not built. Element choice now settled by evidence (§6.1) |
| 2 | The Heathcote-Gursul case in `aero/vv/fsi/` + DVC reference data | ⚠️ | Reference **COMPLETE**: text-sourced exact, figures digitized, reference of record written, R2 passes, operating point fixed (§7.1). Two corrections to the committed file (§6.6, §6.7). The V&V case itself is not built |
| 3 | Pre-registered gate block (ADR-037+) before any campaign run | ❌ | **Not started.** No campaign has run, so nothing is out of order |
| 4 | Flexible-vs-rigid delta with `compose_improvement()` | ❌ | Not started |
| 5 | Provenance for a genuinely two-container run | ✅ | **ADR-038**, landed, tested, and exercised by a real run |
| 6 | ADRs; GO/NO-GO; handoff; tag `v0.0.20` | ⚠️ | ADR-038 `proposed`; this handoff; **no tag, no verdict** |

## 2. Decisions made

- **Extend `ProvenanceTuple`, not hash a container set** (ADR-038, operator-chosen). A composite
  digest resolves to nothing in `containers/SHA256SUMS`, so inverting it needs a side manifest plus
  its own CI check — the same surface arrived at indirectly — and it silently redefines
  `container_sif_sha256` for a subset of runs while leaving the field name and type identical. The
  roster says what happened instead of encoding it. Strictly additive: existing field unchanged,
  new field defaults empty, fifth MLflow tag only when non-empty, nullable Postgres column.
- **The gated-multi-SIF refusal is replaced, not deleted.** `CoupledCaseSpec` only ever knew SIF
  *names*, so it could enforce a proxy at best. `assert_provenance_describes(spec, provenance)`
  enforces the real property — a run's provenance must name every SIF it runs — at the point the
  digests exist.
- **Run the smoke on upstream's bytes verbatim.** The point of the smoke is to learn the
  `ccx_preCICE` conventions the authored case must reproduce; learning them from a case we wrote
  would be circular. It paid immediately (§6.1).
- **A separate tutorial archive, not an extended one.** The Stage-19 archive's sha256 is
  `TutorialPin.archive_sha256` in the FSI3 spec and its manifest backs a closed, tagged verdict.
  Extending it — the obvious shortcut — would have changed that digest and retroactively
  invalidated the Stage-19 record.
- **Treat ssh rc 255 as a transport fault on the exit code alone**, not on a stderr pattern. The
  failure that motivated the fix arrived as rc 255 with an **empty stderr**, so a pattern match
  would have missed exactly the case it was written for. The message says it is a hint, not a
  verdict.
- **Do not publish a half-done digitization.** The text-sourced values are exact and committed; the
  figure-read values are not, and are marked as pending rather than estimated. See §6.2 for why
  this specific reference has earned that caution.

**Session 4 (2026-08-04) — four operator decisions, all of which belong in ADR-039**

- **Time scheme: `backward` IF AND ONLY IF checkpoint fidelity is proved; otherwise `Euler`.**
  Every preCICE OpenFOAM tutorial, including the perpendicular-flap bytes, uses `Euler`. Second
  order in time under *implicit* coupling requires the adapter to checkpoint and restore
  `U.oldTime().oldTime()` on every coupling iteration, and nothing in this repo establishes that
  the pinned adapter does. If it does not, `backward` is silently first-order-plus-noise and the
  record would carry a temporal-accuracy claim it does not have. The probe becomes a **reusable
  pre-flight clause I8** in `aero/vv/` — 5 windows implicit versus the same 5 at
  `max-iterations 1`, comparing window-start field state — not a throwaway spike, so any future
  preCICE stage inherits it. Either way the claim is measured. *(Note the counter-argument that
  makes `Euler` defensible if I8 fails: the fixed coupling time-window-size across all rungs makes
  temporal error common-mode, so it does not contaminate the spatial GCI.)*
- **`NLGEOM` ON unconditionally.** The honest model for a plate deflecting 73x its own thickness,
  even though upstream's proven `flap.inp` omits it at a *larger* 16 % tip deflection and the
  geometric correction at our 5.35 deg is ~0.15 % — three orders inside D0's 0.25 band. B2 is sized
  for whatever it costs; the Newton-loop multiplier over ~70 000 increments is unmeasured on this
  box and I4 must report it.
- **D9 is REPORTED-ONLY; D10 stays gated.** D9 pre-registered `|P2-P1|/P1 <= 0.005` on the rigid
  arm while D8 separately *admits* up to 2 deg of pitch there. At 2 deg the TE's extra velocity is
  `0.060 m x 0.0349 rad x 6.194 rad/s = 0.0130 m/s` against an LE velocity amplitude of
  `a*omega = 0.1084 m/s` — **12 %** — and P1 assumes a single rigid-body velocity. D8 and D9 could
  not both be satisfiable in the worst admissible case, so a D9 NO-GO would have said nothing about
  the physics. `(P1-P2)/P2` is now reported on **both** arms as the measured bias the naive formula
  would have injected. D10 (`|P3-P2|/P2 <= 2 %`) remains in the VERDICT line: it is a genuine
  closure identity with no rigid-body assumption.
- **Budget fallback: raise the ceiling, do not degrade the evidence.** If I7 fixes `dt` and I4 then
  projects wave 1 past its ceiling, the pre-registered response is (1) **per-wave ceiling raised to
  14 days** and (2) **wave 1 reordered to the rung carrying the paired increment, both arms**, with
  wave 2 the two GCI-only rungs — so an overrun costs the GCI term, never the headline increment.
  Cutting settled cycles below 10 and accepting a budget NO-GO are the declared last resorts, in
  that order, and only if 14 days per wave is also exceeded. aero-dev is otherwise idle, so wall
  clock is the cheapest thing to spend.

## 3. Deviations from the stage plan

- **The stage is incomplete.** The approved plan costed the campaign alone at ~5-7 days of
  aero-dev wall clock (3 rungs × 2 arms, operator-chosen), on top of authoring a coupled case that
  has no upstream equivalent. One session was never going to reach a verdict; this handoff records
  where it actually got to.
- **Figure digitization deferred within Phase 2.** Planned as part of acquisition. The text-sourced
  half is exact and done; the figure half is specified but not executed (§7 item 1).
- **The plan's plane-stress element recommendation is superseded** by what the smoke showed
  (§6.1). Evidence over plan — which is why the smoke was sequenced first.

**Session 3 (2026-08-01) — deviations, and why**

- **Only Phase 3A's first half landed.** The two non-regression pins and their goldens are
  committed (`67d8e82`); the refactor they exist to protect is not, nor is anything after it.
  The ordering rule ("land the tests on pre-refactor code, see them green, THEN refactor") is the
  stage's single most important one, and half of it done correctly is worth more than both halves
  done in the wrong order. What is left is enumerated in §7 item 3b.
- **The campaign as scoped does not fit its ceiling, and this was found before the ADR froze
  rather than after** (§6.11). Two operator decisions followed — the settled-cycle ladder with two
  launch waves, and pre-registering the sizing *rule* with B2's numbers filled from I4 in a later
  commit. Both are deviations from the resume prompt's "6 runs launched concurrently" and from
  ADR-036's precedent of concrete numbers in B2; both are recorded here and belong in ADR-039.
- **A new pre-flight clause, I7,** is proposed ahead of ADR-039: a measured max-Courant probe. The
  prompt lists I1/I3/I4/I5/I6 only. Without it the B-family would be pre-registered against an
  estimate, and §6.11 shows the estimate spans an order of magnitude.
- **`PreciceConfigExpectation` needs an additive extension** it was not scoped for, or the
  C-family's "every rendered token is observable in the parsed model" cannot be honoured (§6.12).
- **Two repo-hygiene carve-outs were added** (`.gitignore` negation, `end-of-file-fixer` exclude).
  Both change shared config to protect a fixture, so they are called out rather than buried: see
  §6.10 for why renaming the fixtures instead would have made them stop testing anything.

**Session 4 (2026-08-04) — deviations, and why**

- **Phase 3A landed as specified; Phase 3B is one commit of three.** Three commits landed
  (`1bd7011`, `10fcb70`, `c682671`), suite 380 -> 418 green, mypy clean. The session did not reach
  the authored writers, the ADRs, pre-flight or the campaign. What was done was done to the
  standard the stage demands rather than more of it done thinly — the precedent of sessions 2
  and 3.
- **`MaterializedTree` carries ONE `source` field, not the `pin` XOR `authored` pair every prior
  prompt and plan specified.** This is a deliberate departure with a demonstrated cause: pydantic's
  `model_copy(update=...)` **bypasses** `@model_validator(mode="after")` even on a frozen,
  `validate_assignment=True` model (verified in-process, and pinned by a test), and `case.py`
  mutates trees with exactly that idiom in two places. The XOR would have been enforced only at
  construction and forgeable by any helper written by analogy. See §6.14.
- **A `transient_fvschemes` byte pin had to be invented before `ddt_scheme=` could be added**
  (§6.15). The prompt cites a pin that does not exist. Landing it consumed a commit that was not
  in the plan, and it is the Phase-3A ordering rule applied a second time.
- **The I3/I5 static baseline was measured EARLY, out of the prompt's order.** It needs no new
  code, costs ~15 minutes, and it invalidates two numbers the stage would otherwise have
  pre-registered against. See §6.16. Measuring it before the ADR freezes is the whole point of
  I-family clauses.
- **`85e0b32` was already recorded in §4** by session 3; the resume prompt's instruction to add it
  was stale. No change needed.
- **`_SOLVER_SIF["precice"] -> both SIFs` is not expressible** and Phase 3D must not attempt it:
  the dict is `dict[str, str]` feeding a single-SIF `compute_provenance`. The container of record
  and the extras are already on `CoupledCaseSpec` (`container_of_record`, `extra_container_sifs`),
  so the CLI must derive them from the spec, not widen the table.

## 4. Environment / dependency / schema changes

- `ProvenanceTuple` gains `containers: tuple[ContainerRef, ...] = ()` and a fifth conditional
  MLflow tag `container_sif_set`. `ContainerRef` and `container_roster` are new public names.
- **Postgres: migration `005_container_set`** adds a nullable `container_sif_set TEXT` to
  `mlflow_artifact_provenance` plus a partial index. **APPLIED 2026-07-31** by the operator from
  the Proxmox host (`alembic upgrade head`); `alembic current` reports `005_container_set (head)`.
  Verified after the fact rather than assumed: the column is `text`/nullable, all **1280**
  historical rows are intact with `container_sif_set IS NULL` (correct — every pre-Stage-20 run is
  single-container), and both the old and new indexes are present.
  **The mirror write path is verified too**, inside a transaction that was rolled back: the real
  `_INSERT_SQL` accepts a two-container roster, the stored value is byte-identical to the
  `container_sif_set` MLflow tag, and it round-trips back to both SIF digests. Row count unchanged.
  *(Note the DB is at 192.168.2.184; CT 202 is its CTID, not its address.)*
- `ExecResult` gains `transport_error` / `transport_failed`; `MeshHandle` gains `failure`;
  `aero.orchestration.describe_failure` is new.
- New pytest marker `stage_20`; new test dir `tests/stage_20/`. Suite is **418 green**
  (`pytest -q tests/unit tests/stage_20`), up from 348 at Stage-19 close (380 after session 3).
- **New module `aero/adapters/precice/manifest.py`** — the two `aero-manifest.json` renderers,
  schema v1 (tutorial) and v2 (authored), as free functions over primitives. Stdlib only; it is
  transitively imported by `aero.adapters.precice` and pulls in no banned module (verified).
- `CoupledCaseSpec` loses five fields to `source`; `TutorialTree` is renamed `MaterializedTree`;
  `TutorialSource` / `AuthoredSource` / `CASE_ROOT_DIRNAME` are new public names.
  `PreciceConfigExpectation` gains 15 optional fields plus the `UNSET` sentinel, and
  `MeshExpectation` / `ParticipantDataExpectation` / `MappingExpectation` are new public models.
- **`85e0b32` (operator, 2026-07-31) — `run_long.sh`: a timed-out wait no longer strands the solve
  it was watching.** `cmd_wait` counted only its own sleeps, ignoring the ~0.5 s ssh round trip per
  poll, so a nominal 14400 s ceiling did not fire until ~15800 s while `LocalSSHExecutor` guarded
  the subprocess at `timeout_s + 120`. The guard therefore ALWAYS won the race, SIGKILLed the
  script before its reap branch, and `AERO_RUN_LONG_REAP=1` never ran — "decorative on the one path
  it was written for" (moving-vv run 30615205786 left `pimpleFoam` running on aero-dev). Fixed two
  ways on purpose: `cmd_wait` now measures a real clock (`date +%s`), and the executor reaps for
  itself in its own `TimeoutExpired` branch via the new named `_WAIT_GUARD_MARGIN_S`.
  **This matters directly for a six-run concurrent campaign** — six detached solves, six waits.
- New fixture trees `tests/stage_20/fixtures/{stage19_load_path,materialization}/`, and two
  `.pre-commit-config.yaml` / `.gitignore` carve-outs they need (§6.10).
- New reference dirs `data/references/fsi/{heathcote_gursul_2007,precice_perpendicular_flap}/`.
  The perpendicular-flap archive is DVC-tracked and pushed to `aero-minio`
  (sha256 `6f1c7b9b0b849845…`, 170 files, same pin `cd33e2db` as Stage 19).
- `CONSTITUTION.md` Invariant 3 item 3 **clarified** (not amended in substance): the rule is
  unchanged — four tags, same shape — only the description widens to name the container of record
  and point at the roster.

## 5. CI/CD changes

- **No new workflows, no new required checks.** `vv-required`'s paths filter already covers
  `aero/adapters/**` and `aero/vv/**`.
- All 10 host-side required checks are green on PR #44 (draft).
- The `stage_20` unit tests ride the existing required `pytest unit (py3.12)` job.

## 6. Gotchas discovered

### 6.1 Upstream's 2-D CalculiX idiom is a 3-D slab, not plane stress

`perpendicular-flap/solid-calculix/all.msh` is a **one-element-thick 3-D mesh** (z ∈ {0, 1}) of
**`C3D8I`** elements (738 nodes, 244 elements), with `*BOUNDARY Nall, 3` suppressing the
out-of-plane dof, while both preCICE meshes are declared `dimensions="2"`. The plan had
recommended CalculiX plane-stress (`CPS8R`) elements; upstream's own proven idiom is the slab.
**Use the slab, and use `C3D8I`** — the incompatible-modes hex is what cures shear locking in a
thin bending member, which is exactly the HG plate's regime, and it is what the calculix-adapter is
actually exercised against.

Also learned, and all needed by the Stage-20 deck writer:

- the adapter's `config.yml` `patch:` name maps to an `*NSET` with an `N` prefix
  (`patch: surface` → `*NSET,NSET=Nsurface`);
- the adapter injects forces by **overwriting a `*CLOAD` block** the deck declares as zeros on the
  interface node set — the deck must declare it or there is nothing to overwrite;
- the calculix-adapter reads **`Force`**, not FSI3's `Stress` — that difference belongs in the
  C-family of the gate block;
- upstream's coupling numerics for this class: `parallel-implicit`, `max-iterations 50`, relative
  5e-3 on **both** `Displacement` and `Force`, IQN-ILS with QR2 filter, `initial-relaxation 0.5`,
  `time-windows-reused 15`;
- the OpenFOAM side needs `preciceDict` with `locations faceCenters` and a dimensioned `rho`.

### 6.2 The reference has two live traps, both recorded before use

**Figures 5.6 and 5.1 plot `C_T/St²`, not `C_T`** — despite Figure 5.6's caption reading "Thrust
coefficient as a function of Strouhal number". At St = 0.3 that is a factor of **11.1**. And there
are **three** Heathcote experiments that are easy to conflate: this one (chordwise flexibility,
teardrop + steel plate, 90 mm chord, thesis Ch. 5 = the AIAA-J 2007 paper); the repo's existing
`plunging_airfoil_hg2007` (rigid NACA-0012, thesis Fig 2.9); and Heathcote, Wang & Gursul 2008
(spanwise flexibility, NACA-0012, 100 mm chord). The existing file's own `⚠️ CORRECTION` section
records that its values were once wrong by 3-5× — thrust digitized off the efficiency curve.

### 6.3 `u95_input` here is measured, not estimated

The thesis states its own instrument uncertainty: **≈5 % on thrust**, **≈10 % on efficiency**
(the latter because efficiency uses gauge readings in both directions), with a component
breakdown. That is far better evidence than a digitization guess, and it is what should flow into
`compose_reportable`/`compose_improvement`.

**The increment's `u95_input` is legitimately smaller than the absolutes'**: both points are read
off the *same figure with the same axes* and measured on the *same gauge with the same
calibration*, so the axis-calibration and systematic terms largely cancel in the difference. That
must be *shown* in `digitization.csv`, not asserted.

### 6.4 An unreachable host used to read as "blockMesh failed"

`moving-vv` run 30568971572 died in 18 s because the CI runner cannot resolve `aero-dev`. ssh
returned 255, `OpenFOAMSolver.mesh` logged only `returncode` and `stdout`, and
`BenchmarkRunner._drive` raised a hard-coded `"blockMesh failed"` — the message also named
`blockMesh` for pipelines running four or five utilities. Fixed; `ExecResult.transport_failed`
distinguishes "the command never ran" from "the command ran and failed".

### 6.5 The ruff-format pre-commit hook rolls commits back silently

Observed three times this session: hooks reformat, the commit does not land, and the shell shows
no obvious failure. **Run `git log` after every commit.** Running
`ruff format && ruff check --fix` before `git add` avoids it.

### 6.6 The recorded thesis sha256 was never reproducible — and neither is any raw PDF digest here

Bath's Pure repository **re-wraps the PDF on every download** with `OpenPDF 1.4.2`. Two fetches of
the same URL, minutes apart, differ in exactly **60 bytes of 12,175,275** — the `/CreationDate`
stamp and the `/ID` trailer array. Every content stream is byte-identical. So `fdee2ce4…`, recorded
2026-07-30, was a per-fetch artifact, and this reference's claim that the figure render was
"reproducible from the recorded PDF digest" was **false as written**.

Replaced by two invariants, both verified across independent fetches: a **content digest**
(`276cec6e…`, `/ID` + dates normalized) and a **per-page 200 dpi raster digest** under a pinned
`pymupdf==1.26.3`. The raster digest is the stronger one — it pins the exact pixels that were read.
**Generalise this:** any digest of a document fetched from a repository that stamps downloads is
worthless as a reproducibility anchor. Check before recording one.

### 6.7 The plunge amplitude in `reference.md` was wrong — `h = 0.194`, not 0.175

§2.1.4 fixes `a = 17.5 mm` for **every** water-tunnel run, and this airfoil's chord is 90 mm, so
`h = a/c = 0.194` — which is how the thesis writes it dozens of times through Chapters 3–5.
`h = 0.175` belongs to the **other two** Heathcote experiments: the NACA-0012 validation model
(p78) and the **spanwise** wing, where `h = a_ROOT/c = 0.175` because that chord is 100 mm. Same
shaker amplitude, different chord. That is precisely the three-way conflation the reference file's
own opening callout warns about — and the file had made it. 11 % on the plunge amplitude, which
propagates into the frequency-from-Strouhal conversion, the mesh-motion probe, and every solve.

### 6.8 This thesis's blanket "for all Reynolds numbers" prose does not survive its own figures

§5.3.2 states the rigid drag→thrust transition is at "St=0.17" and holds "for all Reynolds
numbers" (§5.3.3 repeats it for efficiency). Figure 5.6 gives **0.191 / 0.161 / 0.167** at
Re = 9000 / 18000 / 27000. Two of three reproduce it; **Re = 9000 — the gated Re — is +12.6 %**.

The digitization is not at fault: per-panel calibration is verified three independent ways, and
Fig 5.9a corroborates Re = 9000 independently (negative-efficiency points "are not shown", and the
rigid efficiency series begins at St = 0.205 with nothing below it). At 9× magnification there is
no marker hidden on the zero line — the crossing is genuinely unmarked.

**The lesson generalises past this anchor.** A blanket "for all Re" statement in this thesis is a
rounded generalisation, not a measurement. Its *condition-specific* prose is a different and much
stronger class of claim — the 6°/17° pitch amplitudes, each tied to a named foil and a named St,
reproduce to **0.1 %**. Weight them accordingly. R2 gates the crossover only where prose and
figure agree; the measured Re = 9000 value is carried as a row in the reference of record.

### 6.9 The C-grid's non-orthogonality has always been ~85, so I5 cannot use an absolute threshold

The mesh spike measured max non-orthogonality of **84.9** for the HG section, **80.5** for a stock
NACA 0012 at identical knobs, and **86.5** for the platform's own default Stage-05 production V&V
mesh — the one every TMR run uses. It barely moves with far-field extent (20/50/100 c), normal
count (80/120/140) or first-cell height (2e-6/1e-5/1e-4 c), and the **average is only ~18**. It is
a localised property of this C-grid family and always has been; the HG section adds ~4°.

So ADR-024's absolute `non-ortho ≤ 70`, applied to I5, **would fail on the static mesh before any
motion** — and would equally fail the platform's production V&V mesh. ADR-024's 70 was measured on
the *flapping-wing* writer, a different mesh. **I5 must gate the DEGRADATION under motion against
the recorded static baseline**, plus absolute skewness ≤ 4 and zero negative volumes — which is
what ADR-024's real failure mode looked like anyway (skewness 5503, 18 145 inverted pyramids):
catastrophic, not marginal. Write that into ADR-039 rather than inheriting the number.

Also note `MeshQualityGate`'s M2 = 65 default was authored in Stage 18 for the **snappy** path and
has never been applied to the blockMesh C-grid. Applying it now would be a new, retroactive gate.

### 6.10 Four traps in the Stage-19 non-regression fixtures, all found by writing them

The two pins landed at `67d8e82` (`tests/stage_20/test_stage19_{load_path_unchanged,
materialization_is_byte_identical}.py`). Each of these would have produced a *green* or
*absent* test rather than a loud one:

- **`load()` emits 23 scalars, not 20.** The resume prompt says 20. A golden written against
  "20 scalars" would have passed vacuously. The test spells all 23 out as a literal.
- **`*.log` is gitignored repo-wide** (`.gitignore:60`), and the fixture's filenames are load
  bearing — `find_iterations_logs` globs `precice-*-iterations.log`, `watchpoint_path` builds
  `precice-<Participant>-watchpoint-<name>.log`. The fixture would have been committed incomplete
  and CI would have failed on a missing file, not on a wrong number. Scoped negation added.
- **`end-of-file-fixer` was appending a newline to those fixtures.** preCICE's `TXTTableWriter`
  PREFIXES each row with `"\n"`, so its files genuinely end without one, and `_txt_table` relies
  on that to spot a partially-written final row. The hook is now scoped away from them rather than
  the fixtures being made unfaithful.
- **`tarfile.extractall` chowns every member when running as root** (with `-1/-1`, because the
  `data` filter strips recorded ownership), so a monkeypatched `os.chown` sees far more than
  `_chown_tree`'s calls. Discriminate on the uid. The property actually worth pinning — chown
  after digest verification, *before* the manifest write — is observable as `aero-manifest.json`
  being absent from the call list, which needs no real inode and so works on a CI runner.

`.within()`'s window scoping is verified by **mutation, not assumption**: neutering
`CouplingIterationReport.within` makes `load()` raise on the fixture. And the K1 unification the
refactor performs is **provably a no-op on the tagged Stage-19 record** —
`data/vv/stage19_turek_hron_fsi3.json` reports `n_nonconverged: 0` over 8000/8000 windows for both
participants, so whole-run and window-scoped agree there. Record that in ADR-037; it is the
evidence that makes the behaviour change safe rather than merely plausible.

### 6.11 The flexible plate is the clock, and the default wall spacing is unrunnable

Two mesh facts decide the campaign's wall time, and neither is in the plan:

- **`CaseSpec.first_cell_height` defaults to `2.0e-6` chords** (`schemas.py:176`) — 0.18 µm on a
  90 mm chord, authored for a y+<1 RAS TMR mesh. The wake-cut block inherits it, and the transverse
  velocity there is the full plunge speed, so `Co <= 1` would need `dt ~ 1.7e-6 s`. **The mesh
  spike used this default**, so its 48 240 cells / skew 2.40 numbers describe a mesh nobody can
  integrate at a fixed time step. `PlungingAirfoilSpec` already uses **`5.0e-4`** (Stage-11/13
  precedent) — that is the value to pre-register, and I3/I5 must re-measure the static baseline
  with it.
- **The C-grid's surface blocks are `simpleGrading (1.0 …)`** (`case_writer.py:209-216`), i.e.
  UNIFORM in arc length — the cosine-spaced control points are shape fidelity, not the cell
  distribution. That is what makes a Courant estimate tractable at all, and it had not been
  written down anywhere.

With those, the binding limiter is the **blunt-TE base of the flexible plate**: 76.5 µm across
`n_te` cells. At `n_te = 2` that is 38 µm against a peak plunge velocity `a*omega = 0.1084 m/s`
(1.08 U), giving `dt ~ 3.5e-4 s` — **5x tighter than the rigid arm**, which the paired A-family
forces both arms to share. At `T = 1.0145 s` that is ~2900 windows/cycle; 24 cycles is ~70 000
windows, and the finest rung (dt scaled by the refinement ratio) ~90 000. **The campaign does not
fit a 7-day ceiling on the central estimate** (fine rung ~8.3 d), and the plausible band is wide.

Two operator decisions were taken on this, both to be written into ADR-039:

1. **Settled-cycle ladder plus two launch waves** — >=20 settled cycles on the rung carrying the
   paired increment, >=10 on the GCI-only rungs (`DEFAULT_MIN_SAMPLES` is 8, so 10 is a declared
   margin, and a GCI needs converged *means*, not tight variances); wave 1 = coarse+mid, wave 2 =
   fine, with the 7-day ceiling applying **per wave**.
2. **Pre-register the sizing RULE, not the numbers.** ADR-039 lands complete with B2 carrying the
   rule plus a `<<B2-PENDING-I4>>` marker; the I4/I7 record lands next with its own four-fold
   tuple; a third commit fills the marker only, and a committed pure sizing function plus a test
   re-derive the numbers from the I4 JSON so they are an output rather than a decision. The driver
   refuses a gated run unless `git merge-base --is-ancestor` proves ADR-039's first commit precedes
   the I4 record.

Add **I7**, a cheap measured max-Courant probe (a few fluid-only steps at the candidate `deltaT`
with the mesh at mid-stroke), and run it **before** ADR-039 freezes, so the arithmetic above
becomes a measurement rather than an estimate. Pre-flight FAILS on `Co > 1`; it never adjusts.

### 6.12 Three things in the authored case that fail silently, not loudly

Found by reading upstream's actual `perpendicular-flap/solid-calculix/flap.inp` bytes:

- **The CalculiX slab's z-thickness must equal the OpenFOAM `span`.** preCICE `Force` is an
  absolute force in newtons. Upstream's flap gets away with a `z in {0,1}` slab because its fluid
  span is also 1. The HG fluid span is 2.5 mm (`tests/stage_20/test_hg_section.py`), so a 1 m slab
  under-loads the plate by 400x: `checkMesh` is fine, the coupling converges, and the pitch
  amplitude just comes out at 0.01 degrees. One `span` field must feed both writers, with a
  C-family clause asserting the emitted `.inp` z-extent equals the emitted `blockMeshDict` span.
- **`*STEP, INC=1000000`.** CalculiX's default is 100. At `INC=100` with tens of thousands of
  windows ccx finishes its step, writes its `.frd` and exits **0**; `read_coupled_status` reads rc 0
  as `exited-ok`, `stopped_by` becomes `all-exited`, and **K2 passes**. The failure only surfaces
  at S3, after the fluid has burned its ceiling.
- **`PreciceConfigExpectation` has no field for the RBF `support-radius`** or for any acceleration
  parameter (`config.py:536-557`), even though `MappingDecl.support_radius` and the
  `AccelerationDecl` fields are all parsed. So "assert every rendered token is observable in the
  parsed model" is **not achievable through `assert_config` as it stands** — it needs an additive
  extension (`| None = None` fields, so FSI3's expectation and its tests stay byte-identical).
  Upstream's `support-radius="1."` is one metre on a 0.09 m chord and must be scaled.

Also settled by reading those bytes: `*BOUNDARY Nall, 3` gives plane **strain**, so the effective
modulus is `E/(1-nu^2) = 2.253e11`, not 2.05e11 — the naive `Eb^3/12` hand-check is otherwise 10 %
off. And with `ALPHA=0.0` and no damping, the cycle-mean reaction power over the prescribed region
equals the interface power exactly, which is what makes D10 a real closure check *and* a check
that `ALPHA=0` held.

### 6.13 The ADR-039 bands, computed — and the floor binds on four of five

Applying the pre-registered rule `4 x (u95_ref/|value|)`, floored 0.25, capped 0.50, to
`hg2007_recomputed.csv` (instrument systematic 5 % thrust / 10 % efficiency on **absolute** rows
only; increments use the reading terms alone, which is what the CSV's `u_axis_abs = 0` encodes):

| clause | quantity | value | `u95_ref` | raw 4x | band | binding |
|---|---|---|---|---|---|---|
| D0 | pitch amplitude, flexible | 5.34637 deg | 0.08651 | 0.065 | **0.25** | floor |
| D1 | `C_T` flexible | 1.00772 | 0.05187 | 0.206 | **0.25** | floor |
| D2 | `eta` flexible | 0.175279 | 0.01756 | 0.401 | **0.40** | — |
| D3 | `dC_T` | 0.609257 | 0.00325 | 0.021 | **0.25** | floor |
| D4 | `d eta` | 0.0865273 | 0.0 | 0.0 | **0.25** | floor |

**The cap never binds; the floor binds four times out of five, so for D3 and D4 the 4x rule is
decorative and 0.25 is a policy number.** Say that in the ADR rather than letting the formula imply
the band was derived. It matters: ADR-022 measured this platform's 2-D plunging solve missing HG's
absolute rigid thrust by -28 %/+58 %, and if that error is multiplicative and common-mode the
increment inherits ~28 % — **a NO-GO on D3 is at least as likely as one on D1**.

Two structural notes for the same section. `MetricSpec` only expresses relative/absolute/normalized
numeric bands, so D5/D6 (signs) and D7 (admissibility) have to be structural predicates carrying a
literal `(no band)` token, while D8 (rigid pitch <= 2 deg), D9 and D10 ride the existing harness as
`comparison="absolute"` against a reference of `0.0` with the power *ratios* emitted into
`solve.scalars`. And ADR-036's band-parity regex `r"^\s+(D\d) [^\n]*within (\d+) %"` has three
defects for Stage 20: `D\d` matches **`D10` as `D1`** (a phantom pair, silently), `(\d+) %` cannot
express D9's 0.5 %, and `^\s+` also matches five-space continuation lines.

### 6.14 A nullable XOR pair is forgeable, because `model_copy` skips after-validators

Every prior Stage-20 plan specified `MaterializedTree` (was `TutorialTree`) as carrying `pin` XOR
`authored`, with `write_manifest` dispatching on `pin is not None`. That shape is unsound here.
Verified in-process on a frozen, `extra="forbid"`, `validate_assignment=True` model with an
`@model_validator(mode="after")` enforcing the XOR:

    m = M(a=1)                      -> a=1 b=None
    m.model_copy(update={"b": 2})   -> a=1 b=2      # the validator did NOT run

and `case.py` builds trees with `tree.model_copy(update={"mutations": ...})` in **both**
`select_fluid_mesh` (`:392`) and `record_max_time_mutation` (`:415`). So the invariant would have
held only at construction, and any authored-path helper written by analogy with those two — the
obvious thing for the next session to write — could produce a both-set tree.

**What that costs, concretely.** A both-set tree takes the `pin is not None` branch and emits a
**schema-v1 tutorial manifest for a case we authored**: a `"pin"` block naming
`precice/tutorials @ cd33e2db` beside bytes this platform wrote, with every authored-provenance
key silently dropped. That manifest ships in the bundle. Nothing raises. A reviewer reads it as
"this run laid down the pinned upstream tutorial". It is a provenance lie produced by a runtime
predicate — the exact class of failure the Phase-3A discipline exists to prevent.

**The fix removes the predicate.** One `source: TutorialSource | AuthoredSource` field on the tree;
both emitters are free functions in a new `aero/adapters/precice/manifest.py`; and `_write_case`
selects between them by an exhaustive `match spec.source.kind` with `assert_never`, so a third
source type in a future stage is a **type error** rather than a silent fall-through. There is no
invariant left to forge. Generalise it: *any* invariant expressed only as an after-validator is
bypassable in a codebase that uses `model_copy(update=...)` at all.

### 6.15 The `transient_fvschemes` byte pin the prompt relies on does not exist

`tests/stage_11/test_dynamic_mesh_writers.py:62` is

    assert (tmp_path / "system" / "fvSchemes").read_text() == fc.transient_fvschemes()

Both sides call the same function. It pins writer/consumer **agreement** — that the cylinder writer
really renders the shared helper — and nothing about the bytes. Change the default output and both
sides move together; the test stays green. `grep -rn "1df84e21" tests/` returns nothing.

Measured on pre-change code, and now pinned as literals in
`tests/stage_20/test_fvschemes_bytes_before_ddt_scheme.py`:

| turbulence model | length | sha256 |
|---|---:|---|
| `laminar` (the default) | **781** | `1df84e211d7836d8fe9b7b935f5cd4af339174ef3c0d8aacc84b190c0678e4ef` |
| `kOmegaSST` | 886 | `4edd1332bf0bba804327e9e52dd3f6c0c1100e45ea040404b5ad5908b3d4c302` |
| `kOmegaSSTLM` | 958 | `3703fe5ca9f6735f404d1a4df3d2e7fc607063c772872ca9f219e3f841fc0f90` |

Without it, a mistake in a new `ddt_scheme=` default branch would silently rewrite the `fvSchemes`
of the Stage-10 static cylinder, the Stage-11 plunging foil and the Stage-13 URANS decks —
invalidating the records those decks produced, with nothing going red. The pin lives in
`tests/stage_20/` on purpose: `tests/stage_11/` is **not** in the mandated
`pytest -q tests/unit tests/stage_20` suite.

### 6.16 I3/I5 measured: the failing checkMesh check is ASPECT RATIO, not non-orthogonality —
### and it fails identically on the platform's own stock NACA 0012

Re-measured on aero-dev at the **pre-registered** `first_cell_height = 5.0e-4 c` (the spike's
numbers came from the `2.0e-6` default and do not apply), both arms, three candidate rungs, span
slab 2.5 mm. Every number recorded, passing or not:

| rung | arm | cells | nonOrtho max | skew max | aspect ratio | min vol | neg vols | `Mesh OK` |
|---|---|---:|---:|---:|---:|---:|:-:|:-:|
| fine | flexible | 130 032 | 86.315 | 1.768 | 1847.56 | 2.466e-12 | no | **no** |
| fine | rigid | 130 032 | 86.317 | 1.767 | 1847.56 | 2.462e-12 | no | **no** |
| mid | flexible | 77 240 | 85.230 | 2.163 | 1884.45 | 4.133e-12 | no | **no** |
| mid | rigid | 77 240 | 85.233 | 2.162 | 1884.45 | 4.127e-12 | no | **no** |
| coarse | flexible | 45 682 | 85.650 | 2.555 | 1914.12 | 6.968e-12 | no | **no** |
| coarse | rigid | 45 682 | 85.651 | 2.554 | 1914.12 | 6.958e-12 | no | **no** |

Controls, at the mid rung and identical knobs:

| variant | cells | nonOrtho | skew | aspect ratio | `Mesh OK` |
|---|---:|---:|---:|---:|:-:|
| **stock NACA 0012**, 5.0e-4 | 76 896 | 82.565 | 1.998 | **1884.4471** | **no** |
| HG flexible, 5.0e-4 | 77 240 | 85.230 | 2.163 | **1884.4471** | no |
| HG flexible, 2.0e-6 (the spike's mesh) | 77 240 | 87.288 | 2.322 | 2954.45 | no |

Five things follow, and three of them change what ADR-039 may say:

1. **checkMesh's own non-orthogonality check reports "Non-orthogonality check OK" at 85.23.** The
   one failing check is `***High aspect ratio cells found, Max aspect ratio: 1884.4471, number of
   cells 2892`. §6.9 reached the right conclusion about I5 for a slightly wrong reason.
2. **The aspect ratio is byte-identical (1884.4471) between the HG section and the stock NACA
   0012.** It is a pre-existing property of the platform's own eight-block C-grid family, in the
   far field, untouched by the surface curve. Stage 20 did not introduce it.
3. **`MeshQualityGate`'s M1 ("Mesh OK") therefore cannot be an absolute I5 gate either** — it fails
   on the platform's own stock airfoil mesh at the pre-registered spacing. This extends §6.9's
   argument from M2 to M1, now with a control. I5 gates **degradation against the recorded static
   baseline** plus absolute skew <= 4 and zero negative volumes; **M1 and M2 are reported, never
   gated**, and the ADR must say why with these numbers beside it.
4. **The pre-registered spacing is better on every metric than the spike's**: non-ortho
   87.29 -> 85.23, skew 2.32 -> 2.16, aspect ratio 2954 -> 1884. Changing it was not only necessary
   for the time step, it improved the mesh.
5. **The rung ladder is clean.** Cell counts 45 682 / 77 240 / 130 032 give
   `sqrt(77240/45682) = 1.300` and `sqrt(130032/77240) = 1.298` — a uniform 2-D refinement ratio of
   1.30 across both steps, which is what a three-grid GCI wants. Knobs, built downward:
   fine `(n_surface, n_normal, n_front, n_wake, n_te) = (140, 140, 70, 112, 6)`,
   mid `(108, 108, 54, 86, 4)`, coarse `(83, 83, 42, 66, 3)`.
   The two arms differ only in the 5th significant figure of every quality metric, so the paired
   increment is not confounded by mesh quality.

Raw JSON for both probes is in the session scratchpad; it must be re-run by the I3/I5 pre-flight
into `data/vv/` with its own four-fold tuple before ADR-039 cites it. **These numbers are a
measurement, not yet a record.**

## 7. Open items for the next stage (and beyond)

**Blocking, in order — this is the resumption path**

1. ~~Finish the figure digitization~~ — **DONE 2026-07-31.** `digitization.csv` (208 markers,
   Figs 5.6a/b/c + 5.9a + 5.13a), `hg2007_recomputed.csv` (the reference of record),
   `scripts/stage20_digitize_hg_figures.py` and `scripts/stage20_acquire_hg_reference.py`.
   **R2 PASSES** on all five anchors — pitch amplitude 16.99° vs 17° (−0.1 %) and 5.48° vs 6°
   (−8.6 %), crossover at Re 18000/27000, and both increments positive — with the one documented
   disagreement in §6.8. Three readings per marker are three independent *binarizations* of a
   cross-correlation match against each figure's own legend glyph, declared as a deviation from
   "three human passes" and strictly more auditable (anyone can re-run it).

   **The gated operating point is fixed** (from the reference alone, before any solve):
   **Re = 9000, St = 0.345, flexible `b/c = 0.85e-3` (76.5 µm) vs rigid `b/c = 4.23e-3`
   (380.7 µm)** ⇒ `U = 0.1 m/s`, `f = 0.9857 Hz`, `T = 1.0145 s`. Reference values:
   `C_T` 1.008 / 0.398 (`ΔC_T` = 0.609), `η` 0.1753 / 0.0888 (`Δη` = 0.0865), pitch amplitude
   5.35°. **Re = 9000 is forced** — Fig 5.13 exists only there, so it is the only Re at which the
   D0 structural gate has a reference at all.

   **The selection rule changed and ADR-039 must record why.** The originally approved rule
   ("largest measured `ΔC_T`") is degenerate: `C_T` scales as `St²`, so `ΔC_T` rises monotonically
   to the figure's right-hand edge (it peaks at St = 0.89, where f = 2.54 Hz is the top of the
   rig's stated 0.3–2.5 Hz range and peak plunge velocity is 2.8× freestream). That is exactly why
   HG plot `C_T/St²`. The operator-chosen replacement maximises **`Δ(C_T/St²)` inside the
   `0.2 < St < 0.4` band the thesis itself calls out** as observed in nature and containing its own
   efficiency optimum (St = 0.29). Note the optimal plate thickness **moves with St** — the thesis
   says so, and the digitization reproduces it — so plate and Strouhal number are chosen together.

1b. **The mesh feasibility spike PASSED; the thin-plate fallback is not needed.** Both arms mesh
   at the chosen `b/c = 0.85e-3`: `checkMesh` "Mesh OK", 48 240 cells, skewness 2.40/2.39, no
   negative volumes. `CaseSpec.section` (`TeardropPlateSection`) swaps only the surface curve the
   existing eight-block C-grid wraps, so the grid stays self-similar under refinement and a real
   3-grid GCI remains admissible. The NACA path is pinned byte-identical by test. **But read §6.9
   before writing I5.**
2. ~~Apply Postgres migration `005_container_set`~~ — **DONE 2026-07-31**, see §4. The multi-container
   mirror path is clear; nothing else in the provenance chain blocks the campaign.
3. **Run `scripts/grant_aero_build_ssh_to_aero_dev.sh`** (operator; packaged, not executed —
   authorising a remote root key is the class auto-mode blocks by design). Runbook at
   `docs/operator/aero-build-to-aero-dev-ssh.md`. **Not on the campaign's critical path**: the
   campaign is launched by hand from the Proxmox host, which reaches aero-dev already. This unblocks
   *CI* reaching the 16-core box — including `test_unsteady_plunging_airfoil`, which has never
   completed there.
3b. ~~**Phase 3A's non-regression pins are DONE (`67d8e82`); the refactor they protect is NOT.**~~
   — **DONE 2026-08-04 at `1bd7011`.** The ordering held and is checkable:

       git merge-base --is-ancestor 67d8e82 1bd7011              # true
       git diff --stat 67d8e82 1bd7011 -- tests/stage_20/fixtures/   # EMPTY
       git diff --stat 67d8e82 1bd7011 -- tests/stage_20/test_stage19_load_path_unchanged.py
                                                                 # EMPTY

   The goldens were not re-captured, the load-path pin is untouched, and the materialization pin
   changed only in how it CONSTRUCTS a spec — not one assertion moved. `MaterializedTree` carries
   one `source` field rather than the specified XOR pair (§6.14). **The FSI3 `config_hash` moved,
   as predicted: `c524faff...` -> `3f94f394...`**, pinned by test with the old value in the
   docstring; ADR-037 must record both and say plainly that the materialized *bytes* are proved
   identical while the *spec serialization* moved — different claims.

   Also landed: **`10fcb70`** — the additive `PreciceConfigExpectation` extension (15 fields, all
   defaulting to "do not check", each driven with a wrong value in a parametrized test; ordered
   `mappings` tuple; an `UNSET` sentinel so "assert absent" is distinguishable from "do not check";
   and `max_time`, which the plan omitted but which an authored case must assert because there it
   is a rendered token rather than the one permitted mutation). And **`c682671`** — the
   `transient_fvschemes` byte pin, on pre-change code, because the one the prompt cites does not
   exist (§6.15).

   ~~Old text follows for context.~~ Formerly:
   The two tests, their fixtures and their goldens landed in a single commit on pre-refactor code,
   which is the ordering rule the stage turns on. Prove it before trusting the refactor:

       git log --oneline -- tests/stage_20/fixtures/          # must be exactly 67d8e82
       git merge-base --is-ancestor 67d8e82 <refactor sha>    # must be true

   Still to do, in one commit: `CoupledCaseSpec.source: TutorialSource | AuthoredSource`
   (discriminator `kind`); `TutorialTree` -> `MaterializedTree` (`pin` XOR `authored`);
   `DeclaredMutation.kind += "authored"` with `before_sha256: str | None`;
   `select_fluid_mesh(fluid_participant_dir=...)`; `_materialize` as a **method**;
   `CASE_ROOT_DIRNAME` + `_case_dir()`; and the `_assert_status_gate` / `_assert_coupling_
   converged_over` extraction. Note the site count: **7 production + 2 test literals**, not eight.

   **Keep the manifest bytes identical by versioning the SHAPE, not by adding fields.** Extract
   a pure `render_tutorial_manifest_json(...)` (schema v1, dicts built by hand from explicit
   fields, never `model_dump()`) whose docstring says its bytes are a committed golden reproduced
   in every pre-Stage-20 bundle; give authored cases a *separate* emitter. `json.dumps(sort_keys=
   True)` is recursive, so a single new optional field on `MaterializedFile` or `DeclaredMutation`
   rewrites all 94 `files` entries, and a new top-level key re-sorts the document. Keep `dest` at
   `host_path/CASE_ROOT_DIRNAME` and assert `tree.root.name == CASE_ROOT_DIRNAME` in a validator,
   or `case_dir` and every mutation `path` shift.

4. **Author the coupled case** — the largest remaining chunk: CalculiX `.inp` writer + re-reader,
   adapter `config.yml` writer, a committed digest-verified `precice-config.xml` template with a
   renderer, a **dimensional** OpenFOAM fluid writer (do **not** reuse `plunging_airfoil.py`; it
   hard-codes `RHO_INF = U_INF = 1.0`), the force/power path on the coupled route
   (`PreciceCoupledSolver.load()` returns `cd=None, cl=None` today), and the V&V case registered in
   **all three** `aero/cli.py` sites.
5. **ADR-039, before any campaign run.** Families P/C/I/R/K/S/**A**/D/**M**/X, byte-bound to the
   driver, with the two deliberate improvements on ADR-036: every gated clause named in the VERDICT
   line (ADR-036 omitted S5 — the clause its own review had just added), and a shape-7 test
   asserting every clause identifier is either in the VERDICT line or the reported-only list.
6. **Pre-flight + I4**, then the campaign. **Do not extrapolate a rate from the transient**: Stage
   19 was off by 3.5-9.6× in one direction and the B3 diagnostic by ~1.8× in the other.

**Design decisions already taken, do not re-litigate**

- Plunge driven from the **solid's** leading edge (the pitch is not prescribed — it *arises* from
  the flexibility, per the thesis, so prescribing it would model a different experiment).
- CalculiX **3-D slab of `C3D8I`, dof 3 suppressed**, not plane stress (§6.1).
- **Solid geometry is settled**: 30 mm aluminium teardrop (≈9.6 mm max thickness, measured off the
  scale diagram and cross-checked to 1.7 %) + 60 mm steel plate, structural root at `x = 30 mm`
  where the plate is clamped between the two machined LE halves. Recorded in `reference.md`; the
  deck writer's boundary condition goes at the root, not the nose.
- The rigid control is the **same coupled path with a stiffer plate** (`b/c = 4.23e-3`), which HG
  measured — so both ends of the increment carry an experimental anchor.
- Both the **absolute** bands and the **increment** bands sit in the VERDICT line (operator
  decision), knowing ADR-022 makes a NO-GO on the absolute clause a live outcome.
- The paired path must segment on the **prescribed** period, never an FFT-detected one:
  `paired_delta_uncertainty` compares periods at `period_rtol = 1e-9` and would — correctly —
  refuse two independently-detected periods.

**Ledger (carried, not dropped)**: Stage-11 PSS gates share the S3/S5 hole; mesh fallback ladder
into the V&V runner; vertex-manifoldness (bowtie) check; 3D external-geometry mode; fair-test
surrogate speed-up; **the 393² certification rung (Stage 16, still untouched)**; `vv-transonic.yml`
lacks both a concurrency group and `AERO_RUN_LONG_REAP`; the README STATUS generator cannot express
"complete, not yet tagged"; `select_fluid_mesh` hard-codes `fluid-openfoam` instead of using
`spec.fluid_participant_dir`.

**STAGE-21 prompt**: not yet authored — Stage 20 is not finished, and the next session resumes
Stage 20 rather than starting 21.

## 8. Pointers for next session

- **Read first:** this file (especially §2's session-4 operator decisions and §6.14-§6.16), then
  `docs/handoff-bundle/STAGE-20-RESUME.md`, then ADR-038, then
  `data/references/fsi/heathcote_gursul_2007/reference.md` (§6.2's traps are live). Session 4's
  roadmap, with the four operator decisions folded in, is
  `/root/.claude/plans/stage-20-flexible-refactored-aurora.md`; it carries a commit-by-commit
  sequence for the rest of Phases 3B-4 and a costed pre-flight ordering.
- **Do not re-derive:** the `ccx_preCICE` conventions (§6.1 — they came from upstream's bytes), the
  HG geometry and uncertainties (`reference.md`, text-sourced and exact), or the provenance
  decision (ADR-038 records the rejected alternative and why).
- **Run first to verify:** `pytest -q tests/unit tests/stage_20` (**418** pass), then
  `python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5` (~35 s end to end;
  re-verified PASS on 2026-08-04, `stopped_by=all-exited`, both participants rc=0, 2790 cells).
- **Do NOT re-derive:** the ADR-036 band-regex defects. Measured this session, and the
  work-of-record had them wrong: `r"^\s+(D\d) [^\n]*within (\d+) %"` **silently DROPS** `D9` and
  `D10` (it needs a literal space after the id, so `D10 ` never matches), the phantom pair comes
  from `^\s+` matching **five-space continuation lines**, and greedy `[^\n]*` reports the **last**
  band on a line mentioning two. Silent omission is strictly worse than aliasing for a parity test:
  forget `D10` in `metrics()` too and both sides agree. The replacement must anchor at exactly two
  spaces, use `[A-Z]\d{1,2}`, accept fractional percents and `\(no band\)`, be **non-greedy**, and
  guard that no clause line carries two band tokens.
- **Corrections to the resume prompt**, all verified against the code — carry them forward:
  `_write_case` is `PreciceCoupledSolver._write_case` at `solver.py:168-207`, **not** in `case.py`;
  `load()` emits **23** scalars, not 20; the `"tutorial"` literal appears at **7 production + 2
  test** sites, not eight; and the approved-plan path the prompt names
  (`tage-20-flexible-warm-beacon.md`) **does not exist** — the real one is
  `/root/.claude/plans/stage-20-flexible-typed-pinwheel.md`, itself stale on `h`, on the
  plane-stress element choice (superseded by the C3D8I slab) and on its Phase-6 sizing. This
  session's roadmap, with the two operator decisions folded in, is
  `/root/.claude/plans/stage-20-flexible-cryptic-umbrella.md`.

## 9. Artifacts produced

7 commits on `stage-20-flexible-flapping-wing-fsi`, PR **#44** (draft, all 10 host-side required
checks green). New: ADR-038; `db/migrations/005_container_set.{py,sql}`;
`scripts/stage20_{acquire_perpendicular_flap,calculix_smoke}.py`;
`scripts/grant_aero_build_ssh_to_aero_dev.sh` + its runbook; `tests/stage_20/` (45 tests);
`data/references/fsi/{heathcote_gursul_2007,precice_perpendicular_flap}/`;
`data/vv/stage20_calculix_smoke.json`. Modified: the provenance package, `CoupledCaseSpec`, the
executor and the three adapters' failure paths, `CONSTITUTION.md`.

## 10. Confidence / risk

**Confident.** The two-container coupling is real and measured, not inferred: 50/50 windows
converged, both participants exited 0, and the tip trace shows a deflection under a fluid force
that grows from zero. The provenance change is strictly additive and its backward compatibility is
pinned by tests that construct pre-Stage-20 JSON. The reference's text-sourced values are quoted,
not read off a plot.

**Not yet established.** Everything Stage 20 is actually *for*. There is no authored case, no
pre-registration, no campaign, and therefore no application-fidelity claim — and none may be made
until ADR-039 exists. The smoke says the plumbing works; it says nothing about Heathcote-Gursul,
and the physics it ran is upstream's flap in a channel.

**The known-hard part is still ahead.** ADR-022 measured the platform's 2-D plunging solve missing
HG's *absolute* rigid thrust by −28 %/+58 % with an St-dependent slope error. Stage 20 removes one
of its two root causes (the teardrop-vs-NACA-0012 geometry substitution) but not the other
(2-D vs 3-D). With the absolute clause gated by operator decision, a NO-GO on it is a live and
reasonable outcome; the verdict is designed to be reported clause by clause so that "NO-GO on
absolute fidelity, GO on the flexibility increment" reads as the honest result it would be.

**Bus factor.** The single most important fact not derivable from the code is §6.1 — upstream's
CalculiX conventions, learned from bytes rather than documentation. §6.2's two reference traps are
second: a `C_T/St²` axis under a "thrust coefficient" caption has already cost this repo one
wrong reference file.
