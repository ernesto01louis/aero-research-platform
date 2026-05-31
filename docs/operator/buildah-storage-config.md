# Buildah storage moved to /mnt/pve/Storage (Stage 08 follow-up)

## What changed

Buildah's container storage was at `/var/lib/containers/storage` on the
Proxmox host's 68 GB root volume. The CUDA + torch + PyG wheels in the
`surrogate-smoke.sif` build push transient storage to ~45 GB, which
deadlocked the build twice (the second time the cleanup itself ran out
of disk space).

Live fix on `Homelab1` (the Proxmox host) in `/etc/containers/storage.conf`:

```toml
[storage]
driver = "overlay"
graphroot = "/mnt/pve/Storage/containers-storage"
runroot = "/run/containers/storage"

[storage.options]
# No mount_program — we're root, so native overlay works
```

`/mnt/pve/Storage` is on the 4 TB NVMe (`/dev/nvme0n1p1`) with ~1.8 TB
free, which is plenty for any future SIF build.

## Why it's not in this repo's CI / Ansible

The Stage 02 Ansible role didn't anticipate the surrogate-smoke SIF's
disk needs. When Stage 09 (DoMINO) ships, its `physicsnemo.sif` will be
even bigger; this fix should land in the Ansible playbook by then.

For now: any Proxmox-host operator setting up a fresh aero-build
environment must apply this `storage.conf` before running any
`scripts/build_*_sif.sh` that pulls torch / jax / large CUDA wheels.

## Recovery procedure when storage fills again

If the disk deadlocks (cleanup fails because disk has 0 free):

```bash
# WARNING: destroys all in-progress builds; their SIFs on aero-build
# are unaffected
rm -rf /var/lib/containers/storage/overlay-{layers,images,containers}
df -h /
buildah images   # should be empty
```

Then re-launch the build that was in progress.
