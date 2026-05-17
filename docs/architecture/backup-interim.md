# Interim Backup Hedge

Stage 02 put an **interim** backup in place for the aero LXC fleet. This is a
hedge, not the final backup architecture — the operator is provisioning a
dedicated backup target, at which point this is revisited.

## What is backed up

A single Proxmox `vzdump` job, scoped to **only the seven aero-* LXCs**:

| Field | Value |
|---|---|
| Job ID | `77c7f864-7abb-4202-8530-9185b76801dc` |
| Guests | LXC 210-216 (aero-build/dev/mlflow/vv/prefect/agent/lit) — enumerated explicitly |
| Schedule | Daily 03:00 |
| Target | `Storage` pool (`/mnt/pve/Storage/dump/`) |
| Mode | `suspend` |
| Compression | `zstd` |
| Retention | `keep-last=7` (seven most recent per guest) |

The job enumerates the seven aero VMIDs explicitly — never `--all`, never a
pool selector — so no non-aero workload is ever included (Hard Rule 11).

## Why `suspend` mode

`Storage` is a `dir`-type (ext4) pool, which does not support LXC snapshots.
`vzdump --mode snapshot` detects this and falls back to `suspend`
automatically; the job is set to `suspend` explicitly so the nightly logs
stay clean. Suspend mode briefly pauses the container during the final
sync — observed at **<1 second** for a fresh aero LXC.

## Scope and ownership

- **Interim.** This protects against single-guest loss while the operator
  stands up a proper backup target (PBS / NAS / off-site). Revisit then.
- **Operator-owned.** The overall backup architecture is the operator's
  sysadmin task; Stage 02 only placed the hedge.
- **aero-only.** Non-aero guests on the host have **no** backup job — that
  pre-existing gap is flagged in the inventory report and remains the
  operator's call. Stage 02 deliberately does not touch it.
- **NFS side.** The TrueNAS `aero/` dataset (DVC remote, MLflow artifacts,
  datasets, container SIFs) is covered separately by a nightly TrueNAS
  snapshot task — see the Stage 02 handoff.

## Verifying / restoring

```bash
# list aero backup archives
ls -lh /mnt/pve/Storage/dump/vzdump-lxc-21*.tar.zst

# inspect the scheduled job
pvesh get /cluster/backup

# one-off backup of a single guest (does not wait for 03:00)
vzdump 210 --storage Storage --mode suspend --compress zstd

# restore a container to a NEW id (never overwrite a running guest)
pct restore <new-id> /mnt/pve/Storage/dump/vzdump-lxc-210-<timestamp>.tar.zst
```

Stage 02 first-dump verification: `vzdump-lxc-210-2026_05_17-22_04_27.tar.zst`
(659 MB) was produced and confirmed.

See `docs/adrs/ADR-002-proxmox-topology.md` for the rationale.
