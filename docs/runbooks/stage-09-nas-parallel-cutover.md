# Runbook — TrueNAS VM → dedicated NAS, parallel cutover then re-IP (Stage 09)

> **Goal:** replace the TrueNAS *VM* (CT/VM 104, `192.168.2.100`, ZFS pool `f3`,
> dataset `aero`) with dedicated NAS hardware **1-to-1**, preserving the IP so the
> aero platform needs **zero code changes**. Method: stand the new box up on a
> temp IP, ZFS-replicate while the VM still serves, verify, power off the VM, then
> re-IP the new box to `192.168.2.100`.
>
> **Operator-owned** (this is sysadmin work, not a Claude Code deliverable). This
> runbook is the checklist + the platform's dependency map. See ADR-011.

## What actually lives on the NAS (must survive the move)

`/mnt/f3/aero` (exported over NFS, mounted `/mnt/aero-nfs` on the host →
bind-mounted `/mnt/aero` in the aero LXCs) holds:

- `containers/` — all Apptainer SIFs (openfoam, su2, pyfr, nekrs, jax-fluids,
  surrogate-smoke, and Stage-09's physicsnemo.sif). Verify against
  `containers/SHA256SUMS`.
- `datasets/` — DVC-materialized reference data + dataset working copies.
- `runs/` — every `aero run` CFD case history.
- **`.keyring-escrow/` — the encrypted Apptainer container-signing keyring**
  (`SECURITY.md` §6). **CROWN JEWEL** — root-owned, permission-sensitive. ZFS
  replication preserves its perms/xattrs; plain rsync can mangle them. ADR-012's
  Vault key migration depends on this surviving.

## What is NOT on the NAS (don't expect the move to carry it)

- The **DVC content store** (`dvc push` target) = MinIO bucket `aero-dvc` on
  aero-mlflow LXC 212's local 50 GB disk — **not** the NAS.
- **MLflow** tracking (`192.168.2.234:5000`) + artifacts (MinIO on LXC 212) +
  Postgres (LXC 202). Backed up by nightly `vzdump` of the LXCs, separately.
- **Vault** secrets (aero-vault LXC 217).

So migrating the NAS does **not** move your experiment-tracking/provenance store.
(The new NAS *can* later host a large DVC remote via TrueNAS-SCALE's native S3 app
— ADR-011's `aero-nas` profile — which is the point of buying CFD-scale storage.)

## "1-to-1" = logical config parity, NOT vdev parity

Replicate pool name `f3`, dataset `aero`, the NFS export path `/mnt/f3/aero`, the
export **options** (NFSv4; maproot/mapall to root for `192.168.2.0/24`), and
users/shares. Do **not** replicate the VM's single qcow2 vdev — the dedicated box
should use real redundancy (mirror / RAIDZ). Use the TrueNAS **Save Config**
(System → General) → restore on the **same SCALE version** to carry users/shares/
NFS-exports config; replicate the data with `zfs send | zfs recv`.

## Procedure

### 0. Pre-flight
- [ ] New NAS racked; pool `f3` created (real redundancy); dataset `aero` created.
- [ ] New box on a **temp IP** (e.g. `192.168.2.101`); SSH reachable.
- [ ] TrueNAS **Save Config** downloaded from the VM; restore on the new box (same
      SCALE version) → users/shares/NFS-export config land.
- [ ] No RunPod/`aero` job mid-`dvc pull` or mid-run during the cutover window.

### 1. Replicate the data (VM still serving)
```bash
# On the TrueNAS VM (192.168.2.100):
zfs snapshot -r f3/aero@migrate-$(date +%Y%m%d)
# Full send to the temp-IP box (recursive — carries .keyring-escrow, perms, xattrs):
zfs send -R f3/aero@migrate-YYYYMMDD | ssh root@192.168.2.101 zfs recv -F f3/aero
```
- [ ] Keep the VM serving; do a final **incremental** delta at cutover to minimize
      downtime:
```bash
zfs snapshot -r f3/aero@migrate-final
zfs send -RI f3/aero@migrate-YYYYMMDD f3/aero@migrate-final \
  | ssh root@192.168.2.101 zfs recv f3/aero
```

### 2. Verify on the new box (temp IP)
- [ ] `zfs list -r f3/aero` matches expected datasets.
- [ ] `.keyring-escrow/` present and root-owned: `ls -la /mnt/f3/aero/.keyring-escrow`.
- [ ] SIF digests match the manifest:
```bash
cd /mnt/f3/aero/containers && sha256sum -c <(grep -vE '^#' /path/to/repo/containers/SHA256SUMS)
```
- [ ] NFS export options on the new box equal the VM's (NFSv4, maproot/mapall to
      root, allowed-hosts `192.168.2.0/24`). **A root-squash mismatch breaks the
      LXC apptainer-as-root reads + the signing-key escrow** — check carefully.

### 3. Cut over (the only brief downtime)
- [ ] Power **off** the TrueNAS VM (frees `192.168.2.100`).
- [ ] **Re-IP the new box to `192.168.2.100`.** Bring NFS up; bring the
      TrueNAS-SCALE S3 app up (for the future `aero-nas` DVC remote).
- [ ] On the Proxmox host: the `/etc/fstab` NFS line + Proxmox `mp` bind mounts
      (`pct set <id> -mp0 /mnt/aero-nfs,mp=/mnt/aero`) are **unchanged** (same IP);
      just remount: `umount /mnt/aero-nfs; mount -a`.
- [ ] Re-mount on every aero LXC (or `pct reboot`); confirm `/mnt/aero` populated.

### 4. Re-verify end-to-end
- [ ] `for h in aero-build aero-dev aero-mlflow aero-vv; do ssh root@$h 'ls /mnt/aero/containers | wc -l'; done`
- [ ] Re-run the SIF digest check on a couple of SIFs.
- [ ] `ssh root@aero-build "${REPO}/scripts/_apptainer_sign.sh /mnt/aero/containers/physicsnemo.sif"`
      still finds the escrowed key (ADR-012).
- [ ] An `aero run naca0012 --executor local-ssh` writes to `/mnt/aero/runs/` and
      logs to MLflow.

## Repo / host references to the NAS IP — what changes (almost nothing)

Because the IP is **preserved**, no repo or host file's NAS IP changes:

| Location | Reference | Changes on this migration? |
|---|---|---|
| host `/etc/fstab` | `192.168.2.100:/mnt/f3/aero` | **No** (same IP) — just remount |
| Proxmox `mp` bind mounts | `/mnt/aero-nfs → /mnt/aero` | **No** |
| `ansible/inventory.yml` | `truenas: ansible_host: 192.168.2.100` | **No** (verify it's still `.100`) |
| `.claude/hooks/block-dangerous-bash.sh` | blocks SSH to `192.168.2.100` | **No** |
| `conf/storage/nas.yaml` | `http://192.168.2.100:9000` (future S3) | **No** — already points at `.100` |

If you ever choose a **different** IP instead, update those five locations + the
host fstab + Proxmox mounts.

## Risk notes

- The **temp-IP window** is the only period NFS is on a non-canonical IP — keep it
  short (incremental send) and quiesce `aero` jobs first.
- `.keyring-escrow/` perms: ZFS `send -R` only (never rsync) so the root-owned
  encrypted keyring + its xattrs survive.
- Confirm the TrueNAS-SCALE S3 app is DVC-remote compatible (MinIO-S3; untested
  here) before relying on the `aero-nas` profile (ADR-011).
