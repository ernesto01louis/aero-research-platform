# ADR-034 — Pre-registered external-geometry gates: ingestion Q, mesh M, ladder F, validation V

- **Status:** accepted
- **Date:** 2026-07-26
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 18)
- **Stage:** 18
- **Supersedes:** —

## Context and problem statement

Stage 18 proves one external geometry end-to-end (ingest → quality-gate → robust mesh →
CFD-verified evaluation, Turek-Hron rigid-flag CFD tests as the reference). The
evaluation is only worth anything if every gate — ingestion quality, mesh quality, the
fallback ladder's shape, and the validation tolerances — is committed BEFORE any
campaign mesh or solve. Stages 15-17 retracted/blocked/capped four would-be shortcuts;
the gates are the product (stage prompt: "never relax a mesh-quality threshold to
manufacture a passing mesh"). This ADR is the pre-registration of record; **the gate
block is duplicated verbatim in `scripts/stage18_turek_hron.py`'s docstring (the
operational copy); any drift between the two is a bug.**

Mesh-gate calibration facts: the platform never had a reusable checkMesh gate (the
Stage-16 scripts' closures gated nothing); ADR-024 pre-registered the only prior
thresholds (escalate at non-ortho > 70 / skewness > 4 / negative volumes); the legacy
airfoil C-grid systematically fails `Mesh OK` at wake-cut non-ortho ~84 (ADR-028/030)
— that exemption is documented history, **not** inherited: snappy hex-dominant meshes
routinely achieve non-ortho ≤ 65, so the Stage-18 gate is set there.

## Decision drivers

- Honest GO/NO-GO: the bar must be immovable once solves start.
- A ladder must degrade *cost* (resolution, layers), never *quality*.
- Serial-only aero-dev (MPI blocked): budgets are wall-clock-real.
- The quasi-2D constraint: snappy cannot refine anisotropically, so 2D-ness must come
  from the case construction, not from refinement tricks.

## Considered options

1. **Full pre-registration (this ADR)** — every gate + the ladder + tolerances +
   budget committed before the campaign; contingencies named in advance.
2. **Gate-as-you-learn** — tune thresholds against the first meshes. Rejected: that is
   exactly the manufactured-pass failure mode Stages 15-17 exist to prevent.
3. **checkMesh "Mesh OK" alone** — no explicit thresholds. Rejected: unparseable
   output or a changed checkMesh layout could silently pass; named per-check
   thresholds make the gate auditable.

## Decision outcome

Chose **Option 1**. Implementation: `aero/geometry/ingest.py` (Q, R),
`aero/adapters/openfoam/mesh_quality.py` (M), `aero/adapters/openfoam/robust_mesh.py`
(F — the gate object is constructed once and structurally cannot vary per rung),
`aero/vv/external_geometry/turek_hron_cfd.py` (V tolerances).

## The pre-registered gate block (committed before any campaign solve; NEVER relaxed)

**Q — ingestion quality** (evaluated on the post-repair surface; defaults of
`QualityGateConfig`):

- **Q1** watertight: zero boundary edges.
- **Q2** topology: (a) edge-manifold — no edge on more than two faces; (b)
  orientation-consistent winding; (c) zero duplicate faces.
- **Q3** zero self-intersecting non-adjacent triangle pairs (ε = 1e-9 · bbox-diag;
  touching counts as intersecting; the check must have RUN — a skipped check fails
  the gate).
- **Q4** zero degenerate triangles (repeated vertex index, or area < 1e-12 ·
  bbox-diag²).
- **Q5** feature-vs-cell floor: the thinnest declared geometric feature of the
  campaign geometry (the Turek-Hron flag thickness, 0.02 m per the published spec,
  cross-checked by V1) ≥ 2 × the rung's background cell size. The generic per-surface
  min-edge/min-altitude proxy is REPORTED, never gated — tessellation fineness is not
  feature size.

**R — repair bounds** (repair is opt-in; anything outside the bounds is left broken
for Q to refuse; defaults of `RepairConfig`):

- **R1** vertex-merge tolerance ≤ 1e-6 × bbox-diag.
- **R2** hole filling: planar ear-clip patches only, ≤ 32 boundary edges per hole,
  ≤ 8 holes per surface.
- **R3** every mutation recorded as a typed `RepairAction` in the bundle; no
  unledgered change to the surface.

**M — mesh quality** (checkMesh, `MeshQualityGate` defaults; ONE gate for every rung):

- **M1** checkMesh reports "Mesh OK" (zero failed checks).
- **M2** max non-orthogonality ≤ 65.
- **M3** max skewness ≤ 4.
- **M4** zero negative-volume cells.
- **M5** ≥ 1000 cells (a degenerate near-empty mesh must not read as a pass).
- **D1** (diagnostics, never gated): max aspect ratio, min volume, per-rung cell
  counts, snappy layer coverage.

**F — the fallback ladder** (`DEFAULT_LADDER`):

- **F1** rungs, in order: **R0** = h = 0.005 m + 2 surface layers; **R1** = h = 0.005 m,
  no layers; **R2** = h = 0.0075 m, no layers.
- **F2** the first rung passing M1-M5 wins; every attempt (including failures) is
  recorded in the `MeshLadderReport`.
- **F3** all rungs fail ⇒ loud NO-GO (`GeometryError` carrying the full report); the
  deliverable is then the ingestion + gate + loud-failure ladder, documented honestly.
- **F4** the `MeshQualityGate` is constructed once per campaign; no rung may alter a
  threshold (structural: the ladder never builds a gate).
- **F5** quasi-2D construction: one-cell-thick background at target resolution,
  castellate + snap with **no volumetric refinement**, `flattenMesh`, `empty`
  front/back. Pre-declared fallback *construction* (not a gate change) if snapped
  empty-patch planarity cannot be restored: a 4-cell thin slab with `symmetryPlane`
  front/back, reported as a quasi-2D caveat.

**V — end-to-end validation** (Turek & Hron 2006, rigid-flag CFD tests;
coefficient-normalized, `Cd = F / (0.5 ρ Ū² D)`, D = 0.1 m):

- **V1** ingestion metrology: the ingested surface's measured extents within 0.001 m
  (1 % of D) of the published geometry (channel 2.5 × 0.41; cylinder r = 0.05 at
  (0.2, 0.2); flag 0.35 × 0.02 ending at x = 0.6).
- **V2** the CFD2 solve converged (simpleFoam residualControl 1e-6, or a documented
  stationary force tail).
- **V3** CFD2 (Ū = 1, Re = 100, steady): **cd within 5 %**, **cl within 10 %** of the
  published values (lift is the small, sensitive quantity on a quasi-2D snappy mesh).
- **V4** four-fold provenance (clean tree) + MLflow run recorded for every gated
  solve; the STL byte-digest (`surface_sha256`) rides in `config_hash` and the STL is
  DVC-tracked (bytes in `dvc_input_hash`).
- **V5** (stretch — CFD3, Ū = 2, Re = 200, periodic; run only within the pre-declared
  budget): **mean cd within 5 %**, **lift oscillation frequency within 5 %**, **lift
  amplitude within 15 %**; the near-zero mean lift is a diagnostic, never gated
  (a relative tolerance on ~0 invites tolerance inflation). Skipping CFD3 on budget
  is NOT a NO-GO.

**Verdict rule: GO ⇔ Q ∧ (some rung passes M under F) ∧ V1-V4.** V5 is reported
additionally when run. NO-GO handling per F3.

**Budget (pre-declared):** aero-dev only, serial, no cloud spend; CFD2 ceiling
`--timeout 14400` (4 h); CFD3 ceiling `--timeout 43200` (12 h).

**Contingencies (pre-registered):**

- If `exprFixedValue` is unavailable in the v2412 SIF, the parabolic inlet uses the
  discretized `timeVaryingMappedFixedValue` boundaryData written by the case writer
  (`inlet_bc="mapped"`) — an implementation mechanism, not a gate change. The
  preflight smoke decides before any campaign solve.
- If the upstream extraction cannot produce a closed surface within the R bounds, the
  ADR-033 §7 fallback acquisition applies, with its weaker-externality disclosure.

### Consequences

- **Positive:** the verdict is decided by gates that existed before the first solve;
  the ladder is auditable end-to-end; a NO-GO is a deliverable, not a failure to
  deliver.
- **Negative (honest):** V3/V5 tolerances are set from engineering judgment (quasi-2D
  snappy at h = 0.005 vs the benchmark's mesh-converged 2D values), not from a
  platform-owned convergence study — a formal GCI on snapped snappy grids is out of
  scope (no fixed mapping, ADR-028's premise fails); M2/M3 are stricter than anything
  the platform's own legacy C-grid satisfies, which is intentional but means the two
  mesh families are held to different documented bars. The `aero vv run` path runs
  these cases single-shot (no ladder) — the ladder lives in the campaign driver;
  promoting it into the V&V runner is ledgered follow-up.
- **Neutral / followup:** the M-gate module retires the Stage-16 script closures for
  future campaigns (the scripts themselves stay as historical records); a 3D
  (non-slab) external-geometry mode is future work.

## Pros and cons of considered options

(Option 1 pros/cons are the Consequences above; options 2 and 3 are rejected on the
grounds stated in Considered options — both reintroduce a movable bar.)

## Links

- Stage prompt: `docs/handoff-bundle/STAGE-18-arbitrary-geometry-ingestion.md`
- Related ADR: ADR-033 (ingestion contract); ADR-024 (threshold calibration
  precedent); ADR-028/030 (legacy C-grid checkMesh history); ADR-032 (the
  pre-registration pattern this mirrors)
- Related handoff: `docs/handoffs/STAGE-17-surrogate-accelerated-optimization-DONE-2026-07-24.md`
- External: Turek & Hron (2006), DOI 10.1007/3-540-34596-5_15
