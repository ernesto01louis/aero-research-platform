# STAGE-13: Multi-Cloud GPU Orchestration

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Compute targets and topology" and Pass 1 §"Compute &
orchestration plane":

- Three cloud-GPU backend adapters behind one `Executor` interface:
  RunPod, Lambda Labs, Vast.ai.
- A cost-aware router that selects the cheapest backend matching a job's
  constraints (GPU class, region, on-demand vs spot, reliability tier).
- The long-running CFD job pattern from Stage 02 generalized: `submit → poll →
  result` works across all three backends.
- The on-prem Slurm executor stub (for future cluster) interface-compatible but
  not implemented.
- Spot-eviction handling for Vast.ai (checkpoint + resume from MLflow).

## ROLE

You are turning the "minimal RunPod executor" from Stage 07 into a real multi-
cloud abstraction. Cost optimization, fault tolerance, and spot/on-demand
routing become first-class. From this stage on, jobs declare what they need;
the platform picks where they run.

## GOAL

1. Generalize the `Executor` interface at `aero/orchestration/_base.py`:
   - `Executor.submit(job: JobSpec) -> JobHandle`
   - `Executor.poll(handle: JobHandle) -> JobStatus`
   - `Executor.fetch_result(handle: JobHandle) -> ResultBundle`
   - `Executor.cancel(handle: JobHandle) -> None`
   - `JobSpec` (pydantic strict): GPU class (H100/A100/L40S/RTX4090/CPU),
     min memory, max wall-time, container SIF SHA256, command, input volumes,
     output paths, reliability tier (production / experiment / opportunistic)
2. Author concrete executors:
   - `aero/orchestration/runpod/` — full RunPod API (pod create, attach
     persistent volume, run command, fetch logs, terminate); replaces the
     Stage 07 minimal version
   - `aero/orchestration/lambda_labs/` — Lambda Cloud API for on-demand A100/
     H100 long-training
   - `aero/orchestration/vast/` — Vast.ai API for opportunistic RTX 4090 work,
     with spot-eviction handling
3. Author `aero/orchestration/router/`:
   - `cost_router.py` — given a JobSpec, queries live pricing from each
     backend (cached for 1 hour), selects the cheapest backend matching the
     constraints
   - Reliability-tier policy:
     - `production`: Lambda Labs or RunPod Secure Cloud only
     - `experiment`: any on-demand backend
     - `opportunistic`: any backend including Vast.ai spot
   - Cost cap: per-month ceiling enforced; jobs that would exceed fail loud
4. Author the on-prem Slurm executor stub at `aero/orchestration/slurm/`:
   - `Executor` interface implemented as a no-op + clear NotImplementedError
   - Placeholder so the architecture is ready for future on-prem cluster
5. Author the spot-eviction handler:
   - On Vast.ai job start, write a periodic checkpoint to MinIO (frequency
     based on job's wall-time estimate)
   - On eviction, the router auto-resubmits with `resume_from=<checkpoint>`
   - The resumed run shares an MLflow parent-run; the full provenance chain
     is preserved
6. Author Prefect 3 flows wrapping the executor for orchestration:
   - `aero/orchestration/flows/` — Prefect flow definitions for the V&V suite,
     surrogate training pipelines, UQ studies
   - Each flow uses the cost router by default; can be overridden per task
7. Refactor the V&V harness from Stages 05/06/07/12 to dispatch via the
   router rather than the LocalSSHExecutor. The TMR cases still run locally for
   speed; DPW/HLPW/scale-resolving fan out to cloud GPU.
8. Add `aero[orchestration]` extras: `prefect>=3.0`, `covalent`, the backend
   SDKs.
9. Add a `production-budget` CI check: any PR that introduces a new
   `tag=production` workflow must document the projected $-cost in the PR
   description (enforced by a workflow that greps the PR body).
10. Author ADR-013 documenting:
    - The three-backend choice and the spot-eviction handling design
    - The cost-router policy and how to tune it
    - The Slurm stub's reserved interface
    - The Prefect flow patterns the project uses
11. Update CLAUDE.md with the new "router-by-default, LocalSSHExecutor only
    for dev" rule.
12. Tag `v0.0.13`.

## WHY

A research platform that can only run on one cloud provider is a hostage to
that provider's pricing and availability. Pass 1's economic analysis showed
RunPod, Lambda, and Vast.ai cover three different value points (Secure on-
demand, long-training reliable, opportunistic cheap). The router exploits all
three.

The Slurm stub is cheap insurance: when the user eventually has an on-prem GPU
cluster, the interface is already shaped correctly. Retrofitting later is far
more expensive.

Spot-eviction handling is what makes Vast.ai viable at all. Without checkpoint
+ resume, a 24-hour training job has a meaningful probability of losing its
work; with it, evictions are a 5-minute delay.

## HOW

- Live pricing: each backend has a pricing API or scrapeable page. Cache for
  1 hour; refresh on cache miss. Don't query live for every submission.
- Checkpoint frequency for spot: heuristic — checkpoint every 30 minutes for
  jobs >2 hours; every 10 minutes for jobs >8 hours.
- Prefect flows: deploy to the `lxc-prefect` LXC from Stage 02. UI on VPN only.
- For consistent submission semantics across backends, normalize on a single
  container model: every job runs a single Apptainer SIF with a single
  command. The SIF is pulled at job start (cached on backend volume if available).
- Reliability-tier enforcement: implement as a hard guard in the router; a
  `production`-tier job will refuse to route to Vast.ai even if it's cheapest.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-13-multicloud-gpu-orchestration.md` (this file)
- `docs/handoffs/STAGE-12-*-DONE-*.md`
- ADR-007 (Stage 07's minimal RunPod executor), ADR-012 (production-tag UQ
  requirement)
- Pass 1 §"Compute & orchestration plane"

## GUARDRAILS — DO NOT

1. Do NOT auto-route `production`-tier jobs to spot/preemptible backends.
   Reliability-tier policy is structural.
2. Do NOT hardcode credentials anywhere. Vault for all three backends.
3. Do NOT bypass the cost cap. If a routed job would exceed the monthly
   ceiling, fail loud.
4. Do NOT remove the LocalSSHExecutor. Dev workflows still use it.
5. Do NOT implement the Slurm executor body. Stub only.
6. Do NOT skip spot-eviction tests. Simulate an eviction (kill the pod) and
   verify resume works.

## DELIVERABLES

- [ ] All three concrete executors implemented and tested
- [ ] Cost router selects cheapest backend respecting reliability tier
- [ ] Spot-eviction + resume verified end-to-end on Vast.ai
- [ ] Prefect flows wrap the executor; V&V suite runs via flows
- [ ] DPW/HLPW workflow fans out via router
- [ ] Slurm stub present and raises NotImplementedError cleanly
- [ ] `production-budget` PR check active
- [ ] ADR-013 committed
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.13`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- Provisioning credentials for Lambda Labs and Vast.ai (Vault paths)
- The monthly cost ceiling (e.g., $200/month for the full platform; operator
  picks)
- The reliability-tier mapping (proposed defaults above)
- Marking `production-budget` as a required check

## POST-STAGE HANDOFF

Required emphases:

- **Cost-router policy table**: per-tier backend allowlist, with rationale.
- **Spot-eviction test result**: log the eviction, the resume, and the
  preserved provenance chain.
- **Backend $-comparison** for a representative job (e.g., one DoMINO training
  run): wall-clock × $/hr per backend.
- **Open items for Stage 14**: the agent layer wraps the executor; MCP tools
  for "submit a job" should expose the JobSpec cleanly.
- **Gotchas**: API quirks per backend, Apptainer SIF pull caching, persistent-
  volume edge cases.
