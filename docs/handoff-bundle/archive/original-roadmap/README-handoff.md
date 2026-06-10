# aero-research-platform — Claude Code Handoff Bundle

This directory contains 19 files for building `ernesto01louis/aero-research-platform`
from an empty repository to a working, publishable-grade aerodynamics research
platform. Each stage file is self-contained — paste it into a fresh Claude Code session
along with `00-CONTEXT-project-brief.md` and the latest post-stage handoff, and the
model has every piece of context it needs.

This bundle uses the same structure as the RF direction-finding handoff bundle (README
+ 00-CONTEXT + numbered stages) with one important addition: **after every stage,
Claude Code writes a `docs/handoffs/STAGE-NN-DONE-YYYY-MM-DD.md` document** that the
next session reads first. That post-stage handoff is the bridge across Claude Code's
between-session amnesia and is the single most important convention in this bundle.

## What this project is

`aero-research-platform` is a fully open-source, hardware-agnostic, peer-review-grade
aerodynamics research platform. Scope spans:

- Classical CFD: OpenFOAM-ESI, SU2, PyFR, NekRS for everything from steady RANS to
  wall-resolved LES, hypersonic, and aeroacoustics.
- Differentiable CFD: JAX-Fluids 2.0 for learned closures and end-to-end gradient-based
  shape optimization.
- ML surrogates: NVIDIA PhysicsNeMo (DoMINO, Transolver, FIGConvNet, X-MeshGraphNet,
  MoE) trained on AhmedML / WindsorML / DrivAerML / DrivAerNet++.
- Adjoint optimization: DAFoam for aero shape; SU2 adjoint as secondary path.
- Multi-physics coupling: preCICE 3 for FSI (flapping wing, vibrating surfaces) and
  conjugate heat transfer.
- Agentic CAE: NVIDIA NeMo Agent Toolkit + a fork of the AI-Q Blueprint.
- V&V automation: NASA Turbulence Modeling Resource, AIAA DPW/HLPW workshops,
  ERCOFTAC, with UQpy/Dakota for uncertainty quantification.
- Multi-cloud GPU orchestration: RunPod / Lambda Labs / Vast.ai with a future on-prem
  GPU cluster as just another backend.
- Provenance and reproducibility: DVC + MLflow + Postgres + MinIO + Apptainer SIF
  hash chain, every result traceable to (git SHA, DVC hash, container SHA256,
  config hash).

Five guiding principles, in priority order:

1. **Reproducibility is non-negotiable.** Every published number reproduces from a
   git SHA + DVC hash + Apptainer SIF SHA256 + config hash. This is the prerequisite
   for peer review.
2. **Compute is fungible.** No code path may assume a specific backend. Proxmox LXC,
   RunPod H100, future on-prem Slurm — all the same interface.
3. **Solvers are containers.** Every solver is an Apptainer SIF (HPC) and a Docker
   image (cloud). Image digests are part of the provenance record.
4. **The ML and agentic layers augment, never replace, validated physics.** A
   surrogate is admissible only with a published certificate of validity (training
   distribution, held-out error, applicability envelope) below threshold.
5. **GPL is fine; everything stays open.** GPL-3 / LGPL-3 / Apache-2.0 / BSD-3 only.
   No proprietary blobs.

## What to paste, in what order

Always paste, alongside each stage prompt:

| File | When |
|---|---|
| `00-CONTEXT-project-brief.md` | Every session, every stage. The distilled invariants. |
| `STAGE-NN-<name>.md` | The current session's work-of-record. |
| `docs/handoffs/STAGE-(NN-1)-*-DONE-*.md` | Every session except Stage 01. The previous stage's exit notes. |

Stages, in order:

| File | When | Goal |
|---|---|---|
| `STAGE-01-scaffolding-and-conventions.md` | Session 1 | Empty repo → green CI. CLAUDE.md, CONSTITUTION.md, pyproject.toml, branch protection, Conventional Commits enforcement, pre-commit hooks, the post-stage handoff template, CITATION.cff, coverage gate ≥ 60%, ADR template, `docs/handoffs/_template.md`. |
| `STAGE-02-proxmox-and-container-pipeline.md` | Session 2 | Proxmox LXC topology stood up (Postgres, MinIO, MLflow, Prefect, Covalent dispatcher, agent runtime, dev/build VMs). Apptainer SIF build pipeline. SSH-driven Claude Code workflow validated. |
| `STAGE-03-walking-skeleton-openfoam.md` | Session 3 | The walking skeleton: STL → Apptainer-OpenFOAM-ESI `simpleFoam` on Proxmox LXC → MLflow run with DVC inputs → reported Cd. One end-to-end slice. |
| `STAGE-04-provenance-backbone.md` | Session 4 | DVC + MLflow + Postgres + MinIO fully wired with the four-fold provenance tuple. Apptainer SIF SHA256SUMS. ADR for the provenance contract. |
| `STAGE-05-vv-harness-tmr.md` | Session 5 | V&V harness against the NASA Turbulence Modeling Resource. One full case (flat-plate / 2D bump) reproducing reference Cd/Cl within tolerance. CI integration. |
| `STAGE-06-su2-adapter.md` | Session 6 | SU2 v8 adapter. Compressible, transonic, hypersonic-ready. Proves the platform-not-hub abstraction holds across two solvers. |
| `STAGE-07-pyfr-and-nekrs-adapters.md` | Session 7 | PyFR (flux reconstruction GPU) and NekRS (spectral element GPU) adapters as optional extras. High-order scale-resolving capability. |
| `STAGE-08-jax-fluids-and-surrogate-plumbing.md` | Session 8 | JAX-Fluids 2.0 differentiable solver adapter. Surrogate base class, certificate-of-validity framework, data loaders for AhmedML/DrivAerML. |
| `STAGE-09-domino-baseline-surrogate.md` | Session 9 | NVIDIA PhysicsNeMo DoMINO baseline trained on DrivAerML subset. Full provenance triple logged. First GPU rental backend used end-to-end. |
| `STAGE-10-surrogate-ensemble-and-moe.md` | Session 10 | Transolver, FIGConvNet, X-MeshGraphNet trained on the same data. Mixture-of-Experts gating network. Cross-surrogate comparison framework. |
| `STAGE-11-precice-coupling-and-fsi.md` | Session 11 | preCICE 3 coupling layer. OpenFOAM + CalculiX FSI demo (perpendicular flap or Turek-Hron). The base for flapping-wing and vibrating-skin work. |
| `STAGE-12-full-vv-and-uq.md` | Session 12 | Full V&V suite: AIAA DPW-7, HLPW-5 subsets. UQpy + Dakota wiring. Every published-quality run carries a UQ envelope. |
| `STAGE-13-multicloud-gpu-orchestration.md` | Session 13 | RunPod, Lambda Labs, Vast.ai backend adapters behind one `Executor` interface. Cost-aware router. Long-running CFD job tmux pattern. Future on-prem Slurm executor stub. |
| `STAGE-14-agentic-cae-nemo-aiq.md` | Session 14 | NVIDIA NeMo Agent Toolkit deployed. Fork of AI-Q Blueprint adapted for CAE. MCP tools wrapping every solver, mesher, V&V primitive, UQ primitive. CAEBench harness. |
| `STAGE-15-literature-mining-and-citation.md` | Session 15 | arXiv + Semantic Scholar + OpenAlex pipeline. pgvector retrieval. Weekly hypothesis-generation cron. Zenodo deposit workflow. CITATION.cff/ORCID hardening. |
| `STAGE-16-hardening-and-release-v0.1.md` | Session 16 | Documentation polish (mkdocs site), README status auto-regeneration verified, JOSS submission prep, first conference paper template, v0.1.0 release tag. |

## Ordering rationale

1. **Scaffold first.** Every future Claude Code session reads docs and CLAUDE.md at
   start. Get them right on day 1 — don't accumulate documentation debt.
2. **Infrastructure second.** Proxmox/LXC/Apptainer pipeline must exist before any
   solver runs anywhere. SSH-driven workflow validated here.
3. **Walking skeleton third.** One CFD slice end-to-end (geometry → mesh → solve →
   provenance → result) before adding any flesh. This proves the architecture works
   on real hardware.
4. **Provenance fourth.** All subsequent stages produce data that must be traceable.
   Get the provenance contract right before generating mountains of data.
5. **V&V fifth.** A red TMR/DPW dashboard must mean *no production runs allowed*. The
   harness goes in before the second solver does, because the second solver will be
   tested against it.
6. **Solver fleet stages 6–8.** SU2, PyFR, NekRS, JAX-Fluids each added behind the
   abstraction proved in Stages 03–05. They are parallelizable in principle but for
   a single Claude Code session at a time should run sequentially.
7. **Surrogates stages 9–10.** DoMINO baseline first (simplest path, NVIDIA's
   recommended starting point), then the ensemble. This is where rented GPU first
   gets meaningfully used.
8. **preCICE eleventh.** FSI coupling is the gateway to flapping-wing and vibrating-
   surface research — but only meaningful after the solver fleet works.
9. **Full V&V + UQ twelfth.** The thesis-grade gate. Up to here, V&V is one case; here
   it becomes the full DPW/HLPW workshop suite and every result carries a UQ envelope.
10. **Multi-cloud orchestration thirteenth.** Rented compute has been used opportunistically
    in earlier stages; here it becomes a first-class abstraction with cost routing.
11. **Agentic CAE fourteenth.** The agent layer wraps a working platform. Building it
    earlier would mean wrapping nothing.
12. **Literature mining fifteenth.** Concept synthesis runs alongside the agent layer;
    Zenodo / citation hardening also lives here.
13. **Hardening and release last.** mkdocs site, JOSS prep, first paper, v0.1.0.

## The post-stage handoff (new vs RF bundle)

After every stage, Claude Code writes a file to `docs/handoffs/STAGE-NN-<slug>-DONE-
YYYY-MM-DD.md`. The template lives at `docs/handoffs/_template.md` (created in Stage
01). The next stage prompt's "BEFORE YOU START — READ" line explicitly names the
previous handoff. This is what gives the next session a working memory of what
just happened.

Required frontmatter fields:
- `stage`, `stage_name`, `status` (complete | partial | blocked)
- `date_started`, `date_completed`, `session_duration_hours`
- `claude_code_version`, `model`
- `git_sha_start`, `git_sha_end`, `stage_tag`
- `next_stage`, `next_stage_name`

Required sections:
1. Deliverables status (mirrors the stage's DELIVERABLES checklist)
2. Decisions made (with rationale, and rejected alternatives)
3. Deviations from the stage plan
4. Environment / dependency / schema changes
5. CI/CD changes
6. Gotchas discovered
7. Open items for the next stage (and beyond)
8. Pointers for the next session (read first / do not re-read / run first to verify)
9. Artifacts produced (narrative index; commit log is in git)
10. Confidence / risk note

A `Stop` hook installed in Stage 01 blocks the session from ending until this file
exists and frontmatter is filled. The `v0.0.NN` git tag is gated on the handoff
existing.

## How each stage file is structured

Same as the RF bundle, with one added section:

- **REQUIREMENTS THIS STAGE DELIVERS** — concrete capabilities, cross-referenced to the project brief
- **ROLE** — what Claude Code is doing this session
- **GOAL** — numbered list of deliverables
- **WHY** — rationale (lets Claude Code make tradeoffs intelligently)
- **HOW (think through this)** — implementation guidance, not step-by-step
- **BEFORE YOU START — READ** — files to load into context first (always includes the previous handoff)
- **GUARDRAILS — DO NOT** — explicit forbidden patterns
- **DELIVERABLES** — acceptance criteria, machine-verifiable
- **PROPOSE FIRST, EXECUTE LATER** — wait for "approved" before destructive ops
- **POST-STAGE HANDOFF** — explicit reminder to write `docs/handoffs/STAGE-NN-*-DONE-*.md` before tagging

## Cross-stage guardrails (inherited from the architecture, SOTA, and best-practices research)

These apply to every stage. They are also encoded in `CLAUDE.md` as hard rules:

1. **Platform-not-hub.** No solver-specific or ML-framework-specific imports in
   `aero/` core. They live in adapters under optional extras only. `pip install aero`
   without extras must import cleanly with only stdlib + numpy + pydantic.
2. **Fail-loud.** Pydantic strict (`extra='forbid'`). No silent fallback for missing
   config keys or schema mismatch. Fail at startup with a clear error.
3. **Provenance from day one.** Every CFD run and every ML training run logs (git SHA,
   DVC hash, Apptainer SIF SHA256, config hash) to MLflow tags. No exceptions.
4. **Docs match reality, always.** README `## Status` section is auto-regenerated
   from the latest post-stage handoff frontmatter in CI. A PR that edits it by hand
   fails CI.
5. **Conventional Commits + Conventional Comments.** Commit format
   `<type>(<stage-NN>): <subject>`. CI rejects malformed messages. PR comments use
   Conventional Comments labels.
6. **Propose first, execute later.** Every stage requires explicit `approved` before
   destructive or persistent operations.
7. **CI green before next stage.** Each stage's deliverables include CI verification.
   The previous stage's tag must exist before the next stage starts.
8. **No secrets in repo.** `.env` is gitignored. Secrets in HashiCorp Vault on the
   Proxmox host. The agent reads them at job time, never persists them.
9. **Branch protection from day 1.** No direct push to `main`. PR + status checks +
   1 approval + linear history + 24-hour cooling-off rule.
10. **Heavy deps in optional extras only.** Base `pip install aero` pulls only
    stdlib + numpy + pydantic. `aero[openfoam]`, `aero[su2]`, `aero[pyfr]`,
    `aero[nekrs]`, `aero[jax-fluids]`, `aero[physicsnemo-cu12]`, `aero[precice]`,
    `aero[agentic]`, `aero[gpu-rental]`, `aero[literature]` for the rest.
11. **No `--no-verify`. No `--dangerously-skip-permissions` outside ephemeral
    containers.** Pre-commit and Claude Code hooks are not optional.
12. **Pin everything that's heavy.** Containers by SHA256, Python by version,
    OpenFOAM/SU2/preCICE/PhysicsNeMo by release tag. Document every pin in an ADR.

## What's NOT in this bundle

- **A "build me a wind tunnel" stage.** Physical experimental validation is out of
  scope. The platform validates against published workshop data (NASA TMR, AIAA DPW/
  HLPW, ERCOFTAC) — not against your own wind tunnel.
- **A specific thesis-paper stage.** Once v0.1.0 ships, writing the thesis or first
  paper is a research activity, not a platform-building activity. The platform exists
  to make research possible; the research is yours.
- **Custom solver development.** Modifying OpenFOAM C++ kernels or writing new
  SU2 numerics is research that happens *on top of* the platform, not part of
  building it. The platform's job is to package, run, validate, and provenance-track
  solvers — not to compete with them.
- **A commercial-software-integration stage.** The architecture explicitly chose
  open-source. If you later want a STAR-CCM+ or Fluent adapter, that's a follow-on
  optional extra (`aero[starccm]`) that slots into the existing adapter abstraction
  — no platform changes required.
- **Quantum CFD, neuromorphic, or other speculative compute.** Out of scope for v0.1.

## Pre-flight checks before Session 1

Before pasting `STAGE-01` into Claude Code, verify:

1. Empty `ernesto01louis/aero-research-platform` repository exists on GitHub (no
   auto-initialization — empty repo, no README, no .gitignore, no license).
2. `gh` CLI is authenticated (`gh auth status` shows your account, scope includes
   `repo` and `workflow`).
3. Local working directory chosen for the clone (e.g.,
   `~/projects/aero-research-platform/`).
4. Python 3.11+ available locally (`python --version`). 3.12 preferred.
5. `uv` installed (`uv --version`). If not: `curl -LsSf https://astral.sh/uv/install.sh
   | sh`.
6. `pre-commit` installed (`pre-commit --version`). If not: `uv tool install pre-commit`.
7. Proxmox inspection complete (you've run `PROMPT-00-proxmox-inspection.md` and have
   the inventory report). **Stage 02 needs the inventory.**
8. You've opened `00-CONTEXT-project-brief.md` in another tab so you can paste it
   alongside each stage prompt.
9. The architecture document (Pass 1) and SOTA document (Pass 2) are accessible — they
   are not pasted into every session, but are referenced when the agent needs deep
   context on a specific decision.
10. You have a PyPI account in case you eventually publish (Stage 01 scaffolds for
    this; actual publish is much later — Stage 16).

## Versioning & release cadence

- `v0.0.NN` — stage tag per completed stage. Pre-alpha, breaking changes anytime.
  Stages 01–15 ship under this.
- `v0.1.0-alpha` — after Stage 12 (full V&V passes). API not yet stable, but the
  platform produces publishable numbers.
- `v0.1.0` — first stable platform release, after Stage 16. JOSS submission targets
  this tag.

The git tag for each stage is created **only after the post-stage handoff exists** —
this is enforced by a CI check.

## Cross-references to other deliverables

This bundle assumes:

1. The **architecture document** (Pass 1) is in your possession as the canonical
   technical spec. Stages reference it for specific solver choices, deployment
   topology, and decision rationale.
2. The **SOTA literature review** (Pass 2) is in your possession as the canonical
   reference for current best practices, dead-ends to avoid, and citation-ready
   prior art.
3. The **best-practices guide** (Pass 3) is in your possession for the rationale
   behind CLAUDE.md, the handoff template, hooks, and MCP server choices. Stages
   do not re-explain it; they enforce it.
4. The **Proxmox inventory report** produced by `PROMPT-00-proxmox-inspection.md`
   is available before Stage 02 runs. Stage 02 explicitly asks Claude Code to read
   it before proposing topology.

## After Stage 16

You have a working, hardware-agnostic, multi-cloud-compute, peer-review-grade
aerodynamics research platform with V&V automation, UQ wiring, ML surrogates,
agentic CAE, and full provenance. Remaining work is research, not platform-
building:

- First conference paper (AIAA SciTech, APS DFD)
- Master's thesis writing
- New surrogate architectures
- New benchmark contributions
- Bio-inspired drag-reduction studies (riblets, vibrating surfaces)
- Flapping-wing aerodynamics
- Hypersonic and reacting-flow studies (SU2-NEMO + Mutation++)

The platform itself is stable. The science happens on top.
