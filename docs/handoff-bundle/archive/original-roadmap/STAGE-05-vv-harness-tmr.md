# STAGE-05: V&V Harness Against NASA TMR

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"V&V benchmark set" and Pass 1 §"V&V and benchmarks":

- A V&V harness that runs canonical NASA Turbulence Modeling Resource cases
  through the OpenFOAM adapter and compares against reference data with tight
  tolerances.
- The harness becomes a required CI check: a red TMR dashboard means **no
  `production` runs allowed**.
- ASME V&V 20-compliant Grid Convergence Index (GCI) automated for the bumps and
  flat plate.
- Mesh independence study automation primitive that subsequent stages reuse.

## ROLE

You are turning the loose ±25% tolerance from Stage 03 into a peer-reviewable
V&V harness. From this stage on, every solver and every code change is
auto-tested against published reference data.

## GOAL

1. Add the canonical TMR cases under `aero/vv/tmr/`:
   - `flat_plate_te` (turbulent flat plate, Re_L = 5e6, Mach 0.2; reference data
     from TMR)
   - `bump_2d` (2D bump in channel; reference Cf and Cp distributions)
   - `naca0012_verification` (existing NACA 0012 with proper TMR-aligned BCs)
   Mirror the reference data files from `tmbwg.github.io/turbmodels/` (re-host with
   attribution; check license — TMR is US Govt work, public domain).
2. Author `aero/vv/_base.py`:
   - `BenchmarkCase` protocol (case name, reference data, comparison metrics,
     tolerance bands)
   - `BenchmarkResult` pydantic (status: pass | fail | regress; per-metric
     numeric error; provenance four-tuple)
   - `BenchmarkRunner` that takes a Solver + an Executor + a BenchmarkCase and
     returns a BenchmarkResult, mirroring it to MLflow with a `validation_tag` tag
3. Author `aero/vv/mesh_sweep.py`:
   - `MeshSweep` primitive: takes a base case and refinement ratios (default
     1.0, 1.3, 1.7), generates the meshes, runs each, computes GCI per ASME V&V
     20, returns a sweep report
   - GCI computation via the standard formula; output includes order-of-accuracy
     estimate and apparent-uncertainty bound
4. Wire `aero/vv/tmr/` cases through the OpenFOAM adapter with proper boundary
   conditions matching TMR specifications. Each case must include:
   - Mesh generation script (blockMesh + snappyHexMesh as needed)
   - `simpleFoam`-or-equivalent dict files generated from `CaseSpec`
   - Reference data file co-located, DVC-tracked
5. Author `tests/vv/test_tmr_flat_plate.py`, `test_tmr_bump_2d.py`,
   `test_tmr_naca0012.py`:
   - Marked `slow` and `vv`
   - Tolerances:
     - Skin friction Cf: 5% pointwise on the published locations (flat plate)
     - Pressure Cp: 3% pointwise (bump)
     - NACA 0012 Cd at Re=6e6, AoA=0: within 3% of NASA reference
   - Each test asserts BenchmarkResult.status == "pass"
6. Turn `vv-smoke.yml` from a placeholder into a real workflow:
   - Triggers on `push` to `main`, on PRs, and nightly via schedule
   - Runs on a self-hosted runner labeled `vv` (operator registers it on
     `aero-build` or a dedicated `aero-vv` LXC)
   - Runs the V&V suite, posts results to a status check
   - Posts the BenchmarkResult JSON as a PR comment for visibility
7. Add a CI job `vv-required` that, for PRs to `main`, requires the V&V suite
   pass. Add it to branch protection required status checks.
8. Author `aero/cli.py` additions: `aero vv list`, `aero vv run --case
   flat_plate_te`, `aero vv report` (queries MLflow for recent vv runs).
9. Add `aero/vv/dashboard.py` — a minimal HTML report generator that produces
   `docs/vv-dashboard.html` summarizing the latest V&V run status. Auto-published
   via mkdocs in Stage 16, but produced from Stage 05 onward.
10. Author ADR-005 documenting:
    - Why TMR (vs ERCOFTAC, vs DPW) is the Stage 05 choice
    - The tolerance choices and their rationale
    - The mesh sweep refinement ratios
    - The "red dashboard = no production" rule (also enforced in CLAUDE.md)
11. Update CLAUDE.md to add: "Before any `production`-tagged run, verify
    `aero vv report --latest` shows all green."
12. Tag `v0.0.5`.

## WHY

A research platform without continuous V&V is just a CFD pipeline that produces
unverified numbers. The TMR cases are the canonical, government-published,
public-domain reference. Tight tolerances against them prove the solver +
adapter + mesh + provenance stack is reliable.

The mesh sweep primitive is the bedrock for every "publish-quality" run in later
stages. ASME V&V 20-compliant GCI is what reviewers expect to see in a methods
section.

CI integration makes V&V continuous, not occasional. The 24-hour cooling-off rule
plus the `vv-required` status check means no Claude Code PR merges with broken
physics.

## HOW

- TMR reference data: download from the TMR site once, place under
  `data/references/tmr/`, DVC-track. Include the license statement (US Govt work,
  public domain) in each case's README.
- For Cf/Cp comparison: interpolate the CFD result to the reference data's
  x-locations using scipy splines; compare pointwise.
- The `vv` self-hosted runner: register it via the GitHub Actions runner install
  script, scope to the repo, label `vv`. The runner needs Apptainer and access
  to the MLflow/Postgres/MinIO services — i.e., it lives on `aero-build` or a
  similar LXC.
- For PR comments: GitHub Actions has `actions/github-script@v7`. Compose the
  BenchmarkResult into a markdown table; post as a comment.
- Branch protection update: `gh api -X PATCH
  repos/:owner/:repo/branches/main/protection --input <json-with-new-checks>`.
- The dashboard HTML: keep it simple — a single page with a table per case, color-
  coded pass/fail/regress, with the four-tuple of the latest run linked to MLflow.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-05-vv-harness-tmr.md` (this file)
- `docs/handoffs/STAGE-04-*-DONE-*.md`
- ADR-003, ADR-004
- Pass 2 SOTA doc §1 (Classical Turbulence Modeling) for context on tolerance
  choices

## GUARDRAILS — DO NOT

1. Do NOT relax a tolerance to make a test pass. If a case fails, file an issue,
   investigate the physics, and document the discrepancy. The tolerance is a
   contract.
2. Do NOT skip the mesh sweep on the bump case. GCI is what makes the result
   citable.
3. Do NOT add a TMR case without checking its license. TMR is US Govt; some
   linked datasets may have other licenses.
4. Do NOT make `vv-required` block CI for stages that don't yet have working
   adapters. Stage-gated: only required for PRs that touch `aero/adapters/` or
   `aero/vv/`.
5. Do NOT log V&V results without the four-tuple. Every BenchmarkResult carries
   the provenance.
6. Do NOT use ad-hoc Python globs to read OpenFOAM output. Use the typed Ofpp
   accessors from Stage 03.

## DELIVERABLES

- [ ] `aero vv list` shows the three TMR cases
- [ ] `aero vv run --case flat_plate_te --executor local-ssh` returns within
      tolerance
- [ ] `aero vv run --case bump_2d --mesh-sweep` produces a GCI report
- [ ] `tests/vv/test_tmr_*.py` all green on self-hosted runner
- [ ] `vv-smoke` workflow runs on PRs and posts a comment
- [ ] `vv-required` is a required status check on `main`
- [ ] `docs/vv-dashboard.html` generated and reflects current state
- [ ] ADR-005 committed
- [ ] CLAUDE.md updated with the "no red dashboard for production" rule
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.5`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- Final tolerance band numbers (Cd 3%, Cf 5%, Cp 3% — operator may want tighter
  or looser)
- Registering the self-hosted runner (it requires access tokens — discuss path)
- Adding `vv-required` as a required check (locks PRs against any V&V failure)
- The DVC-track for TMR reference data (size estimate first; if >1GB, discuss)

## POST-STAGE HANDOFF

Required emphases:

- **The actual Cd / Cf / Cp numbers** for the three reference runs, with the
  four-tuple from each.
- **GCI report** for the bump case: order of accuracy and apparent uncertainty.
- **Open items for Stage 06**: the SU2 adapter must pass the same TMR cases at
  the same tolerances. List the cases and the expected numbers.
- **Gotchas**: TMR data format quirks, BC nuances (`fixedValue` vs
  `freestream`), turbulence model parameter conventions.
- **CI runtime**: how long the V&V suite takes; if >30 min, propose splitting
  into nightly vs PR-gating subsets.
