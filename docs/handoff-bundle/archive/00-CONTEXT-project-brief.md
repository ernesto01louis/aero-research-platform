# 00-CONTEXT: aero-research-platform — Project Brief

**Paste this file alongside every STAGE-NN prompt. It is the distilled set of
invariants Claude Code needs to know on every session. Do not re-explain it in stage
prompts; reference it.**

---

## What we are building

`aero-research-platform` — a fully open-source, peer-review-grade, hardware-agnostic
research platform for computational aerodynamics. Operator: Ernesto Louis. Primary
implementer: Claude Code, working session-by-session against the staged handoff bundle.

End state spans:

1. **Solver fleet**: OpenFOAM-ESI, SU2 v8, PyFR, NekRS, JAX-Fluids 2.0, DAFoam.
2. **ML layer**: NVIDIA PhysicsNeMo (DoMINO, Transolver, FIGConvNet, X-MeshGraphNet),
   Mixture-of-Experts gating, certificate-of-validity framework.
3. **Coupling**: preCICE 3 for FSI (flapping wing, vibrating skin) and CHT.
4. **Agentic CAE**: NVIDIA NeMo Agent Toolkit + fork of AI-Q Blueprint.
5. **V&V + UQ**: NASA TMR, AIAA DPW-7/HLPW-5, ERCOFTAC; UQpy + Dakota.
6. **Orchestration**: Prefect 3 (outer pipelines) + Covalent (heterogeneous executor)
   over Proxmox LXC, RunPod, Lambda Labs, Vast.ai.
7. **Provenance**: DVC + MLflow + Postgres + MinIO + Apptainer SIF SHA256.
8. **Literature mining**: arXiv + Semantic Scholar + OpenAlex via pgvector.

The architecture, SOTA, and best-practices documents (Passes 1–3) are the canonical
deep references. This brief is the *daily-driver context*.

## Five non-negotiable principles

1. **Reproducibility first.** Every published number traces to (git SHA, DVC hash,
   Apptainer SIF SHA256, config hash). No exceptions.
2. **Compute is fungible.** No code path may assume a specific backend.
3. **Solvers are containers.** Apptainer SIFs for HPC, OCI images for cloud, digests
   in the provenance record.
4. **ML augments, never replaces, validated physics.** Surrogates ship only with a
   published certificate of validity.
5. **GPL is fine.** GPL-3 / LGPL-3 / Apache-2.0 / BSD-3 only. No proprietary blobs.

## Hard rules (immutable; override any conflicting stage prompt)

1. **PLATFORM-NOT-HUB.** `aero/` core imports only stdlib + numpy + pydantic.
2. **FAIL-LOUD.** Pydantic strict (`extra='forbid'`). No silent fallbacks.
3. **PROVENANCE FROM DAY ONE.** Every run logs the four-tuple to MLflow tags.
4. **CONVENTIONAL COMMITS + CONVENTIONAL COMMENTS.** Format
   `<type>(<stage-NN>): <subject>`.
5. **PROPOSE FIRST, EXECUTE LATER** for destructive ops. Wait for the literal word
   `approved`.
6. **NO `--no-verify`, NO `--dangerously-skip-permissions`** outside ephemeral
   containers.
7. **NO SECRETS** in code, CLAUDE.md, handoffs, commits, MLflow tags, or PR
   descriptions.
8. **PIN HEAVY DEPS** exactly; document every pin in an ADR.
9. **DOCS MATCH REALITY.** README `## Status` auto-regenerated from latest handoff.
10. **POST-STAGE HANDOFF MANDATORY.** No `v0.0.NN` tag without
    `docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md`.
11. **DO NOT TOUCH PRE-EXISTING NON-AERO INFRASTRUCTURE.** The Proxmox host runs many
    other workloads (LXCs 101–207 except where listed below, VMs 100/104/111/112).
    The aero stack provisions its own NEW `aero-*` LXCs and SHARES read/write access
    only to the small explicitly-listed set of application-agnostic services
    (existing Postgres LXC 202, Grafana LXC 205, Tempo LXC 204, Redis LXC 203,
    TrueNAS VM 104 via NFS). Nothing in the existing fleet may be reconfigured,
    restarted, or repurposed without explicit user approval.

## Repository layout

```
aero-research-platform/
├── CLAUDE.md                          # Claude Code instructions, loaded every session
├── AGENTS.md                          # → see CLAUDE.md (cross-tool compat redirect)
├── CONSTITUTION.md                    # Non-negotiables in spec-kit form
├── README.md                          # Public-facing; ## Status auto-regenerated
├── CITATION.cff                       # Zenodo / software citation
├── CHANGELOG.md                       # One section per v0.0.NN stage tag
├── CONTRIBUTING.md                    # Conventional Commits/Comments, PR workflow
├── SECURITY.md                        # Secret handling, threat model
├── LICENSE                            # AGPL-3.0 or GPL-3.0 (operator's pick at Stage 01)
├── pyproject.toml                     # uv-managed, all extras enumerated
├── .pre-commit-config.yaml
├── .github/                           # workflows, CODEOWNERS, issue/PR templates
├── .claude/                           # rules, agents, skills, commands, settings
├── aero/                              # platform core (stdlib + numpy + pydantic ONLY)
│   ├── adapters/                      # openfoam, su2, pyfr, nekrs, jax_fluids, precice
│   ├── surrogates/                    # _common, domino, transolver, figconvnet, moe
│   ├── orchestration/                 # runpod, lambda_labs, vast, slurm (stub)
│   ├── vv/                            # tmr, dpw, hlpw, ercoftac, scale_resolving, fsi
│   ├── uq/                            # UQpy + Dakota wrappers
│   ├── provenance/                    # DVC/MLflow/Postgres/SIF glue
│   ├── agentic/                       # NeMo Agent Toolkit + AI-Q fork
│   └── literature/                    # arXiv/Semantic Scholar/pgvector
├── containers/                        # Apptainer .def files + SHA256SUMS
├── data/                              # DVC-tracked references and meshes
├── tests/                             # unit, stage_NN, vv
├── dvc.yaml
├── ansible/                           # Proxmox provisioning (Stage 02)
├── docs/
│   ├── handoffs/                      # post-stage handoffs + _template.md
│   ├── adrs/                          # _template.md + ADR-002 onward
│   ├── architecture/                  # Pass 1 doc + Proxmox inventory
│   ├── sota/                          # Pass 2 doc
│   └── handoff-bundle/                # the bundle itself
└── scripts/
```

## Optional extras

Defined in `pyproject.toml`. Base `pip install aero` pulls only `numpy`, `pydantic`,
`typer`, `loguru`, `dvc`. Heavy deps live here:

| Extra | Includes |
|---|---|
| `aero[openfoam]` | pyfoam, Ofpp |
| `aero[su2]` | SU2 Python wrapper, mpi4py |
| `aero[pyfr]` | pyfr (gmsh, h5py, mako) |
| `aero[nekrs]` | nekrs Python bindings if available |
| `aero[jax-fluids]` | jax-fluids, jaxlib (CUDA version) |
| `aero[physicsnemo-cu12]` | nvidia-physicsnemo[cu12], pyg, warp-lang |
| `aero[precice]` | pyprecice |
| `aero[gpu-rental]` | runpod, lambdalabs, vast-python |
| `aero[uq]` | UQpy, chaospy, salib, pyDOE3 |
| `aero[agentic]` | nvidia-nat (NeMo Agent Toolkit), langgraph, mcp |
| `aero[literature]` | semanticscholar, arxiv, sentence-transformers, pgvector |
| `aero[orchestration]` | prefect, covalent |
| `aero[dev]` | ruff, mypy, pytest, pytest-cov, pytest-xdist, pre-commit, gitleaks |
| `aero[docs]` | mkdocs, mkdocs-material, mkdocstrings |

## Compute targets and topology (revised per Proxmox inventory 2026-05-16)

### Existing Proxmox host (no changes to its baseline)

AMD Ryzen 9 9955HX (16C/32T), 92 GiB RAM, ~2.1 TB free on `Storage` (4 TB NVMe),
**iGPU only — no discrete GPU**, Proxmox VE 9.1.11 on Debian 13 trixie. Tailscale +
headscale + CrowdSec on the host. Many unrelated existing LXCs/VMs — leave them
alone.

### Existing infrastructure the aero stack reuses additively

| LXC / VM | Existing purpose | Aero use | First-used stage |
|---|---|---|---|
| LXC 202 `postgres-server` | shared Postgres | New `aero_provenance` DB + `pgvector` extension if missing | Stage 04 |
| LXC 203 `redis-server` | shared Redis | Stage 14 agent cache (optional) | Stage 14 |
| LXC 204 `tempo-server` | Grafana Tempo | Stage 14 agent OpenTelemetry traces | Stage 14 |
| LXC 205 `grafana-server` | dashboards | New aero V&V dashboards | Stage 05 |
| **VM 104 `TrueNAS`** | shared storage | Dedicated NFS dataset `aero/` for DVC remote, MLflow artifacts (NFS-backed MinIO), bulk datasets, container SIF library | Stage 02 |

LXC 201 `prefect-server` is **not** reused; a fresh `aero-prefect` keeps the aero
orchestration plane decoupled.

### New aero-* LXCs (provisioned in Stage 02 unless noted)

On the existing internal `10.10.10.0/24` bridge, alongside the existing
`ai-orchestrator` LXC 200.

| LXC | Cores | RAM | Disk | Purpose | First used |
|---|---:|---:|---:|---|---|
| `aero-build` | 8 | 16 GB | 200 GB | Apptainer SIF builds, GH Actions self-hosted runner | Stage 02 |
| `aero-dev` | 16 | 32 GB | 300 GB | Dev work, JupyterLab, ParaView, mesh prep | Stage 02 |
| `aero-mlflow` | 4 | 8 GB | 50 GB (artifacts on NFS) | MLflow tracking + MinIO sidecar (NFS-backed) | Stage 04 |
| `aero-vv` | 16 | 32 GB | 200 GB | V&V case runner (CPU CFD) | Stage 05 |
| `aero-prefect` | 4 | 8 GB | 30 GB | Aero-scoped Prefect 3 server | Stage 13 |
| `aero-agent` | 8 | 16 GB | 100 GB | NeMo Agent Toolkit runtime | Stage 14 |
| `aero-lit` | 4 | 8 GB | 100 GB | Literature ingestion pipeline | Stage 15 |

Resource ceilings are intentionally generous per operator preference. Total aero
disk footprint: ~1 TB on `Storage` (out of ~2.1 TB free).

### Compute backends for heavy work

**All GPU work is rented.** No discrete GPU on the Proxmox host; no plans to add
one. Every surrogate training and every GPU-resident CFD run uses cloud GPU. The
multi-cloud executor in Stage 13 is therefore **central**, not optional.

- **RunPod (primary)** — H100 PCIe ~$2.39/hr (Secure Cloud), H100 SXM ~$2.99/hr,
  Community Cloud ~$1.99/hr. Zero egress fees.
- **Lambda Labs (long jobs)** — A100 40GB ~$1.29/hr, 80GB ~$1.79/hr.
- **Vast.ai (opportunistic)** — RTX 4090 ~$0.27/hr for dev/inference benchmarking;
  spot-eviction handling in Stage 13.
- **On-prem (Proxmox LXCs)** — CPU-only work: small TMR V&V cases, JAX-Fluids 2D
  smoke, mesh prep, all dev/build.

Default monthly cost cap for cloud GPU CI: **$50**. Documented in ADR-007.
Production-tier or large training runs are operator-approved per-run.

### Networking

- Aero LXCs sit on **`10.10.10.0/24`** alongside the existing `ai-orchestrator`
  LXC 200. MASQUERADE'd out of `vmbr0` for external egress.
- No new VLAN/SDN needed.
- Operator access via existing Tailscale.

### Storage layout

- `Storage` (host ext4 on 4 TB NVMe, ~2.1 TB free) — backing for aero LXC rootfs.
- **TrueNAS VM 104 via NFS** — single dedicated dataset `aero/` with:
  - `aero/dvc-remote/` for DVC content storage
  - `aero/mlflow-artifacts/` for MLflow run artifacts (backing for the MinIO sidecar
    in `aero-mlflow`)
  - `aero/datasets/` for AhmedML, WindsorML, DrivAerML, DrivAerNet++
  - `aero/containers/` for the Apptainer SIF library
- Local DVC cache on `aero-dev` and `aero-vv` for hot working data.

### Backups (operator-managed sysadmin task, in parallel with the build)

Operator is provisioning a NAS for backups. Until that lands, interim hedge:
nightly `vzdump` of aero-* LXCs + nightly TrueNAS `aero/` snapshots. Stage 02
verifies the interim hedge before declaring complete. **This is sysadmin work
the operator owns**, not a Claude Code deliverable.

## V&V benchmark set (canonical)

| Source | Case(s) | Used by |
|---|---|---|
| NASA Turbulence Modeling Resource | 2D flat plate, 2D bump, NACA 0012, 2D multi-element airfoil | Stage 05, 12 |
| AIAA Drag Prediction Workshop (DPW-7) | NASA CRM | Stage 12 |
| AIAA High Lift Prediction Workshop (HLPW-5) | CRM-HL | Stage 12 |
| ERCOFTAC | Backward-facing step, periodic hill, square cylinder | Stage 12 |
| Open ML-CFD datasets | AhmedML, WindsorML, DrivAerML (CC-BY-SA); DrivAerNet++ (CC-BY-NC, quarantined) | Stages 09–10 |

**License note**: DrivAerNet++ is CC-BY-NC. Quarantined per Stage 08 plumbing.

## The provenance contract (four-fold)

Every CFD run and every ML training run logs four tags to MLflow:

1. `git_sha` — `git rev-parse HEAD` at submission time.
2. `dvc_input_hash` — sha256 over the sorted list of `dvc status -c` outputs for all
   `.dvc`-tracked inputs the case touches.
3. `container_sif_sha256` — SHA256 of the Apptainer SIF that ran the job.
4. `config_hash` — SHA256 of the resolved Hydra config serialized as canonical JSON.

Existing Postgres LXC 202 hosts the new `aero_provenance` DB; the
`mlflow_artifact_provenance` table indexes the four tags for cross-run queries.

## The four-layer memory model

1. **CLAUDE.md** (repo root) — invariants every session.
2. **`.claude/rules/<topic>.md`** — path-scoped lazy-loaded rules.
3. **STAGE-NN-*.md** — the current session's work-of-record.
4. **`docs/handoffs/STAGE-(NN-1)-*-DONE-*.md`** — the previous session's exit notes.

## Post-stage handoff: required frontmatter + sections

Frontmatter: `stage`, `stage_name`, `status`, `date_started`, `date_completed`,
`session_duration_hours`, `claude_code_version`, `model`, `git_sha_start`,
`git_sha_end`, `stage_tag`, `next_stage`, `next_stage_name`.

Sections: 1. Deliverables status. 2. Decisions made (rationale + rejected
alternatives). 3. Deviations from plan. 4. Environment/dependency/schema changes.
5. CI/CD changes. 6. Gotchas discovered. 7. Open items. 8. Pointers for next
session. 9. Artifacts produced (narrative index). 10. Confidence/risk note.

## How to ask vs how to act

- Ambiguity in deliverables → **ask**.
- Choice between two reasonable patterns → **propose both with tradeoffs**.
- Refactor outside scope → **STOP and ask**.
- Destructive op → **propose, wait for `approved`**.
- Anything touching a pre-existing non-aero LXC/VM beyond the explicitly-shared
  services above → **STOP, propose, await `approved`**.

## Pinned versions (set in respective stages; orientation only here)

Python 3.12.x · uv ≥ 0.5 · pre-commit ≥ 4.0 · OpenFOAM-ESI v2412 (Stage 03) ·
SU2 v8.x (Stage 06) · PyFR latest stable (Stage 07) · NekRS latest stable (Stage
07) · JAX-Fluids 2.0 (Stage 08) · PhysicsNeMo container pinned in Stage 09 ·
preCICE 3.x via distribution v2404+ (Stage 11) · NeMo Agent Toolkit
(`nvidia-nat`) v1.5.x (Stage 14).

## Reference documents

- **Pass 1 (Architecture)** — `docs/architecture/`.
- **Pass 2 (SOTA)** — `docs/sota/`.
- **Pass 3 (Best Practices)** — `docs/handoff-bundle/`.
- **Proxmox inventory 2026-05-16** — `docs/architecture/proxmox-inventory-2026-05-16.md`
  (committed in Stage 02).

## Final reminder

Every stage prompt ends with **POST-STAGE HANDOFF**. That section is not optional.
The handoff is what the next session reads to know what just happened.
