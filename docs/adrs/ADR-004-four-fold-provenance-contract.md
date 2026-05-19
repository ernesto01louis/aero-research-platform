# ADR-004 — Four-Fold Provenance Contract

- **Status:** accepted
- **Date:** 2026-05-19
- **Deciders:** Operator (Louis Ernesto Schulte Moredo); Claude Code
  agent (Stage 04)
- **Stage:** 04
- **Supersedes:** none (extends ADR-002 topology; lifts ADR-003 out-of-scope items)

## Context and problem statement

Constitution Invariant 1 requires every published number to trace to a tuple
`(git_sha, dvc_input_hash, container_sif_sha256, config_hash)`. Stage 03 logged
only two components (`git_sha`, `container_sif_sha256`) to a local file-store
MLflow, with an `"unknown"` fallback when a value was unavailable. Stage 04
makes provenance a *contract*: every run logs all four components, fails loud
if any cannot be computed, and mirrors the tuple into Postgres for fast
cross-run queries. This ADR records the contract and the decisions standing the
backbone up.

## Decision drivers

- Reproducibility-first: a run that cannot be cited must not be logged.
- PLATFORM-NOT-HUB: `aero/` core stays stdlib + numpy + pydantic only.
- Hard Rule 11: the shared Postgres LXC 202 may be extended additively but
  never reconfigured.
- Hard Rule 7: no secrets in the repo, configs, commits, or MLflow tags.
- Minimise new services to maintain on a memory-constrained host.

## Considered options

1. **Full four-fold backbone** — remote MLflow + Postgres mirror + DVC remote
   + Hydra config hashing + Vault secrets store.
2. **Partial** — remote MLflow only, defer DVC/Hydra/Vault.
3. **Status quo** — keep the Stage 03 local file-store logger.

## Decision outcome

Chose **Option 1**. The four-fold contract is binding from Stage 04 onward.

### The four-fold contract

Every CFD or training run logs four MLflow tags; `compute_provenance`
(`aero/provenance/four_fold.py`) raises `ProvenanceError` if any cannot be
computed, *before* the MLflow run is opened (no orphan half-tagged runs):

1. **`git_sha`** — `git rev-parse HEAD`. A dirty working tree fails loud;
   `--allow-dirty` opts into an exploration run, tagging the SHA `-dirty`.
2. **`dvc_input_hash`** — sha256 of the canonical JSON of `dvc status -c`. An
   in-sync repo hashes `{}` to a stable constant, meaning "inputs are exactly
   the published versions". Stage 04 scope: the only DVC-tracked input is
   `data/references/naca0012/naca0012.csv`.
3. **`container_sif_sha256`** — looked up by basename in `containers/SHA256SUMS`;
   no fallback (the Stage 03 `"unknown"` shortcut is retired).
4. **`config_hash`** — sha256 of the Hydra-resolved config serialized as
   canonical JSON (`OmegaConf.to_container(resolve=True)` → `json.dumps(...,
   sort_keys=True, separators=(",",":"))`).

The tuple is mirrored into `mlflow_artifact_provenance` in the `aero_provenance`
database (alembic revision `004_provenance`). The mirror is a *mirror* — MLflow
remains the source of truth — kept for fast cross-run queries.

### Key decisions

- **Extend the shared Postgres LXC 202** rather than provision a fresh
  instance: the cluster is application-agnostic, the additions (two DBs, two
  roles) are purely additive, and a memory-constrained host should not run a
  parallel Postgres. Executed only after operator `approved`.
- **MinIO sidecar** inside `aero-mlflow` as the DVC + MLflow artifact store,
  rather than a dedicated MinIO LXC: one fewer service to maintain. The plan
  put MinIO's backend on the TrueNAS NFS dataset for durability; deployment
  proved that unworkable — MinIO does not support network filesystems. MinIO
  now stores data on the `aero-mlflow` LXC local disk; durability is the
  nightly `vzdump` of the LXC. See "Deployment outcomes" below.
- **Vault stands up now** (operator decision) on a new dedicated LXC 217
  `aero-vault`, extending the ADR-002 fleet. A dedicated node keeps the secret
  store off the app server. Single-node integrated raft storage; a Vault Agent
  on `aero-mlflow` renders the secret env files. The Stage 02 signing-key
  escrow migrates into Vault.
- **MLflow + MinIO via native packaging + systemd** (operator decision), not
  Apptainer SIFs — the unprivileged-LXC non-root apptainer limitation
  (ADR-002) makes long-running SIF services awkward.
- **Hydra Compose API**, not `@hydra.main`: `@hydra.main` hijacks `sys.argv`
  and the working directory, colliding with the typer CLI.
- **Dirty-tree policy:** fail loud by default; `--allow-dirty` annotates the
  SHA with `-dirty`.
- **`git_sha` / `container_sif_sha256` are computed, never config keys** —
  they have no Hydra override surface, so guardrail 6 is satisfied structurally.

### Deviations from the Stage 04 prompt

- **`compute_provenance` signature.** The prompt specifies
  `compute_provenance(case_dir, container_sif, config_path)`. Implemented as
  `compute_provenance(*, repo_root, container_sif, resolved_config,
  allow_dirty)`: `git`/`dvc` operate on the repo (case dirs live on NFS
  *outside* it), so `repo_root` replaces `case_dir`; and `config_hash` needs the
  *resolved* config object, so `resolved_config` (a plain dict) replaces
  `config_path` — re-composing Hydra from a path risks drift.
- **MinIO installed from the pinned release binary**, not a `.deb` — MinIO does
  not publish a versioned `.deb`; the SHA256-verified release binary plus an
  aero-authored systemd unit pins it exactly.
- **TLS reverse proxy dropped.** The plan put a Caddy TLS proxy on the Proxmox
  host; to avoid touching the host baseline (Hard Rule 11) it would move
  in-LXC, but for Stage 04 the services run plain HTTP, reachable only from
  the aero fleet's trusted CIDRs. An in-LXC TLS front is a follow-up.

### Deployment outcomes (2026-05-19)

The first real rollout of the Ansible roles surfaced infrastructure realities
the plan did not anticipate:

- **MinIO does not support NFS.** The plan stored MinIO's backend on the
  TrueNAS NFS dataset. In practice the export squashes every client uid
  (root included) to `nobody`, and MinIO's IAM layer hit prefix-consistency
  errors — MinIO requires local, directly-attached storage. **MinIO data
  moved to the `aero-mlflow` LXC local disk** (`/opt/aero/minio-data`);
  durability is the nightly LXC `vzdump`. Revisit if artifact volume
  outgrows the 50 GB LXC disk.
- **The aero LXCs have no shared DNS.** Each LXC cannot resolve the others'
  hostnames. Service-to-service config therefore uses **IP addresses**: the
  MLflow `tracking_uri` (`conf/mlflow/default.yaml`), the DVC remote endpoint
  (`.dvc/config`), and the Vault Agent address all point at IPs. A homelab
  DNS entry for the `aero-*` names would let hostnames work — a follow-up.
- **MinIO/MLflow firewall** opens to the fleet's trusted CIDRs (LAN +
  private data plane + Tailscale), matching the `aero-base` SSH policy —
  not the private segment alone, so the Proxmox host (Ansible/dev) can reach
  them. Not internet-exposed.
- **`dvc` is resolved next to `sys.executable`**, not via `PATH` — it ships
  in the `aero[provenance]` extra, so it sits beside the venv's Python; this
  makes `aero run` work without the venv activated.
- **Vault Agent** runs the `vault` binary in template-only mode (no `cache`
  stanza — that needs an API listener the Agent does not define).

### Pinned versions (Hard Rule 8)

| Component | Pin |
|---|---|
| `aero[provenance]` | mlflow≥2.20, dvc[s3]≥3.55, boto3≥1.35, hydra-core≥1.3, omegaconf≥2.3, psycopg2-binary≥2.9, alembic≥1.13 |
| MLflow server | 3.12.0 |
| MinIO server | RELEASE.2025-09-07T16-13-09Z |
| MinIO client `mc` | RELEASE.2025-08-13T08-35-41Z |
| HashiCorp Vault | 1.20.4 |

### Consequences

- **Positive:** every run is citable; cross-run provenance queries are fast;
  secrets are centralised in Vault.
- **Negative:** `aero run` now requires the live cluster (MLflow server +
  Postgres) — the Stage 03 offline `mlruns/` path is gone. Deploy ordering is
  strict: Vault → init/unseal → seed → aero-mlflow.
- **Neutral / followup:** `dvc` remains a base dependency (a latent
  PLATFORM-NOT-HUB tension from Stage 01) — left as-is to avoid breaking
  Stage 03 installs; revisit if it bites. Vault auto-unseal (cloud KMS) is not
  configured; unseal is manual. MinIO on LXC-local disk loses the
  TrueNAS-managed durability the plan wanted — the LXC `vzdump` covers it for
  now. A homelab DNS record for the `aero-*` hosts would retire the
  IP-addressed config.

## Pros and cons of considered options

### Option 1 — full four-fold backbone

- Good: satisfies Invariant 1 completely; V&V (Stage 05) can key on the tuple.
- Bad: large stage; strict deploy ordering; `aero run` now cluster-bound.

### Option 2 — partial

- Good: smaller stage.
- Bad: leaves the contract unsatisfied; Stage 05 would have to finish it.

### Option 3 — status quo

- Good: zero work.
- Bad: violates Invariant 1; no citable runs.

## Links

- Stage prompt: `STAGE-04-provenance-backbone.md`
- Project brief: `00-CONTEXT-project-brief.md` §"The provenance contract"
- Related ADR: ADR-002 (topology), ADR-003 (walking skeleton)
- Related handoff: `docs/handoffs/STAGE-04-provenance-backbone-DONE-2026-05-19.md`
- Rule: `.claude/rules/fail-loud-pydantic.md` (the Hydra→pydantic boundary)
