# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Stage tags
`v0.0.NN` are pre-alpha; v0.1.0 ships after Stage 16.

## [Unreleased]

_(empty — work pending toward the next `v0.0.NN` stage tag)_

## [0.0.2] - 2026-05-19

### Added — Stage 02 (Proxmox Topology & Container Build Pipeline)

- `docs/architecture/proxmox-inventory-2026-05-16.md` — committed host inventory
- Seven `aero-*` LXCs provisioned (IDs 210-216, unprivileged Ubuntu 24.04,
  dual-NIC: LAN + private `10.10.10.0/24`) via `scripts/provision_aero_lxc.sh`
- `ansible/` — inventory, `site.yml`, three roles: `aero-base` (users, scoped
  sudo, ufw, baseline packages, node-exporter), `aero-apptainer` (pinned
  Apptainer 1.5.0), `aero-nfs-client` (NFS bind-mount symlinks)
- TrueNAS `aero/` NFS dataset — host-mounted at `/mnt/aero-nfs`, bind-mounted
  into build/dev/vv/mlflow at `/mnt/aero` (NFS subdirs: dvc-remote,
  mlflow-artifacts, datasets, containers)
- Apptainer SIF pipeline — `containers/_base.def`, `hello-world.def`,
  `scripts/build_base_sifs.sh`; `_base.sif` + `hello-world.sif` built, PGP-
  signed (key `682F6145…`), recorded in `containers/SHA256SUMS`
- `scripts/run_long.sh` — tmux-based long-running-job submit/poll helper
- `scripts/verify_stage_02.sh` — Stage 02 verification gate (30 checks)
- Interim `vzdump` backup job (aero LXCs only, daily 03:00, keep-7)
- `docs/adrs/ADR-002-proxmox-topology.md`; `docs/architecture/`
  `proxmox-topology.md`, `ssh-conventions.md`, `backup-interim.md`
- Hardened `.claude/hooks/block-dangerous-bash.sh` (pct/qm guard, protected
  host paths, shared-host SSH guard)

## [0.0.1] - 2026-05-17

### Added — Stage 01 (Scaffolding & Conventions)

- `LICENSE` — GPL-3.0 (canonical FSF copy)
- Governance: `CLAUDE.md`, `AGENTS.md`, `CONSTITUTION.md`, `CONTRIBUTING.md`,
  `SECURITY.md`, `CITATION.cff` (Zenodo DOI placeholder), `CHANGELOG.md`
- Repository layout per project brief: `aero/{adapters,surrogates,
  orchestration,vv,uq,provenance,agentic,literature}/` skeleton with
  per-subdir `.gitkeep`; `containers/`, `data/`, `ansible/`, `tests/`,
  `scripts/`, `docs/`
- `pyproject.toml` (uv-managed, PEP 621); base deps numpy/pydantic/typer/
  loguru/dvc; optional extras enumerated as placeholders (openfoam, su2,
  pyfr, nekrs, jax-fluids, physicsnemo-cu12, precice, gpu-rental, uq,
  agentic, literature, orchestration, dev, docs)
- `.pre-commit-config.yaml` with ruff, mypy (strict on `aero/`), gitleaks,
  validate-pyproject, large-file check, local pytest-unit hook, local
  docs-status-sync hook
- GitHub Actions: `lint`, `type`, `test`, `docs-sync`, `commit-lint`,
  `vv-smoke` (placeholder)
- `.github/CODEOWNERS`; `PULL_REQUEST_TEMPLATE.md`
- `.claude/` agent configuration: `settings.json` with hooks (PreToolUse
  guards, Stop handoff-existence check), `rules/`, `commands/`, `agents/`,
  `skills/`
- Templates: `docs/handoffs/_template.md`, `docs/adrs/_template.md`
- `docs/adrs/ADR-001-license-and-governance.md` — captures GPL-3.0 choice,
  branch protection ruleset, mypy strict-on-aero policy, commit conventions,
  solo-developer admin-bypass posture
- `scripts/check_handoff_exists.sh` (Stop-hook gate),
  `scripts/regenerate_status.sh` (README STATUS sync)
- `tests/unit/test_smoke.py` — first smoke test (import + version)
- Branch protection on `main`: PR required, status checks (lint/type/test/
  docs-sync/commit-lint), linear history, no force pushes, no direct pushes,
  CODEOWNERS 1-approval; `enforce_admins: false` for solo-admin self-merge
- Post-stage handoff: `docs/handoffs/STAGE-01-scaffolding-and-conventions-DONE-2026-05-17.md`

[Unreleased]: https://github.com/ernesto01louis/aero-research-platform/compare/v0.0.2...HEAD
[0.0.2]: https://github.com/ernesto01louis/aero-research-platform/releases/tag/v0.0.2
[0.0.1]: https://github.com/ernesto01louis/aero-research-platform/releases/tag/v0.0.1
