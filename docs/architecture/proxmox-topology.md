# Proxmox Topology — aero stack

How the aero platform sits on the Proxmox host `Homelab1`. Established in
Stage 02. The pre-existing inventory is
`docs/architecture/proxmox-inventory-2026-05-16.md`; the design rationale is
`docs/adrs/ADR-002-proxmox-topology.md`.

## The aero LXC fleet

Seven new unprivileged Ubuntu 24.04 LXCs, IDs 210-216, rootfs on the
`Storage` pool, `nesting=1`, `onboot=1`. Dual-NIC (see Networking below).

| LXC | ID | Cores | RAM | Disk | LAN IP | Private IP | Role | First used |
|---|---|---:|---:|---:|---|---|---|---|
| aero-build | 210 | 8 | 16G | 200G | 192.168.2.232 | 10.10.10.20 | Apptainer SIF builds, CI runner site | Stage 02 |
| aero-dev | 211 | 16 | 32G | 300G | 192.168.2.233 | 10.10.10.21 | Dev, JupyterLab, ParaView, mesh prep | Stage 02 |
| aero-mlflow | 212 | 4 | 8G | 50G | 192.168.2.234 | 10.10.10.22 | MLflow tracking + MinIO sidecar | Stage 04 |
| aero-vv | 213 | 16 | 32G | 200G | 192.168.2.235 | 10.10.10.23 | V&V CPU CFD runner | Stage 05 |
| aero-prefect | 214 | 4 | 8G | 30G | 192.168.2.236 | 10.10.10.24 | Aero-scoped Prefect 3 server | Stage 13 |
| aero-agent | 215 | 8 | 16G | 100G | 192.168.2.237 | 10.10.10.25 | NeMo Agent Toolkit runtime | Stage 14 |
| aero-lit | 216 | 4 | 8G | 100G | 192.168.2.238 | 10.10.10.26 | Literature ingestion pipeline | Stage 15 |

Stage 02 fully configures **aero-build, aero-dev, aero-mlflow, aero-vv**
(base + apptainer and/or NFS client); **aero-prefect, aero-agent, aero-lit**
are base-only stubs until their stage.

## Reused shared services (additive, non-aero infrastructure)

These pre-existing guests are application-agnostic; the aero stack uses them
additively and modifies no existing state (Hard Rule 11).

| Guest | Existing purpose | Aero integration | First used |
|---|---|---|---|
| LXC 202 `postgres-server` | shared Postgres | new `aero_provenance` DB + `pgvector` | Stage 04 |
| LXC 203 `redis-server` | shared Redis | agent cache | Stage 14 |
| LXC 204 `tempo-server` | Grafana Tempo | agent OpenTelemetry traces | Stage 14 |
| LXC 205 `grafana-server` | dashboards | new aero V&V dashboards + node-exporter scrape | Stage 05 |
| VM 104 `TrueNAS` | shared storage | new NFS dataset `aero/` (dvc-remote, mlflow-artifacts, datasets, containers) | Stage 02 |

LXC 201 `prefect-server` is **not** reused — `aero-prefect` (214) is fresh.
LXC 207 `aero-research` is pre-existing and **left untouched**.

## Networking (dual-NIC)

```
                          Proxmox host Homelab1 (192.168.2.13)
                                       |
                              vmbr0 (LAN bridge)
        ___________________________/  |  \___________________________
       /                              |                              \
  192.168.2.0/24 (LAN)         10.10.10.0/24 (NAT, no gw)      shared services
       |                              |                              |
  aero-* eth0  <-- mgmt/egress    aero-* eth1  <-- data plane    Postgres 202
  .232 .. .238   SSH, Ansible,    .20 .. .26     NFS, inter-     Grafana  205
                 apt, GitHub                     aero traffic   Tempo    204
                                                                Redis    203
   aero-build  aero-dev  aero-mlflow  aero-vv                    TrueNAS  VM104
   aero-prefect  aero-agent  aero-lit                              |
                     |                                       NFS: aero/
                     |____________ /mnt/aero (NFS) ________________|
                                   on build, dev, vv, mlflow
```

Each aero LXC has two NICs on `vmbr0`: `eth0` on the LAN
(`192.168.2.232-238`, gw `192.168.2.1`) for internet egress, SSH, and
Ansible; `eth1` on the private `10.10.10.0/24` segment (`.20-.26`, no
gateway) for the aero data plane. The `10.10.10.0/24` segment has no
host-side gateway, so management traffic uses the LAN NIC. See ADR-002.

## Resource accounting

Stage 02 adds 120 GB of RAM *ceilings* (8+32+8+32+8+16+8) and ~980 GB of
`Storage` disk across the seven LXCs. Combined with the ~509 GB of ceilings
on pre-existing running guests, the host is at ~629 GB of allocated RAM
ceilings against 92 GiB physical. Ceilings are not reservations — idle LXCs
consume near-zero; oversubscription on idle workloads is the operator's
accepted posture (ADR-002). `Storage` has ~2.1 TB free; the aero footprint
fits with ~1.1 TB to spare.

## Backups

Interim `vzdump` job, aero LXCs only, nightly 03:00 — see
`docs/architecture/backup-interim.md`. The TrueNAS `aero/` dataset is
covered by a nightly TrueNAS snapshot task.
