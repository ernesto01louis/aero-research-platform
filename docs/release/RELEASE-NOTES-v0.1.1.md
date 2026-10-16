# aero-research-platform v0.1.1

The first foundation release of ADR-051 (Stage 22, "an honest V&V report"). It changes what the
production gate **shows**, never what a case **is**: no tolerance moved, no case became `pass`
without a passing run, and no physics changed. v0.1.1 makes no new claim of any kind.

## 1. What this release is

- **The V&V report reads the truth.** `aero vv report --latest` used to read the newest 500 of
  ~2400 MLflow runs; `vv-smoke`'s four smoke cases filled that window, so three failures and three
  passes showed as `missing`. It now asks MLflow, per registered case and solver stack, for that
  case's newest run. An independent full pagination of the experiment
  (`scripts/vv_report_crosscheck.py`) agrees with it case for case. The history listing pages the
  whole experiment and states its bound.
- **The status is typed** (`pass | fail | regress | missing | unknown | frozen | deferred`). A run
  without a recognised `vv_status` is `unknown`, never `pass`.
- **The verdict is per solver stack** (ADR-051 D2 (b), operator decision 2026-10-16). A
  `production`-tagged run is gated by its own stack's verdict. The frozen-optional SU2 and PyFR
  stacks (ADR-013) and the deferred `hg2007_flexible_foil` (ADR-046 S4) stay registered and
  visible as `frozen` / `deferred`, and never count as a pass.
- **No V&V workflow is green when it measured nothing.** Every `dvc pull` in CI is targeted and
  fails loudly; only a measured tolerance miss may `xfail`; a solver failure fails its test; a
  cluster that is not ready fails the job; every V&V job writes a step summary of what it measured
  and what it did not, and why. `vv-transonic` (the SU2 stack) runs on dispatch only.

## 2. The V&V state at v0.1.1

| Stack | Verdict | Cases |
|---|---|---|
| openfoam (active) | **RED** | 7 pass, 4 fail (`flat_plate_te`, `naca0012_verification`, `plunging_airfoil_hg2007_st03`, `_st03_lm`), 9 with no run |
| su2 (frozen-optional, ADR-013) | FROZEN | `naca0012_transonic`, `onera_m6`: never evaluated |
| pyfr (frozen-optional, ADR-013) | FROZEN | `taylor_green_p3_32`, `periodic_hill_2d`: never evaluated |
| deferred (ADR-046 S4) | gates nothing | `hg2007_flexible_foil` |

**No stack is clear for `production`-tagged runs, so no result is tagged `production`.** The
OpenFOAM verdict was RED at v0.1.0 too; v0.1.1 shows why, case by case, with run ids (the Stage-22
handoff).

## 3. What v0.1.1 does and does not claim

**The optimizer has never been run on a flapping-wing case, and v0.1.0 makes no flapping-wing
optimization claim.** v0.1.1 adds no claim of any kind, so it makes none either. Everything v0.1.0
reported stands unchanged, including its limits:

- **Stage 14, rigid flapping wing vs. Wang–Birch–Dickinson (2004).** The rotation-timing ordering
  is reproduced, as a pre-registered, non-gated diagnostic. The gated symmetrical mean lift misses
  the experiment by 45.7 % against a pre-registered ±25 % band, a documented NO-GO; the band was
  not relaxed. Overset wake-capture dissipation is the leading hypothesis, untested so far; Stage
  26 of ADR-051 tests it.
- **Stages 15–17, airfoil optimization.** The best tier is *validated*. Stage 16 is a one-gate
  NO-GO; Stage 17's pre-registered speed-up is a degenerate NO-GO.
- **The mission's publication bar is not met.** The turbulent NASA TMR cases still fail or have no
  run, and no CFD-verified optimization delta on a flapping case exists.

## 4. Install

Install from a clone with [uv](https://docs.astral.sh/uv/): `uv sync`, plus `--extra <name>` per
extra. The PyPI name `aero` belongs to an unrelated project and is not this platform.

## 5. Known issues

- **Four OpenFOAM-stack cases fail and nine have never run through the registry path.** Stage 24
  runs the registry under Stage 23's provenance; Stage 25 owns the turbulent canonical cases.
- **The NACA 0012 verification solve diverges** (simpleFoam, ~iteration 83; ADR-017). CI now
  deselects it with that reason in words instead of reporting it as `xfailed`.
- **SU2_CFD fails at startup on the cluster runner** for every SU2 case, and the ONERA M6 Cp slice
  is unimplemented. The SU2 stack is frozen-optional; its verdict is FROZEN.
- **A failed solve logs nothing to MLflow**, so the report shows a crashed case's previous status.
  Stage 24 decides whether a failed solve becomes a logged `fail`.
- **Two provenance weaknesses**, stated in every crate: `dvc_input_hash` is a repository-wide DVC
  sync-state digest, and `container_sif_sha256` is a basename lookup. Stage 23 fixes both.
- **`pip-audit` reports known advisories** in locked transitive dependencies (informational;
  Stage 23 refreshes the lock).
- **The weekly `moving-vv` job times out** on `plunging_airfoil_hg2007` at its 4-hour ceiling.
- **The Stage-17 surrogate certificate expires 2027-01-20.**

## 6. Citation

Zenodo concept DOI: [10.5281/zenodo.20292712](https://doi.org/10.5281/zenodo.20292712). A version
DOI is minted only if a GitHub Release is published for this tag, which is the operator's choice.
See `CITATION.cff`.
