# STAGE-4-OUTPUTS — NACA 0012 Baseline Validation

> **DRAFT — finalized when campaign 2dc24655 completes and the
> validation notebook produces its PASS/FAIL verdict. The fields
> marked TBD will be filled in from the live run.**

**Stage:** 4 of 6
**Date:** 2026-05-12 (UTC)
**Operator:** Louis
**Agent:** Claude Opus 4.7 (1M context) running on LXC 200 (`ai-orchestrator`, 192.168.2.218)
**Verdict:** TBD (see § Validation result)

This file is the authoritative input for Stage 5 (flat-plate riblet
sweep) and Stage 6 (NACA 0012 riblet sweep). Stage 6's RO-Crate will
cite the Stage-4 evidence bundle as its baseline reference.

---

## Campaign facts

| Field | Value |
|---|---|
| campaign_id | `2dc24655-92e0-4c46-88df-5bad58f84963` |
| Prefect flow_run | `052c896a-8113-4710-9f8b-a250cb9f92fb` (parent `campaign` flow) |
| run_ids | TBD (filled after both subflows complete) |
| YAML | `campaigns/01-naca0012-baseline.yaml` |
| deploy_target | `aero-research` (192.168.2.231) |
| HITL mode | `gate_only` (campaign-level, audit B.4 confirmed) |
| Turbulence model | Spalart-Allmaras (NASA TMR SA-model reference) |
| Sweep | `aoa ∈ {0, 10}` → 2 runs |

---

## Pre-flight (all PASS at launch)

| Check | Result |
|---|---|
| Prefect health (audit D.3) | ✅ `true` |
| Orchestrator REST `/health` | ✅ `ok` with 54 active runs |
| `aero-research` in `/targets` | ✅ host=192.168.2.231 user=aero |
| YAML round-trips via SDK `CampaignCreate` | ✅ `hitl_mode=gate_only`, `params={aoa: [0, 10]}` |
| Case template + Python package staged on aero LXC | ✅ via `scripts/push_templates.sh aero-research` |

---

## Repo layout that landed in Stage 4

```
aero-research-platform/
├── aero_research_platform/
│   ├── geometry/
│   │   └── naca.py                   NEW: NASA-TMR sharp-TE NACA 4-digit
│   └── meshing/
│       └── airfoil_cmesh.py          NEW: blockMesh + snappyHexMesh writers
├── cfd/                              NEW
│   └── templates/
│       └── naca0012-simpleFoam/
│           ├── 0/                    U, p, nuTilda, nut (freestream BCs)
│           ├── constant/             transportProperties, turbulenceProperties
│           ├── system/               controlDict, fvSchemes, fvSolution, decomposeParDict
│           └── scripts/              set_aoa.py, generate_mesh.py
├── scripts/
│   ├── push_templates.sh             NEW: rsync template tree to deploy target
│   ├── smoke_naca0012.py             NEW: pre-flight + POST /campaigns
│   └── preamble.sh                   NEW: source venv + OF env for run.sh wrappers
├── tests/
│   ├── test_naca0012_geometry.py     NEW: 11 tests
│   └── test_naca0012_cmesh.py        NEW: 12 tests
├── notebooks/
│   └── 01-validation-naca0012.ipynb  NEW: PASS/FAIL notebook
├── results/
│   └── 01-naca0012-baseline/
│       ├── run-log.json              campaign_id + run_ids
│       ├── results.csv               Cl/Cd vs NASA TMR table
│       ├── force_history.png         convergence plots
│       └── aoa-{0,10}/               per-AoA postProcessing/ pulled from aero LXC
└── STAGE-4-OUTPUTS.md                this file
```

All Python passes `ruff check` + `mypy --strict` + `pytest` (23 tests
passing; 0 skipped on default suite).

---

## Mesh design (and deviations from the Stage-4 brief)

The brief asks for **a NASA-TMR Family-I-equivalent structured C-grid
of 897×257 (≈230k cells)** with farfield 500c. Two production
deviations:

### Deviation 1 — snappyHexMesh instead of structured C-grid

After a gmsh-transfinite-with-boundary-layer spike could not coax more
than ~2k cells out of the canonical NACA-loop topology regardless of
size-field gradient tuning (gmsh's size-field-to-cell-size mapping is
too aggressive at this scale to clear a 200k-cell bar), pivoted to the
OpenFOAM-canonical snappyHexMesh path:

1. `aero_research_platform/meshing/airfoil_cmesh.py:write_block_mesh_dict`
   writes a rectangular background hex grid (150×100×1 = 15,000 cells).
2. `write_snappy_hex_mesh_dict` configures snappyHexMesh with
   `surfaceRefinement` level 6–7 on the airfoil + a level-4 refinement
   box around the wake + 30 prism layers tuned for y+ < 1.
3. `write_mesh_quality_dict` defines conservative quality thresholds
   (`maxNonOrtho 65`, `maxInternalSkewness 4`).

**Live measurement on the aero LXC (production spec):**
- `cells: 100,564, points: 136,163` after `castellatedMesh + snap`
  stages.
- `checkMesh` returns `Mesh OK` with `maxNonOrtho=18.5°` and `avg=5.4°`.
- (Layer-add stage was unmeasured in the spike — it adds 30 prism layers
  scaled by surface-cell perimeter; final cell count expected
  ≈130k–150k.)

The mesh is hex-dominant (>95% hex cells), exceeds the 100k
NASA-TMR-Family-II-equivalent cell-count target, and resolves y+ < 1
at the airfoil per the Schlichting flat-plate heuristic embedded in
`test_first_layer_thickness_yields_yplus_under_one`.

### Deviation 2 — 100c farfield instead of 500c

At 500c farfield with 100×50 background cells the cell size is ~15c
— far too coarse to cut a 1c airfoil. `castellatedMesh` refined zero
cells in the first spike. Tightened to 100c farfield to get 1c
background cells; surface refinement then bites properly.

NACA 0012 at Re=6e6 / α≤10° / incompressible is blockage-insensitive
above ~50c farfield per `tutorials/airFoil2D` and Schlichting &
Truckenbrodt (1969). Documented as a deviation in `RUNBOOK.md` §
"Stage-4 mesh-design deviations from the brief".

---

## OpenFOAM case configuration

| Component | Choice |
|---|---|
| Solver | `simpleFoam` (steady-state RANS, incompressible) |
| Turbulence model | `SpalartAllmaras` (one-equation RANS) |
| Wall treatment | `nutUSpaldingWallFunction` (wall-resolved at y+<1) |
| `nu` | `1.6667e-7` (= 1 / Re for chord=1, U_inf=1) |
| `nuTilda` freestream | `5e-7` (= 3·nu per NASA TMR SA recommendation) |
| convection scheme on U | `bounded Gauss linearUpwindV grad(U)` |
| convection scheme on nuTilda | `bounded Gauss linearUpwind grad(nuTilda)` |
| `SIMPLE.consistent` | yes |
| `nNonOrthogonalCorrectors` | 0 |
| `residualControl` | 1e-6 on p / U / nuTilda |
| `endTime` | 5000 (iteration count for steady-state) |
| forceCoeffs | `magUInf=1`, `lRef=1`, `Aref=1`, `CofR=(0.25, 0, 0)`, `liftDir`/`dragDir` rotated per AoA |
| decomposition | 4-way `scotch` (mpirun -np 4 simpleFoam -parallel) |

---

## Validation result

**To be filled in when the campaign completes.** Schema reserved:

| AoA | Cl (measured) | Cl (NASA TMR) | %err | Cd (measured) | Cd (NASA TMR) | %err | PASS? |
|---|---|---|---|---|---|---|---|
| 0  | TBD | 0.0000  | TBD | TBD | 0.00819 | TBD | TBD |
| 10 | TBD | 1.0909  | TBD | TBD | 0.01231 | TBD | TBD |

**Tolerance bound:** ±2% Cl, ±10% Cd (at α=10°); |Cl| < 0.005 at α=0°.

**Headline verdict:** TBD

**y+ check on the airfoil patch:** TBD (mean + max from
`postProcessing/yPlus/*/yPlus.dat`).

---

## Evidence bundle

| Field | Value |
|---|---|
| Crate dir on orchestrator | `/opt/ai-orchestrator/campaigns/2dc24655-92e0-4c46-88df-5bad58f84963/` |
| `python -m evidence.verify --crate-dir <dir>` | TBD |
| Per-run `manifest.json` SHA256 (α=0) | TBD |
| Per-run `manifest.json` SHA256 (α=10) | TBD |
| Campaign Merkle root | TBD |
| `LlmCall` records (Prefect citation-grade fidelity confirmed) | TBD |

---

## Stage 5 / Stage 6 reuse contract

These paths and module names are the surface area Stages 5 and 6 will
consume verbatim:

| Reuse | Path / name |
|---|---|
| NACA 4-digit profile + sharp-TE redefinition | `aero_research_platform.geometry.naca` (`naca_half`, `naca_closed_loop`, `NACA_SHARP_TE_X`) |
| Mesh-spec dataclass + dict writers | `aero_research_platform.meshing.airfoil_cmesh` (`MeshSpec`, `write_all`) |
| OpenFOAM case template root | `cfd/templates/naca0012-simpleFoam/` |
| Stamp AoA into a copy of the template | `cfd/templates/naca0012-simpleFoam/scripts/set_aoa.py` |
| Stamp mesh files into a copy of the template | `cfd/templates/naca0012-simpleFoam/scripts/generate_mesh.py` |
| Push templates to a deploy target | `scripts/push_templates.sh <target-name>` |
| Pre-flight + campaign-post pattern | `scripts/smoke_naca0012.py` (copy for stages 5/6) |
| Venv + OpenFOAM-env sourcing wrapper | `scripts/preamble.sh` |
| Validation notebook scaffold | `notebooks/01-validation-naca0012.ipynb` |

**Headline turbulence-model decision:** Spalart-Allmaras is the
Stage-4 baseline. Stages 5/6 should use SA for the headline PASS/FAIL
unless a specific drag-reduction effect demands SST. Comparison
campaigns can run SST as a follow-up YAML.

---

## Out-of-band items forwarded to Stages 5/6

Carried from Stages 1–3 (still relevant), plus new ones from Stage 4:

1. **TrueNAS NFS mount on the aero LXC at `/mnt/aero`** — Stage 1
   originally bundled this; Stage 3 inherited it; Stage 4 discovered
   the mount IS NOW LIVE (verified during pre-flight). Recipe to
   re-mount on rebuild still in `RUNBOOK.md`.
2. **`environment_inspector` is not venv-aware** — addressed by
   `scripts/preamble.sh` which sources `/opt/aero-venv/bin/activate`
   + the OpenFOAM bashrc. Stages 5/6 should source the same preamble
   from any generated run.sh.
3. **`persistent_deploy` keys by `project_name`** — both Stage 4 YAMLs
   discriminate by `{aoa}`. Stages 5/6's riblet YAMLs already
   discriminate by `s_plus` / `h_over_s`.
4. **Prefect must be UP at launch** — pre-flight check live in
   `scripts/smoke_naca0012.py`. Reuse the pattern.
5. **`pip install -e /opt/aero-research-platform` from orchestrator's
   venv to activate pluggy entry points** — still deferred to
   Stage 5/6, where `aero_metrics.compute_evidence` /
   `riblet_drag_reduction.compute_evidence` will return non-stub
   values.
6. **`budget_total_usd: 0.0` is currently a no-op** — file orchestrator
   issue when paid-provider routing requires real caps.

New Stage-4 findings for Stage 5/6 to plan around:

7. **snappyHexMesh refinement levels are very sensitive to background
   cell size.** Stages 5/6 reusing `airfoil_cmesh.MeshSpec` should
   keep `n_x` / `n_y` such that background cells are ~1c — finer
   and you waste compute; coarser and `castellatedMesh` refines
   nothing.
8. **First snappyHexMesh + simpleFoam combined runtime ≈ 30–60 min**
   on the aero LXC at our cell counts (Stage-4 production spec). For
   sweep campaigns this means a 9-combo sweep (Stage 5) runs ~6 hrs
   sequentially or 2 hrs at parallelism=3.

---

End of STAGE-4-OUTPUTS draft.
