# Proxmox Inventory — Homelab1 — 2026-05-16

## 1. One-line summary

Single-node **Proxmox VE 9.1.11** (Debian 13 trixie, kernel 7.0.2-2-pve) on **AMD Ryzen 9 9955HX (16C/32T)**, **92 GiB RAM**, **~3.9 TB NVMe** on a dedicated 4 TB disk + 237 GB NVMe boot, **AMD integrated GPU** (Radeon Granite Ridge) shared with several LXCs, **no discrete GPU**, **18 LXCs (17 running) + 4 VMs (2 running)** including an existing `aero-research` LXC already scaffolded for future NVIDIA passthrough, **Ceph monitor running but zero OSDs (HEALTH_WARN)**, **no scheduled backups**, Tailscale + self-hosted headscale + CrowdSec on the host, 22 pending apt updates.

## 2. Hardware

### CPU
- **Model**: AMD Ryzen 9 9955HX (Zen 5, "Granite Ridge"), family 26h
- **Topology**: 1 socket, 16 cores, 32 threads, **1 NUMA node** (NUMA node0 = CPU 0–31)
- **Frequency**: 1.22–5.06 GHz, boost enabled
- **Microcode**: amd64-microcode 3.20251202.1
- All standard vulnerability mitigations applied (IBPB on VMEXIT, Spec store bypass, etc.)
- AMD-V virtualization enabled

### Memory
- **Total**: 92 GiB (96,458 MB)
- **In use**: 23 GiB; **available**: 68 GiB; **buff/cache**: 57 GiB
- **Swap**: 8 GiB total, **5.4 GiB used (68%)** — non-trivial
- Zswap not in use

### Storage
| Mount | Device | Size | Used | Free | Type | Notes |
|---|---|---|---|---|---|---|
| `/` | `/dev/mapper/pve-root` | 68 G | 17 G | 48 G (26%) | ext4 (LVM) | Boot/OS |
| `/boot/efi` | `nvme0n1p2` | 1 G | 9 M | 1014 M | vfat | ESP |
| `/mnt/pve/Storage` | `nvme1n1p1` (CT4000P310SSD8, **4 TB**) | 3.6 T | 1.4 T | **2.1 T (39%)** | ext4 dir-storage | Primary VM/LXC storage |
| `local-lvm` (thinpool `pve/data`) | LV in `pve` VG | 140.9 G | 56.2 G (39.9%) | ~85 G | LVM-thin | Several LXC rootfs disks |
| VG `pve` free extents | — | 16 G | — | 16 G | LVM | Unallocated capacity |

- **Single boot NVMe** (`nvme0n1`, AVOETY AP2000 240 GB), **single data NVMe** (`nvme1n1`, Crucial P310 4 TB) — **no RAID anywhere**
- `sdb` is a 29 GB flash drive with vfat+LUKS partitions (likely Proxmox installer or rescue stick — not mounted)
- **No ZFS pools** despite `zfsutils-linux` being installed (vm-104 has `zfs_member` filesystem signature on its disk, which is TrueNAS' internal pool inside the VM)

### GPU / accelerators
- **iGPU only**: AMD Radeon Graphics (Granite Ridge, PCI `1002:13c0`) — Ryzen on-die graphics, audio + USB controllers
- **No discrete GPU** present
- `amdgpu` module loaded on the host
- `/dev/dri/renderD128` and `/dev/dri/card1` are **bind-mounted into LXCs 101, 105, 107, 109** (docker, ollama, openwebui, ollama-judge) — they share the iGPU
- No `vfio` / `nouveau` / `nvidia` modules loaded
- IOMMU device exposed by AMD: present on PCI bus; not currently used for passthrough
- No NVIDIA driver — clean state for future passthrough

### Network
- Bridges: `vmbr0` (UP, **192.168.2.13/24**, gw 192.168.2.1, bridge-port `nic1`)
- Physical NICs visible: `nic0`, `nic1` (active), `nic2`, `nic3`, `nic4`, `wlp6s0` (all others DOWN)
- **Tailscale**: `tailscale0` UP at `100.81.111.126/32` (+ v6 `fd7a:115c:a1e0::3835:6f7e`)
- An IPv4 NAT chain (`POSTROUTING -s 10.10.10.0/24`) and forwarding are enabled at post-up time — used by LXC 200 (`ai-orchestrator`) which has a second NIC at `10.10.10.10/24`
- Many `veth*` and a few `fwbr*/fwpr*/fwln*` (per-LXC firewall bridges for 104, 108, 200)

## 3. Proxmox configuration

- **Version**: `proxmox-ve 9.1.0`, `pve-manager 9.1.11`, running kernel **7.0.2-2-pve** (signed)
  - Older kernels still on disk: 6.17.13-7, 6.17.13-2, 6.17.4-2, 6.17.2-2
- **Single node** — `pvecm status` returns "not part of a cluster"
- **Ceph daemons running** but cluster non-functional: 1 mon (Homelab1), 1 mgr (active), **0 OSDs**, 0 pools, `HEALTH_WARN: OSD count 0 < osd_pool_default_size 3`. Ceph squid no-subscription repo enabled.
- **Repositories**:
  - Debian trixie main/contrib/non-free-firmware + trixie-updates + trixie-security
  - Proxmox VE no-subscription (`pve-no-subscription`)
  - **Proxmox enterprise repo present but disabled**
  - `pve-test` present but disabled
  - Ceph squid no-subscription
  - Tailscale (trixie) stable
  - CrowdSec packagecloud
- **22 packages pending** upgrade
- pveproxy bound to `192.168.2.13:8006` (LAN-only on host IP) plus Tailscale-served on `100.81.111.126:8006`. Matches saved memory (`/etc/default/pveproxy LISTEN_IP=192.168.2.13`).
- **Container tooling on the host**: none. `apptainer`, `singularity`, `docker`, `podman` all absent. Docker runs **inside** LXC 101 and VM 100.
- Other host services listening: SSH (22), Postfix (25 local), CrowdSec (8080/6060 local), rpcbind (111), spiceproxy (3128), a `node` process on 8680 (likely homepage/dashboard), Tailscale `tailscaled` exposing serve endpoints on 5252/8006/8680/46790, a VS Code remote/tunnel agent (`code-...`, 33131 local).

## 4. Existing workloads

### LXC containers
| ID | Status | Name | Cores | RAM (MB) | Disk | Storage | Tags / notes |
|---:|:--:|:--|---:|---:|:--|:--|:--|
| 101 | running | `docker` | 4 | 16000 | 128 G | Storage | iGPU bind, Docker host inside LXC |
| 102 | running | `technitiumdns` | 4 | 64000 | 4 G | Storage | DNS server |
| 103 | running | `headscale` | 1 | 512 | 2 G | Storage | Self-hosted Tailscale coordinator |
| 105 | running | `ollama` | 32 | 93000 | 500 G | Storage | iGPU bind, swap 90 G |
| 106 | running | `searxng` | 16 | 32000 | 7 G | Storage | Privacy search |
| 107 | running | `openwebui` | 24 | 64000 | 50 G | Storage | iGPU bind |
| 108 | running | `Minecraft` | 8 | 16384 | 64 G | Storage | Game server |
| 109 | running | `ollama-judge` | 32 | 90000 | 500 G | Storage | iGPU bind, swap 512 |
| 110 | **stopped** | `Claude` | 32 | 90000 | **1000 G** | Storage | Large idle container |
| 113 | running | `opensnitch` | 2 | 1024 | 4 G | local-lvm | App firewall |
| 114 | running | `openclaw` | 2 | 2048 | 8 G | local-lvm | — |
| 200 | running | `ai-orchestrator` | 6 | 40000 | 240 G | Storage | Dual-NIC (LAN + 10.10.10.0/24), tailscale tag |
| 201 | running | `prefect-server` | 2 | 2048 | 8 G | Storage | Workflow orchestration |
| 202 | running | `postgres-server` | 1 | 2048 | 20 G | local-lvm | DB |
| 203 | running | `redis-server` | 1 | 2048 | 10 G | local-lvm | Cache |
| 204 | running | `tempo-server` | 1 | 2048 | 10 G | local-lvm | Tracing (Grafana Tempo) |
| 205 | running | `grafana-server` | 1 | 2048 | 8 G | local-lvm | Dashboards |
| 206 | running | `firecrawl-server` | 4 | 8192 | 30 G | local-lvm | Web crawl service |
| 207 | running | `aero-research` | 16 | 32768 | 200 G | Storage | **Already scaffolded for NVIDIA dGPU passthrough (commented-out lxc.cgroup2/lxc.mount lines in description)** |

### VMs
| VMID | Status | Name | Cores | RAM (MB) | Disks | Storage | Notes |
|---:|:--:|:--|---:|---:|:--|:--|:--|
| 100 | running | `docker` | 2 | 4096 | 10 G + 4 M EFI | Storage | OVMF, qemu-guest-agent on |
| 104 | running | `TrueNAS` | 4 | 16000 | 32 G + **1000 G** | local-lvm + Storage | USB passthrough `3-2.3`; the 32 G disk has a ZFS pool signature (TrueNAS internal) |
| 111 | **stopped** | `windows11` | 24 | 32000 | 500 G + virtio-win ISO + Win11 25H2 ISO | Storage | OVMF, TPM v2, `cpu: host` |
| 112 | **stopped** | `tails-usb` | 2 | 8192 | EFI only, USB-boot | local-lvm | Tails-on-USB live VM |

**Resource accounting (running workloads only, allocated not actual):**
- vCPU sum: ~163 (heavy oversubscription vs. 32 threads — normal for LXC)
- RAM allocation sum: **~509 GB allocated** vs. 92 GiB physical → very high logical commit; the 5.4 GiB of swap-in-use and only 23 GiB resident suggest most allocations are loose ceilings, not steady-state, but **headroom under burst is the open question**
- Provisioned LXC rootfs (incl. stopped 110): ~3.0 TB on Storage, ~90 GB on local-lvm

## 5. Risks identified

- **HIGH — No backup jobs**: `/etc/pve/jobs.cfg` is absent; `/var/lib/vz/dump/` is empty. Mitigation: configure a `vzdump` schedule to `Storage` or an offsite target (PBS/restic/rclone), starting with the stateful LXCs (200, 202, 203, 205, 207) and TrueNAS VM 104.
- **HIGH — Memory pressure / heavy commit**: 5.4 GiB swap in use with 23 GiB resident on a 92 GiB box looks fine right now, but allocated RAM across running guests is ~509 GB (5.5× physical) and three giant LXCs (105, 107, 109) each list 64–93 GB. A single burst can OOM the host. Mitigation: lower memory ceilings where you can, or enable ballooning patterns, or accept and monitor (Grafana 205 already on-box).
- **HIGH — Single boot disk, single data disk, no RAID**: `nvme0n1` failure loses Proxmox + every local-lvm guest; `nvme1n1` failure loses every Storage-pool guest (most of the workloads). Mitigation: add a mirror drive and convert to ZFS/mdraid, or at minimum ensure off-host backups exist.
- **MEDIUM — Half-deployed Ceph**: monitor + manager are running but 0 OSDs, 0 pools, `HEALTH_WARN`. Burns RAM and CPU for nothing. Mitigation: either add OSDs to make Ceph real, or stop/uninstall `ceph-mon` and `ceph-mgr`.
- **MEDIUM — 22 pending apt updates** including likely security packages. Mitigation: review and apply during a planned window.
- **MEDIUM — Three reboots in ~1.5 h on Wed May 13** (system was on 6.17.13-2 kernel; current kernel is 7.0.2-2 with 3-day uptime). Investigate whether the May 13 instability is now resolved or carry-over of a kernel issue.
- **MEDIUM — LXC 110 `Claude` is stopped with a 1 TB rootfs** still allocated. Either reclaim the space or document its purpose.
- **LOW — No discrete GPU for CFD**: integrated iGPU is fine for light inference (already powering Ollama LXCs) but is the limiting factor for any real solver acceleration; LXC 207 already anticipates an NVIDIA dGPU.
- **LOW — Mixed pveproxy listeners**: pveproxy is bound to `192.168.2.13:8006` AND `100.81.111.126:8006` (Tailscale serve). Per saved memory this is intentional (`LISTEN_IP` set so `tailscale serve` can take 8006 elsewhere). Worth confirming the intent is still current.

## 6. Capacity for the aero platform

- **Free CPU cores**: 32 physical threads, oversubscribed at the allocation layer (163 vCPU committed) but actual utilization is modest — there is real headroom; safe target is **8–16 cores** for a new aero LXC/VM, or **claim the 16 already assigned to LXC 207 (`aero-research`)** which is the placeholder.
- **Free RAM (real)**: ~68 GiB `MemAvailable`, with the caveat that current commits already exceed physical. Safe carve-out: **16–32 GiB** for a new guest, subject to reining in 105/107/109 ceilings if needed.
- **Free disk**:
  - `Storage` (`/mnt/pve/Storage`, ext4 on 4 TB NVMe): **~2.1 TB free** — recommended target for all aero datasets, container images, and large LXC rootfs.
  - `local-lvm` thinpool: ~85 GB free (plus 16 GB unallocated VG space) — fine for small system LXCs only.
  - `pve-root`: 48 GB free — leave for OS / logs.
- **Free network**:
  - One LAN bridge (`vmbr0`) on `192.168.2.0/24` — directly usable.
  - One internal NAT bridge (`10.10.10.0/24`, MASQUERADE'd out of `vmbr0`) used by `ai-orchestrator` (LXC 200) — could be extended to the aero stack to keep it private.
  - No VLANs or SDN zones configured.
- **Container tooling**: must be installed inside guests; host has none. Apptainer/Singularity will need to live in the aero LXC/VM (or a new one).
- **GPU**: only the iGPU exists; it is already shared by four LXCs. For CFD/ML solvers, **no usable GPU acceleration** until a discrete card is installed and configured for vfio passthrough.

## 7. Open questions for the user

1. **LXC 207 `aero-research`** already exists with 16 cores / 32 GB / 200 GB and a description that pre-stages NVIDIA passthrough lines. Is this the intended target for the new platform, or will we build a fresh LXC/VM next to it?
2. **LXC 110 `Claude`** is stopped with a 1 TB rootfs and 32 cores / 90 GB allocated. Keep, repurpose, or delete? If kept, do we need to count its RAM ceiling against the budget?
3. **Ollama vs. ollama-judge** (105 / 109) — both 500 GB and ~90 GB RAM ceilings, both sharing the iGPU. Are both still needed, or can one be retired to free RAM and storage for aero workloads?
4. **Ceph** — mon+mgr running with zero OSDs. Are we mid-buildout, paused, or should we tear it down to reclaim resources?
5. **Backups** — deliberately off, or simply not configured yet? Where should backups land (a second pool, PBS, off-site)?
6. **Discrete GPU plans** — the LXC 207 description hints at an NVIDIA dGPU arrival. Do we have a model, timeline, and PCIe slot identified? That changes the Stage-02 plan for kernel cmdline / `vfio-pci` config.
7. **TrueNAS VM 104** owns a 1 TB virtual disk on `Storage`. Is that the long-term home for shared datasets we may want to expose to the aero stack via NFS/SMB, or should aero get its own disk path?
8. **Networking** — should the aero platform live on the flat 192.168.2.0/24, on the existing internal 10.10.10.0/24, or do we want a new SDN/VLAN for isolation?
9. **May 13 reboot cluster** — what triggered the three reboots that day, and is it relevant to the move to kernel `7.0.2-2-pve`?

## 8. Raw output index

All under `~/aero-inspect/raw/`:

- `01-host-basics.txt` — `uname`, `pveversion --verbose`, `/etc/os-release`, `lscpu`, `free -h`, `df -h`, `uptime`, `/proc/cmdline`
- `02-cpu-mem.txt` — `lscpu --extended`, `numactl --hardware` (not installed), first 30 lines of `/proc/meminfo`
- `03-gpu.txt` — `lspci -nn` (GPU/VGA filter), `nvidia-smi` (not installed), `lsmod` GPU/vfio filter, `/etc/modprobe.d/` listing
- `04-storage.txt` — `pvesm status`, `lsblk`, `/etc/fstab`, `zpool` (none), `vgs`, `lvs`, `df -h /var/lib/vz`
- `05-network.txt` — `ip -br addr`, `ip route`, `/etc/network/interfaces`, `/etc/hosts`, `ss -tlnp`
- `06-workloads.txt` — `pct list`, `qm list`, full `pct config <ID>` and `qm config <VMID>` for every guest
- `07-backups.txt` — `/etc/pve/jobs.cfg` (absent), `/var/lib/vz/dump/` (empty), `/etc/pve/storage.cfg`
- `08-container-tooling.txt` — apptainer/singularity/docker/podman availability (all absent on host)
- `09-cluster.txt` — `pvecm status` (single node), `pveceph status` (HEALTH_WARN, 0 OSDs)
- `10-security.txt` — pending update count, all `apt` sources, `last -n 20`
