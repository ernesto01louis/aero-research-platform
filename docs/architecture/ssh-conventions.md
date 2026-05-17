# SSH & Long-Running-Job Conventions

Established in Stage 02. How operators and Claude Code sessions reach the
`aero-*` LXC fleet, and how to launch jobs that outlast a single session.

## SSH aliases

The seven aero LXCs are reached through stable aliases, **not** raw IPs.
Aliases live in `~/.ssh/config.d/aero` on the Proxmox host; `~/.ssh/config`
carries an `Include ~/.ssh/config.d/*` directive so the drop-in is picked up.

| Alias | LXC ID | LAN IP (eth0) | Private IP (eth1) | Role |
|---|---|---|---|---|
| `aero-build` | 210 | 192.168.2.232 | 10.10.10.20 | Apptainer SIF builds, CI runner site |
| `aero-dev` | 211 | 192.168.2.233 | 10.10.10.21 | Dev, JupyterLab, ParaView, mesh prep |
| `aero-mlflow` | 212 | 192.168.2.234 | 10.10.10.22 | MLflow + MinIO sidecar |
| `aero-vv` | 213 | 192.168.2.235 | 10.10.10.23 | V&V CPU CFD runner |
| `aero-prefect` | 214 | 192.168.2.236 | 10.10.10.24 | Prefect orchestration (stub) |
| `aero-agent` | 215 | 192.168.2.237 | 10.10.10.25 | NeMo Agent Toolkit runtime (stub) |
| `aero-lit` | 216 | 192.168.2.238 | 10.10.10.26 | Literature ingestion (stub) |

```bash
ssh aero-build              # connects as aero-admin over the LAN NIC
ssh root@aero-build         # break-glass: root login (same key)
```

### Identity

- **`aero-admin`** — the scoped-sudo automation user (created by the
  `ansible/` `aero-base` role). It is the alias default `User` and the
  identity every stage from 03 on uses.
- **`root`** — available for break-glass via `ssh root@aero-<name>`. The
  `~/.ssh/aero_ed25519` key authorizes both.
- Key: `~/.ssh/aero_ed25519` on the Proxmox host (no passphrase; host-root
  owned, mode 600). Not committed.

### Networking (dual-NIC — see ADR-002)

Each aero LXC has two NICs on `vmbr0`:

- **`eth0` (LAN, 192.168.2.23x)** — internet egress, SSH, Ansible. This is
  the management path; aliases resolve to these IPs.
- **`eth1` (private, 10.10.10.2x)** — the aero-internal data plane (NFS,
  inter-service traffic). The `10.10.10.0/24` segment has no host-side
  gateway, so it is **not** used for management SSH.

## Long-running jobs — `scripts/run_long.sh`

CFD and training jobs outlast a single Claude Code turn. The convention is
submit-detach-poll via `tmux`, never a held-open SSH connection.

```bash
scripts/run_long.sh aero-vv mycase "openfoam-run ..."   # submit, returns now
scripts/run_long.sh status aero-vv mycase               # done|failed|running
scripts/run_long.sh wait   aero-vv mycase 7200          # block until sentinel
scripts/run_long.sh logs   aero-vv mycase               # fetch output.log
```

Remote job state lives in `~/.aero-jobs/<session>/` on the target LXC:
`output.log`, `rc`, and a `.done` / `.failed` sentinel. `status` and `wait`
exit 0 (done), 1 (failed), 2 (running/timeout).
