# scripts/ — operator bash + Python utilities

Placeholder. Stage 4+ lands:

- `bootstrap_lxc.sh` — re-runnable provisioning hook on the aero LXC.
- `register_with_orchestrator.py` — one-shot SDK call that confirms
  `deploy_target=aero-research` is wired and reachable.
- `smoke_naca0012.py` — minimal end-to-end SDK roundtrip against the
  first campaign's params for `aoa=0`.

Treat scripts/ as glue between the YAMLs in `campaigns/` and the
orchestrator's public surface. Domain logic lives in the
`aero_research_platform/` package; scripts orchestrate.
