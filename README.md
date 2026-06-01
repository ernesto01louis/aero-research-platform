# aero-research-platform

[![CI](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/test.yml/badge.svg)](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/test.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/1241412451.svg)](https://doi.org/10.5281/zenodo.20292712)

A fully open-source, peer-review-grade, hardware-agnostic research platform for
computational aerodynamics. Spans classical CFD (OpenFOAM-ESI, SU2, PyFR, NekRS),
differentiable CFD (JAX-Fluids 2.0), ML surrogates (NVIDIA PhysicsNeMo —
DoMINO, Transolver, FIGConvNet, X-MeshGraphNet, MoE), multi-physics coupling
(preCICE 3), and agentic CAE (NVIDIA NeMo Agent Toolkit + AI-Q Blueprint fork).
Every published number traces to a `(git_sha, dvc_input_hash,
container_sif_sha256, config_hash)` four-tuple — reproducibility is the
non-negotiable foundation.

## Status

<!-- STATUS:START -->
**Latest tag:** v0.0.9  ·  **Status:** partial  ·  **Completed:** 2026-06-01

**Stage 09 — DoMINO Baseline Surrogate (PhysicsNeMo)** — most recent stage.

**Next:** Stage 10 — Transolver / FIGConvNet / X-MGN ensemble + MoE.

See [`docs/handoffs/`](docs/handoffs/) for per-stage exit notes and
[`CHANGELOG.md`](CHANGELOG.md) for the version-tagged change log.
<!-- STATUS:END -->

## Quick start

```sh
pip install aero  # platform core only — stdlib + numpy + pydantic
```

Optional extras are gated per solver / ML framework. See
[`pyproject.toml`](pyproject.toml) for the full list.

### Run the OpenFOAM walking skeleton

The Stage 03 walking skeleton runs a NACA 0012 case end-to-end — Apptainer
OpenFOAM-ESI `simpleFoam` on an aero LXC — and reports the drag coefficient:

```sh
pip install -e ".[openfoam]"
aero run naca0012 --executor local-ssh
```

This needs the aero Proxmox cluster (Stage 02) with the OpenFOAM SIF published
on `aero-build`. Expected: Cd ≈ 0.0079 (±25% walking-skeleton band).

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — session-start invariants and conventions
- [`CONSTITUTION.md`](CONSTITUTION.md) — non-negotiable design rules
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — Conventional Commits, PR workflow
- [`docs/architecture/`](docs/architecture/) — Pass 1 architecture doc
- [`docs/sota/`](docs/sota/) — Pass 2 SOTA literature review
- [`docs/handoff-bundle/`](docs/handoff-bundle/) — Pass 3 best-practices guide + 16-stage
  build bundle
- [`docs/adrs/`](docs/adrs/) — architecture decision records
- [`docs/handoffs/`](docs/handoffs/) — per-stage handoff exit notes

## License

[GPL-3.0](LICENSE). The whole stack stays open. No proprietary blobs.

## Citation

See [`CITATION.cff`](CITATION.cff). A Zenodo concept DOI will be reserved in
Stage 04; cite the platform via that DOI plus the four-fold provenance tuple
of the specific run you reference.
