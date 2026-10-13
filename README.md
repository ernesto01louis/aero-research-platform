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
**Latest tag:** v0.1.0 (not yet tagged)  ·  **Status:** partial  ·  **Completed:** 2026-10-12

**Stage 21 — Release: Portable Bundles + Hardening + v0.1.0** — most recent stage.

**Next:** resume Stage 21 — Release: Portable Bundles + Hardening + v0.1.0 — partial, not finished.

See [`docs/handoffs/`](docs/handoffs/) for per-stage exit notes and
[`CHANGELOG.md`](CHANGELOG.md) for the version-tagged change log.
<!-- STATUS:END -->

## Quick start

From a clone, with [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/ernesto01louis/aero-research-platform && cd aero-research-platform
uv sync                      # the platform core (numpy, pydantic, typer, loguru, dvc)
uv sync --extra openfoam     # plus an optional extra; see pyproject.toml for the list
```

A released wheel (`aero-<version>-py3-none-any.whl`) is attached to each
[GitHub Release](https://github.com/ernesto01louis/aero-research-platform/releases). Do not
install `aero` from PyPI: that name belongs to an unrelated project.

### Verify a result crate

Each reported result ships as a self-describing **result crate** under [`crates/`](crates/).
A crate holds:
- the exact config preimage;
- the four-tuple;
- the U95 envelope;
- its validity context and limitations;
- RO-Crate 1.3 / PROV metadata.

A crate verifies without the cluster, with nothing but the wheel, numpy and pydantic:

```sh
python -I -B -m aero.crate verify crates/stage*                    # or a downloaded .crate.zip
python -I -B -m aero.crate show crates/stage14-rigid-flapping-wbd2004   # what it does NOT claim
```

### Run the OpenFOAM walking skeleton

The Stage 03 walking skeleton runs a NACA 0012 case end-to-end — Apptainer
OpenFOAM-ESI `simpleFoam` on an aero LXC — and reports the drag coefficient:

```sh
uv sync --extra openfoam --extra provenance
uv run aero run naca0012 --executor local-ssh
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
  21-stage build map ([`README-handoff.md`](docs/handoff-bundle/README-handoff.md)).
  New here? Start with
  [`PROMPT-CONTEXT-RESTORE.md`](docs/handoff-bundle/PROMPT-CONTEXT-RESTORE.md).
- [`docs/adrs/`](docs/adrs/) — architecture decision records
- [`docs/handoffs/`](docs/handoffs/) — per-stage handoff exit notes
- [`crates/`](crates/) — the committed result crates and their digests
- [`SECURITY.md`](SECURITY.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

## License

[GPL-3.0-or-later](LICENSE).
- **Dependencies** are checked against a GPL-3.0-compatible allowlist on every PR (ADR-048). The
  base install and the supported extras are proprietary-free. NVIDIA's proprietary CUDA wheels
  appear only in the frozen-optional GPU extras.
- **Result-crate content** (`crates/`) is CC-BY-4.0.

## Citation

Cite the platform through its Zenodo concept DOI,
[10.5281/zenodo.20292712](https://doi.org/10.5281/zenodo.20292712) (see
[`CITATION.cff`](CITATION.cff)). Cite a specific result by its **crate digest plus its
four-tuple** (`crates/README.md`).

## Support and governance

- **Questions and bugs:** open an issue using the templates. A bug report about a result names
  its four-tuple or its crate id and the version.
- **Security:** report privately, as described in [`SECURITY.md`](SECURITY.md).
- **Governance:** a single maintainer (the operator). Design rules live in
  [`CONSTITUTION.md`](CONSTITUTION.md) and change only through an ADR, a ≥ 72 h review and the
  operator's approval. Decisions are recorded in [`docs/adrs/`](docs/adrs/).
- **Scope:** features that do not serve the optimizer mission or the flapping-wing flagship are
  deferred by design (SCOPE-GATE).
- **Support:** best effort; there is no support guarantee.
