---
stage: 03
stage_name: "Stage 03 — OpenFOAM Walking Skeleton"
status: complete
date_started: 2026-05-19
date_completed: 2026-05-19
session_duration_hours: 6.0
claude_code_version: "2.1.117 (Claude Code)"
model: claude-opus-4-7
git_sha_start: "83bd9c3bceb8a84229d0b250395622ed370e75dc"
git_sha_end: "d082c5d5c1afb4d991aef139c7198cc524d70c97"
stage_tag: v0.0.3
next_stage: 04
next_stage_name: "Stage 04 — Provenance Backbone"
---

# Stage 03 — OpenFOAM Walking Skeleton — DONE 2026-05-19

> Auto-loaded by the Stage 04 session as "BEFORE YOU START — READ".
> The walking skeleton runs CFD end-to-end: `aero run naca0012` reports
> Cd = 0.00875 (ref 0.0079, +11%, within the ±25% band).

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `containers/openfoam-esi.def` builds on aero-build | ✅ | FROM digest-pinned `opencfd/openfoam-default:2412` |
| 2 | SHA256 appended to `containers/SHA256SUMS` | ✅ | `c9d7f329…6e91c  openfoam-esi.sif` |
| 3 | `pip install -e .[openfoam,dev]` succeeds | ✅ | pyfoam 2023.7, ofpp 0.12, xarray 2026.4, mlflow |
| 4 | `pytest tests/unit/test_openfoam_adapter.py` green | ✅ | 12 tests; full unit suite 15/15 |
| 5 | `aero run naca0012 --executor local-ssh` → Cd ±25% <10 min | ✅ | Cd 0.00875; ~90 s wall-clock |
| 6 | MLflow run with provenance tags | ✅ | local `mlruns/`; 5 tags + 4 metrics |
| 7 | `tests/stage_03/test_naca0012_smoke.py` passes | ✅ | slow-marked; 86 s with `--run-slow` |
| 8 | `vv-smoke` GitHub Action runs the smoke test | ⚠️ | workflow wired for `[self-hosted, vv]`; **runner registration is an operator follow-up** — see §7 |
| 9 | ADR-003 committed with out-of-scope list | ✅ | `docs/adrs/ADR-003-openfoam-walking-skeleton.md` |
| 10 | README quick-start updated | ✅ | `aero run naca0012` example |
| 11 | Post-stage handoff written | ✅ | this file |
| 12 | Tag `v0.0.3` | ⚠️ | applied after the Stage 03 PR merges |

## 2. Decisions made

- **Four-block O-grid mesh.** A single wrapping-block C-grid is *degenerate*
  under blockMesh's topology check — a closed trailing edge gives two
  coincident TE corners. Rejected: single-block C-grid (degenerate); a
  conforming multi-block C-grid (more complex, `mergePatchPairs` for the wake
  cut). The O-grid is four positive-volume hexes, distinct vertices, no merge.
- **Analytic geometry, no STL.** `blockMesh` builds the airfoil from a
  coordinate curve; STL is a `snappyHexMesh` input. Rejected: shipping an STL
  the mesh would not use. `data/references/naca0012/naca0012.csv` holds the
  reproducible analytic coordinates instead.
- **`load()` parses `coefficient.dat` with `numpy.loadtxt`.** The
  `forceCoeffs` object writes a columnar text file. Rejected: Ofpp — it parses
  mesh/field files, not function-object output. Ofpp ships in the extra,
  unused until Stage 05.
- **`mlflow` in the `aero[openfoam]` extra.** The whole skeleton installs in
  one step. Rejected: a Stage-03 `provenance` extra — that namespace is
  Stage 04's; `mlflow_basic.py` is interim and Stage 04 supersedes it.
- **`run_long.sh` accepts `[user@]alias`.** Solver SIFs must run as LXC root.
  Rejected: a 30-line internal mirror of the long-job logic — `is_alias` now
  strips a `user@` prefix (~3 lines, backward-compatible).
- **SIFs run as the LXC root.** Non-root `apptainer exec` fails in the
  unprivileged LXC (Stage 02 §6); `LocalSSHExecutor` SSHes `root@aero-build`.
- **`endTime` 1500.** Cd is dead-steady from ≈ iteration 600; 1500 is an ample
  ceiling and halves the run time.

## 3. Deviations from the stage plan

- **`pyfoam` pinned `>=2023.7`, not `>=2024.5`.** The prompt's `>=2024.5` does
  not exist on PyPI — 2023.7 is the latest release. Recorded in ADR-003.
- **Geometry asset is a CSV, not an STL** (decision above; blockMesh needs no
  STL).
- **`mesh()` takes the `Executor` as a parameter** — the prompt's
  `mesh(case_dir)` omitted it; meshing executes inside the SIF remotely
  exactly as the solve does. `mesh(case_dir, executor)` is symmetric with
  `run`.
- **`vv-smoke` self-hosted runner not registered.** The operator selected
  "register now", but the auto-mode classifier (correctly) blocked the
  automated registration — an SSH key authorised for `root` plus a persistent
  CI runner is a high-severity infrastructure change needing explicit
  per-action authorisation. `vv-smoke.yml` is wired and correct; the runner is
  an operator follow-up (§7). The stage prompt's DELIVERABLES explicitly allow
  this deferral.
- **The case runs to `endTime`, not residual convergence** — the pressure
  residual plateaus ≈ 1.5e-3 (O-grid TE skewness). Cd is steady regardless;
  `iterations_to_convergence` therefore records `endTime` (1500).
- **`pyproject.toml` `version` stays `0.0.1`** — per Stage 02's precedent, git
  tags are the stage markers.

## 4. Environment / dependency / schema changes

- `pyproject.toml`: `aero[openfoam]` extra populated — `pyfoam>=2023.7`,
  `ofpp>=0.12`, `xarray>=2024.10`, `mlflow>=2.20`; new `[project.scripts]`
  entrypoint `aero = "aero.cli:app"`.
- `containers/openfoam-esi.sif` — built/signed on aero-build, published to
  `/mnt/aero/containers/`; SHA256 `c9d7f32974c66bfbc924d407193bbf488fa165b2b35b01ee21ed9fdf9606e91c`
  recorded in `containers/SHA256SUMS`.
- `aero/` core gained `orchestration/`, `adapters/openfoam/`, `provenance/`,
  `cli.py` (13 new modules); no base-dependency changes.
- Local `mlruns/` MLflow file store at the repo root (gitignored).
- OpenFOAM case directories accumulate under the NFS dataset
  (`/mnt/aero-nfs/runs/` host-side, `/mnt/aero/runs/` in-LXC). Retention is
  unmanaged — a housekeeping concern for a later stage.
- A repo `.venv` (gitignored) and a `uv.lock` (left untracked — lockfile
  tracking is an open question for Stage 04).
- No changes to any aero LXC or shared service.

## 5. CI/CD changes

- `.github/workflows/vv-smoke.yml` — replaced the Stage 01 placeholder with a
  real job on `[self-hosted, vv]` that runs the NACA 0012 smoke test.
- **Not** added to branch protection — a self-hosted runner that is offline
  must not block PRs. Promote to a required check once it has proven stable.
- No other workflow changes; the five required checks (lint/type/test/
  docs-sync/commit-lint) are unchanged.

## 6. Gotchas discovered

- **A single wrapping-block C-grid is degenerate in blockMesh** when the
  trailing edge is closed (coincident TE corner vertices → "inward-pointing
  faces"). Use an O-grid, or a multi-block C-grid.
- **A single-command `typer` app collapses the command into the root** —
  `aero run X` parses `run` as the argument. An `@app.callback()` (even
  empty) forces named subcommands.
- **The O-grid's sharp TE is skewed** (~41 skew faces, max skewness ~17); the
  pressure residual plateaus ≈ 1.5e-3. checkMesh "fails" on skewness + high
  aspect ratio — the latter is normal for a boundary-layer mesh. The solve is
  stable and Cd is steady; Stage 05 should improve mesh quality.
- **`uv run` re-syncs the project environment** — it dropped the editable
  install / extras mid-session. Use `.venv/bin/python` (or activate the venv)
  directly, not `uv run`, once `uv pip install -e .[…]` has set the venv up.
- **`pyfoam>=2024.5` does not exist on PyPI** (latest is 2023.7).
- **MLflow's file-store backend is deprecated (Feb 2026)** — a `FutureWarning`
  only; Stage 04's tracking-server + DB backend resolves it.

## 7. Open items for the next stage (and beyond)

**Operator follow-up — register the `vv` self-hosted runner** (auto-mode
classifier blocked the automated path):
1. Token: `gh api -X POST /repos/ernesto01louis/aero-research-platform/actions/runners/registration-token --jq .token`
2. On `aero-build` as `aero-admin`: download `actions/runner` v2.334.0
   (`actions-runner-linux-x64-2.334.0.tar.gz`), extract, then
   `./config.sh --url https://github.com/ernesto01louis/aero-research-platform --token <TOKEN> --labels vv --unattended`
3. As root: `./svc.sh install aero-admin && ./svc.sh start`
4. SSH-to-self so the smoke test's `ssh root@aero-build` works: generate an
   `aero-admin` keypair, authorise its pubkey in `root@aero-build`'s
   `authorized_keys`, and `ssh-keyscan aero-build >> ~aero-admin/.ssh/known_hosts`.

**Stage 04 (Provenance Backbone):**
- Four-fold provenance — add `dvc_input_hash` + `config_hash` (needs
  DVC-tracked inputs and Hydra); `aero/provenance/mlflow_basic.py` is interim
  and is superseded by the full logger.
- Stand up the MLflow tracking server on `aero-mlflow` + MinIO sidecar;
  `aero_provenance` DB on Postgres LXC 202; point the tracking URI there.
- DVC-track `data/references/naca0012/`.
- Decide whether to commit `uv.lock`.

**Stage 05:** tighten the ±25% Cd band against NASA TMR data; improve O-grid
mesh quality (resolve the residual plateau); move the V&V runner to `aero-vv`
(install Apptainer there).

**Stage 06:** the multi-solver `Solver` abstraction, when SU2 forces it.

## 8. Pointers for the next session

- **Read first:** this handoff, `docs/adrs/ADR-003-openfoam-walking-skeleton.md`,
  CLAUDE.md (the OpenFOAM walking-skeleton section).
- **Do not re-read:** the SIF build, the adapter implementation — all
  complete and committed.
- **Run first to verify the world:**
  ```bash
  cd /root/projects/aero-research-platform
  uv venv && uv pip install -e ".[openfoam,dev]"
  .venv/bin/pytest -q tests/unit                    # 15 pass
  ssh root@aero-build apptainer verify /opt/aero/containers/openfoam-esi.sif
  .venv/bin/aero run naca0012 --executor local-ssh  # Cd ~ 0.00875
  ```

## 9. Artifacts produced

Branch `stage-03/openfoam-walking-skeleton` (`9aba9fd`→`d082c5d`, 9 commits):

- **Container:** `containers/openfoam-esi.def`, `scripts/build_openfoam_sif.sh`;
  `openfoam-esi.sif` on `/mnt/aero/containers/`; SHA in `SHA256SUMS`.
- **Python core:** `aero/orchestration/` (`_base.py` Executor/ExecResult,
  `local_ssh.py`), `aero/adapters/openfoam/` (`geometry.py`, `schemas.py`,
  `case_writer.py`, `solver.py`), `aero/provenance/mlflow_basic.py`,
  `aero/cli.py`.
- **Reference data:** `data/references/naca0012/{naca0012.csv,reference.md}`.
- **Tests:** `tests/conftest.py`, `tests/unit/test_openfoam_adapter.py`,
  `tests/stage_03/test_naca0012_smoke.py`.
- **Docs/CI:** `ADR-003`, `vv-smoke.yml` (real), README/CHANGELOG/CLAUDE.md
  updates; `run_long.sh` `[user@]alias` support.

## 10. Confidence / risk note

- **High confidence:** the end-to-end pipeline — SIF build/sign, `apptainer
  exec` over SSH as root, `blockMesh`/`simpleFoam`, `coefficient.dat` parsing,
  MLflow logging. Verified twice (`aero run` and the smoke test); Cd 0.00875
  is reproducible.
- **Medium / known-limited:** O-grid mesh quality — the sharp-TE skewness caps
  the pressure residual at ≈ 1.5e-3. Cd is steady and in-band, but this mesh
  is walking-skeleton-grade, not V&V-grade. Stage 05 must improve it before
  tightening tolerances.
- **Low confidence / operator-owned:** the `vv` self-hosted runner is not
  registered (§7); until it is, `vv-smoke` jobs queue without running.
- **Outstanding risks:** none blocking. The case-directory accumulation on NFS
  and the unmanaged `uv.lock` are minor housekeeping items for Stage 04.
