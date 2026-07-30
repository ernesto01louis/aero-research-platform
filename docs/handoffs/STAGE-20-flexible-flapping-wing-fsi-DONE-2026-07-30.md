---
stage: 20
stage_name: "Stage 20 — Flexible Flapping Wing FSI (Heathcote-Gursul)"
status: partial
date_started: 2026-07-30
date_completed: 2026-07-30
session_duration_hours: 3
claude_code_version: "2.1.150 (Claude Code)"
model: claude-opus-5[1m]
git_sha_start: 42ebb55e984f6762e982d358678c443c857b6dce
git_sha_end: 3db1da455242263e1053e6a182a3d3d87b56f011
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
| 2 | The Heathcote-Gursul case in `aero/vv/fsi/` + DVC reference data | ⚠️ | Reference **acquired** (text-sourced values exact, uncertainties measured); figure digitization and the V&V case are not done |
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

## 3. Deviations from the stage plan

- **The stage is incomplete.** The approved plan costed the campaign alone at ~5-7 days of
  aero-dev wall clock (3 rungs × 2 arms, operator-chosen), on top of authoring a coupled case that
  has no upstream equivalent. One session was never going to reach a verdict; this handoff records
  where it actually got to.
- **Figure digitization deferred within Phase 2.** Planned as part of acquisition. The text-sourced
  half is exact and done; the figure half is specified but not executed (§7 item 1).
- **The plan's plane-stress element recommendation is superseded** by what the smoke showed
  (§6.1). Evidence over plan — which is why the smoke was sequenced first.

## 4. Environment / dependency / schema changes

- `ProvenanceTuple` gains `containers: tuple[ContainerRef, ...] = ()` and a fifth conditional
  MLflow tag `container_sif_set`. `ContainerRef` and `container_roster` are new public names.
- **Postgres: migration `005_container_set`** adds a nullable `container_sif_set TEXT` to
  `mlflow_artifact_provenance` plus a partial index. **NOT YET APPLIED on LXC 202** — see §7.
- `ExecResult` gains `transport_error` / `transport_failed`; `MeshHandle` gains `failure`;
  `aero.orchestration.describe_failure` is new.
- New pytest marker `stage_20`; new test dir `tests/stage_20/` (45 tests).
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

`perpendicular-flap/solid-calculix/all.msh` is a **one-element-thick 3-D mesh** (z ∈ {0, 1}) with
`*BOUNDARY Nall, 3` suppressing the out-of-plane dof, while both preCICE meshes are declared
`dimensions="2"`. The plan had recommended CalculiX plane-stress (`CPS8R`) elements; upstream's own
proven idiom is the slab. **Use the slab** — it is what the calculix-adapter is exercised against.

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

## 7. Open items for the next stage (and beyond)

**Blocking, in order — this is the resumption path**

1. **Finish the figure digitization** (Figs 5.6 / 5.9 / 5.13) by the method already fixed in
   `reference.md`: three independent readings per marker, multiply Fig 5.6 by `St²`, and fail loud
   against the text-sourced rows rather than preferring whichever is closer. Then write
   `scripts/stage20_acquire_hg_reference.py` to recompute and cross-check.
2. **Apply Postgres migration `005_container_set` on LXC 202** (`aero_provenance` DB). Additive
   `ALTER TABLE … ADD COLUMN` only. Until it is applied, a gated multi-container run fails loud at
   the mirror — which is the correct behaviour, but it will stop the campaign.
3. **Run `scripts/grant_aero_build_ssh_to_aero_dev.sh`** (operator; packaged, not executed —
   authorising a remote root key is the class auto-mode blocks by design). Runbook at
   `docs/operator/aero-build-to-aero-dev-ssh.md`.
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
- CalculiX **3-D slab with dof 3 suppressed**, not plane stress (§6.1).
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

- **Read first:** this file, then ADR-038, then `data/references/fsi/heathcote_gursul_2007/reference.md`
  (§6.2's traps are live), then the approved plan at
  `/root/.claude/plans/stage-20-flexible-typed-pinwheel.md`.
- **Do not re-derive:** the `ccx_preCICE` conventions (§6.1 — they came from upstream's bytes), the
  HG geometry and uncertainties (`reference.md`, text-sourced and exact), or the provenance
  decision (ADR-038 records the rejected alternative and why).
- **Run first to verify:** `pytest -q tests/unit tests/stage_20` (347 pass), then
  `python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5` (~35 s end to end).

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
