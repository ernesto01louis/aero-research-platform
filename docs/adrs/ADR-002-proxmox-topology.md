# ADR-002 — Proxmox Topology & Container Build Pipeline

- **Status:** accepted
- **Date:** 2026-05-17
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 02)
- **Stage:** 02
- **Supersedes:** —

## Context and problem statement

Stage 02 places the aero platform's physical substrate on the existing
Proxmox host `Homelab1` — seven `aero-*` LXC containers, a TrueNAS NFS
dataset, and an Apptainer SIF build pipeline — without disturbing the 20+
pre-existing non-aero guests (CLAUDE.md Hard Rule 11). Several decisions are
load-bearing and recorded here:

1. **New `aero-*` LXCs vs reuse** of the pre-existing LXC 207 `aero-research`.
2. **A fresh `aero-prefect`** vs reuse of LXC 201 `prefect-server`.
3. **Reuse of the shared services** (Postgres 202, Grafana 205, Tempo 204,
   Redis 203, TrueNAS 104).
4. **GPU passthrough** — whether to configure any.
5. **Networking** — how the aero LXCs attach to the network.
6. **LXC resource allocation** and the host's existing memory overcommit.
7. **Provisioning mechanism** — Ansible Proxmox module vs raw `pct`.
8. **Interim backup policy** for the aero stack.
9. **Apptainer signing-key storage.**

Constraints: the inventory (`docs/architecture/proxmox-inventory-2026-05-16.md`)
is the source of truth; no discrete GPU exists; the host runs ~509 GB of
allocated guest RAM on 92 GiB physical; `Storage` has 2.1 TB free; no host
network or `/etc/pve/` change without operator approval (Hard Rule 5).

## Decision drivers

- **Non-disturbance.** 20+ live non-aero workloads must be untouched.
- **Reproducibility.** Topology must be scriptable and re-runnable.
- **Clean separation.** The aero plane should not entangle with unrelated
  Prefect / exploratory workloads.
- **No discrete GPU.** GPU work is cloud-rented from Stage 13 on.
- **Reality of the internal subnet.** `10.10.10.0/24` is a NAT segment on
  `vmbr0` with **no host-side gateway** — a 10.10.10-only NIC cannot reach
  the internet (no apt/uv/GitHub), which would break provisioning.
- **Generous-ceiling operator preference.** Oversubscription on idle
  workloads is explicitly accepted.

## Considered options

### Reuse vs fresh LXCs

1. **Reuse LXC 207 `aero-research`** as the platform home.
2. **Provision fresh `aero-*` LXCs** (210-216), leave 207 untouched.

### Orchestration LXC

1. **Reuse LXC 201 `prefect-server`** for aero orchestration.
2. **Fresh `aero-prefect`** (214), decoupled.

### Networking

1. **10.10.10-only NIC** — matches the brief literally; needs a host-side
   `10.10.10.1` gateway added to `vmbr0` (`/etc/network/interfaces` change).
2. **Flat LAN only** — single `192.168.2.x` NIC like LXC 207.
3. **Dual-NIC** — a LAN NIC (`192.168.2.232-238`) for egress/SSH/Ansible
   plus a private NIC (`10.10.10.20-26`) for the aero data plane.

### Provisioning mechanism

1. **`community.general.proxmox`** Ansible module (needs `proxmoxer` + an
   API token).
2. **Raw `pct`** wrapped in an idempotent script, run on the host.

### Apptainer signing key

1. **aero-build only** — passphrase-protected keyring on aero-build.
2. **aero-build + TrueNAS escrow** — plus an encrypted backup copy on NFS.
3. **Vault-managed** escrow.

## Decision outcome

1. **Fresh `aero-*` LXCs 210-216.** LXC 207 `aero-research` is pre-existing,
   pre-staged for NVIDIA passthrough, and Hard Rule 11 says leave it alone.
   The platform needs seven role-separated containers, not one.

2. **Fresh `aero-prefect` (214).** LXC 201 is a non-aero workflow server;
   reusing it would couple aero's orchestration to a box outside aero's
   change control. (LXC 201 appears in the Ansible inventory only as a
   read-only reference — never reused or reconfigured.)

3. **Reuse Postgres 202 / Grafana 205 / Tempo 204 / Redis 203 / TrueNAS 104.**
   These are application-agnostic infrastructure explicitly sanctioned for
   additive sharing (Hard Rule 11). The aero stack adds new DBs, dashboards,
   traces, and an NFS dataset; it modifies no existing state. Standing up
   duplicates would waste the constrained RAM budget.

4. **No GPU passthrough.** No discrete GPU exists; the iGPU is already shared
   by four non-aero LXCs. No `vfio` / `modprobe` / kernel-cmdline changes.
   GPU work is cloud-rented (Stage 13).

5. **Dual-NIC networking** (Option 3). `eth0` on `vmbr0` with a static LAN
   address (`192.168.2.232-238`, gw `192.168.2.1`) carries internet egress,
   SSH, and Ansible; `eth1` on `vmbr0` with a static `10.10.10.20-26`
   address (no gateway) is the private aero data plane, mirroring LXC 200's
   `net1`. This satisfies the brief's intent (a private aero segment) and
   reality (the 10.10.10 segment has no host gateway, so a 10.10.10-only NIC
   cannot reach the internet). It adds **guest NICs only** — no bridge, no
   `/etc/network/interfaces` edit, no host network change.
   The planned LAN block `192.168.2.220-226` was abandoned at execution —
   `.222/.224/.226` held live DHCP leases; `.232-.238` is a clean static
   block above LXC 207 (`.231`).

6. **LXC resource ceilings per the project brief** (build 8c/16G/200G, dev
   16c/32G/300G, mlflow 4c/8G/50G, vv 16c/32G/200G, prefect 4c/8G/30G, agent
   8c/16G/100G, lit 4c/8G/100G — all unprivileged, `nesting=1`, rootfs on
   `Storage`). This adds 120 GB of RAM *ceilings* to a host already at
   ~509 GB allocated on 92 GiB physical. Ceilings are not reservations; idle
   LXCs consume near-zero, and oversubscription on idle workloads is the
   operator's stated preference. ~980 GB of `Storage` is consumed (2.1 TB
   free).

7. **Raw `pct` provisioning** via `scripts/provision_aero_lxc.sh` (Option 2).
   We run as root directly on the Proxmox host — `pct` is the native,
   zero-credential path. The Ansible module would add a `proxmoxer`
   dependency and an API token to mint and store. Ansible is the
   configuration-management layer (over SSH, after the containers exist);
   `pct` is the provisioning layer.

8. **Interim `vzdump` backup**, aero-only. A single job enumerating exactly
   IDs 210-216 (never `--all`, never a pool), daily 03:00, target `Storage`,
   mode snapshot, `zstd`, keep-last 7. This is an interim hedge until the
   operator's dedicated backup NAS lands; it touches no non-aero workload's
   backup configuration. See `docs/architecture/backup-interim.md`.

9. **Apptainer signing key: aero-build + TrueNAS escrow** (Option 2). The
   passphrase-protected keyring lives on aero-build (where SIFs are signed);
   an encrypted copy is escrowed to the TrueNAS `aero/` NFS dataset so the
   key survives loss of the aero-build LXC and aero-dev can also sign. The
   public fingerprint is committed (`containers/SIGNING_KEY_FINGERPRINT.txt`);
   the private key is never committed. Vault-managed escrow is deferred to
   Stage 04+.

### Pinned versions

| Component | Pin | Source |
|---|---|---|
| LXC OS template | `ubuntu-24.04-standard_24.04-2` | Proxmox `pveam` |
| `ubuntu:24.04` base image | `sha256:c4a8d5503dfb…41c7b` | Docker Hub index |
| Apptainer | `1.5.0` (`.deb` sha256 `fbc27204…81ea`) | Apptainer GitHub release |
| ansible-core | `2.20.5` | PyPI (via `uv tool`) |
| community.general | `12.6.1` | Ansible Galaxy |
| ansible.posix | `2.1.0` | Ansible Galaxy |

### Consequences

- **Positive:** clean separation from non-aero workloads; reproducible,
  scriptable topology; the aero stack now has backups (it did not before);
  a single SHA256-pinned container root; no API credential surface for
  provisioning.
- **Negative:** dual-NIC means a second interface to manage per LXC; the
  `10.10.10.0/24` data plane remains L2-only (no gateway) — acceptable, as
  NFS and inter-aero traffic do not need routing; the signing key is
  single-homed on aero-build until Vault escrow (mitigated by the encrypted
  TrueNAS copy and the nightly `vzdump`).
- **Neutral / followup work:** unprivileged-LXC + Apptainer `--fakeroot`
  for non-root users needs an expanded LXC idmap (a host-side change),
  deferred — Stage 02 builds SIFs as the container root; Vault-managed key
  escrow lands Stage 04+; the host-wide backup gap (no non-aero backups
  exist) remains the operator's call and is out of Stage 02 scope.

## Pros and cons of considered options

### Reuse LXC 207

- Good: one fewer container to provision.
- Bad: violates Hard Rule 11; one container cannot host seven roles; risks
  contaminating prior exploratory state.

### Fresh `aero-*` LXCs (chosen)

- Good: clean separation, role isolation, reproducible, 207 untouched.
- Bad: more containers; more RAM ceiling pressure (accepted).

### Reuse LXC 201 for orchestration

- Good: no new container.
- Bad: couples aero orchestration to an unrelated workload outside aero's
  change control.

### Fresh `aero-prefect` (chosen)

- Good: decoupled orchestration plane; aero owns its lifecycle.
- Bad: one more idle stub until Stage 13.

### Networking — 10.10.10-only

- Good: matches the brief's wording exactly.
- Bad: requires a host-side gateway on `vmbr0` (`/etc/network/interfaces`
  change, needs approval); 10.10.10-only LXCs cannot reach the internet.

### Networking — flat LAN only

- Good: simplest; no second NIC.
- Bad: drops the private aero data-plane segment the brief specifies.

### Networking — dual-NIC (chosen)

- Good: internet + private segment, no host network change, satisfies brief
  intent and reality.
- Bad: a second NIC per LXC to track.

### Provisioning — Ansible Proxmox module

- Good: one tool for everything.
- Bad: needs `proxmoxer` and an API token (a credential to mint and store)
  for something doable natively as root on the host.

### Provisioning — raw `pct` script (chosen)

- Good: native, zero-credential, idempotent, reviewable in-repo.
- Bad: two layers (host `pct` + Ansible-over-SSH) instead of one.

### Signing key — aero-build only

- Good: simplest.
- Bad: key lost if aero-build is lost; aero-dev cannot sign.

### Signing key — aero-build + TrueNAS escrow (chosen)

- Good: survives aero-build loss; aero-dev can sign; still no secret in git.
- Bad: an encrypted copy to manage on NFS.

### Signing key — Vault-managed

- Good: the long-term correct answer.
- Bad: no Vault until Stage 04+; premature for Stage 02.

## Links

- Stage prompt: `STAGE-02-proxmox-and-container-pipeline.md` (operator bundle)
- Project brief: `00-CONTEXT-project-brief.md`
- Inventory: `docs/architecture/proxmox-inventory-2026-05-16.md`
- Topology: `docs/architecture/proxmox-topology.md`
- Backup: `docs/architecture/backup-interim.md`
- Related ADR: ADR-001 (governance)
- Related handoff: `docs/handoffs/STAGE-02-proxmox-and-container-pipeline-DONE-2026-05-17.md`
- Apptainer: <https://apptainer.org/docs/>
