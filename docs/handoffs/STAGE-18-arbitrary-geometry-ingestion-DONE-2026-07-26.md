---
stage: 18
stage_name: "Stage 18 — Arbitrary-Geometry Ingestion + Robust Meshing"
status: complete
date_started: 2026-07-26
date_completed: 2026-07-26
session_duration_hours: 4
claude_code_version: 2.1.150
model: claude-fable-5
git_sha_start: d0b8fff05d5b8e5a01d80cd1ea36f6ba4e3bd4d4
git_sha_end: 56cff0eca9e93400573cd54d63a60afae3111c4f
stage_tag: v0.0.18
next_stage: 19
next_stage_name: "Stage 19 — preCICE FSI Core (Turek-Hron FSI3)"
---

# Stage 18 — Arbitrary-Geometry Ingestion + Robust Meshing — DONE

## Headline

**GO — every pre-registered gate passed, none relaxed.** An **external** geometry the platform
did not analytically generate (the Turek-Hron cylinder+flag surface, extracted from the pinned
third-party preCICE tutorial mesh) was ingested through a fail-loud quality gate with **zero
repairs required**, meshed by snappyHexMesh behind the platform's first *enforced* `checkMesh`
gate (rung **R0** won on the first attempt: 40 800 cells, max non-orthogonality **28.0** ≤ 65,
max skewness **2.24** ≤ 4, `Mesh OK`), and evaluated by ground-truth CFD against the published
benchmark values:

| test | quantity | measured | reference | error | tol | |
|---|---|---|---|---|---|---|
| CFD2 (Re 100, steady) | cd | 2.70584 | 2.734 | **1.03 %** | 5 % | PASS |
| CFD2 | cl | 0.221659 | 0.210686 | **5.21 %** | 10 % | PASS |
| CFD3 (Re 200, periodic) | mean cd | 2.20458 | 2.19725 | **0.33 %** | 5 % | PASS |
| CFD3 | shedding frequency | 4.51008 Hz | 4.3956 Hz | **2.60 %** | 5 % | PASS |
| CFD3 | lift amplitude | 2.19726 | 2.18905 | **0.38 %** | 15 % | PASS |

The CFD3 stretch was **not** skipped — it ran inside the pre-declared 12 h budget (≈2.5 h wall
clock, serial) and validated tighter than CFD2 on drag. Both solves carry a clean-tree four-fold
provenance tuple and an MLflow run (`54e5983e…` CFD2, `a14e2cd3…` CFD3). Reported tier:
**`validated`** — the evaluation is reference-anchored and CFD-verified, but no formal GCI is
claimed (snapped snappy grids are not geometrically self-similar, so ADR-028's fixed-mapping
premise does not hold; see §10).

## 1. Deliverables status

| # | Deliverable | | Note |
|---|---|---|---|
| 1 | Geometry-ingestion module (`aero/geometry/`, typed `IngestedGeometry`, `GeometryError`) | ✅ | STL (binary+ASCII) + 3MF in core; STEP behind `aero[cad]`; 60 host-side unit tests |
| 2 | Quality gate + bounded DECLARED repair | ✅ | Q1-Q5 gates; `RepairAction` ledger; out-of-bounds defects are left for the gate to refuse, never silently patched |
| 3 | Robust meshing + pre-registered gate + fallback ladder | ✅ | `mesh_quality.py` (M1-M5), `robust_mesh.py` (F1-F5); exhausted ladder = loud NO-GO, thresholds immutable across rungs |
| 4 | One external geometry proven end-to-end, reference-validated | ✅ | Turek-Hron CFD2 **and** CFD3, both under pre-registered tolerances, four-fold provenance + MLflow |

## 2. Decisions made (rationale)

- **Pure-numpy ingestion core + `aero[cad]` for STEP** (ADR-033). Rejected `trimesh` in the core
  (PLATFORM-NOT-HUB, and its convenience auto-repairs are precisely the failure mode this stage
  exists to prevent) and in-SIF-only surface tooling (needs a live cluster + root apptainer for
  what is pure analysis, returns untyped text, cannot run in the required CI unit job).
- **Pre-registration before any campaign solve** (ADR-034, mirroring ADR-032): Q (ingestion),
  R (repair bounds), M (mesh quality), F (ladder), V (validation) — with the block duplicated
  verbatim in the campaign driver's docstring as the operational copy.
- **M2 = non-ortho ≤ 65**, tightened from ADR-024's escalation floor of 70 because snappy
  hex-dominant meshes routinely achieve it. The legacy airfoil C-grid systematically fails
  `Mesh OK` at wake-cut non-ortho ~84 (ADR-028/030) — that exemption is documented history,
  deliberately **not** inherited by the new gate. The two mesh families are held to different,
  documented bars.
- **Quasi-2D by construction, not by refinement**: snappy cannot refine anisotropically, so the
  background is generated at *target* resolution and snappy does **no volumetric refinement** —
  which is what keeps the slab exactly one cell thick. The ladder therefore steps background
  cell size and layer count. A 4-cell slab + `symmetryPlane` fallback was pre-declared as a
  *construction* change (not a gate change) and was not needed.
- **Acquisition preserves externality**: no published Turek-Hron STL/STEP exists anywhere
  (GitHub code search, 0 hits). Rather than author the shape from published dimensions (which
  would make it platform-generated), the surface was extracted from the third-party preCICE
  tutorial's blockMesh at a pinned commit, with only a declared two-cap closure applied — the
  x-y profile is 100 % upstream-authored. The weaker "author from dimensions" path was
  pre-declared as a fallback and not used.
- **CFD3's near-zero mean lift is a diagnostic, never gated** — a relative tolerance on a
  quantity ~2.7 % of its own oscillation amplitude invites tolerance inflation (the WBD2004
  gated-vs-diagnostic pattern).

## 3. Deviations from the plan

- The first R0 mesh attempt **failed** on a case-writer typo (`minMedianAxisAngle`; v2412 spells
  it `minMedialAxisAngle`). This is the system working: the ladder refused the half-written mesh
  rather than meshing on. Fixed as a code defect (commit `8ce157c`) and the campaign restarted
  from scratch; no gate was touched.
- The plan treated CFD3 as a budget-gated stretch that might be skipped. It ran and passed.
- The first adversarial-review workflow was killed by a session usage limit (16/18 agents lost);
  it was re-run to completion afterwards.

## 4. Environment / dependency / schema changes

- **New package** `aero/geometry/` (`_base`, `stl`, `threemf`, `quality`, `repair`, `ingest`,
  `cad`). **New adapter modules** `aero/adapters/openfoam/{external_geometry,mesh_quality,robust_mesh}.py`.
  **New V&V package** `aero/vv/external_geometry/`.
- **New extra** `aero[cad] = build123d==0.11.1` (Apache-2.0 / OCP-OCCT LGPL-2.1+exception).
- **New spec** `ExternalGeometrySpec` (carries a mandatory `surface_sha256`; the writer refuses
  to mesh bytes that do not match it). `OpenFOAMSolver.prepare/mesh` gained additive
  external-geometry branches (the detached-mesh path); no protocol or ABC change.
- **New CLI group** `aero geometry ingest` (exit code 5 for `GeometryError`).
- **Data:** `data/references/fsi/turek_hron_fsi3/` — `cylinder_flag.stl` (DVC, `aero-minio`),
  `cylinder_flag.stl.sha256` (git), `cfd_reference.csv` (git), `reference.md`.
- `stage_18` pytest marker; `cad_extra_installed` fixture; `.aero-stage` → 18.

## 5. CI/CD changes

- **`tag-handoff-gate.yml` (NEW)** — the tag-push handoff check that CLAUDE.md Hard Rule 10 and
  `handoff-discipline.md` had *claimed existed since Stage 16* but never did. It now runs
  `scripts/check_handoff_exists.sh` on `v0.0.*` tag pushes. Docs corrected to say Stage 18.
- `import-platform-only.yml`: imports `aero.geometry`; bans `build123d`/`OCP`/`cadquery`.
- `vv-required.yml`: internal paths-filter now covers `aero/geometry/**` (the workflow itself
  is still never path-filtered — the Stage-13 lesson).

## 6. Gotchas discovered

- **OpenFOAM-ESI v2412 spells it `minMedialAxisAngle`** (medial, not median) in
  `addLayersControls`. A single wrong key aborts snappy after the castellate+snap work is done.
- **OCCT tessellation duplicates face-boundary vertices**, so a STEP import is topologically
  "open" until exact-welded — the same normalization an STL triangle soup needs. Without it a
  clean CAD box reports 24 boundary edges and 34 self-intersecting pairs.
- **`pre-commit`'s ruff-format hook can silently abort a commit** (staged-changes-vs-hook-fixes
  conflict → "Rolling back fixes", exit 0, nothing committed). Always verify with `git log`
  after committing; two commits were lost to this mid-session before it was noticed.
- **`surfaceMeshExtract` patch lists don't survive nested SSH quoting** — write the command to a
  script file and run `bash -lc /case/extract.sh` (the login shell is also required for the FOAM
  environment).
- The Stage-16 `checkMesh` "gate" never gated anything (it recorded metrics into untyped dicts
  and no threshold was ever compared). The stage prompt's "reuse the existing checkMesh gate"
  was a build, not a reuse.
- A naive float regex (`[0-9.eE+-]+`) swallows the sentence period in
  `Min volume = 1.2e-08.` and crashes `float()` — parse floats with an anchored pattern.

## 7. Open items for the next stage (and beyond)

- **STAGE-19 prompt exists**: `docs/handoff-bundle/STAGE-19-precice-fsi-core.md` (preCICE FSI
  core — populate `aero/adapters/precice/` + `aero[precice]`, verify coupling on the pinned
  upstream Turek-Hron FSI3 tutorial, gate on published displacement bands, build the CalculiX
  SIF; ADR-016 → `accepted` on gate pass).
- **Ledger (new this stage):** promote the mesh fallback ladder into the V&V runner (`aero vv run`
  runs external-geometry cases single-shot today — the ladder lives in the campaign driver);
  vertex-manifoldness (bowtie) check in `aero/geometry/quality.py`; 3D (non-slab)
  external-geometry mode.
- **Ledger (updated):** "Turek-Hron tabulated → Stage 18" **CLOSED**; the generic external-aero
  autogen template got a progress note (quasi-2D channel pipeline done; 3D sizing / BC templates
  / turbulence-y+ strategy remain); the fair-test surrogate speed-up is now unblocked by
  higher-DV shape spaces this stage enables. The 393² certification rung stays open, untouched.

## 8. Pointers for next session

- **Read first:** this handoff → ADR-033 → ADR-034 → `data/references/fsi/turek_hron_fsi3/reference.md`
  → `data/vv/stage18_turek_hron.json`.
- **Verify quickly (no cluster needed):**
  `aero geometry ingest data/references/fsi/turek_hron_fsi3/cylinder_flag.stl` → Q-gates green,
  zero repairs, extents 0.15–0.60 × 0.15–0.25. `pytest -q tests/unit` → all green.
- **Do NOT re-read:** the Stage-16/17 certification detail (unchanged); the geometry math is
  covered by its unit tests.

## 9. Artifacts produced

- Campaign bundle `data/vv/stage18_turek_hron.json` (ingestion record + both ladders + both
  benchmark results + verdict). MLflow runs `54e5983e5a92424d96cd31931c3feaa5` (CFD2),
  `a14e2cd34b1145b48b858a1b96fa0ac8` (CFD3) in `aero-provenance`.
- The acquired external geometry + its reference data (DVC + git sidecars + provenance doc).
- ADR-033, ADR-034; STAGE-19 prompt; `tag-handoff-gate.yml`; ~60 new unit tests (full suite
  green, mypy strict clean, ruff clean).

## 10. Confidence / risk note

- **High confidence:** the geometry is genuinely external and its provenance chain is complete
  and reproducible (pinned upstream commit + recorded digests + a declared, minimal transform);
  the mesh gate is real and enforced (it demonstrably refused a broken mesh); both CFD results
  are reference-anchored, CFD-verified, and comfortably inside tolerances that were fixed before
  the campaign ran.
- **Honest limitations:** (i) the V3/V5 tolerances are engineering judgment for a quasi-2D snappy
  mesh at h = 0.005, not derived from a platform-owned convergence study — **no GCI is claimed**
  and the tier is `validated`, not thesis-grade; (ii) one geometry, one mesher, one flow regime
  (laminar, channel-confined) — robustness on *arbitrary* geometry families is asserted only for
  what was tested, and the ledgered 3D/autogen work is where that generalizes; (iii) `aero vv run`
  can still solve these cases single-shot without the ladder (the ladder is campaign-driver-side)
  — ledgered, and the M-gate is not bypassed in the campaign path; (iv) repair breadth is
  deliberately narrow (planar ear-clip holes, edge-manifoldness only — bowtie vertices pass).
- **Bus factor:** every number in this handoff traces to the committed bundle JSON with run IDs
  and clean four-fold provenance; the acquisition is re-runnable from
  `scripts/stage18_acquire_geometry.py` plus the pinned upstream SHA in `reference.md`.
