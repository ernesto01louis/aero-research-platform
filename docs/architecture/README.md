# `docs/architecture/`

Architectural reference material for `aero-research-platform`.

- **Pass 1 — Architecture & Build Specification** lands here once the
  operator commits it. Canonical three-plane (control / compute /
  physics-ML) design covering the full solver fleet, ML layer,
  orchestration, provenance, and the 80-week phased roadmap.
- **Proxmox inventory** (`proxmox-inventory-YYYY-MM-DD.md`) — committed
  by Stage 02 from `/root/aero-inspect/proxmox-inventory-2026-05-16.md`
  on the host. Source of truth for what LXCs/VMs already exist on
  Homelab1 and what the aero stack may additively touch.
- **Proxmox topology** (`proxmox-topology.md`) — produced by Stage 02;
  table of aero-* LXCs vs reused services with planned-by-stage
  allocation.
- **SSH conventions** (`ssh-conventions.md`) — produced by Stage 02.
- **Backup interim policy** (`backup-interim.md`) — produced by Stage 02;
  documents the interim `vzdump` + TrueNAS-snapshot hedge while the
  operator's new NAS comes online.
- **FSI roadmap** (`fsi-roadmap.md`) — produced by Stage 11; sketches
  the deferred research directions (flapping wing, vibrating skin,
  conjugate heat transfer).

This directory is read by every stage prompt's "BEFORE YOU START — READ"
section as needed. Don't bury operational state here that belongs in
`docs/handoffs/`; this is *architecture* (slow-changing).
