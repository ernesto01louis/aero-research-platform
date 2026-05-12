# RUNBOOK — aero-research-platform

Operational recipes for running campaigns through this consumer.

## Pre-flight

Before any campaign launch, verify:

| Check | Command |
|---|---|
| Orchestrator REST is up | `curl -fsS $ORCHESTRATOR_URL/health` returns `{"status":"ok"}` |
| **Prefect is up** (mandatory — audit D.3) | `curl -fsS http://192.168.2.182:4200/api/health` returns `true` |
| `deploy_target: aero-research` exists in orchestrator config | `curl -fsS $ORCHESTRATOR_URL/targets | jq '.targets[] | select(.name=="aero-research")'` returns a row |
| Aero LXC (CT 207) is reachable | `ssh -i /root/.ssh/id_ed25519_aero_target aero@192.168.2.231 'uname -a'` |

If Prefect is down the orchestrator silently falls back to a degraded
in-process execution path (`.fn` invocation) that bypasses the state
hooks populating `LLM_CALL_LOG` — so the resulting evidence bundle
will not have citation-grade fidelity. **Don't post campaigns when
Prefect is unhealthy.**

## Run a campaign via the SDK

```python
# scripts/run_campaign.py (sketch — landing properly in a future commit)
from pathlib import Path
import os, yaml
from ai_orchestrator_client import (
    BearerTokenAuth, CampaignCreate, OrchestratorClient,
)

template_path = Path("campaigns/01-naca0012-baseline.yaml")
data = yaml.safe_load(template_path.read_text())
request = CampaignCreate(**data)

token = os.environ.get("ORCHESTRATOR_TOKEN")
auth = BearerTokenAuth(token) if token else None

with OrchestratorClient(
    base_url=os.environ.get("ORCHESTRATOR_URL", "http://127.0.0.1:8000"),
    auth=auth,
) as client:
    ack = client.start_campaign(request)
    print(f"campaign_id={ack.campaign_id} run_count={ack.run_count}")

    campaign = client.get_campaign(ack.campaign_id)
    for run in campaign.iter_runs(client):
        print(f"  {run.run_id}  {run.params}  {run.phase}")

    verify = client.verify_campaign_merkle(ack.campaign_id)
    assert verify.valid, verify
```

## Run a campaign via raw REST (fallback)

When you don't have the SDK installed — e.g. on a Pi or a colleague's
laptop — drive the API with `curl`. The one-liner below converts a YAML
file to JSON and POSTs it:

```sh
python -c "import yaml,json; print(json.dumps(yaml.safe_load(open('campaigns/01-naca0012-baseline.yaml'))))" \
  | curl -s -X POST $ORCHESTRATOR_URL/campaigns \
      -H 'content-type: application/json' \
      ${ORCHESTRATOR_TOKEN:+-H "authorization: Bearer $ORCHESTRATOR_TOKEN"} \
      -d @-
```

Then poll:

```sh
curl -s $ORCHESTRATOR_URL/campaigns/<campaign_id>/tree | jq .
curl -s $ORCHESTRATOR_URL/campaigns/<campaign_id>/verify-merkle | jq .
```

## Known orchestrator-side behaviors to plan around

These are not bugs — they are deliberate orchestrator choices documented
in `/opt/ai-orchestrator/CLAUDE.md` and in `STAGE-2-OUTPUTS.md`. The
aero campaigns are designed around them.

### `budget_total_usd` current behavior

All three Phase-1 campaign YAMLs set `budget_total_usd: 0.0` at the top
level (per the design brief). **This is currently a no-op on the live
orchestrator** for two reasons:

1. The SDK's `CampaignCreate.model_config` is `ConfigDict(extra="ignore")` —
   any top-level field that isn't in the Pydantic model is silently
   dropped during validation.
2. Even if the field were passed through, `core/budget.py` treats
   `<=0` as "no limit / unlimited" and uses `None` for "no cap set".

So the line documents intent — *we expect these campaigns to cost
zero USD because they route through local Ollama* — but does not
enforce anything today. If a real cap becomes necessary (e.g. when a
campaign starts routing through paid providers), file an issue against
ai-orchestrator to add `budget_total_usd` to `CampaignCreate.model_validate`.
**Do not** patch around this on the consumer side.

### `environment_inspector` is not venv-aware (Stage 2 deviation #5)

The orchestrator's environment-inspector calls `pip list` against the
default Python interpreter — on CT 207 that's `/usr/bin/python3.11`,
**not** `/opt/aero-venv/bin/python`. If a campaign needs the
orchestrator to introspect the aero stack (PhysicsNeMo / PyTorch /
CadQuery / pymoo / etc.), the planner's prompt or the generator's
preamble must explicitly activate the venv before `pip list`:

```sh
source /opt/aero-venv/bin/activate
```

The orchestrator's auto-generated `run.sh` wrapper does NOT activate
venvs. Stage 4's first real campaign should bake the activation into
either the prompt or a small `scripts/preamble.sh` that's invoked from
the planner's output.

### `persistent_deploy` keys by `project_name` (Stage 2 deviation #4)

Different runs against the same `project_name` overwrite each other's
deploy directory at `/home/aero/ai-projects/<project_name>/`. All
three Phase-1 campaign YAMLs already discriminate by a unique-per-run
param:

| Campaign | `project_name` pattern | Discriminator |
|---|---|---|
| 01 | `naca0012-baseline-{aoa}` | `aoa` |
| 02 | `flat-plate-riblet-{s_plus}-h{h_over_s}` | `(s_plus, h_over_s)` |
| 03 | `naca0012-riblet-{s_plus_target}` | `s_plus_target` |

When adding new campaigns, include a unique discriminator. Otherwise
the second run scribbles over the first.

### `OrchestrateRequest` does not accept `language` or `hitl_mode` (Stage 2 deviation #1)

`hitl_mode` lives on `CampaignTemplate`, not on per-run `OrchestrateRequest`.
All three Phase-1 YAMLs set `hitl_mode: gate_only` at the
`template:` level — that's correct. Don't try to thread `hitl_mode`
through `/orchestrate` directly.

`language` is inferred by the planner from the prompt; don't fight it.
The three current campaigns aren't language-constrained (they describe
OpenFOAM cases, not Python scripts), so the planner has full latitude
to choose between bash/python/etc.

## Activate evidence/ entry points (Stage 5/6)

The pluggy entry points declared in `pyproject.toml` only become live
once the orchestrator's Python env can `import aero_research_platform`.
On the orchestrator LXC, with the orchestrator's venv active:

```sh
pip install -e /opt/aero-research-platform
sudo systemctl restart ai-orchestrator
```

Then any subsequent `evidence.builder.build_bundle(campaign_id)` call
will discover `aero_metrics.hook` and `riblet_drag_reduction.hook` and
include their `CalculatorResult` entries in the bundle's
`calculators[]` array.

Today both hooks return `[]`. Stage 5/6 fills them in.

## Stage 4 — re-run the NACA 0012 baseline validation

The Stage-4 smoke pipeline lives entirely in `scripts/smoke_naca0012.py`.
It pre-flights Prefect, the orchestrator REST, the aero target, the YAML
SDK round-trip, and template staging, then POSTs `/campaigns` and writes
`results/01-naca0012-baseline/run-log.json`.

Full sequence to re-run from scratch:

```sh
# 1. Push the case template + Python package to the aero LXC.
scripts/push_templates.sh aero-research

# 2. Launch the campaign (does pre-flight first; --no-launch dry-runs).
scripts/smoke_naca0012.py
# or:  scripts/smoke_naca0012.py --no-launch    # to verify only

# 3. Poll progress.
CAMP=$(jq -r '.latest.campaign_id' results/01-naca0012-baseline/run-log.json)
curl -s http://127.0.0.1:8000/campaigns/$CAMP/tree | jq '{status: .campaign.status, runs: [.runs[] | {id, params, status, score}]}'

# 4. After both runs reach status="completed", pull artifacts:
for aoa in 0 10; do
    mkdir -p results/01-naca0012-baseline/aoa-$aoa
    scp -i /root/.ssh/id_ed25519_aero_target -r \
        aero@192.168.2.231:/home/aero/ai-projects/naca0012-baseline-$aoa/runs/'*'/postProcessing \
        results/01-naca0012-baseline/aoa-$aoa/
done

# 5. Verify the evidence bundle.
python -m evidence.verify --crate-dir /opt/ai-orchestrator/campaigns/$CAMP/

# 6. Render the validation notebook and inspect PASS/FAIL.
jupyter nbconvert --to notebook --execute notebooks/01-validation-naca0012.ipynb
cat results/01-naca0012-baseline/results.csv
```

### Stage-4 mesh-design deviations from the brief

Two production deviations recorded here (and in
`STAGE-4-OUTPUTS.md`) so reviewers see them before reading the source:

1. **snappyHexMesh instead of structured 897×257 C-grid.** The brief
   asks for a NASA-TMR Family-I-equivalent structured C-grid. After a
   gmsh transfinite-with-boundary-layer-field spike could not coax more
   than a few thousand cells out regardless of size-field tuning, we
   pivoted to OpenFOAM-canonical snappyHexMesh: a rectangular hex
   background mesh, surface refinement levels 6–7 on the airfoil, and
   30 prism layers tuned for y+ < 1 at Re=6e6. Produces 100k+ hex-
   dominant cells with NASA-TMR-equivalent wall resolution.
2. **100c farfield instead of 500c.** Background hex cells at 500c span
   were too coarse to cut a 1c airfoil — castellatedMesh refined zero
   cells. 100c is well-established in the literature for NACA 0012
   incompressible RANS (blockage < 0.5% for Cl at this Re/AoA per
   `tutorials/airFoil2D` and Schlichting & Truckenbrodt 1969).

### Why HITL mode is `gate_only`, not `full_auto`

Audit B.4 — campaign-level `hitl_mode` overrides the orchestrator's
`config.json` default. We need `gate_only` so the orchestrator pauses
on a Gates denial (Phase 3.1 HITL) but otherwise runs unattended. A
gate denial typically means the LLM-generated command looks like a
filesystem-destructive operation; the operator approves or rejects via
the notification action button. **Don't flip to `full_auto`** to "save
time" — Gates is what protects the LXC from a malformed run.sh.

## TrueNAS NFS mount on the aero LXC (deferred from Stage 1)

Stage 1's brief originally bundled a TrueNAS NFS mount onto CT 207 at
`/mnt/aero`; it was deferred so Stage 1 wouldn't require TrueNAS UI
access. CT 207 has `nfs-common` installed and `/mnt/aero` exists as
an empty placeholder. To activate:

1. **On TrueNAS** (`192.168.2.222`): create dataset `tank/aero`, user
   `aero-research`, NFS export to `192.168.2.231`.
2. **On CT 207** (`192.168.2.231`):
   ```sh
   echo "192.168.2.222:/mnt/tank/aero  /mnt/aero  nfs  defaults,_netdev,nofail  0  0" \
     | sudo tee -a /etc/fstab
   sudo mount -a
   df -h /mnt/aero
   ```

Independent of this repo's purpose — handle whenever convenient. The
aero campaigns can write to `/home/aero/ai-projects/<project>/` on
local storage in the meantime.
