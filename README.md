# aero-research-platform

[![CI](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/test.yml/badge.svg)](https://github.com/ernesto01louis/aero-research-platform/actions/workflows/test.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/1241412451.svg)](https://doi.org/10.5281/zenodo.20292712)

A fully open-source, peer-review-grade, hardware-agnostic **aerodynamic shape
optimizer**: plug in geometry (parametric, then CAD/STL/3MF), define an aerodynamic
objective, and the platform returns an **improved, CFD-verified design** — with CFD as
the ground truth. The forward CFD + UQ + provenance stack (OpenFOAM-ESI core; preCICE
FSI; the flapping-wing flagship validation ladder) is the foundation that makes every
claimed improvement trustworthy. Every reported number traces to a `(git_sha,
dvc_input_hash, container_sif_sha256, config_hash)` four-tuple, and **no improvement is
thesis-grade unless its CFD-verified delta exceeds its quantified uncertainty** —
reproducibility and honest error bars are the non-negotiable foundation. See
[`docs/handoff-bundle/00-MISSION-AND-SCOPE.md`](docs/handoff-bundle/00-MISSION-AND-SCOPE.md)
for scope.

## Status

<!-- STATUS:START -->
**Latest tag:** v0.0.17  ·  **Status:** complete  ·  **Completed:** 2026-07-24

**Stage 17 — Surrogate-Accelerated Optimization (own-data)** — most recent stage.

**Next:** Stage 18 — Arbitrary-Geometry Ingestion + Robust Meshing.

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
- [`docs/handoff-bundle/`](docs/handoff-bundle/) — governing scope
  ([`00-MISSION-AND-SCOPE.md`](docs/handoff-bundle/00-MISSION-AND-SCOPE.md)) + the
  20-stage build map ([`README-handoff.md`](docs/handoff-bundle/README-handoff.md)).
  New here? Start with
  [`PROMPT-CONTEXT-RESTORE.md`](docs/handoff-bundle/PROMPT-CONTEXT-RESTORE.md).
- [`docs/adrs/`](docs/adrs/) — architecture decision records
- [`docs/handoffs/`](docs/handoffs/) — per-stage handoff exit notes

## License

[GPL-3.0](LICENSE). The whole stack stays open. No proprietary blobs.

## Citation

See [`CITATION.cff`](CITATION.cff). A Zenodo concept DOI will be reserved in
Stage 04; cite the platform via that DOI plus the four-fold provenance tuple
of the specific run you reference.
