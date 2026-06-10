# STAGE-12: Full V&V Suite & UQ Wiring

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"V&V + UQ" and Pass 1 §"V&V and benchmarks":

- The AIAA Drag Prediction Workshop (DPW-7) subset implemented and passing
  within published consensus bands for at least the NASA CRM at cruise.
- The AIAA High Lift Prediction Workshop (HLPW-5) subset for the CRM-HL at one
  representative AoA.
- ERCOFTAC backward-facing step and square cylinder cases added.
- UQpy + Dakota wired as `aero[uq]`: every publishable run can be wrapped in a
  forward-UQ envelope (parametric uncertainty in geometry, BCs, turbulence
  constants).
- The "thesis-grade gate": no run is marked `production` without an attached
  UQ envelope.
- The full V&V dashboard rolls everything from Stages 05, 06, 07, 11, and 12
  into one report.

## ROLE

You are completing the V&V scaffold from research-grade smoke (Stage 05) to
thesis-grade, publishable-quality verification with uncertainty quantification.
After this stage, every published number from the platform carries an error
bar that a peer reviewer would accept.

## GOAL

1. Add DPW-7 cases at `aero/vv/dpw/`:
   - NASA CRM (Common Research Model), wing-body, cruise condition (Mach 0.85,
     AoA 2.5°, Re=5e6)
   - DPW-7 published consensus bands: drag, lift, pitching moment
   - Mesh from DPW-7 official grid family (use medium grid for CI; full sweep
     in nightly)
2. Add HLPW-5 case at `aero/vv/hlpw/`:
   - CRM-HL (High Lift), one representative AoA (~7° approach)
   - HLPW-5 published consensus bands
3. Add ERCOFTAC cases at `aero/vv/ercoftac/`:
   - Backward-facing step (canonical separated flow)
   - Square cylinder (vortex shedding, Strouhal number)
4. Author `aero/uq/`:
   - `_base.py` — `UQStudy` protocol: takes a base case + a parameter
     distribution dict, produces an `UQResult` (mean, std, quantiles, full
     ensemble of run handles)
   - `uqpy_adapter.py` — wraps UQpy for sampling (Monte Carlo, Latin Hypercube,
     polynomial chaos)
   - `dakota_adapter.py` — wraps Dakota for the adjoint/gradient-enhanced
     methods Dakota does well
   - `provenance.py` — UQ runs log a *bundle* of four-tuples (one per inner
     run) plus the UQ-specific tags (sampling method, sample count, parameter
     distribution hash)
5. Add `aero[uq]` extras: `UQpy`, `chaospy`, `salib` (sensitivity), `pyDOE3`,
   and document the Dakota install (binary release; Apptainer SIF
   `containers/dakota.def`).
6. Author the `production` run gate:
   - `aero/cli.py` adds `aero run --tag production --uq <study>` that REQUIRES
     a `--uq` argument; the run won't proceed without one
   - The MLflow tag `tag=production` is only set if the UQ envelope is attached
   - CI check `production-uq-required` fails any PR that attempts a production
     run without UQ
7. Demonstration UQ studies:
   - Run a Monte Carlo UQ on the NACA 0012 case from Stage 03/05, sampling
     turbulence-model coefficient uncertainty (TMR has published distributions
     for this)
   - Run a polynomial-chaos UQ on the DPW-7 case for inflow-Mach uncertainty
8. Add `aero/vv/dashboard.py` enhancements:
   - Roll up all V&V results from Stages 05, 06, 07, 11, 12 into one HTML
     dashboard
   - Per-case: status, error vs reference, link to MLflow run, link to UQ
     envelope if any
   - Auto-published via mkdocs (Stage 16) but already generated here
9. Author `vv-full.yml` workflow:
   - Triggers nightly
   - Runs all V&V cases (TMR + transonic + scale-resolving + DPW + HLPW +
     ERCOFTAC + FSI3)
   - Posts dashboard as a PR comment for PRs to `main` (read-only, not gating
     because of cost)
10. Tighten tolerances where Stage 05/06 set loose bands and the platform has
    proven it can do better. Update CLAUDE.md's "no red dashboard for production"
    rule with the new tolerances.
11. Author ADR-012 documenting:
    - The full V&V case set and the rationale for each
    - The `production`-tag UQ requirement
    - UQpy vs Dakota division of labor
    - Tightened tolerances from earlier stages
12. Tag `v0.0.12`. This is the **thesis-grade gate** — the platform is now
    capable of producing publishable numbers with reviewer-grade error bars.

## WHY

DPW and HLPW are the workshops every aerodynamicist's CFD validation gets
benchmarked against. Reproducing their published consensus is what proves the
platform is in the same league as the industry codes (Star-CCM+, Fluent, CFL3D,
FUN3D).

UQ is non-negotiable for thesis-grade work in 2026. A Cd number without an
error bar is a guess. The `production` gate is structural — it makes UQ
impossible to forget.

ERCOFTAC adds separated-flow cases that DPW doesn't cover well; the backward-
facing step and square cylinder are canonical and have decades of reference
data.

## HOW

- DPW/HLPW grids: download the official grid families from the workshop's
  public archive. DVC-track them; they're large (~GBs per grid level).
- DPW consensus bands: from the published DPW-7 summary paper (Tinoco et al.);
  cite explicitly in the case's README.
- UQ runs are expensive: a 100-sample Monte Carlo on a DPW-7 case is 100×
  the cost of a single run. Use Latin Hypercube to reduce sample count;
  polynomial chaos for smooth response surfaces.
- Dakota integration: Dakota is a separate process; wrap via subprocess with
  the standard Dakota input file format. Apptainer SIF for portability.
- The `production` tag: implement as a Hydra config field that flows into the
  MLflow tags; the CLI refuses to proceed if `tag=production` and `--uq` is
  unset.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-12-full-vv-and-uq.md` (this file)
- `docs/handoffs/STAGE-11-*-DONE-*.md`
- ADR-005 (V&V harness), ADR-009/010 (surrogate certificates — UQ pattern
  similar), ADR-011 (FSI)
- Pass 1 §"V&V and benchmarks", Pass 2 §1 (RANS-LES, where DPW lives)

## GUARDRAILS — DO NOT

1. Do NOT mark any run `production` without UQ. The gate is structural.
2. Do NOT relax tolerances to make a DPW/HLPW case pass. If it fails, file an
   issue and investigate; the published consensus is the truth.
3. Do NOT skip the parameter-distribution provenance. UQ runs that don't
   record what distributions they sampled are not reproducible.
4. Do NOT run DPW or HLPW grids in CI on hosted runners. They're far too big.
   Self-hosted GPU runner only.
5. Do NOT bundle DPW/HLPW grids into the git repo. DVC-only.

## DELIVERABLES

- [ ] DPW-7 CRM cruise case runs and matches consensus bands
- [ ] HLPW-5 CRM-HL case runs at one AoA
- [ ] ERCOFTAC backward-facing step and square cylinder cases pass
- [ ] `aero[uq]` extras installable
- [ ] One Monte Carlo UQ and one polynomial-chaos UQ study run end-to-end
- [ ] `aero run --tag production --uq ...` enforced
- [ ] CI `production-uq-required` check active
- [ ] Full V&V dashboard generated
- [ ] `vv-full.yml` nightly workflow active
- [ ] ADR-012 committed
- [ ] CLAUDE.md updated with tightened tolerances
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.12` — **thesis-grade gate**

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- The DPW/HLPW grid downloads (storage footprint)
- Per-case tolerance choices (operator may have institutional preferences)
- Sample counts for the demonstration UQ studies (cost)

## POST-STAGE HANDOFF

Required emphases:

- **DPW/HLPW numbers** vs published consensus, with the four-tuple per run.
- **UQ envelopes** for the demonstration studies: mean, std, 95% CI.
- **Tightened tolerances** vs Stages 05–07 — table comparing old vs new bands.
- **Open items for Stage 13**: full V&V workflow is currently on a single
  self-hosted runner; multi-cloud orchestration in Stage 13 should fan it out.
- **Gotchas**: DPW grid format quirks, Dakota input-file gotchas, UQpy version
  compatibility.
