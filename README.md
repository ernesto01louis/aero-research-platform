# aero-research-platform

[![CI](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/test.yml/badge.svg)](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/test.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

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
**Latest tag:** v0.0.1  ·  **Status:** complete  ·  **Completed:** 2026-05-17

**Stage 01 — Scaffolding & Conventions** — most recent stage.

**Next:** Stage 02 — Proxmox Topology & Container Build Pipeline.

See [`docs/handoffs/`](docs/handoffs/) for per-stage exit notes and
[`CHANGELOG.md`](CHANGELOG.md) for the version-tagged change log.
<!-- STATUS:END -->

## Quick start

```sh
pip install aero  # platform core only — stdlib + numpy + pydantic
```

Optional extras are gated per solver / ML framework. See
[`pyproject.toml`](pyproject.toml) for the full list.

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
