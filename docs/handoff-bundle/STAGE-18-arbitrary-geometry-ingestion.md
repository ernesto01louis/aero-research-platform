# STAGE 18 — Arbitrary-Geometry Ingestion + Robust Meshing

> Stages 15-17 optimized a 2-DV NACA-4 airfoil whose mesh topology is invariant by
> construction — the shape parametrization guarantees a valid mesh for every candidate, which
> is exactly what let the matched-condition deltas stay honest. That invariance is also the
> ceiling: the optimizer cannot yet touch a geometry the platform did not analytically
> generate. Stage 18 removes the ceiling — ingest an EXTERNAL geometry (STL / CAD), quality-gate
> and repair it, mesh it robustly with a fallback ladder, and prove one external geometry all
> the way through to a CFD-verified evaluation. This is the on-ramp to higher-DV shape spaces
> (FFD / SDF, the `aero[bo]` BoTorch/Ax backend reserved in ADR-026) and to the flapping-wing
> flagship geometries.

## BEFORE YOU START — READ

1. `CLAUDE.md` (Invariants; the 21-stage map — Stage 18 is arbitrary-geometry ingestion).
2. `.aero-stage` (→ `18`). `docs/handoffs/STAGE-17-*-DONE-*.md` (the surrogate-accelerated
   result + the own-data corpus you now have) and `docs/handoffs/STAGE-16-*-DONE-*.md` (the
   certification verdict — the 393² rung is still ledgered, out of scope here too).
3. ADR-026 (the direct-CFD optimizer + the reserved `aero[bo]` extra), ADR-018/019 (mesh
   motion + unsteady post-processing), and the mesh-family machinery in
   `aero/optimize/mesh_family.py` (ADR-028 — fixed-mapping refinement, which an ingested
   geometry cannot assume).
4. `.claude/rules/flapping-validation-ladder.md` — the FSI tier names Turek-Hron FSI3 (Stage 18
   in the ladder table) as the reference case; acquire its geometry + reference data early.
5. `.claude/rules/optimization-integrity.md`, `docs/vv/output-validity-bar.md`.

## Why this stage

Every real design study starts from a CAD model or a scanned surface, not a NACA equation. To
be a general aerodynamic optimizer the platform must (a) ingest an arbitrary watertight
surface, (b) refuse or repair the ones that would silently produce a garbage mesh, and (c)
mesh robustly enough that an optimizer can vary the geometry without a human babysitting the
mesher. The hard part is not the happy path — it is failing loud on the geometries that would
otherwise pass a broken mesh into a CFD solve and report a confident wrong number.

## Deliverables

1. **A geometry-ingestion module** (`aero/geometry/` — new) that loads STL / CAD (STEP via a
   CAD kernel behind an extra, or a pre-tessellated STL/3MF in the core), and exposes a typed
   `IngestedGeometry` carrying the surface + a computed quality report. Fail-loud on
   non-manifold / non-watertight / self-intersecting input — a `GeometryError`, never a silent
   repair-and-proceed.
2. **A quality gate + bounded repair** — watertightness, manifoldness, minimum feature size vs
   target first-cell, degenerate-triangle detection; a bounded, DECLARED repair pass (hole
   filling / re-tessellation) whose every action is recorded in the quality report, so a
   repaired geometry is auditable and a human can see what changed.
3. **A robust meshing path with a fallback ladder** — a snappyHexMesh (or equivalent) driver
   that meshes the ingested geometry, checks `checkMesh` against pre-registered quality
   thresholds, and on failure steps down a DECLARED ladder (coarser refinement / relaxed
   layers) rather than shipping a bad mesh; a mesh that cannot pass the floor is a loud NO-GO,
   not a silent pass. Reuse the existing `checkMesh` gate + provenance plumbing.
4. **One external geometry proven end-to-end** — ingest → quality-gate → mesh → a single
   CFD-verified evaluation with four-fold provenance, validated against a reference where one
   exists. The natural anchor is the **Turek-Hron FSI3 cylinder+flag geometry** (the FSI tier
   of the validation ladder, needed for Stage 19 anyway) or a published external airfoil STL;
   acquire the reference data DVC-tracked under `data/reference/<case>/` with a `reference.md`.

## GO / NO-GO

**GO** = an external geometry the platform did NOT analytically generate is ingested,
quality-gated, robustly meshed, and evaluated by ground-truth CFD, with the quality report +
mesh gate + four-fold provenance all recorded, and (where a reference exists) the evaluation
validated against it. **NO-GO** = if robust meshing cannot clear the pre-registered mesh gate
on a real external geometry, document the failure modes honestly and ship the ingestion +
quality gate + the loud-failure ladder as the deliverable — a mesher that fails loud on bad
geometry is itself the safety property; never relax a mesh-quality threshold to manufacture a
passing mesh.

## Infra + conventions

Serial OpenFOAM on aero-dev; snappyHexMesh is CPU-heavier than the airfoil blockMesh — budget
accordingly and keep the detached-driver + clean-tree-provenance discipline. A CAD kernel
(CadQuery / build123d / OCP) rides behind a new optional extra, NOT the core (PLATFORM-NOT-HUB;
the core stays stdlib + numpy + pydantic). Conventional commits `<type>(stage-18)`; branch +
PR; the four-layer memory/handoff discipline.

## POST-STAGE HANDOFF (mandatory)

Write `docs/handoffs/STAGE-18-*-DONE-*.md` (frontmatter + 10 sections). Emphasize the
ingestion contract, the quality gate + repair ledger, the mesh fallback ladder and its
pre-registered thresholds, and the one end-to-end external-geometry evaluation. Confirm the
Stage-19 prompt exists (preCICE FSI core — Turek-Hron FSI3). Tag `v0.0.18`.
