# Prompt: Proxmox Host Inspection — Read-Only Reconnaissance

**Paste this entire file into a fresh Claude Code session.** Claude Code will SSH into
your Proxmox host, gather an inventory of the system, and produce a structured report.
The report will then be fed back to me (Claude in chat) so I can tailor the
aerodynamics platform handoff bundle to what's actually on your hardware.

This is a **READ-ONLY** reconnaissance pass. Claude Code must not modify, install, or
restart anything.

---

## ROLE

You are performing read-only reconnaissance of a Proxmox VE host that will eventually
host the control plane for an open-source aerodynamics research platform. Your job is
to inventory what's there and produce a structured Markdown report. You will not
propose changes, install packages, or modify configuration in this session.

## GOAL

Produce a single Markdown report at `~/aero-inspect/proxmox-inventory-YYYY-MM-DD.md`
containing the sections enumerated below. Save it locally on your workstation, NOT on
the Proxmox host.

## CONNECTION

The user (Ernesto) will tell you the SSH alias or `user@host` to use. Confirm the SSH
target with the user before starting. Use SSH key auth; do not prompt for or store
passwords.

Suggested first message to user:

> "What SSH target should I use to reach the Proxmox host? (e.g., `proxmox`,
> `root@10.0.0.5`). I will run only read-only commands and will not modify anything."

## HARD GUARDRAILS — DO NOT

1. Do NOT run any command that writes, installs, modifies, restarts, or deletes
   anything on the Proxmox host. Read-only ops only.
2. Do NOT print or copy the contents of: `/etc/shadow`, `/etc/pve/priv/*`,
   `~/.ssh/*`, any `*.key` or `*.pem` file, `/root/.bash_history`, environment
   variables containing `TOKEN`, `KEY`, `SECRET`, `PASS`.
3. Do NOT use `sudo` unless the user explicitly grants it for a specific named
   command, and even then only for read operations (e.g., `sudo cat
   /proc/cmdline`). Most of the inspection should work without `sudo` since
   Proxmox runs as root by default — verify which user the SSH session lands as
   before assuming.
4. Do NOT pipe long outputs into the conversation. Capture to local files under
   `~/aero-inspect/raw/` and reference them in the report; only summarize in the
   conversation itself.
5. Do NOT run any `pct create`, `qm create`, `apt install`, `apt update`,
   `pveam download`, `pvesm add`, `zpool create`, `systemctl restart`, or any
   verb that modifies state.
6. Do NOT enumerate or test SSH keys, certificates, or credentials of any kind.
7. If anything looks like it might require write access or `sudo`, STOP and ask
   the user before proceeding.

## INSPECTION CHECKLIST

Run each of the following via `ssh <target> '<command>'`. Capture output to
`~/aero-inspect/raw/<section>.txt` and write a summary in the report.

### 1. Host basics
- `uname -a`
- `pveversion --verbose`
- `cat /etc/os-release`
- `lscpu`
- `free -h`
- `df -h`
- `uptime`
- `cat /proc/cmdline`

### 2. CPU and memory topology
- `lscpu --extended` (NUMA awareness matters for CFD)
- `numactl --hardware` (if installed; if not, note as missing)
- `cat /proc/meminfo | head -30`

### 3. GPU and accelerators
- `lspci -nn | grep -iE 'nvidia|amd|vga|3d|display'`
- `nvidia-smi` if present; if `nvidia-smi: command not found`, note as no NVIDIA
  driver on host (which is the recommended state for Proxmox with GPU passthrough)
- `lsmod | grep -E 'nvidia|nouveau|vfio|amdgpu'`
- `ls /etc/modprobe.d/` (just listing, not contents, unless filenames suggest GPU
  passthrough config — then `cat` only the GPU-related ones)
- `dmesg | grep -iE 'vfio|iommu' | head -40` (may need `sudo` — ask first)

### 4. Storage
- `pvesm status`
- `lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,MODEL`
- `cat /etc/fstab`
- If ZFS: `zpool list`, `zpool status`, `zfs list -t all | head -30`
- If LVM: `vgs`, `lvs`
- `df -h /var/lib/vz` (default Proxmox storage)

### 5. Network
- `ip -br addr`
- `ip route`
- `cat /etc/network/interfaces`
- `cat /etc/hosts`
- `ss -tlnp | head -30` (listening ports — useful to know what's already running)

### 6. Existing workloads
- `pct list` (LXC containers)
- `qm list` (VMs)
- For each LXC: `pct config <ID>` (resources, mounts, network)
- For each VM: `qm config <VMID>` (resources, disks, network)

### 7. Backups and snapshots
- `cat /etc/pve/jobs.cfg` (scheduled backups)
- `ls -la /var/lib/vz/dump/ 2>/dev/null | head -20`
- Per-storage backup retention if visible

### 8. Container tooling on host
- `which apptainer singularity docker podman`
- For each one found: `<tool> --version`

### 9. Proxmox cluster state
- `pvecm status` (single node vs cluster)
- `pveceph status` (if Ceph present)

### 10. Security and updates
- `apt list --upgradable 2>/dev/null | wc -l` (just the count, not the list)
- `cat /etc/apt/sources.list /etc/apt/sources.list.d/*.list` (which repos are
  enabled — Proxmox enterprise vs no-subscription)
- `last -n 20` (recent logins — sanity check)

## REPORT STRUCTURE

Save to `~/aero-inspect/proxmox-inventory-YYYY-MM-DD.md`. Use this template:

```markdown
# Proxmox Inventory — <hostname> — <date>

## 1. One-line summary
<e.g., "Single-node Proxmox VE 8.2.4, 32 cores AMD EPYC, 98 GB RAM, 2 TB ZFS,
no GPU on host, 4 LXCs and 1 VM currently running, no scheduled backups.">

## 2. Hardware
- CPU model, cores, threads, NUMA layout
- Memory total, used, swap config
- Storage: pools, sizes, free space, filesystem types
- GPUs: present? passthrough configured? driver state?
- Network interfaces and current IP plan

## 3. Proxmox configuration
- Proxmox version
- Single node or cluster
- Repos enabled (enterprise vs no-subscription)
- Pending updates count
- Apptainer / Singularity / Docker / Podman availability

## 4. Existing workloads
| Type | ID | Name | CPU | RAM | Disk | OS | Purpose (if obvious) |
|------|----|----|-----|-----|------|----|----|

## 5. Risks identified
- Bullet points: no backups, single PSU, GPU not in vfio, full disk, etc.
- Each risk: severity (low/medium/high) and a one-line mitigation hint

## 6. Capacity for the aero platform
Based on what's there:
- Free CPU cores: X
- Free RAM: Y GB
- Free disk: Z TB (which pool)
- Free network bridges or VLANs

## 7. Open questions for the user
Bullet points of things you noticed but cannot interpret without operator input.

## 8. Raw output index
List of files captured under `~/aero-inspect/raw/` with one-line description each.
```

## OUTPUT TO THE CONVERSATION

After writing the report, print to the conversation:

1. A 5–10 line executive summary of what you found.
2. The path to the full report (so the user can `cat` it and paste it back to me).
3. Any blocker or ambiguity you hit during inspection.
4. The exact list of files under `~/aero-inspect/raw/` you created.

Do NOT paste the full report into the conversation — it will be long. The user will
read it from disk and share the relevant parts with me.

## TERMINATION

After the report is written and the summary is printed:
- Do not stage, commit, or push anything to any git repo.
- Do not start any background process or `tmux` session.
- Do not propose next steps. The user will paste the report back to me (Claude in
  chat) and I will produce the Stage-02 plan.

End the session here.
