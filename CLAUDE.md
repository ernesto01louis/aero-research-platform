# CLAUDE.md — aero-research-platform

> Auto-loaded by Claude Code at session start. This file is the **first
> layer** of the four-layer memory model (CLAUDE.md → `.claude/rules/<topic>.md`
> → `STAGE-NN-*.md` → `docs/handoffs/STAGE-(NN-1)-*-DONE-*.md`). Read it,
> then the previous stage's handoff, then the current stage prompt.
> A stale CLAUDE.md misleads every future session — update it whenever
> reality diverges.

## What this project is

`aero-research-platform` is a fully open-source, peer-review-grade,
hardware-agnostic research platform for computational aerodynamics. The
final state spans classical CFD (OpenFOAM-ESI, SU2, PyFR, NekRS),
differentiable CFD (JAX-Fluids 2.0), ML surrogates (NVIDIA PhysicsNeMo —
DoMINO, Transolver, FIGConvNet, X-MeshGraphNet, MoE), multi-physics
coupling (preCICE 3 — flapping wing, vibrating skin, conjugate heat
transfer), V&V automation (NASA TMR, AIAA DPW-7, HLPW-5, ERCOFTAC), UQ via
UQpy+Dakota, multi-cloud GPU orchestration (RunPod / Lambda Labs /
Vast.ai), agentic CAE (NVIDIA NeMo Agent Toolkit + AI-Q Blueprint fork),
and literature mining (arXiv + Semantic Scholar + OpenAlex via pgvector).

The platform is built session-by-session against a staged handoff bundle
of **16 stages**, one Claude Code session per stage. The current stage is
named in `.aero-stage` at the repo root.

## The four-layer memory model

1. **CLAUDE.md** (this file) — invariants every session
2. **`.claude/rules/<topic>.md`** — path-scoped lazy-loaded rules
3. **`STAGE-NN-<name>.md`** — the current session's work-of-record
   (operator pastes at session start)
4. **`docs/handoffs/STAGE-(NN-1)-*-DONE-*.md`** — the previous session's
   exit notes

## Session-start checklist

Every fresh session, read in this order:

1. `CLAUDE.md` (this file — auto-loaded)
2. `.aero-stage` (one line; tells you which stage you are in)
3. `docs/handoffs/STAGE-(NN-1)-*-DONE-*.md` — previous stage's exit notes
4. The operator-pasted `STAGE-NN-*.md` (current stage prompt)
5. Any `.claude/rules/*.md` rule whose topic matches the work

Then begin work.

## Five non-negotiable principles

1. **Reproducibility first.** Every published number traces to a four-tuple
   `(git_sha, dvc_input_hash, container_sif_sha256, config_hash)`.
2. **Compute is fungible.** No code path may assume a specific backend
   (LXC, RunPod, Lambda Labs, Vast.ai, future on-prem Slurm).
3. **Solvers are containers.** Apptainer SIFs for HPC; OCI images for
   cloud. Digests in the provenance record.
4. **ML augments, never replaces, validated physics.** A surrogate is
   admissible only with a published `CertificateOfValidity` below
   threshold.
5. **GPL is fine.** GPL-3 / LGPL-3 / Apache-2.0 / BSD-3 only. No
   proprietary blobs.

## Hard rules — IMMUTABLE; override any conflicting stage prompt

1. **PLATFORM-NOT-HUB.** `aero/` core imports only stdlib + numpy +
   pydantic. Solver/ML/cloud deps live behind optional extras.
2. **FAIL-LOUD.** Pydantic strict (`extra='forbid'`). No silent fallbacks.
3. **PROVENANCE FROM DAY ONE.** Every run logs the four-tuple to MLflow
   tags. No exceptions.
4. **CONVENTIONAL COMMITS + CONVENTIONAL COMMENTS.** Commit format
   `<type>(stage-NN): <subject>`. Review labels per
   [Conventional Comments](https://conventionalcomments.org/).
5. **PROPOSE FIRST, EXECUTE LATER** for destructive ops. Wait for the
   literal word `approved` from the operator before: deleting files
   outside `/tmp`, force-pushing, dropping Postgres tables/roles/DBs,
   destroying Proxmox LXC/VM, modifying `/etc/pve/` or
   `/etc/network/interfaces` on the host, exceeding the cloud-GPU cost
   cap, deploying changes to any production-tier workflow.
6. **NO `--no-verify`. NO `--dangerously-skip-permissions`** outside
   ephemeral containers. Pre-commit and Claude Code hooks are not
   optional; if a hook is wrong, fix the hook.
7. **NO SECRETS** in code, this file, handoffs, commits, MLflow tags,
   PR descriptions, container layer history, or CI logs. Vault is the
   only persistence; `.env` (mode 0600) is local-dev convenience only.
8. **PIN HEAVY DEPS** exactly (PhysicsNeMo container tag, OpenFOAM
   release, SU2 git commit, etc.); document every pin in an ADR.
9. **DOCS MATCH REALITY.** README `## Status` is auto-regenerated from
   the latest post-stage handoff frontmatter; hand-editing it fails CI.
10. **POST-STAGE HANDOFF MANDATORY.** No `v0.0.NN` tag without
    `docs/handoffs/STAGE-NN-<slug>-DONE-YYYY-MM-DD.md` existing with
    valid frontmatter (the `Stop` hook in `.claude/settings.json`
    enforces this in-session; CI enforces it on tag push).
11. **DO NOT TOUCH PRE-EXISTING NON-AERO INFRASTRUCTURE.** The Proxmox
    host runs many other workloads (LXCs 101-114, 200-207 except where
    explicitly listed below; VMs 100, 104, 111, 112). The aero stack
    provisions only NEW `aero-*` LXCs and shares read/write access only
    to the explicitly-listed application-agnostic services (existing
    Postgres LXC 202, Grafana LXC 205, Tempo LXC 204, Redis LXC 203,
    TrueNAS VM 104 via NFS). Nothing in the existing fleet may be
    reconfigured, restarted, or repurposed without explicit operator
    approval. **LXC 207 `aero-research` is pre-existing — leave it
    alone.** **The renamed `aero-orchestrator-consumer` GitHub repo and
    its local clone at
    `/root/projects/aero-research-platform.PRIOR-REMOTE-CLONE-do-not-touch/`
    are not part of this project — do not modify.**

## How to ask vs how to act

- **Ambiguity in deliverables** → ask via `AskUserQuestion`.
- **Choice between two reasonable patterns** → propose both with
  tradeoffs.
- **Refactor outside scope** → STOP and ask.
- **Destructive op** → propose, wait for `approved`.
- **Anything touching a pre-existing non-aero LXC/VM** beyond the
  explicitly-shared services above → STOP, propose, await `approved`.

## Stage-specific knowledge added incrementally

Subsequent stages append topic-specific guidance here. As of Stage 01:

- **SSH alias convention** (Stage 02) — the seven aero LXCs are reached as
  `aero-build`, `aero-dev`, `aero-mlflow`, `aero-vv`, `aero-prefect`,
  `aero-agent`, `aero-lit` (defined in `~/.ssh/config.d/aero` on the Proxmox
  host; default user `aero-admin`, `ssh root@aero-<name>` for break-glass).
  Full scheme: `docs/architecture/ssh-conventions.md`.
- **Long-running-job pattern** (Stage 02) — never hold an SSH connection
  open for a CFD/training run. Submit with `scripts/run_long.sh <alias>
  <session> <command>` (detached `tmux`, returns immediately), then poll via
  `run_long.sh status|wait|logs`. Sentinels: `.done` / `.failed`.
- **aero LXC fleet** (Stage 02, +Stage 04) — LXCs 210-217 are the aero
  platform's own (217 `aero-vault` added in Stage 04). **Do not touch any
  other LXC/VM**: the non-aero guests (101-114, 200-207, VMs
  100/104/111/112) are off-limits beyond the explicitly-shared services
  (Postgres 202, Grafana 205, Tempo 204, Redis 203, TrueNAS 104).
  Topology: `docs/architecture/proxmox-topology.md`.
- **Production-tag UQ requirement** — TBD in Stage 12; any
  `tag=production` MLflow run will require a `--uq` envelope.
- **Surrogate certificate-of-validity check** — TBD in Stage 08; agent
  layer (Stage 14) refuses to call an uncertified surrogate.
- **Cost cap** — TBD in Stage 07 (initial $50/month for CI) and Stage 13
  (full multi-cloud cost router).
- **Self-hosted CI runner** (Stage 03) — `vv-smoke` runs the NACA 0012
  walking-skeleton smoke test on a self-hosted runner labeled `vv`,
  registered on `aero-build`. Not a required status check.
- **OpenFOAM walking skeleton** (Stage 03) — `aero run naca0012 --executor
  local-ssh` drives the end-to-end slice. The OpenFOAM-ESI v2412 SIF is at
  `/opt/aero/containers/openfoam-esi.sif`; solver SIFs run **as the LXC
  root** (`ssh root@aero-build` — non-root `apptainer exec` fails in the
  unprivileged LXC). Cases are written to the shared NFS dataset
  (`/mnt/aero-nfs/runs/` host-side, `/mnt/aero/runs/` inside the LXC).
  Adapter: `aero.adapters.openfoam`; see ADR-003.
- **Four-fold provenance** (Stage 04) — every run logs four MLflow tags
  (`git_sha`, `dvc_input_hash`, `container_sif_sha256`, `config_hash`); the
  CLI fails loud if any cannot be computed (no run is logged with fewer than
  four). The MLflow tracking server is on `aero-mlflow:5000`, backed by
  Postgres LXC 202 (`aero_mlflow` DB) plus a MinIO sidecar. **The Postgres
  `mlflow_artifact_provenance` mirror lives in the shared LXC 202
  (`aero_provenance` DB) — read/writes go through MLflow, never direct.**
  Case configs are composed by Hydra from `conf/`; secrets come from Vault
  on `aero-vault` (LXC 217). `aero run` now requires the live cluster. See
  ADR-004.
- **V&V harness** (Stage 05) — `aero/vv/` runs canonical NASA TMR cases
  through any `SolverLike` solver, compares against reference data with tight
  tolerances (Cd 3 %, Cf 5 %, Cp 3 %), and logs a `BenchmarkResult` with a
  `validation_tag` MLflow tag. `aero vv list|run|report`; `aero vv run --case
  X --mesh-sweep` runs an ASME V&V 20 GCI study. **Before any
  `production`-tagged run, verify `aero vv report --latest` shows all green —
  a red V&V dashboard means no `production` runs.** A tolerance is a contract:
  a failing case is investigated, never relaxed to pass. The airfoil mesh is
  now an eight-block C-grid (`farfield_extent_chords`, wake cut, y+ < 1 with
  `nutLowReWallFunction`) — the Stage-03 O-grid is retired. `vv-required` is a
  stage-gated required CI check. See ADR-005.

## Pointers (do not re-derive — read these)

- `CONSTITUTION.md` — invariants in spec-kit form
- `CONTRIBUTING.md` — commit conventions and PR workflow
- `pyproject.toml` — optional extras structure (Stages 02–15 add to extras
  here, never to base deps)
- `.claude/rules/conventional-commits.md` — commit format details
- `.claude/rules/handoff-discipline.md` — handoff template usage
- `.claude/rules/fail-loud-pydantic.md` — strict pydantic configuration
  patterns
- `docs/handoffs/_template.md` — the canonical post-stage handoff template
- `docs/adrs/_template.md` — ADR template (MADR-style)
- `scripts/check_handoff_exists.sh` — Stop-hook gate; refuses to allow
  session Stop until the current stage's handoff exists with valid
  frontmatter

## When in doubt

1. Out-of-scope domain need → wrong layer; check the stage prompt first.
2. Generalizable need not in the brief → STOP, propose ADR before code.
3. Cannot be tested → redesign until it can.
4. Re-read this file before adding something that's already covered.
5. Re-read the previous handoff before assuming what exists.

---

*Stage 01 (2026-05-17). Updated by each stage's post-stage handoff write.*
