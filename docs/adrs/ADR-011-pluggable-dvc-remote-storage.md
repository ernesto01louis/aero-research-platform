# ADR-011 — Pluggable DVC-remote storage backend (cloud-now / on-prem-NAS-later)

- **Status:** accepted
- **Date:** 2026-06-01
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code agent (Stage 09)
- **Stage:** 09

## Context and problem statement

DoMINO trains on DrivAerML (~600 GB surface meshes). The Stage-04 DVC remote is
MinIO on the aero-mlflow LXC (212), backed by a **50 GB** LXC-local disk
(ADR-004 deliberately kept MinIO off NFS — no atomic renames, root-squash breaks
its IAM). That remote cannot hold CFD-scale datasets. The operator is procuring a
dedicated NAS for on-prem CFD-scale storage but wants development to proceed
**cloud-driven now** and to flip to on-prem **with config only** once the NAS is
live. The NAS migration is a parallel-cutover→re-IP that preserves the NAS IP
(`192.168.2.100`).

## Decision drivers

- **Compute is fungible** (Principle 2) — extend the same posture to storage.
- **No code change to flip backends** — the operator's explicit requirement.
- **No secrets in the repo** (Hard Rule 7) — endpoints/keys via Vault / gitignored
  `.dvc/config.local`.
- **DVC is already fully config-driven** — `.dvc/config` carries `url` +
  `endpointurl`; creds ride the boto3 env-var chain.

## Considered options

1. **Named DVC remotes + a Hydra `storage` group pointer** — no new Python; the
   training entrypoint reads `cfg.storage.dvc_remote` for its `dvc pull -r`.
2. **A Python storage-backend abstraction** wrapping DVC behind an interface.
3. **Resize the LXC MinIO disk** (status quo, single remote) — no cloud/NAS split.

## Decision outcome

Chose **Option 1** because the remote is already config-driven — "pluggable" is
named remotes + a Hydra selector, not new code. Flipping cloud→NAS is config +
Vault creds only, zero code change (the requirement).

### Key decisions

- **Three named remotes** in `.dvc/config` (default `[core] remote = aero-minio`):
  - `aero-minio` — Stage-04 MinIO on LXC 212; small artifacts (smoke certs, model
    checkpoints).
  - `aero-cloud` — cloud S3 (vendor is an open operator decision: B2 / R2 / S3 /
    RunPod-volume MinIO); holds the 600 GB DrivAerML subset for RunPod **now**.
  - `aero-nas` — the future TrueNAS-SCALE native S3 app at
    `http://192.168.2.100:9000`; running MinIO/S3 natively on ZFS sidesteps the
    NFS-atomicity/root-squash reason ADR-004 kept MinIO off NFS.
- **Hydra `conf/storage/{cloud,nas,minio}.yaml`** group, default `- storage: cloud`
  in `conf/config.yaml`. `cfg.storage.dvc_remote` selects the `-r` for
  `dvc pull`/`push`. The surrogate path embeds the same `storage:` block in
  `conf/surrogate/domino.yaml` (the CLI loads that yaml directly).
- **Credentials** are per-tier Vault secrets rendered into the gitignored
  `.dvc/config.local` + the boto3 env-var chain — never committed.
- **Migration flip:** after the NAS cutover, change the default to
  `- storage: nas` (and the `aero-cloud` data is re-pulled/re-pushed to `aero-nas`).

### Consequences

- **Positive:** development unblocked immediately (cloud); on-prem is a one-line
  config flip later; storage joins the run's hashed config context.
- **Negative:** the `aero-cloud` endpoint + vendor are pending an operator
  decision before the 600 GB stage; adding `storage` to the global config shifts
  every `aero run` `config_hash` (correct — storage is part of the run context).
- **Neutral / followup:** the NAS cutover runbook is
  `docs/runbooks/stage-09-nas-parallel-cutover.md`; confirm TrueNAS-SCALE S3
  DVC-remote compatibility on first use (MinIO-compatible, untested here).

## Links

- Stage prompt: `STAGE-09-domino-baseline-surrogate.md`
- Related ADR: ADR-004 (MinIO-off-NFS rationale), ADR-010 (DoMINO consumer)
- Related runbook: `docs/runbooks/stage-09-nas-parallel-cutover.md`
