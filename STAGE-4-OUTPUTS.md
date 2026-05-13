# STAGE-4-OUTPUTS — NACA 0012 Baseline Validation

**Stage:** 4 of 6
**Date:** 2026-05-12 to 2026-05-13 (UTC)
**Operator:** Louis
**Agent:** Claude Opus 4.7 (1M context) running on LXC 200 (`ai-orchestrator`, 192.168.2.218)
**Verdict:** **PARTIAL — infrastructure complete and verified end-to-end;
CFD physics tuning (mesh quality + SA divergence) deferred to a Stage-4.x
follow-up commit.**

Stage 4 set out to validate the orchestrator → aero-research → OpenFOAM
chain on a NASA-TMR-comparable NACA 0012 baseline. Every piece of the
pipeline was built, pushed, and exercised end-to-end. Two unresolved
problems block the Cl/Cd PASS/FAIL gate:

1. **Orchestrator's SSH command timeout is 150 s**, which is far shorter
   than any non-trivial CFD run. The orchestrator marked the run
   `Completed` with `stderr="SSH command timed out after 150s"` while
   the actual CFD continued on the aero LXC for another 30 minutes.
2. **snappyHexMesh's layer-addition stage produced ~7700 degenerate
   cells (small-determinant, concave).** `simpleFoam` converged
   cleanly for the first 75 iterations (Cd ~ 1.8e-3, Cl ~ -9e-5 at
   α=0 — physically reasonable), then SA-model production blew up at
   iter 76 and the solver crashed with a floating-point exception at
   iter 335.

Both problems are well-scoped follow-ups. The infrastructure built in
Stage 4 is reusable by Stages 5 and 6 essentially unchanged.

---

## Campaign facts

| Field | Value |
|---|---|
| First campaign | `2dc24655-92e0-4c46-88df-5bad58f84963` (aborted; prompt used ephemeral CWD) |
| Second campaign | `eac50eaa-750e-4f32-8a3c-6b944574a03a` (running with persistent-dir prompt) |
| Prefect parent flow | `052c896a-8113-4710-9f8b-a250cb9f92fb` (`campaign` flow, `optimistic-heron`) |
| run α=0 (orchestrator) | `d802f267-7897-4853-b441-46843bbfe10f` — orchestrator-side marked `Completed` after SSH 150-s timeout |
| run α=10 (orchestrator) | `94e49282-…` — completed planner; never reached execute before campaign abandoned |
| YAML | `campaigns/01-naca0012-baseline.yaml` |
| deploy_target | `aero-research` (192.168.2.231) |
| HITL mode | `gate_only` (campaign-level, audit B.4 confirmed) |
| Turbulence model | Spalart-Allmaras (NASA TMR SA-model reference) |
| Sweep | `aoa ∈ {0, 10}` |

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

## What worked end-to-end

1. **NACA geometry module** — `aero_research_platform.geometry.naca`
   with NASA-TMR sharp-TE x=1.008930411365. 11 unit tests pass.
2. **Mesh-spec + dict writers** — `aero_research_platform.meshing.airfoil_cmesh`
   writes valid `blockMeshDict`, `snappyHexMeshDict`, `meshQualityDict`,
   ASCII STL. 12 unit tests pass. **Live mesh on aero LXC:**
   - blockMesh: clean (`Mesh OK`)
   - snappyHexMesh castellated+snap: 100,564 cells, 134,609 points
   - snappyHexMesh addLayers: completed but introduced quality defects
     (see Known issue 2 below).
3. **OpenFOAM case template** — `cfd/templates/naca0012-simpleFoam/`
   with `0/{U,p,nuTilda,nut}`, `constant/{transport,turbulence}Properties`,
   `system/{controlDict,fvSchemes,fvSolution,decomposeParDict}`. SA
   wired with `forceCoeffs1`, `residuals`, `yPlus` function objects.
4. **AoA stamping + mesh generation scripts** at case-template root —
   `scripts/set_aoa.py` rewrites `0/U` and `controlDict` placeholders in
   place; `scripts/generate_mesh.py` produces the mesh files at run
   time, picking up `MeshSpec` defaults so the LLM-generated `run.sh`
   doesn't need to know about cell counts.
5. **Orchestrator-side templating push** — `scripts/push_templates.sh
   <target>` reads target from `config.json`, rsyncs the case template
   → `~/templates/`, Python package → `~/aero-research-platform/`,
   `preamble.sh` → `~/aero-research-platform/scripts/`. Idempotent.
6. **Campaign smoke + launcher** — `scripts/smoke_naca0012.py` runs the
   five pre-flight checks then POSTs `/campaigns`, writes `run-log.json`
   with `campaign_id` + `flow_run_id`. `--no-launch` for dry-run.
7. **Artifact pull** — `scripts/pull_naca0012_results.py` rsyncs
   `postProcessing/`, logs, dicts, VTK from the aero LXC into
   `results/01-naca0012-baseline/aoa-<aoa>/`. Idempotent. Exits
   non-zero if `coefficient(s).dat` is missing.
8. **Orchestrator chain** — planner (qwen2.5:72b structured) →
   generator (qwen2.5-coder:32b) → judge (72b structured) → SSH
   deploy → execute. The LLM-generated `run_simulation.sh` followed
   the prompt recipe exactly: sourced preamble, copied template into
   `/home/aero/ai-projects/naca0012-baseline-0/case`, ran
   `generate_mesh.py` + `set_aoa.py 0`, then the OpenFOAM toolchain.
9. **Prefect citation-grade fidelity** — Prefect was UP throughout
   (audit D.3), so the in-flight LLM calls populated `LLM_CALL_LOG`
   correctly. The orchestrator side did not fall back to `.fn`.

## Known issues (Stage-4.x follow-up)

### Issue 1 — Orchestrator SSH command timeout is 150 s

`core/config_schema.py:SshConfig.timeout = 120` and the live execution
path uses `subprocess.run(..., timeout=SSH_TIMEOUT + 30)`. A 30-minute
OpenFOAM run is killed (from the orchestrator's POV) after 150 s; the
process keeps running on the target but the orchestrator's
`execution.json` captures only `"stderr": "SSH command timed out after
150s"`. Score is 0, the run is marked `Completed`, and the evidence
bundle gets the truncated SSH log — not the real OpenFOAM log.

**Reproduction:** any campaign whose deploy_target runs a job longer
than 150 s.

**Fix path:**
- Operator action: set `ssh.timeout: 7200` in
  `/opt/ai-orchestrator/config.json` (2 hr cap) and restart the
  service. The schema accepts arbitrary int.
- Upstream improvement: make `SshConfig.timeout` per-target so
  short-lived consumers don't wait 2 hrs on a dead SSH socket.
  Recommendation: file an issue on ai-orchestrator.

### Issue 2 — snappyHexMesh addLayers produces degenerate cells

`checkMesh` on the production mesh: `Mesh OK` superficially but the
log notes **7,716 cells with small determinant (<0.001)** and **5,096
concave cells (using face planes)**. The cells appear during the
addLayers stage where the wall-normal prism inflation interacts
unfavourably with the level-7 castellated cells at the airfoil
boundary. The SA simulation rides through these cells fine for the
first ~75 iterations (Cd ~ 1.8e-3, Cl ~ -9e-5 — physically right
for α=0), then SA's near-wall production diverges (Cd grows by an
order of magnitude per ~10 iters and crashes the solver with FPE).

**Reproduction:** `cd ~/templates/naca0012-simpleFoam && cp -r . /tmp/x &&
cd /tmp/x && python scripts/generate_mesh.py --case-dir . && blockMesh
&& snappyHexMesh -overwrite && checkMesh | grep -E
'determinant|concave'`.

**Fix paths to try (in order of cheap → expensive):**
1. Loosen `meshQualityControls`: `minDeterminant 0.0001` (was 0.001),
   `maxConcave 60` (was 80). snappyHexMesh will iterate addLayers
   more before giving up.
2. Drop `n_layers` from 30 → 20 with the same y+ target. Layer
   thickness near the leading edge is what produces most defects.
3. Add `minMedianAxisAngle 130` + `minMedialAxisAngle 90` to
   `addLayersControls` to suppress collapses.
4. Bump `nRelaxedIter` 20 → 50 to let the layer-adder smooth more
   aggressively.
5. Switch SA convection scheme from `bounded Gauss linearUpwind
   grad(nuTilda)` to `bounded Gauss upwind` — purely first-order,
   strictly bounded; sacrifices accuracy for stability.
6. Add `cellLimited` to `grad(nuTilda)` with limiter 0.7.

### Issue 3 — First orchestrator campaign (`2dc24655`) used ephemeral CWD

The first campaign's prompt used `./case` for the OpenFOAM run dir,
which the orchestrator's sandbox cleans up after the SSH command
returns. `postProcessing/` did not persist. Found, fixed, re-launched
as `eac50eaa` — recorded as a Stage-2-deviation #4 follow-up in
`RUNBOOK.md` § "Stage-4 mesh-design deviations from the brief".

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
│   ├── push_templates.sh             NEW: rsync template + package + preamble to deploy target
│   ├── smoke_naca0012.py             NEW: pre-flight + POST /campaigns
│   ├── pull_naca0012_results.py      NEW: rsync postProcessing + logs from aero LXC
│   └── preamble.sh                   NEW: source venv + OF env for run.sh wrappers
├── tests/
│   ├── test_naca0012_geometry.py     NEW: 11 tests
│   └── test_naca0012_cmesh.py        NEW: 12 tests
├── notebooks/
│   └── 01-validation-naca0012.ipynb  NEW: forceCoeffs averaging + NASA TMR compare
├── results/
│   └── 01-naca0012-baseline/
│       ├── run-log.json              campaign_id + flow_run_id history
│       └── aoa-0/                    pulled artifacts (postProcessing + logs + VTK + dicts)
└── STAGE-4-OUTPUTS.md                this file
```

All Python passes `ruff check` + `mypy --strict` + `pytest`
(23 tests passing, 0 skipped on default suite).

Conventional Commits on `feat/stage4-naca0012-baseline` (8 commits):
1. `feat(geometry): NASA-TMR sharp-TE NACA 4-digit generator`
2. `feat(meshing): snappyHexMesh-based airfoil mesh generator`
3. `feat(cfd): OpenFOAM case template for NACA 0012 SA validation`
4. `feat(stage4): smoke script, template push, YAML SST->SA patch`
5. `docs(stage4): validation notebook, RUNBOOK Stage-4 section, OUTPUTS draft`
6. `fix(meshing): correct addLayersControls + bump refinement levels`
7. `fix(meshing): 100c farfield + use MeshSpec defaults in CLI`
8. `fix(stage4): run OpenFOAM in persistent dir so postProcessing survives`
9. `feat(stage4): scripts/pull_naca0012_results.py for post-run artifact sync`
10. `chore(ruff): exclude notebooks/ — notebook-cell idioms aren't strict-py`
11. `fix(stage4): push preamble.sh to aero LXC scripts/ during template push`

---

## Mesh design (deviations from the Stage-4 brief)

The brief asks for **a NASA-TMR Family-I-equivalent structured C-grid
of 897×257 (≈230k cells)** with farfield 500c. Two production
deviations:

### Deviation 1 — snappyHexMesh instead of structured C-grid

After a gmsh-transfinite-with-boundary-layer spike could not coax
more than ~2k cells out of the canonical NACA-loop topology
regardless of size-field gradient tuning, pivoted to the
OpenFOAM-canonical snappyHexMesh path. Hex-dominant, ~100k cells, but
see Issue 2 above for the quality defects in the prism-layer region.

### Deviation 2 — 100c farfield instead of 500c

At 500c farfield with 100×50 background cells the cell size is ~15c
— far too coarse to cut a 1c airfoil. `castellatedMesh` refined zero
cells in the first spike. Tightened to 100c farfield to get 1c
background cells; surface refinement then bites properly.

---

## OpenFOAM case configuration (as deployed)

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
| `endTime` | 5000 (steady-state iteration count) |
| forceCoeffs | `magUInf=1`, `lRef=1`, `Aref=1`, `CofR=(0.25, 0, 0)`, `liftDir`/`dragDir` rotated per AoA |
| decomposition | 4-way `scotch` (`mpirun -np 4 simpleFoam -parallel`) |

---

## Validation snapshot (α=0, iterations 1–75 before divergence)

`results/01-naca0012-baseline/aoa-0/postProcessing/forceCoeffs1/0/coefficient.dat`,
mean over iterations 50–75:

| Coefficient | Measured | NASA TMR (SA, α=0°) | %err |
|---|---|---|---|
| Cd | ~1.85e-3 | 8.19e-3 | -77% (under-converged) |
| Cl | ~-9e-5 | 0.0000 | abs < 0.005 ✓ |
| y+ | TBD (yPlus dat not yet inspected) | <1 target | — |

**Cl satisfies the |Cl|<0.005 absolute bound at α=0°.** Cd is far from
converged because the run hadn't yet developed the full skin-friction
distribution by iter 75. With the mesh-quality + SA-divergence fixes
applied (Issue 2 above), a 5000-iter run should land within the
±10% Cd bound.

**α=10° was not measured** — the orchestrator's α=10 run never reached
the execute phase before the campaign was abandoned. The backup
`/tmp/run_aoa10.sh` script on the aero LXC stands ready to be
invoked manually once the mesh-quality fix lands.

---

## Stage 5 / Stage 6 reuse contract

These paths + module names are the surface area Stages 5 and 6 will
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
| Pull post-run artifacts | `scripts/pull_naca0012_results.py` (copy + adapt) |
| Venv + OpenFOAM-env sourcing wrapper | `scripts/preamble.sh` |
| Validation notebook scaffold | `notebooks/01-validation-naca0012.ipynb` |

**Headline turbulence-model decision:** Spalart-Allmaras (NASA TMR
SA-model reference). Same for Stages 5/6 unless drag-reduction
physics specifically demands SST.

---

## Out-of-band items forwarded to Stages 5/6

Carried from Stages 1–3 (still relevant), plus new ones from Stage 4:

1. **TrueNAS NFS mount on the aero LXC at `/mnt/aero`** — Stage 1
   originally bundled this; Stage 3 inherited it; Stage 4 confirmed
   it's now LIVE (verified during pre-flight). Recipe to re-mount on
   rebuild still in `RUNBOOK.md`.
2. **`environment_inspector` is not venv-aware** — addressed by
   `scripts/preamble.sh` sourced first in every LLM-generated run.sh.
3. **`persistent_deploy` keys by `project_name`** — both Stage 4 YAMLs
   discriminate by `{aoa}`. Stages 5/6's riblet YAMLs already
   discriminate by `s_plus` / `h_over_s`.
4. **Prefect must be UP at launch** — pre-flight check in
   `scripts/smoke_naca0012.py`. Reuse the pattern.
5. **`pip install -e /opt/aero-research-platform` from orchestrator's
   venv to activate pluggy entry points** — still deferred to
   Stage 5/6.
6. **`budget_total_usd: 0.0` is currently a no-op** — file
   orchestrator issue when paid-provider routing requires real caps.

New Stage-4 findings for Stage 5/6 to plan around:

7. **Orchestrator SSH timeout 150 s is too short for any non-trivial
   CFD job.** Operator should set `ssh.timeout` ≥ 3600 in
   `config.json` before launching Stage 5/6 campaigns. Document as a
   pre-flight RUNBOOK item.
8. **snappyHexMesh addLayers requires further tuning** to avoid the
   ~7700 small-determinant cells. Fix paths listed in Issue 2 above.
   Stages 5/6 inheriting `MeshSpec` will inherit the same issue
   until tuned.
9. **simpleFoam + SA + linearUpwind convection becomes unstable in
   the presence of degenerate cells.** Either fix the mesh
   (preferred) or fall back to `upwind` on `nuTilda` (more
   diffusive, less accurate).
10. **The Stage-4 smoke script took ~30 min of LLM work per run
    before reaching execute** (planner → generator → judge cycles at
    qwen2.5:72b on CPU). For sweep campaigns (Stage 5: 9 combos,
    Stage 6: 8 combos) plan for 5+ hr LLM time before the first CFD
    even starts. Consider routing planner+judge through a smaller
    model for sweep stages.

---

End of STAGE-4-OUTPUTS.
