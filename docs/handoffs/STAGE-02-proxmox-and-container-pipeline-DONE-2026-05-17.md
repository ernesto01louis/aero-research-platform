---
stage: 02
stage_name: "Stage 02 — Proxmox Topology & Container Build Pipeline"
status: partial
date_started: 2026-05-17
date_completed: 2026-05-17
session_duration_hours: 3.0
claude_code_version: "claude-code-vscode-extension"
model: claude-opus-4-7
git_sha_start: "aca8c600bc504af0734945936086853cd0439fbf"
git_sha_end: "421d84427ac48449ff6d0f7630a77267e920c958"
stage_tag: v0.0.2
next_stage: 03
next_stage_name: "Stage 03 — OpenFOAM Walking Skeleton"
---

# Stage 02 — Proxmox Topology & Container Build Pipeline — PARTIAL 2026-05-17

> **STATUS: PARTIAL.** The infrastructure is provisioned and configured;
> two items are blocked on operator host actions (TrueNAS access + the FUSE
> kernel module). This file flips to `status: complete` once those land and
> the remaining steps below run. Do **not** tag `v0.0.2` until then.

## 0. What to do first if you are resuming this stage

Two operator actions unblock everything remaining:

**A — FUSE (run on the Proxmox host):**
```bash
modprobe fuse
echo fuse | tee /etc/modules-load.d/aero-fuse.conf
pct set 210 -dev0 /dev/fuse
pct set 211 -dev0 /dev/fuse
pct reboot 210 && pct reboot 211
```

**B — TrueNAS:** enable SSH on TrueNAS `192.168.2.100`, add the aero key
(`~/.ssh/aero_ed25519.pub`) to root's authorized keys, and create
`.claude/settings.local.json` with
`{"permissions":{"allow":["Bash(ssh truenas:*)"]}}`.

Then run, in order: §7 "Remaining work".

## 1. Deliverables status

| # | Deliverable | Status | Note |
|---|---|---|---|
| 1 | `proxmox-inventory-2026-05-16.md` committed | ✅ | `docs/architecture/` |
| 2 | Seven `aero-*` LXCs provisioned + reachable | ✅ | IDs 210-216, dual-NIC, all SSH-reachable |
| 3 | Apptainer ≥ pinned on build+dev | ✅ | 1.5.0 on aero-build, aero-dev |
| 4 | TrueNAS NFS dataset `aero/` + export + snapshot | ❌ | BLOCKED — operator TrueNAS access |
| 5 | `_base.sif` + `hello-world.sif` built/signed/SHA | ⚠️ | build verified; sign + SHA + NFS placement pending |
| 6 | `scripts/run_long.sh` | ✅ | submit/poll/wait verified end-to-end |
| 7 | `scripts/verify_stage_02.sh` exits 0 | ⚠️ | written; not yet run green (blocked deps) |
| 8 | `proxmox-topology.md` | ✅ | |
| 9 | `ssh-conventions.md` | ✅ | |
| 10 | `backup-interim.md` | ✅ | |
| 11 | Interim `vzdump` schedule + first dump | ✅ | job `77c7f864…`, test dump 659 MB verified |
| 12 | TrueNAS nightly snapshot policy | ❌ | BLOCKED — operator TrueNAS access |
| 13 | ADR-002 | ✅ | |
| 14 | CLAUDE.md updated | ✅ | SSH + long-job conventions + fleet reminder |
| 15 | `.claude/settings.json` PreToolUse hardening | ❌ | deliberately deferred to land last (see §3) |
| 16 | Post-stage handoff | ⚠️ | this file (partial) |
| 17 | Tag `v0.0.2` | ❌ | gated on the above |

Provisioning, base configuration, the Apptainer toolchain, the helper
scripts, the interim backup, and all docs/ADR are **done**. The container
pipeline is **built and proven**; only signing + final NFS placement remain.

## 2. Decisions made

- **Dual-NIC networking** (ADR-002). The `10.10.10.0/24` segment has no
  host-side gateway, so a 10.10.10-only NIC cannot reach the internet.
  Every aero LXC gets `eth0` (LAN, mgmt/egress) + `eth1` (10.10.10, data
  plane). Rejected: 10.10.10-only (needs a host `/etc/network/interfaces`
  change); flat-LAN-only (drops the private segment).
- **LAN block 192.168.2.232-238** (not the planned `.220-.226`). `.222`,
  `.224`, `.226` held live DHCP leases; `.232-.238` is a clean static block
  above LXC 207 (`.231`).
- **Raw `pct` provisioning** via `scripts/provision_aero_lxc.sh`, not the
  Ansible Proxmox module — we are root on the host; zero API-credential
  surface.
- **Stage 02 Ansible runs as `root`** (key-injected); `aero-base` creates
  `aero-admin` (scoped-sudo), the identity for Stage 03+.
- **Interim `vzdump` uses `suspend` mode** — the `Storage` dir pool does not
  support LXC snapshots; `snapshot` mode auto-falls-back, set explicitly.
- **`_base.def` does no network in `%post`** — the Apptainer build sandbox
  in the unprivileged LXC cannot open sockets (see §6). The base is pinned
  Ubuntu 24.04 with a filesystem-only `%post`. Rejected: keeping the apt
  `%post` (fails the build).
- **Signing key: aero-build keyring + encrypted TrueNAS escrow** (ADR-002,
  operator choice). Pending — needs the SIF pipeline finalisation.

## 3. Deviations from the stage plan

- **LAN IPs** `.220-.226` → `.232-.238` (DHCP collision; the plan
  anticipated execution-time verification).
- **`ansible.cfg`** initially set `stdout_callback = yaml`, which
  community.general 12 removed; fixed to `stdout_callback = default` +
  `result_format = yaml`.
- **`_base.def` simplified** — no `%post` package install (build-sandbox
  socket restriction, §6). Package-bearing solver images are a Stage 03
  concern.
- **Host `fuse` module required** — running SIFs in the unprivileged LXC
  needs `/dev/fuse`. The plan said "no modprobe changes" (written for
  GPU/vfio); loading the stock `fuse` module is a small, necessary,
  operator-approved exception. BLOCKED pending operator action.
- **`.claude` hardening (deliverable 15) intentionally deferred** to land
  last — a buggy SSH-allowlist hook would self-block the `ssh aero-*` and
  `ssh truenas` calls the remaining work needs.
- **`containers/SHA256SUMS`** will be a real version-controlled file, not a
  repo symlink into NFS (a committed checksum file is correct for a
  provenance-mandated project and survives CI checkout).
- **`ansible/` layout** — no `host_vars/` or per-group `group_vars` files;
  the group structure (`aero_full`/`aero_stub`/`aero_apptainer`/
  `aero_nfs_client`) plus role defaults fully classify the fleet.

## 4. Environment / dependency / schema changes

- **Host:** `ansible-core` 2.20.5 installed via `uv tool`; Galaxy
  collections `community.general` 12.6.1 + `ansible.posix` 2.1.0. Ubuntu
  24.04 LXC template downloaded (`pveam`). SSH keypair
  `~/.ssh/aero_ed25519` generated; `~/.ssh/config` gained
  `Include ~/.ssh/config.d/*`; `~/.ssh/config.d/aero` + `truenas` written.
  `vzdump` backup job `77c7f864-7abb-4202-8530-9185b76801dc` created.
- **New guests:** LXCs 210-216 (`aero-build/dev/mlflow/vv/prefect/agent/lit`),
  unprivileged Ubuntu 24.04, dual-NIC, `nesting=1`, rootfs on `Storage`.
- **Inside each aero LXC:** apt dist-upgrade; baseline packages; `uv`;
  `aero-admin` user + scoped sudoers; `ufw` enabled; `prometheus-node-exporter`.
  aero-build/dev additionally: Apptainer 1.5.0 + subuid/subgid maps.
- **Pinned:** Apptainer 1.5.0 (`.deb` sha256 `fbc27204…81ea`); `ubuntu:24.04`
  digest `sha256:c4a8d550…41c7b`. All recorded in ADR-002.
- **Not yet done:** TrueNAS dataset, NFS mounts, SIF SHA256SUMS, signing key.

## 5. CI/CD changes

None. No workflow files were modified. The `.github/workflows/` set is
unchanged from Stage 01. (Self-hosted runner registration on `aero-build`
remains deferred per the Stage 01 handoff.)

## 6. Gotchas discovered

- **Apptainer build sandbox cannot open sockets** in the unprivileged LXC:
  `%post` network ops fail with `socket: Permission denied` (not a DNS or
  routing issue — `resolv.conf`, `nsswitch.conf`, and routes are all
  correct). Package installs cannot run during a build here. Stage 03 must
  bootstrap solver images from registry images that already contain their
  dependencies, or resolve the sandbox restriction (AppArmor/seccomp).
- **Running a SIF needs `/dev/fuse`** (squashfuse) — absent in the
  unprivileged LXC. `apptainer build` works; `apptainer run` fails until
  the host `fuse` module is loaded and `/dev/fuse` is passed through.
- **`Storage` dir pool → no LXC snapshots** — `vzdump` uses `suspend` mode
  (≈1 s container pause).
- **community.general 12 removed the `yaml` stdout callback** — use
  `stdout_callback = default` + `result_format = yaml`.
- **The auto-mode classifier gates** SSH to the shared TrueNAS host,
  self-modification of `.claude` permission settings, and host `modprobe` —
  each needs an explicit operator action / permission rule.
- **LXC `pct` snapshot fallback** and **dual-NIC on one bridge** (both NICs
  on `vmbr0`, mirroring LXC 200) both work fine.

## 7. Open items — remaining work for this stage

After the §0 unblock actions:

1. **TrueNAS** (`scripts/setup_truenas_aero_dataset.sh`, to be written):
   over `ssh truenas`, `midclt`-create dataset `<pool>/aero` + subdirs
   `dvc-remote/ mlflow-artifacts/ datasets/ containers/`; NFSv4 export
   scoped to the aero LAN block with `maproot`; nightly snapshot task.
   Then set `aero_nfs_export` in `ansible/roles/aero-nfs-client/defaults/main.yml`.
2. **`ansible-playbook site.yml --tags nfs`** — mount `/mnt/aero` on
   build/dev/vv/mlflow + `/opt/aero/*` symlinks.
3. **SIF pipeline** — generate the signing keypair on aero-build
   (passphrase in `.env` 0600), build `_base.sif` + `hello-world.sif`, sign
   both, write `containers/SHA256SUMS` + `containers/SIGNING_KEY_FINGERPRINT.txt`,
   place SIFs in `/mnt/aero/containers/` (symlink `/opt/aero/containers/`),
   escrow the encrypted private key to TrueNAS NFS. Capture the steps into
   `scripts/build_base_sifs.sh`.
4. **`scripts/verify_stage_02.sh`** — run; must exit 0.
5. **`.claude` hardening (deliverable 15)** — `settings.json` allow/deny +
   `block-dangerous-bash.sh` SSH-allowlist / `pct,qm` / protected-path
   rules. Land last; re-run verify afterward.
6. **Docs finalisation** — `CHANGELOG.md` `[0.0.2]`; `SECURITY.md`
   signing-key note; `regenerate_status.sh` for the README.
7. **Flip this handoff** to `status: complete`, update `git_sha_end`.
8. **PR → merge → tag `v0.0.2`**.

For Stage 03: first OpenFOAM SIF lands on `aero-build`, stored at
`/mnt/aero/containers/openfoam-esi.sif`; run target `aero-vv`. The
build-sandbox socket restriction (§6) means the OpenFOAM image should
bootstrap from a registry image that already contains OpenFOAM.

For Stage 04: `aero_provenance` DB on Postgres LXC 202 (`192.168.2.184`);
MinIO sidecar on `aero-mlflow` backing onto NFS.

## 8. Pointers for the next session

**Read first:** this file (§0, §7), the plan at
`/root/.claude/plans/we-are-continuing-with-squishy-lollipop.md`, ADR-002.

**Run first to verify state:**
```bash
cd /root/projects/aero-research-platform && git status
git log --oneline | head -12
for h in build dev mlflow vv prefect agent lit; do ssh aero-$h true && echo "aero-$h ok"; done
pvesh get /cluster/backup            # job 77c7f864 present
ssh aero-build apptainer --version   # 1.5.0
```

**Do not re-do:** provisioning, aero-base, aero-apptainer, the backup job —
all idempotent and complete.

## 9. Artifacts produced

Branch `stage-02-proxmox-and-container-pipeline`, 13 commits
(`332e63d`…`421d844`) atop `aca8c60`.

- **Provisioning:** `scripts/provision_aero_lxc.sh` (7 LXCs created).
- **Ansible:** `ansible/` — `inventory.yml`, `site.yml`, `ansible.cfg`,
  `requirements.yml`, `group_vars/aero_lxc.yml`, three roles
  (`aero-base`, `aero-apptainer`, `aero-nfs-client`), `README.md`.
- **Scripts:** `run_long.sh` (verified), `verify_stage_02.sh` (authored).
- **Containers:** `_base.def`, `hello-world.def` (built & proven on
  aero-build; signing pending).
- **Docs:** `proxmox-inventory-2026-05-16.md`, `proxmox-topology.md`,
  `ssh-conventions.md`, `backup-interim.md`, `ADR-002-proxmox-topology.md`;
  `CLAUDE.md` updated.
- **Host (not committed):** `~/.ssh/aero_ed25519`, `~/.ssh/config.d/{aero,truenas}`,
  `vzdump` job `77c7f864…`, first dump `vzdump-lxc-210-2026_05_17-22_04_27.tar.zst`.

## 10. Confidence / risk note

- **High confidence:** LXC fleet, dual-NIC networking, aero-base config,
  Apptainer install, `run_long.sh`, the interim backup (test dump verified).
- **Medium:** the SIF signing flow (Apptainer 1.5 non-interactive
  `key newpair` / `sign` invocations not yet exercised); the TrueNAS
  `midclt` API parameter schemas (to be verified against the live box).
- **Blocked / unknown:** TrueNAS NFS (no access yet); whether `pct set
  -dev0 /dev/fuse` + reboot fully resolves SIF execution (expected to, but
  unverified).
- **Risk:** the build-sandbox socket restriction (§6) will resurface in
  Stage 03 — flagged there. The signing key is single-homed on aero-build
  until the TrueNAS escrow lands.
