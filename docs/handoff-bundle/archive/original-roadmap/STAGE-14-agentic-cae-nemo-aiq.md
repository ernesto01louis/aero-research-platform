# STAGE-14: Agentic CAE — NeMo Agent Toolkit + AI-Q Blueprint

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"Agentic CAE" and Pass 1 §"Agentic CAE layer" and
Pass 2 §10 (agentic CFD: ChatCFD 82.1%, MetaOpenFOAM, OpenFOAMGPT, Foam-Agent 2.0):

- NVIDIA NeMo Agent Toolkit (`nvidia-nat`) deployed on `aero-agent` LXC.
- A fork of NVIDIA's AI-Q Blueprint adapted for CAE workflows (the upstream
  blueprint is research-focused; the fork narrows it to engineering design
  agents).
- MCP tools wrapping every solver, mesher, V&V primitive, UQ study, surrogate,
  and orchestration primitive in the platform — so the agent can compose
  workflows by calling typed tools rather than generating brittle shell
  commands.
- The certificate-of-validity gate from Stage 08 enforced at the tool level:
  surrogate-invocation tools refuse to run with an expired certificate.
- CAEBench harness — a small benchmark suite of design tasks (e.g., "minimize
  Cd for an airfoil at fixed Cl") that the agent attempts; success rate is
  tracked over time.

## ROLE

You are wrapping the working platform in an agentic interface. The platform's
solvers, surrogates, V&V, and orchestration are now exposed as typed tools that
an LLM agent can compose. This is the layer that makes "autonomous design" a
real capability — but only because everything beneath it (provenance,
certificates, V&V) makes the agent's outputs trustworthy.

## GOAL

1. Provision NVIDIA NeMo Agent Toolkit on `aero-agent`:
   - Install `nvidia-nat` (latest 1.5.x or current); pin version
   - Configure the runtime to point at the project's MLflow + Postgres for
     observability
   - Set up auth: agent runs under a dedicated user with scoped credentials
2. Fork NVIDIA's AI-Q Blueprint at `aero/agentic/aiq_fork/`:
   - Take the upstream blueprint as a starting point
   - Strip components not relevant to CAE (e.g., generic chat surfaces)
   - Add CAE-specific workflow templates: shape optimization, V&V triage,
     literature-informed hypothesis generation
3. Author MCP tool wrappers at `aero/agentic/mcp_tools/`:
   - `solver_tools.py` — one tool per solver (`run_openfoam`, `run_su2`, etc.),
     each accepting a typed `CaseSpec` and returning a typed result handle
   - `surrogate_tools.py` — `predict_with_moe`, plus per-surrogate tools; ALL
     check `CertificateOfValidity` before predicting and refuse on expired/
     out-of-envelope inputs
   - `vv_tools.py` — `run_vv_case`, `get_vv_dashboard`, `compare_solvers`
   - `uq_tools.py` — `run_uq_study` with the UQpy/Dakota interface from Stage 12
   - `orchestration_tools.py` — `submit_job` via the cost-routed executor from
     Stage 13
   - `provenance_tools.py` — `query_runs_by_tag`, `get_four_tuple_for_run` —
     READ-ONLY access via the `provenance_reader` Postgres role
4. Author the CAE workflow templates at `aero/agentic/workflows/`:
   - `shape_optimization.py` — agent loop: propose geometry → run CFD → check
     V&V envelope → if outside, escalate; if inside, accept → optimize
   - `vv_triage.py` — when a V&V case fails, agent investigates and proposes
     a hypothesis (mesh issue, BC issue, solver-version drift, etc.)
   - `literature_informed_hypothesis.py` — agent reads recent arXiv via the
     Stage 15 literature pipeline (deferred dependency) and proposes
     experiments — stub for now, fleshes out in Stage 15
5. Author CAEBench at `aero/agentic/benchmark/`:
   - A small set of design tasks with measurable success criteria (e.g.,
     "design an airfoil with Cd < 0.012 and Cl > 0.4 at Mach 0.7, Re=6e6")
   - Harness runs the agent against each task, records success/failure +
     wall-clock + $-cost
   - Dashboard tracks success rate over time as the agent's tools improve
6. Add `aero[agentic]` extras: `nvidia-nat`, `langgraph`, `mcp`, plus the MCP
   server framework the project uses.
7. Add a "no agent in production without human-in-the-loop" rule: the agent
   can submit `experiment`-tier and `opportunistic`-tier jobs autonomously,
   but `production`-tier jobs require explicit human approval via a Prefect
   pause-and-resume pattern.
8. Author ADR-014 documenting:
   - The NeMo Agent Toolkit version pin and update policy
   - The AI-Q Blueprint fork's divergence from upstream
   - The MCP tool surface (one section per tool category)
   - The human-in-the-loop gate for production-tier jobs
   - The CAEBench design philosophy and current success-rate baseline
9. Update CLAUDE.md with the agentic layer's invariants:
   - "Every agent tool is typed; no free-form shell access"
   - "Production-tier jobs require human approval"
   - "Surrogate calls always check certificates"
10. Tag `v0.0.14`.

## WHY

The agentic layer is what differentiates this platform from a "pile of solver
scripts." Pass 2 §10 shows agentic CFD is real and improving fast — ChatCFD's
82.1% success rate on certain task classes, Foam-Agent 2.0, MetaOpenFOAM. The
platform's job is to give the agent typed tools (not bash) so it inherits the
platform's provenance, certificates, V&V, and UQ guarantees.

The AI-Q Blueprint fork rather than a from-scratch agent: NVIDIA has done the
hard parts (planner, memory, MCP integration). We adapt it to CAE rather than
reinventing.

CAEBench is how the platform tracks whether the agent layer is actually
getting smarter over time — without it, agentic claims are vibes.

The certificate gate inside the MCP tool is the structural enforcement of "ML
augments, never replaces, validated physics." A misbehaving surrogate cannot
be silently called by the agent; the tool refuses.

## HOW

- NeMo Agent Toolkit deployment: follow the upstream docs precisely; pin
  exactly. The toolkit is evolving fast; expect breaking changes between
  versions.
- MCP tools: use the official MCP Python SDK. Each tool gets a clear
  description (LLMs select tools by description match) and typed input/output
  schemas (pydantic strict).
- Tool descriptions matter enormously for selection quality. Run a small
  evaluation: ablate the description, check selection accuracy on a fixed
  task set.
- Human-in-the-loop for production: Prefect supports
  `prefect.runtime.pause` pattern. The agent submits the job through Prefect;
  Prefect pauses on `tag=production` and surfaces a manual-approval task to
  the operator.
- CAEBench tasks: start small (5-10 tasks). Add tasks over time as the agent's
  tool surface grows.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md`
- `STAGE-14-agentic-cae-nemo-aiq.md` (this file)
- `docs/handoffs/STAGE-13-*-DONE-*.md`
- ADR-008 (certificate framework), ADR-013 (executor + cost router)
- Pass 1 §"Agentic CAE layer"
- Pass 2 §10 (agentic CFD SOTA: ChatCFD, MetaOpenFOAM, Foam-Agent 2.0)
- NeMo Agent Toolkit release notes for the chosen version

## GUARDRAILS — DO NOT

1. Do NOT expose any tool that bypasses the certificate check on surrogates.
2. Do NOT give the agent free-form shell access. Every action is a typed tool.
3. Do NOT allow the agent to submit `production`-tier jobs without HITL.
4. Do NOT use `latest` for the NeMo Agent Toolkit pin. Pin a specific version
   with the rationale in ADR-014.
5. Do NOT skip CAEBench. Without the baseline, no claim about "agent improved"
   is testable.
6. Do NOT hardcode the agent's LLM choice. Make it a config field; the operator
   may swap between Claude/GPT/local.

## DELIVERABLES

- [ ] NeMo Agent Toolkit running on `aero-agent` LXC
- [ ] AI-Q Blueprint fork at `aero/agentic/aiq_fork/`, divergent commits
      documented in ADR-014
- [ ] All six MCP tool categories implemented; tools selectable by description
- [ ] Surrogate tools enforce certificate gate (tested)
- [ ] Production-tier HITL gate working via Prefect pause/resume
- [ ] CAEBench harness with at least 5 design tasks; baseline success rate
      recorded
- [ ] `pip install -e .[agentic,dev]` works
- [ ] ADR-014 committed
- [ ] CLAUDE.md updated with agentic-layer invariants
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.14`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- The NeMo Agent Toolkit version pin
- Provisioning the agent's LLM API credentials (Vault)
- The initial CAEBench task set (operator picks; should reflect actual
  research priorities)
- Enabling the agent to actually submit jobs (start with a dry-run mode that
  shows what *would* be submitted)

## POST-STAGE HANDOFF

Required emphases:

- **CAEBench baseline**: per-task success/failure + wall-clock + $-cost.
- **MCP tool descriptions** — paste the descriptions verbatim; these are
  load-bearing for selection quality.
- **HITL flow demonstration**: one production-tier job that paused, got
  approved, and resumed.
- **Open items for Stage 15**: the `literature_informed_hypothesis` workflow
  is stubbed pending the literature pipeline.
- **Open items for Stage 16**: docs polish needs to cover the agent interface
  prominently — this is the user-facing layer.
- **Gotchas**: NeMo Agent Toolkit gotchas, MCP server registration quirks,
  Prefect pause/resume edge cases.
