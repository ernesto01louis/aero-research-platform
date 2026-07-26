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
  the re-run completed and **found 9 confirmed defects (14 further findings refuted)**, all
  fixed with regression tests before the tag — see §6. Two were in the self-intersection
  test itself, i.e. in gate Q3's own machinery. The campaign was then **re-run end to end
  under the fixed code** so the shipped bundle is produced by the shipped gates; all five
  gated quantities reproduced identically.

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

**From the post-implementation adversarial review (9 confirmed, 14 refuted) — all fixed
in `6abf00f`, with regression tests:**

- **A self-intersection FALSE NEGATIVE in gate Q3's own machinery.** Möller's odd-vertex
  selection was missing its two canonical zero-distance branches, so a vertex lying
  *exactly* on the other triangle's plane — routine for axis-aligned or planar-faceted
  CAD — made both interpolants collapse to a point, the interval degenerate, and a real
  intersection invisible. A self-intersecting surface could pass Q3 and reach snappy.
  Fixed; the regression suite now includes a **corner-order-invariance property test**
  (rotating a face's corners is the same geometry, so the verdict may not change), which
  structurally forbids the whole class of bug rather than the one instance.
- **The intersection epsilon had the wrong units.** Plane distances were dotted with
  un-normalized normals (|n| = 2·area) and compared against a length, so the effective
  perpendicular tolerance scaled as 1/area: on a finely tessellated surface, distinct
  sheets closer than ~1 mm were reported as intersecting (a false *positive* that would
  have failed valid geometry at a gate that may not be relaxed). Now normalized; covered
  by tessellation-density and coordinate-scale invariance tests.
- **The acquired geometry was re-verified under the corrected gate** (still 0
  self-intersections, 0 repairs), and the fixed code was differential-tested against a
  brute-force reference over 3000 randomized triangle pairs with zero real mismatches —
  so the campaign's Q attestation stands.
- **`n_elements` published the wrong number.** snappy never prints `nCells:`, so the
  external-geometry branch reported blockMesh's *pre-snap background* count (41 000)
  while the gate's own checkMesh in the same record said 40 800 — two contradictory mesh
  sizes in one bundle, with the wrong one in the provenance-bearing field. Now parses the
  last snappy stage line.
- **checkMesh diagnostics vanished exactly when the mesh was bad.** v2412 prints each
  metric in two mutually exclusive branches; the regexes matched only the pass wording
  (`Max aspect ratio = X OK.`), so a loud NO-GO report lost the D1 numbers that explain
  it (the fail branch uses `Max aspect ratio: X`).
- **The pre-registered mapped-inlet contingency was dead on arrival.** Every boundaryData
  sample shared one z, i.e. the points were collinear, and v2412's planar-interpolation
  basis FatalErrors on exactly that ("are all your points on a single line instead of a
  plane?"). Now emits two z rows spanning the slab.
- **The Q attestation was not bound to the meshed surface.** `ingest()` gated an
  in-memory surface from `--stl` while the case spec independently took the repo STL, and
  nothing compared the two digests — so `--repair` (which is never written back) or a
  `--stl` override could have attested Q-gates for a surface snappy never saw. The driver
  now refuses to proceed unless the gated digest equals the meshed digest.
- **The verdict stamped a rule it did not evaluate.** The bundle claimed
  `GO <=> Q and M-under-F and V1-V4` while V2 (the solve converged) was never checked
  anywhere — a run that burned every iteration with the force still drifting would have
  been reported if `cd[-1]` happened to land in tolerance. V2 is now enforced fail-loud in
  `TurekHronCFD2.evaluate`, and every verdict clause is evaluated and recorded in the
  bundle. (The Stage-18 solve did converge — simpleFoam exited at 265 iterations — so the
  reported result was sound; the *gate* was the defect.)

**From implementation:**

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
- ADR-033, ADR-034; STAGE-19 prompt; `tag-handoff-gate.yml`; ~80 new unit tests including the review regressions (full
  suite green: 209 unit tests, mypy strict clean, ruff clean).

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
- **Reviewed:** a 4-dimension adversarial review (geometry math, OpenFOAM correctness,
  gate integrity, docs/test honesty) with a per-finding refutation pass ran against the
  finished diff; 9 of 23 findings survived refutation and were fixed before the tag. The
  two most serious were in the self-intersection test that gate Q3 depends on — a
  reminder that a gate is only as trustworthy as the code implementing it, and that the
  campaign passing is not evidence the gate was correct.
- **Bus factor:** every number in this handoff traces to the committed bundle JSON with run IDs
  and clean four-fold provenance; the acquisition is re-runnable from
  `scripts/stage18_acquire_geometry.py` plus the pinned upstream SHA in `reference.md`.
