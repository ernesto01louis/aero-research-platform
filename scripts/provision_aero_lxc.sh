#!/usr/bin/env bash
# scripts/provision_aero_lxc.sh
#
# Stage 02 — idempotent provisioner for the aero-* LXC containers
# (Stage 04 appends aero-vault, LXC 217).
# Runs ON the Proxmox host as root. Uses raw `pct` (see ADR-002 for why the
# Ansible Proxmox module was not used: we are root on the host, so `pct` is
# the native, zero-credential path).
#
# Each LXC is dual-NIC (ADR-002 networking decision — the 10.10.10.0/24
# segment has no host-side gateway, so a private-only NIC cannot reach the
# internet for apt/uv/GitHub):
#   eth0 — vmbr0, static LAN IP, gw 192.168.2.1   (internet + SSH + Ansible)
#   eth1 — vmbr0, static 10.10.10.2x, no gateway  (private aero data plane)
#
# Idempotent: a container that already exists is left untouched. This script
# only ever creates and starts; it never stops or destroys anything, and it
# only ever touches IDs 210-217.
#
# Usage:  ./scripts/provision_aero_lxc.sh

set -euo pipefail

TEMPLATE="local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
STORAGE="Storage"
BRIDGE="vmbr0"
LAN_GW="192.168.2.1"
NAMESERVER="192.168.2.1"
PUBKEY="${HOME}/.ssh/aero_ed25519.pub"
KNOWN_HOSTS="${HOME}/.ssh/known_hosts"

# Fleet table.  Fields: id name cores ram_mb disk_gb swap_mb lan_ip priv_ip
FLEET=(
  "210 aero-build    8  16384 200 2048 192.168.2.232 10.10.10.20"
  "211 aero-dev     16  32768 300 2048 192.168.2.233 10.10.10.21"
  "212 aero-mlflow   4   8192  50 2048 192.168.2.234 10.10.10.22"
  "213 aero-vv      16  32768 200 2048 192.168.2.235 10.10.10.23"
  "214 aero-prefect  4   8192  30 2048 192.168.2.236 10.10.10.24"
  "215 aero-agent    8  16384 100 2048 192.168.2.237 10.10.10.25"
  "216 aero-lit      4   8192 100 2048 192.168.2.238 10.10.10.26"
  "217 aero-vault    2   4096  20 2048 192.168.2.239 10.10.10.27"
)

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[provision] $*"; }

# ---------------------------------------------------------------- pre-flight
command -v pct   >/dev/null || die "pct not found — must run on the Proxmox host"
command -v pveam >/dev/null || die "pveam not found — must run on the Proxmox host"
[[ -f "$PUBKEY" ]] || die "SSH public key not found: $PUBKEY"
pveam list local | grep -q "ubuntu-24.04-standard_24.04-2" \
  || die "Ubuntu 24.04 template missing — pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst"

log "pre-flight: validating IDs and LAN IPs"
for entry in "${FLEET[@]}"; do
  read -r id name _ _ _ _ lan_ip _ <<<"$entry"
  if pct status "$id" >/dev/null 2>&1; then
    log "  LXC $id ($name) exists — create will be skipped"
  elif ping -c1 -W1 "$lan_ip" >/dev/null 2>&1; then
    die "LAN IP $lan_ip ($name) is in use but LXC $id does not exist — IP conflict, aborting"
  fi
done

# ----------------------------------------------------------- create + start
for entry in "${FLEET[@]}"; do
  read -r id name cores ram disk swap lan_ip priv_ip <<<"$entry"
  if pct status "$id" >/dev/null 2>&1; then
    log "LXC $id ($name) already exists — skipping create"
  else
    log "creating LXC $id ($name): ${cores}c ${ram}MB ${disk}GB rootfs  eth0=$lan_ip eth1=$priv_ip"
    pct create "$id" "$TEMPLATE" \
      --hostname        "$name" \
      --cores           "$cores" \
      --memory          "$ram" \
      --swap            "$swap" \
      --rootfs          "${STORAGE}:${disk}" \
      --net0            "name=eth0,bridge=${BRIDGE},ip=${lan_ip}/24,gw=${LAN_GW}" \
      --net1            "name=eth1,bridge=${BRIDGE},ip=${priv_ip}/24" \
      --nameserver      "$NAMESERVER" \
      --ostype          ubuntu \
      --unprivileged    1 \
      --features        nesting=1 \
      --onboot          1 \
      --tags            aero \
      --ssh-public-keys "$PUBKEY" \
      --description     "aero-research-platform Stage 02 — ${name}. Provisioned by scripts/provision_aero_lxc.sh; configured by ansible/. Do not hand-edit." \
      --start           0
  fi
  if [[ "$(pct status "$id" 2>/dev/null)" != "status: running" ]]; then
    log "starting LXC $id ($name)"
    pct start "$id"
  fi
done

# --------------------------------------------------- wait for SSH + keyscan
log "waiting for containers to accept SSH on port 22"
for entry in "${FLEET[@]}"; do
  read -r id name _ _ _ _ lan_ip _ <<<"$entry"
  ok=""
  for _ in $(seq 1 45); do
    if timeout 2 bash -c "exec 3<>/dev/tcp/${lan_ip}/22" 2>/dev/null; then ok=1; break; fi
    sleep 2
  done
  [[ -n "$ok" ]] || die "$name ($lan_ip) did not open port 22 within ~90s"
  ssh-keyscan -T 5 "$lan_ip" 2>/dev/null >>"$KNOWN_HOSTS" || true
  log "  $name reachable at $lan_ip"
done
[[ -f "$KNOWN_HOSTS" ]] && sort -u "$KNOWN_HOSTS" -o "$KNOWN_HOSTS"

log "provisioning complete — aero-* fleet:"
pct list | awk 'NR==1 || $0 ~ /aero-(build|dev|mlflow|vv|prefect|agent|lit|vault)/'
