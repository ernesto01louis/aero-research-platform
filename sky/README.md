# sky/ — SkyPilot YAML specs

Placeholder. Stage 4+ lands:

- `openfoam-cpu.yaml` — CPU burst for OpenFOAM cases too large for the on-prem aero LXC.
- `train-fno.yaml` — A100 burst for PhysicsNeMo FNO training.
- `train-mgn.yaml` — A100 burst for MeshGraphNet training.

The orchestrator's Phase 2.5 `core.sky` wrapper consumes these via
`POST /runs/{run_id}/burst` (per-burst USD ceiling enforced; idle-stop
daemon kills clusters after `sky.idle_timeout_minutes`).

See [RUNBOOK.md](../RUNBOOK.md) for the operational flow once specs land.
