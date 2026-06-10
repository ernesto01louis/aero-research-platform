# STAGE-02: Proxmox Topology & Container Build Pipeline (revised)

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Compute targets and topology" (revised per the 2026-05-16
inventory) and Pass 1 architecture:

- The Proxmox inventory committed to the repo as a canonical reference.
- Six new `aero-*` LXCs provisioned via Ansible on the existing internal
  `10.10.10.0/24` bridge — `aero-build`, `aero-dev`, `aero-mlflow`, `aero-vv` now;
  `aero-prefect`, `aero-agent`, `aero-lit` stubbed with reduced scope (DBs/services
  not yet deployed; just the LXC shells with users, SSH, base packages, Apptainer
  where relevant).
- TrueNAS VM 104 configured with a dedicated NFS dataset `aero/` exposing four
  subdirectories: `dvc-remote/`, `mlflow-artifacts/`, `datasets/`, `containers/`.
- Apptainer SIF build pipeline operational on `aero-build`.
- The interim backup hedge in place: nightly `vzdump` of aero-* LXCs + nightly
  TrueNAS `aero/` snapshots.
- SSH alias convention configured locally and documented; `tmux`-based long-
  running-job pattern validated on a trivial job.

## ROLE

You are extending the existing Proxmox host with a NEW aero stack, integrating
additively with a small set of explicitly-shared application-agnostic services.
You are NOT touching any pre-existing non-aero LXC/VM, NOT installing GPU drivers
or vfio (no discrete GPU planned), and NOT competing with services already
running.

The inventory report (`docs/architecture/proxmox-inventory-2026-05-16.md`) is the
source of truth for what's already there. Read it first.

## GOAL

1. Commit the inventory report. Operator will provide the report file
   `proxmox-inventory-2026-05-16.md` (already produced via
   `PROMPT-00-proxmox-inspection.md`). Place at
   `docs/architecture/proxmox-inventory-2026-05-16.md`.
2. **Propose** the concrete aero LXC layout (resources, network, mounts) and
   wait for `approved` before any `pct create`. Target layout from the project
   brief:

   | LXC name | Cores | RAM | Disk | Storage pool | Network |
   |---|---:|---:|---:|---|---|
   | `aero-build` | 8 | 16 GB | 200 GB | `Storage` | `10.10.10.0/24` |
   | `aero-dev` | 16 | 32 GB | 300 GB | `Storage` | `10.10.10.0/24` |
   | `aero-mlflow` | 4 | 8 GB | 50 GB | `Storage` | `10.10.10.0/24` |
   | `aero-vv` | 16 | 32 GB | 200 GB | `Storage` | `10.10.10.0/24` |
   | `aero-prefect` | 4 | 8 GB | 30 GB | `Storage` | `10.10.10.0/24` |
   | `aero-agent` | 8 | 16 GB | 100 GB | `Storage` | `10.10.10.0/24` |
   | `aero-lit` | 4 | 8 GB | 100 GB | `Storage` | `10.10.10.0/24` |

   All unprivileged, Ubuntu 24.04 LTS template. Each gets a static IP in
   `10.10.10.20–10.10.10.26` (verify no collision with `ai-orchestrator` LXC 200
   which uses `10.10.10.10`).

3. Author Ansible inventory + playbooks at `ansible/`:
   - `ansible/inventory.yml` with the seven aero LXCs + a separate group for the
     shared-services hosts (Postgres 202, Grafana 205, TrueNAS 104) read-only for
     verification only
   - `ansible/roles/aero-base/` — common: users (`aero-admin` with sudo NOPASSWD
     for specific commands only), SSH key auth, ufw firewall (allow SSH from
     LAN/Tailscale only, allow internal 10.10.10.0/24 freely), apt update +
     upgrade, baseline packages (`git`, `python3.12`, `python3-pip`, `tmux`,
     `nfs-common`, `curl`, `ca-certificates`, `uv`), node-exporter for Grafana
     scraping
   - `ansible/roles/aero-apptainer/` — Apptainer install (apt or upstream `.deb`),
     `/etc/subuid` + `/etc/subgid` mapping for `aero-admin`, signing-key
     fingerprint check; applied to `aero-build` and `aero-dev`
   - `ansible/roles/aero-nfs-client/` — mount `aero/` from TrueNAS at
     `/mnt/aero` with `containers/` symlinked into `/opt/aero/containers`,
     `datasets/` to `/opt/aero/datasets`, etc. Applied to all aero LXCs that
     need shared storage (build, dev, vv, mlflow).
   - `ansible/site.yml` — orchestrates the roles.
4. Run the playbooks. Long-running ops via `tmux` per the long-running pattern.
   Verify each LXC reachable: `for h in build dev mlflow vv prefect agent lit;
   do ssh aero-$h true; done`.
5. Configure TrueNAS VM 104:
   - Create a new ZFS dataset `aero/` (or whatever the existing pool naming
     convention is — propose first based on the inventory's TrueNAS pool layout)
   - Inside it: `dvc-remote/`, `mlflow-artifacts/`, `datasets/`, `containers/`
   - Export `aero/` via NFSv4 with read/write access scoped to `10.10.10.0/24`,
     `no_root_squash` only if strictly needed for Apptainer fakeroot ops (propose)
   - Enable a nightly TrueNAS snapshot policy for the dataset
   - Verify mount from `aero-build`: `mount | grep aero` and `ls /mnt/aero/`
   - **All TrueNAS GUI/API changes are propose-first** — operator confirms each
6. Set up local SSH aliases on the operator's workstation. Write
   `~/.ssh/config.d/aero` (or similar) with entries for each aero LXC via
   Tailscale. Document the alias scheme in `docs/architecture/ssh-conventions.md`.
7. Bootstrap the Apptainer SIF pipeline on `aero-build`:
   - Generate an Apptainer signing keypair (`apptainer key newpair`); store the
     fingerprint in `containers/SIGNING_KEY_FINGERPRINT.txt`. **Private key
     never leaves the host**; operator confirms the storage path
   - Author `containers/_base.def` — Ubuntu 24.04 minimal base
   - Author `containers/hello-world.def` — trivial test SIF that prints
     "hello aero"
   - Build both: `apptainer build --fakeroot <name>.sif <name>.def`
   - Sign each, append SHA256 to `containers/SHA256SUMS`
   - Store the built SIFs under `/mnt/aero/containers/` (NFS), symlink into
     `/opt/aero/containers/` for local access
8. Author `scripts/run_long.sh` — the canonical long-running-job pattern from
   Pass 3 §6.3:
   - `run_long.sh <ssh-alias> <session-name> <command>` — submits via
     `ssh <alias> "tmux new-session -d -s <session-name> '<command> > <log>
     2>&1 && touch <session>.done'"`, returns immediately; polling helper
     functions for `.done` / `.failed` sentinels
9. Author `scripts/verify_stage_02.sh` — exit 0 iff:
   - All seven aero LXCs reachable via SSH alias
   - Apptainer ≥ pinned version on `aero-build` and `aero-dev`
   - Hello-world SIF runs on `aero-build` and prints expected output
   - SHA256SUMS contains entries for `_base.sif` and `hello-world.sif`
   - NFS mount of `/mnt/aero` works on at least `aero-build`, `aero-dev`,
     `aero-vv`, `aero-mlflow`
   - `tmux` available on all aero LXCs
   - Existing Postgres LXC 202 reachable from `aero-mlflow` (just TCP — no DB
     ops yet; that's Stage 04)
   - Existing Grafana LXC 205 reachable from `aero-vv` (TCP only; dashboards
     come in Stage 05)
   - Long-running job pattern works: submit a `sleep 30` via `run_long.sh`,
     verify it returns immediately and the `.done` sentinel appears after 35s
10. **Set up the interim backup hedge** (per the project brief; operator's
    larger backup plan runs in parallel):
    - Configure `vzdump` schedule on the Proxmox host for the aero-* LXCs only
      (NOT touching backup configuration for any other workload)
    - Daily 03:00 dump to `Storage` retention of 7 (interim only)
    - Verify the first dump runs successfully
    - Document the schedule in `docs/architecture/backup-interim.md` with a clear
      note that this is interim, owned by the operator, and to be revisited when
      the new NAS is online
11. Author `docs/architecture/proxmox-topology.md` — table of every aero LXC →
    resource allocation → role → planned-by-stage. Includes a one-line section
    for each existing reused service (Postgres 202, Redis 203, Tempo 204,
    Grafana 205, TrueNAS 104) with the form of the integration (NFS mount,
    new DB, new dashboard, etc.).
12. Author ADR-002 `docs/adrs/ADR-002-proxmox-topology.md`:
    - The chosen LXC layout and resource allocations (rationale: "operator
      prefers generous ceilings, oversubscription is fine on idle workloads")
    - Why fresh `aero-*` LXCs instead of reusing LXC 207 `aero-research`
      ("clean separation; no risk of contaminating earlier exploration")
    - Why fresh `aero-prefect` instead of reusing LXC 201 `prefect-server`
      ("aero orchestration plane decoupled from other Prefect workloads")
    - Why reusing existing Postgres (202), Grafana (205), Tempo (204), Redis
      (203), TrueNAS (104) — application-agnostic platforms; aero adds new
      DBs/dashboards/traces/snapshots/datasets without modifying existing state
    - No GPU passthrough configured (no discrete GPU); cloud-only for GPU work
    - Network choice (10.10.10.0/24 internal, MASQUERADE'd via vmbr0)
    - Backup interim policy and its operator ownership
13. Update CLAUDE.md (added in Stage 01) with:
    - SSH alias convention (`aero-build`, `aero-dev`, etc.)
    - The long-running-job pattern (one paragraph + pointer to
      `scripts/run_long.sh`)
    - Reminder: **do not touch any non-aero LXC/VM** beyond the explicitly-listed
      shared services
14. Update `.claude/settings.json` PreToolUse matchers to:
    - Allow `ssh aero-*` (all aero LXC aliases)
    - Allow `ssh <Postgres-LXC-host>` and similar shared-service hosts ONLY for
      read-only operations (TCP probes, `psql -c 'SELECT 1'` style); block
      writes to those hosts via a SQL-content filter
    - Block `ssh` to any host outside the allowlist
    - Block `pct destroy`, `pct stop` of any LXC ID
    - Block `qm destroy`, `qm stop` of any VM ID
    - Block writes to `/etc/network/interfaces`, `/etc/pve/`, `/etc/subuid`,
      `/etc/subgid` on the Proxmox host without `approved`
15. Tag `v0.0.2` after the post-stage handoff exists.

## WHY

The inventory revealed substantial pre-existing infrastructure (LXC 207 was
already pre-named "aero-research"; Prefect, Postgres, Redis, Tempo, Grafana,
TrueNAS, Tailscale, headscale, CrowdSec all running). Provisioning fresh
`aero-*` LXCs gives the platform clean separation; reusing the application-
agnostic shared services (Postgres, Grafana, Tempo, Redis, TrueNAS) avoids
unnecessary duplication while leaving every existing workload undisturbed.

No discrete GPU on the host means GPU work is cloud from day one. The platform's
Stage 13 multi-cloud orchestration is therefore central, not optional. Stage 02
does not configure GPU passthrough or vfio.

The interim backup hedge protects against single-disk loss while the operator
provisions a proper NAS-based backup target. It's a Stage-02 deliverable because
the next several stages will produce data that's expensive to regenerate.

Apptainer SIFs going on NFS (TrueNAS) rather than local LXC disks means the same
signed SIF is reachable from `aero-build`, `aero-dev`, `aero-vv`, and any future
compute LXC — single source of truth.

## HOW

- Ansible Proxmox modules: `community.general.proxmox` for LXC create if you have
  credentials. Otherwise, use `pct` directly via `delegate_to: proxmox-host`. The
  operator may have a preference — propose first.
- `aero-admin` sudo: limit NOPASSWD to a tight allowlist (`apt`, `apptainer`,
  `systemctl restart aero-*`, `mount`/`umount` for NFS) rather than full sudo.
- Tailscale on aero LXCs: optional. The internal `10.10.10.0/24` is already
  reachable from the operator's workstation via the existing Tailscale setup on
  the host. Don't add Tailscale clients to every LXC unless needed.
- NFSv4 vs NFSv3 on TrueNAS: prefer NFSv4 for proper user mapping. Verify the
  TrueNAS VM's NFS service is enabled and configure the exports through the
  TrueNAS UI (operator confirms each click).
- For Apptainer NFS gotchas: Apptainer's overlay storage can have issues over
  NFS. Use `--no-mount tmp` or set `APPTAINER_TMPDIR` to a local LXC path if
  problems appear. Document any workaround in the ADR.
- For `vzdump` interim schedule: Proxmox UI → Datacenter → Backup, schedule
  daily at 03:00, target `Storage`, mode snapshot, retention 7. **Do not include
  any LXC outside the aero-* group.**

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md` (revised; reflects the inventory)
- `STAGE-02-proxmox-and-container-pipeline.md` (this file)
- `docs/handoffs/STAGE-01-*-DONE-*.md` (the Stage-01 exit notes)
- `docs/architecture/proxmox-inventory-2026-05-16.md` (commit this in step 1
  if not already committed)
- ADR-001 (from Stage 01) if it exists; ADR-002 (this stage) is new

## GUARDRAILS — DO NOT

1. **Do NOT touch LXC 207 `aero-research`.** It's pre-existing. Leave it as the
   operator left it. The aero stack uses fresh LXCs.
2. **Do NOT modify any other existing LXC/VM** (101, 102, 103, 105, 106, 107,
   108, 109, 113, 114, 200, 201, 206, VMs 100, 104 except for adding the `aero/`
   NFS dataset, 111, 112). Adding new aero-* LXCs alongside is allowed; modifying
   existing ones is not.
3. **Do NOT install GPU drivers, configure vfio-pci, or modify
   `/etc/modprobe.d/`** on the Proxmox host. No discrete GPU, no passthrough.
4. **Do NOT enable the Proxmox enterprise repo** or change subscription state.
5. **Do NOT touch Ceph configuration** (mon+mgr running with 0 OSDs; operator's
   prerogative).
6. **Do NOT alter network configuration on the host** (`/etc/network/interfaces`,
   firewall rules, Tailscale config) without explicit `approved`.
7. **Do NOT use Proxmox root user** for automation. Use a dedicated
   `aero-admin` non-root user with scoped sudo.
8. **Do NOT pull `latest` tags** for any container base image. Pin SHA256.
9. **Do NOT expose any aero service to the public internet.** All access via
   `10.10.10.0/24` + Tailscale.
10. **Do NOT skip the inventory commit (step 1).** The inventory IS the source of
    truth for what's already there.
11. **Do NOT modify backup schedules for any non-aero workload.** The interim
    backup hedge applies only to aero-* LXCs.

## DELIVERABLES

- [ ] `docs/architecture/proxmox-inventory-2026-05-16.md` committed
- [ ] Seven `aero-*` LXCs provisioned and reachable via SSH alias
- [ ] Apptainer ≥ pinned version on `aero-build` and `aero-dev`
- [ ] TrueNAS NFS dataset `aero/` with four subdirectories exported; mounted at
      `/mnt/aero` on `aero-build`, `aero-dev`, `aero-vv`, `aero-mlflow`
- [ ] `_base.sif` and `hello-world.sif` built, signed, SHAs in
      `containers/SHA256SUMS` (which lives under NFS at
      `/mnt/aero/containers/SHA256SUMS`; symlinked in repo)
- [ ] `scripts/run_long.sh` works against an `aero-vv` test job
- [ ] `scripts/verify_stage_02.sh` exits 0
- [ ] `docs/architecture/proxmox-topology.md` matches reality
- [ ] `docs/architecture/ssh-conventions.md` documents the alias scheme
- [ ] `docs/architecture/backup-interim.md` documents the interim hedge
- [ ] Interim `vzdump` schedule active and first dump verified
- [ ] TrueNAS nightly snapshot policy active for the `aero/` dataset
- [ ] ADR-002 committed
- [ ] CLAUDE.md updated with SSH + long-running conventions
- [ ] `.claude/settings.json` PreToolUse matchers updated
- [ ] Post-stage handoff `docs/handoffs/STAGE-02-*-DONE-*.md` written
- [ ] Tag `v0.0.2`

## PROPOSE FIRST, EXECUTE LATER

Wait for the literal word `approved` from the operator before any of:

- The LXC layout (cores/RAM/disk per LXC; the proposed numbers may be revised)
- Static IPs in `10.10.10.0/24` (verify no collision)
- The TrueNAS dataset path and NFS export configuration
- The `no_root_squash` decision on the NFS export (security tradeoff)
- Any `pct create` or `pct destroy`
- Any change to `/etc/subuid`, `/etc/subgid`, `/etc/network/interfaces`, or any
  file under `/etc/pve/` on the Proxmox host
- The Apptainer signing keypair generation (it's a persistent secret — discuss
  storage)
- The interim `vzdump` schedule (operator's overall backup plan is in flight)
- Any sudo allowlist additions

## POST-STAGE HANDOFF

Required emphases for `docs/handoffs/STAGE-02-*-DONE-*.md`:

- **Topology diagram** in the "Artifacts produced" section: ASCII or mermaid
  showing aero-* LXCs + reused services + NFS, in
  `docs/architecture/proxmox-topology.md`.
- **Resource accounting**: post-Stage-02 total RAM allocated across all guests
  (existing + new aero), as a sanity check vs the 92 GB physical.
- **TrueNAS configuration steps actually taken** (which UI panels, which CLI
  commands) — Stage 04 will reference this.
- **The Apptainer signing key fingerprint** (public part) and the path where
  the private key is stored (not the key itself — never paste the key).
- **NFS gotchas**: any Apptainer-over-NFS issues observed and how they were
  worked around.
- **Open items for Stage 03**: which SSH alias `aero-vv` or `aero-build` will
  host the first OpenFOAM run; where the SIF will live (`/mnt/aero/containers/
  openfoam-esi.sif`); the executor target.
- **Open items for Stage 04**: the `aero_provenance` DB will land in the existing
  Postgres LXC 202; pgvector availability check; the MinIO sidecar inside
  `aero-mlflow` backing onto NFS — confirm the pattern.
- **Gotchas**: LXC-specific quirks (unprivileged + NFS + Apptainer fakeroot can
  fight), TrueNAS UI variations between versions, Ansible idempotency edge
  cases.
- **Verify the interim backup ran** and the first dump is recoverable (small
  test restore would be ideal but not required).
