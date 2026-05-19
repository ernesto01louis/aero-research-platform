---
stage: 02
stage_name: "Stage 02 — Proxmox Topology & Container Build Pipeline"
status: complete
date_started: 2026-05-17
date_completed: 2026-05-19
session_duration_hours: 7.0
claude_code_version: "claude-code-vscode-extension"
model: claude-opus-4-7
git_sha_start: "aca8c600bc504af0734945936086853cd0439fbf"
git_sha_end: "2fc845c8fcb52a5582b2fc6a4e3e57d942521b8e"
stage_tag: v0.0.2
next_stage: 03
next_stage_name: "Stage 03 — OpenFOAM Walking Skeleton"
---

# Stage 02 — Proxmox Topology & Container Build Pipeline — DONE 2026-05-19

> Auto-loaded by the Stage 03 session as "BEFORE YOU START — READ".
> `scripts/verify_stage_02.sh` exits 0 (30/30 checks) — the stage gate is green.

## 1. Deliverables status

| # | Deliverable | Status | Note |
|---|---|---|---|
| 1 | Proxmox inventory committed | ✅ | `docs/architecture/proxmox-inventory-2026-05-16.md` |
| 2 | Seven `aero-*` LXCs provisioned + SSH-reachable | ✅ | IDs 210-216, dual-NIC, unprivileged |
| 3 | Apptainer ≥ pinned on build+dev | ✅ | 1.5.0 |
| 4 | TrueNAS NFS dataset `aero/` + export + snapshot | ✅ | export `/mnt/f3/aero`; snapshot task created by operator |
| 5 | `_base.sif` + `hello-world.sif` built/signed/SHA | ✅ | signed (key `682F6145…`), on `/mnt/aero/containers/` |
| 6 | `scripts/run_long.sh` | ✅ | verified end-to-end |
| 7 | `scripts/verify_stage_02.sh` exits 0 | ✅ | 30/30 |
| 8 | `proxmox-topology.md` | ✅ | |
| 9 | `ssh-conventions.md` | ✅ | |
| 10 | `backup-interim.md` | ✅ | |
| 11 | Interim `vzdump` schedule + first dump | ✅ | job `77c7f864…`; first dump verified |
| 12 | TrueNAS nightly snapshot policy | ✅ | created by operator in the TrueNAS UI |
| 13 | ADR-002 | ✅ | |
| 14 | CLAUDE.md updated | ✅ | SSH + long-job conventions + fleet reminder |
| 15 | `.claude` PreToolUse hardening | ⚠️ | `block-dangerous-bash.sh` hardened + committed; **needs `jq` installed on the host to activate** (see §7); `settings.json` allow/deny additions are an operator follow-up (see §7) |
| 16 | Post-stage handoff | ✅ | this file |
| 17 | Tag `v0.0.2` | ⚠️ | applied after the Stage 02 PR merges |

## 2. Decisions made

- **Dual-NIC networking** (ADR-002). `10.10.10.0/24` has no host-side
  gateway, so every aero LXC has `eth0` (LAN — egress/SSH/Ansible) + `eth1`
  (`10.10.10.2x` — private data plane). Rejected: 10.10.10-only (no egress);
  flat-LAN-only (no private segment).
- **LAN block `192.168.2.232-238`** — the planned `.220-.226` overlapped
  live DHCP leases (`.222/.224/.226`).
- **Raw `pct` provisioning** (`scripts/provision_aero_lxc.sh`), not the
  Ansible Proxmox module — root on the host, zero API-credential surface.
- **Stage 02 Ansible runs as `root`**; `aero-base` creates `aero-admin`
  (scoped sudo), the Stage 03+ automation identity.
- **NFS via host-mount + bind-mount, not in-container mount** — NFS cannot
  be mounted inside an unprivileged LXC (kernel: NFS lacks `FS_USERNS_MOUNT`;
  `features: mount=nfs` does not override it). The host mounts
  `192.168.2.100:/mnt/f3/aero` at `/mnt/aero-nfs`; each consuming LXC gets a
  Proxmox `mp` bind mount of it at `/mnt/aero`. The `aero-nfs-client` role
  was reworked to only wire `/opt/aero/*` symlinks.
- **`_base.def` is network-free** — the Apptainer build sandbox in the
  unprivileged LXC cannot open sockets, so `%post` does no apt. The base is
  pinned Ubuntu 24.04 (digest `c4a8d550…`).
- **vzdump uses `suspend` mode** — the `Storage` dir pool has no LXC
  snapshot support.
- **Signing key: aero-build keyring + encrypted TrueNAS escrow** (ADR-002).
- **`block-dangerous-bash.sh` uses `python3`, not `jq`** — the committed
  hook still calls `jq`; see §6/§7 (jq is absent on the host).

## 3. Deviations from the stage plan

- **LAN IPs** `.220-.226` → `.232-.238` (DHCP collision).
- **NFS architecture** — host-mount + Proxmox `mp` bind, not the planned
  in-container `ansible.posix.mount` (kernel restriction). `aero-nfs-client`
  role reworked accordingly; `aero-apptainer` subuid/subgid entries are
  vestigial for non-root fakeroot (see §6).
- **`_base.def`** — no `%post` apt (build-sandbox socket restriction).
- **Host `fuse` module + `/dev/fuse`** — required for SIF execution; loaded
  by the operator (the plan said "no modprobe changes" — a scoped exception,
  operator-applied).
- **`ansible.cfg`** — `stdout_callback` fixed (`yaml` callback removed in
  community.general 12).
- **`containers/SHA256SUMS`** is a real committed file (not a repo symlink
  into NFS) — correct for a provenance-mandated, CI-checked-out repo.
- **`ansible/`** — no `host_vars/` or per-group `group_vars`; the group
  structure plus role defaults classify the fleet.
- **Deliverable 15 partially operator-applied** — the auto-mode classifier
  reserves `.claude/` safety-config self-modification for explicit operator
  action; see §7.

## 4. Environment / dependency / schema changes

- **Proxmox host:** `ansible-core` 2.20.5 (`uv tool`); Galaxy collections
  `community.general` 12.6.1 + `ansible.posix` 2.1.0; Ubuntu 24.04 LXC
  template downloaded. SSH keypair `~/.ssh/aero_ed25519`; `~/.ssh/config`
  gained `Include ~/.ssh/config.d/*`; `~/.ssh/config.d/{aero,truenas}`.
  `vzdump` job `77c7f864-7abb-4202-8530-9185b76801dc`. `fuse` module loaded
  (`/etc/modules-load.d/aero-fuse.conf`). NFS mount of `192.168.2.100:/mnt/f3/aero`
  at `/mnt/aero-nfs` (host `/etc/fstab`). `.claude/settings.local.json`
  created by the operator with the `ssh truenas` allow rule (gitignored).
- **New guests:** LXCs 210-216, unprivileged Ubuntu 24.04, rootfs on
  `Storage`. `features`: 210/211 `nesting=1,mount=nfs,fuse=1`; 212/213
  `nesting=1,mount=nfs`; 214-216 `nesting=1`. 210-213 have `mp0`
  bind-mounting `/mnt/aero-nfs` → `/mnt/aero`.
- **Inside each aero LXC:** apt dist-upgrade; baseline packages; `uv`;
  `aero-admin` + scoped sudoers; `ufw`; `prometheus-node-exporter`.
  build/dev also: Apptainer 1.5.0 + subuid/subgid.
- **TrueNAS VM 104:** new dataset `f3/aero` + NFSv4 export to
  `192.168.2.0/24` (Mapall root) + nightly snapshot task — operator-applied.
- **Pinned:** Apptainer 1.5.0 (`.deb` sha256 `fbc27204…81ea`); `ubuntu:24.04`
  digest `c4a8d550…41c7b`. SIFs: `_base.sif` `ec16d562…`, `hello-world.sif`
  `7c901bea…` (`containers/SHA256SUMS`).
- No `aero/` Python core or `pyproject.toml` changes.

## 5. CI/CD changes

None. No workflow files modified. Self-hosted runner registration on
`aero-build` remains deferred (per the Stage 01 handoff).

## 6. Gotchas discovered

- **Unprivileged LXCs cannot mount NFS** — kernel restriction (NFS is not
  `FS_USERNS_MOUNT`); `features: mount=nfs` does not help. Use host-mount +
  Proxmox `mp` bind.
- **Apptainer build sandbox cannot open sockets** in the unprivileged LXC
  (`socket: Permission denied`) — no network in `%post`. Solver images
  (Stage 03+) must bootstrap from registry images that already contain
  their dependencies, not install via `%post`.
- **Non-root `apptainer run` fails** in the unprivileged LXC — both the
  non-suid path (session-layer error: "failed to add  as session directory")
  and the suid path (`apptainer-suid` setuid bit not honoured in an
  unprivileged container). SIFs run fine **as the LXC root**. `verify_stage_02.sh`
  check [3] runs the SIF as root accordingly. **Stage 03 must settle the
  solver-execution identity** (run as LXC root, or revisit).
- **`jq` is not installed on the Proxmox host** — the Stage 01
  `block-dangerous-bash.sh` (and the Stage 02 hardened version) call `jq`
  to parse the hook input; without `jq` the hook fails **open**. Install
  `jq`, or switch the hook's parse line to `python3` — see §7.
- **Running a SIF needs `/dev/fuse`** — host `fuse` module + `features:
  fuse=1` + the LXC restarted *after* the module is present.
- **`Storage` dir pool → no LXC snapshots** — `vzdump` uses `suspend` mode.
- **community.general 12 removed the `yaml` stdout callback.**
- **The auto-mode classifier gates** SSH to shared hosts, agent
  self-modification of `.claude/` config, and host kernel/`fstab` changes —
  each needs explicit operator action.

## 7. Open items for the next stage (and beyond)

**Operator follow-up (to fully close deliverable 15):**
- Install `jq` on the Proxmox host (`apt-get install -y jq`) so
  `block-dangerous-bash.sh` is active — until then it fails open.
- Optionally apply the `.claude/settings.json` `permissions` additions
  (allow `ssh aero-*`, `ansible*`, read-only `pct/qm/pveam/pvesm`; deny
  `pct create`) — convenience + one guard; the agent cannot self-modify
  `.claude/` config.

**Stage 03 (OpenFOAM walking skeleton):**
- First OpenFOAM SIF on `aero-build`, stored `/mnt/aero/containers/openfoam-esi.sif`;
  run target `aero-vv`. Bootstrap from a pre-built OpenFOAM registry image
  (the build sandbox has no `%post` network — §6).
- **Settle non-root SIF execution** (§6) — run solvers as the LXC root, or
  resolve the Apptainer session-layer issue.
- `vv-smoke.yml` becomes a real NACA 0012 case.

**Stage 04:** `aero_provenance` DB on Postgres LXC 202 (`192.168.2.184`);
MinIO sidecar on `aero-mlflow` over NFS; Vault stands up (takes over the
signing-key escrow).

## 8. Pointers for the next session

**Read first:** this file, `docs/adrs/ADR-002-proxmox-topology.md`,
`docs/architecture/proxmox-topology.md`, CLAUDE.md.

**Run first to verify:**
```bash
cd /root/projects/aero-research-platform && git status
./scripts/verify_stage_02.sh          # expect 30/30 PASS
for h in build dev mlflow vv prefect agent lit; do ssh aero-$h true; done
ssh root@aero-build apptainer run /opt/aero/containers/hello-world.sif
```

**Do not re-do:** provisioning, the Ansible roles, the backup job, the SIF
build — all idempotent and complete.

## 9. Artifacts produced

Branch `stage-02-proxmox-and-container-pipeline` (`aca8c60`→`v0.0.2`):
- **Provisioning:** `scripts/provision_aero_lxc.sh`.
- **Ansible:** `ansible/` — inventory, `site.yml`, roles `aero-base` /
  `aero-apptainer` / `aero-nfs-client`.
- **Scripts:** `run_long.sh`, `verify_stage_02.sh`, `build_base_sifs.sh`.
- **Containers:** `_base.def`, `hello-world.def`, `SHA256SUMS`,
  `SIGNING_KEY_FINGERPRINT.txt`; SIFs on `/mnt/aero/containers/`.
- **Docs:** `proxmox-inventory-2026-05-16.md`, `proxmox-topology.md`,
  `ssh-conventions.md`, `backup-interim.md`, `ADR-002`; CLAUDE.md, CHANGELOG,
  SECURITY updated.
- **`.claude`:** `block-dangerous-bash.sh` hardened.
- **Host (not committed):** `~/.ssh/aero_ed25519`, `~/.ssh/config.d/*`,
  `vzdump` job `77c7f864…`, the `/mnt/aero-nfs` mount, the `fuse` module.

## 10. Confidence / risk note

- **High confidence:** LXC fleet, dual-NIC networking, aero-base config,
  Apptainer install, the SIF build/sign/escrow pipeline, NFS host-bind,
  `run_long.sh`, the interim backup (`verify_stage_02.sh` 30/30).
- **Medium / known-limited:** non-root `apptainer run` does not work in the
  unprivileged LXC (§6) — Stage 03 must decide solver-execution identity;
  the hardened hook is inert until `jq` is installed (§7).
- **Risk:** the build-sandbox socket restriction shapes how Stage 03 builds
  the OpenFOAM image; the signing key is single-homed on aero-build (plus
  the encrypted TrueNAS escrow) until Vault (Stage 04+).
