# Stage map (10–20) + cross-stage guardrails — the optimizer mission

> The re-aimed build map after the optimizer-mission refocus (ADR-013). Supersedes the
> original Stage 10–16 roadmap (archived under `archive/original-roadmap/`). Read with
> the governing scope `00-MISSION-AND-SCOPE.md`. Stages 01–09 are complete/partial; their
> exit notes are in `docs/handoffs/`.

## How stages work now

- **One Claude Code session per stage.** The current stage is in `.aero-stage`.
- **Stage prompts are committed** at `docs/handoff-bundle/STAGE-NN-<slug>.md` from Stage 10
  on. **Each stage's post-stage handoff authors the next stage's prompt** before session
  Stop (handoff-discipline rule). Stages 01–09 prompts were operator-side only; the
  originals are archived.
- **Tag `v0.0.NN` per stage** after the handoff exists (Hard Rule 10). v0.1.0 ships after
  Stage 20.

## The two interwoven tracks

- **Forward-capability track** (the trustworthy ground truth): V&V debt → moving-mesh +
  unsteady post-proc → UQ core → transition → rigid flapping → FSI core → flexible flapping.
- **Optimizer track** (the mission): parametric CFD-in-the-loop optimization → surrogate
  acceleration → arbitrary-geometry ingestion → (post-v0.1.0) adjoint/generative.

The optimizer is demonstrated on the **rigid** flapping problem first (Stage 15) so the
first thesis result does not wait on FSI — the hardest, off-supported capability. The
Stage-15 optimization loop generates the validated own-CFD corpus the Stage-16 surrogate
factory trains on (the data flywheel; NO-SURROGATE-ON-FOREIGN-DATA satisfied by
construction).

## Map

| # | Name | Goal | Validation gate | Budget tier |
|---|---|---|---|---|
| 10 | **V&V Debt Retirement + Output-Validity Bar (HARD GO/NO-GO)** | Fix NACA 0012 Cd / flat-plate Cf / 2D bump; **add forward-regime canonical cases** (Blasius flat plate, low-Re cylinder Strouhal, transitional airfoil); ship `docs/vv/output-validity-bar.md` + `aero/vv/reportable.py` skeleton; bump cost-cap default $50→$150 (ADR-014). | Canonical set (turbulent table-stakes + low-Re regime) reaches stated tolerance **or STOP and rethink** — no silent "document and proceed". Tolerances never relaxed. | baseline |
| 11 | **Moving-Mesh + Unsteady Post-Processing Toolkit** | OpenFOAM `dynamicMotionSolverFvMesh`/AMI/`overPimpleDyMFoam` (v2412); `aero/postprocess/` phase-averaging, Strouhal, thrust/power/propulsive efficiency, viscous/pressure force decomposition; periodic-steady-state (cycle-convergence) detection. | Oscillating-cylinder + plunging-airfoil reproduce published Strouhal; force decomposition closes to total within tolerance. | baseline |
| 12 | **Verification & UQ Core** | `u95_numerical` (GCI) + `u95_statistical` (batch-means/N_eff + cycle-convergence) + `u95_input`; full `ReportableResult`; Invariant 10 CI `small-signal-gate`; Invariant 11 `data_origin`. Merge the ADR-015 constitution PR (post-72 h). | U95 (incl. statistical term) demonstrated end-to-end on an unsteady case; both new CI gates green + required. | baseline |
| 13 | **Transition + Unsteady-Airfoil Validation** | `kOmegaSSTLM` (γ-Reθ); laminar/transitional low-Re path; pitching/plunging airfoil vs McCroskey / Heathcote-Gursul (rigid). | Transition onset + pitch/plunge force loops within bands. | baseline |
| 14 | **Rigid Flapping-Wing Validation** | Prescribed-kinematics flapping Re 10²–10⁴, LEV capture (laminar/incompressible); validate vs Dickinson 1999 / Wang-Birch-Dickinson 2004. | Force traces within bands; full `ReportableResult` (incl. statistical U95). The validated forward problem the optimizer runs on. | baseline |
| 15 | **CFD-in-the-Loop Parametric Optimization [THESIS CHECKPOINT]** | Kinematics/planform parametrization (FFD/morphing, ~5–10 vars); objective (e.g. propulsive efficiency at fixed thrust); **Bayesian optimization with direct CFD**; CFD-verified optimum, delta > k·U95 (matched-condition); selection-bias-aware; CFD-VERIFIED-OPTIMUM-ONLY (promote Hard Rule 14 to constitutional). | A **CFD-verified improvement delta exceeding its combined U95** on a parametric flapping case = first thesis-grade result. | sustained |
| 16 | **Grid-Converged Certification of the Airfoil Optimum** *(inserted after the Stage-15 audit retracted the "+47%" GO; the original Stage-16 slides to 17)* | Graded (fixed-mapping) mesh family (`aero/optimize/mesh_family.py`, ADR-028); hard-gated verdicts (`certification_gates`); steady path exhausted honestly; URANS / independent-U95 path (ADR-029). | A grid-converged matched-delta clearing 2·U95 (finest grid included, all solves converged, monotone/bounded order) surviving the 3-lens adversarial panel — OR an honest documented NO-GO. | baseline |
| 17 | **Surrogate-Accelerated Optimization (own-data factory)** | Train a geometry/kinematics-aware surrogate on the platform's OWN validated CFD (`Surrogate` ABC + cert; **no foreign data**); surrogate-in-the-loop optimization with **mandatory ground-truth-CFD verification of optima**; certificate gating. | Surrogate-accelerated optimum matches a direct-CFD optimum within tolerance, CFD-verified, valid certificate. | sustained/burst |
| 18 | **Arbitrary-Geometry Ingestion + Robust Meshing** | STL/CAD/3MF ingestion; watertightness/quality gating + repair; sandboxed meshing with fallback; FFD/SDF-space optimize → emit CAD via CadQuery/build123d. | Ingest an external geometry, mesh it robustly (quality-gated), run a CFD-verified evaluation, emit manufacturable CAD. | baseline/sustained |
| 19 | **preCICE FSI Core** | Populate `aero/adapters/precice/` + `aero[precice]`; **verify coupling on the supported Turek-Hron FSI3 tutorial (OpenFOAM + deal.II/Nutils)**; build the CalculiX SIF for the application (ADR-016). | Turek-Hron FSI3 displacement amplitude + frequency within published bands (`aero/vv/fsi/`). | sustained |
| 20 | **Flexible Flapping Wing (FSI) [flagship capstone forward capability]** | OpenFOAM + CalculiX flexible-wing FSI; validate vs Heathcote-Gursul flexible-foil data (documented solid-solver caveats). | Flexible-vs-rigid propulsive efficiency, full thesis-grade `ReportableResult`. | burst |
| 21 | **Flexible-Flapping Optimization + Portable Bundles + Hardening + v0.1.0** | Optimization over flexible-flapping (surrogate + FSI); RESULTS-MUST-TRAVEL self-describing bundle (+ RO-Crate/W3C-PROV; promote Hard Rule 16); license-scan CI; JOSS/Zenodo; release. | Bundle round-trips on a clean machine; all required CI green; v0.1.0 tagged. | burst |

> **Renumbering note (Stage-16 insertion, 2026-07-12; RATIFIED 2026-07-15):** the
> certification stage was inserted at 16 after the Stage-15 audit, sliding surrogate→17,
> geometry→18, FSI→19, flexible→20 and the v0.1.0 release stage→21. The operator ratified
> KEEPING the 21-stage plan (stages are session-sized work units; compressing well-scoped
> stages to preserve a round number serves nothing). "v0.1.0 after Stage 20" statements
> elsewhere mean "after the release stage (21)".

**Post-v0.1.0 (committed, named, further out):** adjoint shape/topology optimization
(DAFoam v5 + SU2 adjoint — SU2 already built) → generative / true-topology proposers
(performance-conditioned generative geometry + the discovery flywheel).

**Reference-data acquisition** lives in the owning stage, DVC-tracked under
`data/reference/<case>/` with a `reference.md`: McCroskey + Heathcote-Gursul → Stage 13;
Dickinson + Wang-Birch-Dickinson → Stage 14; Turek-Hron tabulated → Stage 18.

## Cross-stage guardrails (carry these into every session)

1. **Stage 10 is a hard go/no-go.** No optimization or flapping result is thesis-grade on a
   solver off the canonical cases. If the canonical set can't reach tolerance, STOP and
   rethink — do not proceed to build on an untrusted solver.
2. **Frozen, not deleted (ADR-013).** `aero/adapters/{su2,pyfr,nekrs,jax_fluids}/`,
   `aero/surrogates/{domino,baselines,_common}/`, `scripts/stage09_domino_train.py`, all
   SIFs, all loaders, the empty `transformer`/`figconvnet`/`moe`/`vv/{dpw,hlpw}` `.gitkeep`
   dirs — keep them; do not invest, do not delete.
3. **DrivAerML (~353 GiB) / `physicsnemo.sif` / `SHA256SUMS` are off-limits** without literal
   `approved`. Disk reclaim is a separate propose-first decision.
4. **No tolerance relaxation, ever.** A failing V&V case is investigated, never relaxed.
5. **Improvement-exceeds-uncertainty + CFD-verified-optimum** gate every reported result
   (Hard Rules 12, 14; `.claude/rules/optimization-integrity.md`).
6. **Surrogates train only on own validated CFD** (Hard Rule 13).
7. **Budget tiers (ADR-014):** baseline $150/mo; sustained $200–600 and burst $1–2k are
   per-campaign-approved and named in the stage prompt.
8. **Do NOT start over** — Stages 1–8 are the correct foundation.
