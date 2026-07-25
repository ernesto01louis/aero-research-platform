# ADR-033 — Arbitrary-geometry ingestion contract + the `aero[cad]` extra

- **Status:** accepted
- **Date:** 2026-07-26
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 18)
- **Stage:** 18
- **Supersedes:** —

## Context and problem statement

Stages 15-17 optimized a NACA-4 airfoil whose blockMesh topology is valid by
construction. Stage 18 (`docs/handoff-bundle/STAGE-18-arbitrary-geometry-ingestion.md`)
removes that ceiling: the platform must ingest an **external** surface it did not
analytically generate, refuse or repair the ones that would silently produce a garbage
mesh, and only then let a mesher near them. Nothing existed before this stage — no STL
code, no quality checks, no `aero/geometry/` package (`aero/adapters/openfoam/geometry.py`
is the analytic NACA-4 curve generator and says so in its docstring).

Constraints: PLATFORM-NOT-HUB (Invariant 1/4 — the core imports stdlib + numpy +
pydantic only, structurally enforced by `import-platform-only.yml`); FAIL-LOUD
(Invariant 2); four-fold provenance (Invariant 3) must cover the geometry bytes and
identity; license posture (Invariant 5).

## Decision drivers

- The dominant practical failure mode is **automated meshing on never-before-seen,
  non-watertight, or thin-feature geometry** (`00-MISSION-AND-SCOPE.md` §3.2) — the
  hard part is failing loud on bad input, not the happy path.
- A repaired geometry must be auditable: a human must see exactly what changed.
- The geometry identity must enter the provenance tuple: `config_hash` covers only the
  case spec, so an ingested surface's bytes would otherwise be invisible to it.
- A CAD kernel is heavy (OCCT); the core must not carry it.

## Considered options

1. **Pure-numpy core (STL + 3MF) + STEP behind a new `aero[cad]` extra (build123d)** —
   loaders, quality analysis, and bounded repair implemented in-repo on stdlib + numpy
   + pydantic; the CAD kernel only for STEP tessellation, lazy-imported.
2. **`trimesh` as a core dependency** — mature checks/repair for free, but drags a
   dependency tree into the platform core (PLATFORM-NOT-HUB violation) and its silent
   auto-repair conveniences are exactly the failure mode the stage forbids.
3. **In-SIF OpenFOAM surface tooling only** (`surfaceCheck`/`surfaceClean`/
   `surfaceSplitNonManifolds`) — zero new host code, but couples ingestion to a running
   cluster + root apptainer, returns unstructured text instead of typed reports, and
   cannot run in the required CI unit job.

## Decision outcome

Chose **Option 1**: a new `aero/geometry/` core package (pure stdlib + numpy +
pydantic, added to the `import-platform-only` import list) with STEP behind the new
`aero[cad]` extra. In-SIF surface tools remain available to campaign scripts as
cross-checks, not as the gate of record.

The contract, concretely:

1. **`TriSurface`** (`aero/geometry/_base.py`) — read-only numpy arrays
   (`vertices (V,3) float64`, `faces (F,3) int64`), structural validation only.
   Deliberately **not** a pydantic model (10^5+ triangles; the `Signal` tuple idiom
   does not scale); everything that travels in a bundle IS strict pydantic.
   Topological brokenness passes construction **on purpose** so the quality report can
   describe it — only structurally meaningless input (bad shapes, out-of-range
   indices, non-finite coordinates) raises at construction.
2. **Loaders** — STL (binary + ASCII, format detected by the binary size equation, not
   the `solid` prefix) and single-mesh 3MF in core; STEP via
   `aero.geometry.cad.load_step` (lazy import, declared tessellation deflections).
   The STL reader welds **bitwise-identical** coordinates (lossless normalization that
   makes edge topology meaningful); tolerance merging is strictly a repair action.
3. **`QualityReport`** (`aero/geometry/quality.py`) — watertightness, edge-manifoldness,
   orientation consistency, duplicate faces, degenerate triangles
   (area < 1e-12 · bbox_diag², or a repeated index), non-adjacent pairwise
   self-intersections (sweep-and-prune AABB broadphase + vectorized Möller narrow phase,
   ε = 1e-9 · bbox_diag, *touching counts as intersecting* — conservative by design),
   and feature-size proxies (min edge length, min triangle altitude).
4. **Bounded, declared repair** (`aero/geometry/repair.py`) — opt-in only, never
   implicit. Fixed order: exact/tolerance vertex merge → drop duplicate faces → drop
   degenerate faces → BFS winding fix (+ outward global flip via signed volume) →
   planar ear-clip hole filling. Every mutation is a typed `RepairAction` in the
   returned ledger; anything outside the pre-registered bounds (ADR-034 R-gates) is
   left untouched for the gate to refuse.
5. **`ingest()`** (`aero/geometry/ingest.py`) — load → (declared repair) → quality →
   Q-gate. Failure raises **`GeometryError`** naming every failed check and every
   repair applied (CLI exit code 5 via `aero geometry ingest`). The returned
   `IngestedGeometry` record serializes without the in-memory surface and carries
   **`surface_sha256`** (SHA-256 of the source file bytes) — downstream case specs
   embed it so `config_hash` covers the geometry identity, and the source file is
   DVC-tracked so `dvc_input_hash` covers the bytes.
6. **`aero[cad]` = `build123d==0.11.1`** (pinned exactly, Hard Rule 8). License
   disposition: build123d is Apache-2.0; it rides on the OCP wheel wrapping OCCT,
   which is **LGPL-2.1 with the OCCT exception**. Invariant 5 lists GPL-3/LGPL-3/
   Apache-2.0/BSD-3; the platform already accepts MIT (typer, loguru, JAX-Fluids —
   ADR-008 §D2 precedent that the list names the *posture*, not an exhaustive
   whitelist). LGPL-2.1-with-exception is a weak-copyleft license strictly milder in
   practice than the LGPL-3 already admitted, is dynamically linked behind an optional
   extra, and ships no proprietary blobs — admitted on that basis and recorded here.
7. **External-anchor acquisition** (executed under ADR-034's V-gates): the Turek-Hron
   FSI3 cylinder+flag surface is **extracted from the third-party-authored preCICE
   tutorial case** (`github.com/precice/tutorials`, LGPL-3.0, pinned commit SHA) by
   running the *upstream* blockMeshDict once and extracting the cylinder+flag wall
   patches; the platform applies only **declared, shape-preserving transforms**
   (z-extrusion of the prismatic band + end caps to close the solid — the x-y profile
   stays 100 % third-party-authored), every command + SHA-256 recorded in
   `data/references/fsi/turek_hron_fsi3/reference.md`. No published Turek-Hron
   STL/STEP exists anywhere (GitHub code search, 2026-07-25: zero hits). Pre-declared
   fallback if extraction proves unusable: author STEP from the published dimensions
   via `aero[cad]`, documented honestly as weaker externality.

### Consequences

- **Positive:** ingestion is typed, auditable, host-testable (44 unit tests in the
  required CI job), and structurally clean (`aero.geometry` imports under
  `import-platform-only`; `build123d`/`OCP`/`cadquery` added to its banned tuple).
  The mesher can trust its input or a loud `GeometryError` explains why not.
- **Negative (honest limits, all declared in docstrings):** the grid-quantized
  tolerance merge can miss near-duplicate pairs straddling a grid cell; hole filling
  handles simple planar-ish loops only (ear clipping, ≤ `max_hole_edges`); the
  intersection ε is conservative (near-touching counts as intersecting); 3MF support
  is single-mesh (no assemblies/transforms); vertex-manifoldness (bowtie vertices) is
  not checked in v1 — edge-manifoldness + orientation + intersection cover the mesher
  -relevant failure modes.
- **Neutral / followup:** the mesh-side gate (checkMesh thresholds + fallback ladder)
  is ADR-034's; a future FFD/SDF optimization space (ledgered) would build on
  `TriSurface`.

## Pros and cons of considered options

### Option 1 — pure-numpy core + `aero[cad]` extra

- Good: PLATFORM-NOT-HUB preserved; every check unit-testable in required CI; typed
  reports; repair semantics exactly as strict as the stage demands.
- Bad: we own the computational-geometry code (mitigated: small, tested, and the
  campaign cross-checks against in-SIF `surfaceCheck`).

### Option 2 — trimesh in core

- Good: battle-tested checks and repair out of the box.
- Bad: violates Invariant 1/4; its convenience auto-repairs are the anti-pattern the
  stage exists to prevent; still needs a wrapper to make reports typed.

### Option 3 — in-SIF tooling only

- Good: zero new geometry code; the same binaries the mesher uses.
- Bad: cluster + root-apptainer required for *ingestion*; text parsing instead of
  types; not CI-testable; couples a pure-analysis step to infrastructure.

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-18-arbitrary-geometry-ingestion.md`
- Related ADR: ADR-034 (pre-registered mesh gate + ladder + validation protocol);
  ADR-008 §D2 (license-fact precedent); ADR-016 (FSI strategy — Stage 19 consumer of
  the Turek-Hron geometry)
- Related handoff: `docs/handoffs/STAGE-17-surrogate-accelerated-optimization-DONE-2026-07-24.md`
- External: Turek & Hron (2006), "Proposal for numerical benchmarking of fluid-
  structure interaction between an elastic object and laminar incompressible flow";
  `github.com/precice/tutorials` (turek-hron-fsi3); build123d 0.11.1 (Apache-2.0);
  OCCT license (LGPL-2.1 + exception)
