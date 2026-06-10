# STAGE-07: PyFR & NekRS — High-Order GPU Adapters

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Solver fleet" and Pass 2 §2.1-2.2 (scale-resolving SOTA):

- PyFR adapter (flux reconstruction, GPU-resident) as `aero[pyfr]` extras.
- NekRS adapter (spectral element, GPU-resident) as `aero[nekrs]` extras.
- High-order curved mesh pipeline (NekMesh, Gmsh high-order) for both.
- The first rented-GPU CFD run: a small NekRS or PyFR case on a RunPod or
  Lambda H100, proving the cloud-GPU path works end-to-end before Stage 09 needs
  it for surrogate training.
- TMR cases extended where applicable (PyFR can run the flat plate; NekRS is
  more challenging for boundary-layer cases but doable for periodic-hill / Taylor-
  Green).
- The `Solver` abstraction is further refined by these two adapters; refactor
  as needed (this is expected).

## ROLE

You are adding two high-order GPU-resident solvers and validating the
abstraction holds across four very different codes. You are also taking the
first rented-GPU step — proof that the cloud path works end-to-end.

## GOAL

1. Author `containers/pyfr.def` — Apptainer SIF for PyFR from upstream (BSD-3).
   Include CUDA 12 backend (or 13, matching the host driver — check Stage 02's
   inventory). Build and sign.
2. Author `containers/nekrs.def` — Apptainer SIF for NekRS from upstream
   (BSD-3). Include OCCA + libParanumal backends. Build and sign.
3. Author `aero/adapters/pyfr/` and `aero/adapters/nekrs/`:
   - Both implement the `Solver` protocol from Stage 06
   - Both handle their native mesh formats (Gmsh `.msh` high-order for PyFR;
     `.re2` for NekRS)
   - Both expose convergence as the typed series the protocol expects
4. Author `aero/adapters/_meshing/` — high-order mesh utilities:
   - NekMesh wrapper for spectral-element meshes
   - Gmsh high-order export helper
5. Add `aero[pyfr]` and `aero[nekrs]` extras to pyproject.toml.
6. Author benchmark cases:
   - **PyFR**: Taylor-Green vortex (canonical high-order benchmark), flat plate
     LES (TMR-compatible at low Reτ if computationally feasible)
   - **NekRS**: Taylor-Green vortex, periodic hill LES (canonical separated-flow
     benchmark from ERCOFTAC; comparable to literature reference data)
7. Refactor the `Solver` protocol if these two adapters reveal seams. Document
   the refactor in ADR-007.
8. Provision a minimal rented-GPU executor at `aero/orchestration/runpod_basic.py`
   — NOT the full multi-cloud abstraction (that's Stage 13). Just enough to:
   - Launch a single H100 pod via RunPod API
   - Upload the SIF and case directory via SCP or RunPod's volume mount
   - Run the case
   - Pull results back
   - Terminate the pod
   Credentials via Vault (no API keys in repo).
9. Run one PyFR case (e.g., Taylor-Green at moderate resolution) on a RunPod
   H100 end-to-end. Log all four provenance tags. Verify the result matches the
   local reference within numerical noise.
10. Author `aero/vv/scale_resolving/` directory with the canonical benchmarks:
    - Taylor-Green vortex (kinetic energy dissipation vs reference DNS)
    - Periodic hill (mean profiles vs LES reference data)
11. Update `vv-transonic.yml` → split into multiple `vv-*.yml` workflows; add
    `vv-scale-resolving.yml` which runs on a GPU runner (self-hosted GPU LXC if
    available, otherwise scheduled to use RunPod via the new executor with cost
    cap).
12. Update CLAUDE.md with PyFR/NekRS adapter SSH conventions and a note about
    the cost cap on cloud GPU CI runs.
13. Author ADR-007 documenting:
    - PyFR vs NekRS scope split (PyFR: mixed-element, more flexible; NekRS:
      hex-dominant, scales harder)
    - Why we ship both rather than choosing one
    - The minimal RunPod executor scope and the deferred full abstraction
    - Cost cap policy for cloud GPU CI ($/month ceiling, alert path)
14. Tag `v0.0.7`.

## WHY

PyFR and NekRS are the open-source SOTA for high-order GPU-resident scale-
resolving simulation (Pass 2 §2.1-2.2 confirmed). They are how the platform
reaches wall-resolved LES and DNS — required for bio-inspired drag-reduction
research (riblets, vibrating surfaces) which is explicit in the user's research
goals.

Validating two GPU-resident solvers also means *both* must containerize
correctly with GPU passthrough, both must work via `apptainer exec` with `--nv`,
and both must work on rented GPU. If we wait until Stage 09 (surrogate training,
which actually needs the GPU) to discover that GPU passthrough is broken in our
container, the cost compounds.

The minimal RunPod executor is the canary for Stage 13. If you can't launch a
single PyFR run on a single H100, you can't build the cost-routed multi-cloud
abstraction.

## HOW

- PyFR build: prefer the upstream PyPI release; for the SIF, pip-install inside
  the Ubuntu CUDA base. PyFR is sensitive to CUDA + CuPy versions; pin all of
  them and document in the .def.
- NekRS build: source-build from the upstream git tag. Long compile (~30-60
  min). Use `tmux`.
- For GPU passthrough in Apptainer: `apptainer exec --nv` works if the host has
  NVIDIA drivers. On RunPod, the container runs on a host that already has the
  drivers; just need to ensure the SIF doesn't try to install its own driver.
- The RunPod executor: keep it stupid for now. Single-pod, no pooling, no
  retry-on-spot-eviction, no S3-style sync. Stage 13 makes it sophisticated.
- Cost cap: implement as a pre-launch check that queries RunPod billing for the
  month-to-date; fail loud if above a configured ceiling. Default ceiling: $50/
  month for CI (operator can raise via config).
- Taylor-Green vortex: dissipation rate compared against the Brachet et al. DNS
  reference at Re=1600.
- Periodic hill: mean velocity profiles compared against Breuer et al. or
  Rapp/Manhart LES references.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-07-pyfr-and-nekrs-adapters.md` (this file)
- `docs/handoffs/STAGE-06-*-DONE-*.md`
- ADR-006 (`Solver` protocol final shape; this stage may extend it)
- Pass 2 §2.1-2.2 for PyFR/NekRS technical context

## GUARDRAILS — DO NOT

1. Do NOT install GPU drivers inside the SIFs. Drivers come from the host
   (Proxmox GPU VM or RunPod host).
2. Do NOT hardcode the RunPod API key. Vault, env var injection, never repo.
3. Do NOT exceed the cost cap. If a CI run would, fail loud with the projected
   cost.
4. Do NOT use `--dangerously-skip-permissions` for the cloud runs. The Claude
   Code session does the *submission*; the actual run happens on the cloud GPU
   without Claude Code attached.
5. Do NOT skip the Taylor-Green V&V. It's the canonical high-order accuracy test
   and required by the ADR-005 V&V harness contract.
6. Do NOT add cloud orchestration features beyond "launch one pod, run, pull,
   terminate". Stage 13 is the home for cost routing, multi-cloud, retry, spot
   handling, queue, etc.

## DELIVERABLES

- [ ] PyFR and NekRS SIFs build successfully; SHAs in SHA256SUMS
- [ ] `pip install -e .[pyfr,dev]` and `pip install -e .[nekrs,dev]` work
- [ ] Both pass Taylor-Green vortex within high-order accuracy expectations
- [ ] NekRS passes periodic hill within LES reference tolerance
- [ ] PyFR runs the flat plate or simpler high-order benchmark within tolerance
- [ ] One PyFR run completes end-to-end on RunPod H100 with all four provenance
      tags logged
- [ ] `vv-scale-resolving.yml` workflow active (with cost cap)
- [ ] `import-platform-only` CI job still green (no leakage)
- [ ] ADR-007 committed
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.7`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- RunPod account credentials provisioning (Vault path, key scope)
- The CI cost cap ($/month ceiling)
- Any `Solver` protocol-level refactor (these affect OpenFOAM and SU2 adapters
  retroactively)
- The first non-trivial cloud GPU run (operator should see the projected $ cost
  before launch)

## POST-STAGE HANDOFF

Required emphases:

- **First-cloud-run details**: wall-clock, $ cost, pod type, four-tuple, results.
- **The refined `Solver` protocol**: link, diff vs Stage 06.
- **Cost cap state**: where it's enforced, how to raise it, monthly burn so far.
- **Open items for Stage 08**: JAX-Fluids will be the first differentiable solver
  and the first one that uses JAX/XLA rather than the typical OpenFOAM/SU2/PyFR/
  NekRS pattern. Flag where the protocol might need yet another tweak.
- **Open items for Stage 09**: surrogate training will reuse the RunPod executor;
  list any rough edges that need smoothing.
- **Gotchas**: GPU driver/CUDA pinning, Apptainer `--nv` edge cases, RunPod
  volume mount quirks.
