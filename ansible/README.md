# Ansible — aero LXC fleet provisioning

Stage 02 configuration management for the seven `aero-*` LXC containers. The
containers are *created* by `scripts/provision_aero_lxc.sh` (raw `pct` on the
Proxmox host); Ansible *configures* them over SSH.

## Layout

| Path | Purpose |
|---|---|
| `inventory.yml` | The 7 aero LXCs (`aero_full` / `aero_stub`, plus `aero_apptainer` / `aero_nfs_client`) and a read-only `shared_services` reference group |
| `site.yml` | Top-level playbook — runs the three roles |
| `requirements.yml` | Galaxy collection pins |
| `group_vars/aero_lxc.yml` | Fleet-wide variables |
| `roles/aero-base` | Users, scoped sudo, SSH keys, ufw, baseline packages, node-exporter — all 7 |
| `roles/aero-apptainer` | Pinned Apptainer + subuid/subgid — aero-build, aero-dev |
| `roles/aero-nfs-client` | TrueNAS `aero/` NFS mount + `/opt/aero` symlinks — build, dev, vv, mlflow |

## Usage

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml
ansible all -m ping                  # connectivity check
ansible-playbook site.yml            # configure the whole fleet
ansible-playbook site.yml --limit aero-build
```

Stage 02 connects as `root` (key injected at provision time). The `aero-base`
role creates `aero-admin`, the scoped-sudo identity used from Stage 03 onward.
The `shared_services` group is **never** a play target — Hard Rule 11.

See `docs/adrs/ADR-002-proxmox-topology.md` for the design rationale.
