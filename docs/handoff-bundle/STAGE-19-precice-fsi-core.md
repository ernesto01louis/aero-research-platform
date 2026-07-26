# STAGE 19 — preCICE FSI Core (Turek-Hron FSI3)

> Stage 18 gave the platform arbitrary-geometry ingestion + robust meshing and proved the
> Turek-Hron cylinder+flag geometry end-to-end through rigid-flag CFD (CFD2 validated against
> the published benchmark). Stage 19 makes the flag MOVE: populate `aero/adapters/precice/` +
> the `aero[precice]` extra, verify partitioned fluid-structure coupling on the supported
> preCICE Turek-Hron FSI3 tutorial, and gate on the published displacement bands. This is the
> FSI machinery the flexible-flapping flagship (Stage 20) stands on, per ADR-016.

## BEFORE YOU START — READ

1. `CLAUDE.md`; `.aero-stage` (→ `19`); `docs/handoffs/STAGE-18-*-DONE-*.md` (esp. the
   quasi-2D snappy approach, the exprFixedValue inlet finding, and the acquisition record).
2. ADR-016 (FSI structural-solver strategy — the split decision this stage executes; it
   moves to `accepted` when the FSI3 gate passes). ADR-033/034 (the ingested Turek-Hron
   geometry + the pre-registered gate pattern to mirror for the FSI gates).
3. `data/references/fsi/turek_hron_fsi3/reference.md` — the Stage-18 geometry
   provenance. **Branch caveat:** Stage 18 pinned `precice/tutorials` @ `98a78fe2` on the
   `master` branch, but the repo's default/maintained branch is **`develop`** (head
   `cd33e2db` at 2026-07-26). The `blockMeshDict` is byte-identical on both, so the
   Stage-18 geometry is fine — but the FSI tutorial's `reference-results/` tarballs
   (`fluid-openfoam_solid-dealii.tar.gz`, `fluid-nutils_solid-nutils.tar.gz`) and the
   `solid-nutils` / `fluid-nutils` participants exist **only on `develop`**. Pin a
   `develop` commit for this stage and record it; acquire the FSI3 displacement
   reference DVC-tracked under `data/references/fsi/turek_hron_fsi3/`.
4. `.claude/rules/flapping-validation-ladder.md` (FSI tier); `docs/vv/output-validity-bar.md`.

## Why this stage

Every flexible-flapping claim (Stage 20) rests on trustworthy partitioned FSI. The supported
preCICE tutorial (OpenFOAM fluid + deal.II or Nutils solid) is the reference-validated path
to demonstrate coupling correctness; CalculiX is the application solid solver built here so
Stage 20 does not block on container work (ADR-016: coupling-correctness and
application-fidelity are deliberately distinct claims).

## Deliverables

1. **`aero/adapters/precice/`** populated + `aero[precice]` extra (pyprecice, pinned; the
   preCICE 3.x OpenFOAM-adapter + solid-solver version pins confirmed in an ADR — Hard
   Rule 8). SIF/container strategy for the coupled pair documented (two SIFs + one
   precice-config, or one combined SIF — ADR the choice). **Solid-solver note:**
   `solid-nutils` (pure-Python, pip-installable) is a far lighter first participant than
   `solid-dealii` (C++ build) and is on `develop` with its own reference-results tarball;
   ADR-016 named deal.II/Nutils interchangeably, so either satisfies the coupling-
   verification claim. Consider Nutils first to de-risk, deal.II only if needed.
2. **Turek-Hron FSI3 coupling verification** on the pinned upstream tutorial: run the
   supported OpenFOAM + deal.II (or Nutils) FSI3 case; gate on the flag-tip displacement
   amplitude + frequency within the published Turek & Hron (2006) bands
   (pre-registered tolerances, ADR-032/034 pattern, committed BEFORE the campaign run);
   `aero/vv/fsi/` case + registry + CLI wiring (the Stage-18
   `aero/vv/external_geometry/` pattern).
3. **CalculiX SIF built** (+ smoke: the preCICE perpendicular-flap or FSI3 solid replaced
   by CalculiX as a non-gated diagnostic) — the Stage-20 application path.
4. **FSI3 reference data** DVC-tracked under `data/references/fsi/turek_hron_fsi3/`
   (displacement watchpoints; extend the existing reference.md — same acquisition
   discipline as Stage 18).
5. ADR-016 → `accepted` on gate pass; new ADR(s) for pins/containers; GO/NO-GO; handoff;
   STAGE-20 prompt (flexible flapping wing — Heathcote-Gursul); tag `v0.0.19`.

## GO / NO-GO

**GO** = the supported FSI3 tutorial runs through the platform's plumbing with four-fold
provenance, and the flag-tip displacement amplitude + frequency fall within the
pre-registered bands of the published values. **NO-GO** = coupling runs but misses the
bands, or cannot run serial-only: document honestly, ship the adapter + harness + the
loud gate, and record what infrastructure is missing. Never relax a band to pass.

## Infra + conventions + inherited notes

- Serial-only aero-dev (MPI blocked) — FSI3 is long (physical 10+ s at small dt, two
  coupled solvers): budget wall-clock honestly, pre-declare ceilings, consider the
  coarser upstream mesh levels first (`blockMeshDict` vs `_refined`); a NO-GO on budget
  grounds with the machinery shipped is acceptable per ADR-016's staged claims.
- The Stage-18 quasi-2D snappy mesh is NOT the FSI3 fluid mesh — the tutorial's own
  body-fitted blockMesh (deforming, preCICE-coupled) is the supported path; the ingested
  STL remains the Stage-18 artifact (and the Stage-20+ geometry on-ramp).
- Ledger items carried (do not silently drop): fair-test surrogate speed-up (reduced
  prior / higher-DV — Stage 18's ingestion now unblocks higher-DV shape spaces); FFD/SDF
  differentiable parametrization; the 393² certification rung (Stage 16); promoting the
  mesh fallback ladder into the V&V runner (`aero vv run` currently single-shot);
  balanced flywheel-growth corpus curation; content-addressed dataset hash.
- Conventional commits `<type>(stage-19)`; branch + PR; cancel vv-smoke if it starves
  the required checks; pre-commit needs `.venv/bin` on PATH.

## POST-STAGE HANDOFF (mandatory)

`docs/handoffs/STAGE-19-*-DONE-*.md` (frontmatter + 10 sections). Emphasize: the coupling
verification result vs the published bands, the version-pin ADR, the CalculiX SIF status,
what Stage 20 needs. Confirm the STAGE-20 prompt exists (flexible flapping wing FSI —
Heathcote-Gursul). Tag `v0.0.19`.
