---
stage: 04
stage_name: "Stage 04 — Provenance Backbone"
status: partial
date_started: 2026-05-19
date_completed: 2026-05-19
session_duration_hours: 5.0
claude_code_version: "2.1.117 (Claude Code)"
model: claude-opus-4-7
git_sha_start: "453bfb507aefa43e15b9043fe555484d4235dcfa"
git_sha_end: "e6863bccc2ec1fa05768dd3a2433698f9332426d"
stage_tag: v0.0.4
next_stage: 05
next_stage_name: "Stage 05 — V&V Harness"
---

# Stage 04 — Provenance Backbone — DONE 2026-05-19

> Auto-loaded by the Stage 05 session as "BEFORE YOU START — READ".
> **status: partial.** The in-repo four-fold provenance backbone is complete,
> tested, and committed (8 commits). The live-infrastructure deployment
> (Vault, MLflow/MinIO, the Postgres LXC 202 databases) and the Zenodo DOI
> are an operator-run follow-up — the auto-mode classifier blocks the agent
> from shared-Proxmox / shared-Postgres changes. Runbook:
> `docs/runbooks/stage-04-provenance-deploy.md`.

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `aero_provenance` + `aero_mlflow` DBs on Postgres LXC 202 | ⚠️ | DDL written (`db/provision/aero_databases.sql`); apply is operator-run (runbook §5) |
| 2 | MLflow + MinIO on `aero-mlflow` LXC | ⚠️ | Ansible role `aero-mlflow` written; deploy is operator-run (runbook §7) |
| 3 | MinIO sidecar, NFS-backed, buckets `aero-mlflow`/`aero-dvc` | ⚠️ | In the role; created on deploy |
| 4 | DVC remote on MinIO | ⚠️ | `.dvc/config` committed; `dvc push` needs the live MinIO (runbook §9) |
| 5 | SIF SHA256 hashing automated | ✅ | `four_fold.container_sif_sha256` reads `containers/SHA256SUMS` |
| 6 | Hydra config system + config hashing | ✅ | `conf/` tree; `four_fold.config_hash` |
| 7 | Four-fold tuple logged as MLflow tags | ✅ | `aero/provenance/mlflow.py`; needs the live server to exercise |
| 8 | `mlflow_artifact_provenance` Postgres table | ✅ | alembic `004_provenance`; applied on deploy (runbook §8) |
| 9 | `aero/provenance/four_fold.py` | ✅ | `compute_provenance`, `ProvenanceTuple`, `ProvenanceError` |
| 10 | `mlflow_basic.py` → `mlflow.py` refactor | ✅ | `start_provenance_run` context manager |
| 11 | Hydra in `aero/cli.py` | ✅ | Compose API; `--allow-dirty` flag |
| 12 | `CaseSpec` Hydra-loadable | ✅ | `conf/case/naca0012.yaml`; strict pydantic boundary |
| 13 | `aero/provenance/db.py` Postgres mirror | ✅ | `mirror_provenance_row`, transactional |
| 14 | `aero[provenance]` extra | ✅ | mlflow, dvc[s3], boto3, hydra-core, omegaconf, psycopg2-binary, alembic |
| 15 | Re-run NACA 0012 through the new pipeline | ❌ | needs the live cluster — operator runbook §10 |
| 16 | CITATION.cff Zenodo DOI | ❌ | operator reserves the concept DOI (runbook §11); agent then writes it |
| 17 | CI `provenance-completeness` check | ✅ | workflow + test written; not yet a required check |
| 18 | `tests/stage_04/` passes | ✅ | 48 hermetic tests pass; 2 slow (cluster) skipped |
| 19 | ADR-004 | ✅ | `docs/adrs/ADR-004-four-fold-provenance-contract.md` |
| 20 | Post-stage handoff | ✅ | this file |
| 21 | Tag `v0.0.4` | ❌ | deferred until the deployment + Zenodo close the stage |

## 2. Decisions made

- **Vault stands up on a dedicated new LXC 217 `aero-vault`** (operator chose
  "stand up Vault now"). Rejected: co-locating Vault on `aero-mlflow` — putting
  the secret store on the app server that consumes the secrets defeats its
  purpose. A Vault Agent on `aero-mlflow` renders the secret env files.
- **MLflow + MinIO via native packaging + systemd** (operator choice), not
  Apptainer SIFs — the unprivileged-LXC non-root apptainer limitation
  (Stage 02 §6) makes long-running SIF services awkward.
- **MinIO installed from the pinned release binary**, not a `.deb` — MinIO
  publishes no versioned `.deb`; the SHA256-verified release binary + an
  aero-authored systemd unit pins it exactly.
- **`compute_provenance` signature changed** from the prompt's
  `(case_dir, container_sif, config_path)` to
  `(*, repo_root, container_sif, resolved_config, allow_dirty)` — git/dvc
  operate on the repo (case dirs live on NFS *outside* it); `config_hash`
  needs the resolved config object, not a path (re-composing risks drift).
  Recorded in ADR-004.
- **Module named `aero/provenance/mlflow.py`** as the prompt specifies — safe
  because Python-3 absolute imports resolve `import mlflow` (function-scoped)
  to the installed package; there is no top-level `import mlflow`.
- **`config_hash` covers the whole resolved config** (case + mlflow +
  provenance layers), per the brief's "the resolved Hydra config". The case
  YAML lists all 13 `CaseSpec` fields explicitly so no pydantic default falls
  outside the hash; a test asserts YAML keys == `CaseSpec.model_fields`.
- **`uv.lock` committed** (operator choice); the `check-added-large-files`
  pre-commit hook now exempts it (679 KB generated lockfile > the 500 KB
  guard). The 500 KB guard still applies to every other file.
- **TLS reverse proxy on `aero-mlflow` itself**, not the Proxmox host — avoids
  touching the host baseline (Hard Rule 11). Deferred / optional: see §3.

## 3. Deviations from the stage plan

- **Infrastructure not deployed this session.** The auto-mode classifier
  blocks the agent from `pct create`, Ansible SSH deploys to shared/new
  hosts, and Postgres LXC 202 DDL — the same gating Stage 02/03 hit. All of
  it is captured as an operator runbook (`docs/runbooks/stage-04-provenance-
  deploy.md`); the agent finalizes the stage once the operator reports back.
- **Caddy host reverse proxy dropped.** The plan said "Caddy on the host"; to
  avoid a host-baseline change the design moved TLS into `aero-mlflow`. For
  Stage 04 the services are HTTP on the VPN-only private segment; an in-LXC
  Caddy is a follow-up if TLS is wanted (not deployed, not in the role yet).
- **`config_hash` third argument** is the resolved config dict, not a path
  (decision in §2 / ADR-004).
- **`v0.0.4` tag deferred** until the deployment + Zenodo land.

## 4. Environment / dependency / schema changes

- `pyproject.toml`: `aero[provenance]` extra populated — `mlflow>=2.20`,
  `dvc[s3]>=3.55`, `boto3>=1.35`, `hydra-core>=1.3`, `omegaconf>=2.3`,
  `psycopg2-binary>=2.9`, `alembic>=1.13`.
- `uv.lock` is now committed and tracked.
- New `aero/provenance/` modules: `four_fold.py`, `mlflow.py`, `db.py`
  (`mlflow_basic.py` removed).
- New top-level dirs: `conf/` (Hydra), `db/` (alembic + provision SQL).
- DVC initialized: `.dvc/`, `.dvcignore`; `data/references/naca0012/
  naca0012.csv` moved from git to DVC tracking (`naca0012.csv.dvc`).
- **Postgres LXC 202 — not yet changed.** On deploy it gains: roles
  `aero_mlflow_user`, `aero_provenance_reader`; DBs `aero_mlflow`,
  `aero_provenance`; `pgvector` in `aero_provenance`; one `pg_hba.conf` line.
  Capture the pre-deploy `\l \du \dx` snapshot when running runbook §5.
- **New LXC 217 `aero-vault`** — provisioner fleet table updated; not yet
  created.
- No `containers/SHA256SUMS` change this stage.

## 5. CI/CD changes

- `.github/workflows/provenance-completeness.yml` — new self-hosted (`vv`)
  job: end-to-end NACA 0012 run, asserts four tags + the Postgres mirror row.
- Reads `secrets.AERO_PROVENANCE_DSN` — the operator must add that repo
  secret (runbook §11).
- **Not** a required status check yet (same rationale as `vv-smoke` — a
  self-hosted offline runner must not block PRs). Promote once stable.
- `.pre-commit-config.yaml`: `check-added-large-files` now excludes `uv.lock`.

## 6. Gotchas discovered

- **`check-added-large-files` (500 KB) silently rejected every commit** —
  `uv.lock` is 679 KB. The failure scrolled off the top of truncated commit
  output; eight commits appeared to succeed but none landed. Always read the
  *full* pre-commit output, or check `git rev-parse HEAD` moved.
- **The pre-commit `pytest-unit` hook needs `pytest` on `PATH`** — it is a
  `language: system` hook. Commit with the venv activated, or
  `PATH=".venv/bin:$PATH" git commit`.
- **The pre-commit mypy hook runs in an isolated env** (only the deps in
  `additional_dependencies`). `omegaconf` is absent there, so a
  `# type: ignore` that the project venv needs is flagged "unused". Use
  `typing.cast` instead of annotate-plus-ignore at the OmegaConf boundary.
- **YAML scientific notation** — `6.0e6` parses as a *string* (PyYAML float
  resolver needs an explicit exponent sign); write `6.0e+6` / `5.0e-6`.
- **The auto-mode classifier gates all shared-infra ops** regardless of an
  in-chat approval — `pct`, SSH deploys to shared/new hosts, Postgres DDL.
  Plan for these as operator-run from the start.

## 7. Open items for the next stage (and beyond)

**Operator follow-up — deploy the backbone (THIS stage's completion):**
Run `docs/runbooks/stage-04-provenance-deploy.md` end to end, then report the
Zenodo concept DOI and the end-to-end run result back so the agent can write
`CITATION.cff`, flip this handoff to `complete`, and tag `v0.0.4`.

**Stage 05 (V&V Harness):**
- The V&V harness must key each run on the four-tuple — `compute_provenance`
  returns the `ProvenanceTuple`; use it as the run identity.
- Move the V&V runner to `aero-vv` (install Apptainer there).
- Improve the O-grid mesh quality (Stage 03 residual plateau ≈ 1.5e-3) and
  tighten the Cd band against NASA TMR data.

**Beyond:**
- Promote `provenance-completeness` to a required status check once the
  `vv` self-hosted runner is registered and stable.
- Vault auto-unseal is not configured (no cloud KMS) — unseal is manual.
- Optional in-LXC Caddy TLS front for MLflow/MinIO.

## 8. Pointers for the next session

- **Read first:** this handoff, `docs/adrs/ADR-004-*.md`,
  `docs/runbooks/stage-04-provenance-deploy.md`, CLAUDE.md (Stage 04 entry).
- **Do not re-read:** the provenance modules / Ansible roles — committed and
  complete.
- **Run first to verify the world:**
  ```bash
  cd /root/projects/aero-research-platform
  uv pip install -e ".[openfoam,provenance,dev]"
  .venv/bin/pytest -q tests/unit tests/stage_04        # 48 pass, 2 slow skip
  curl -sf http://aero-mlflow:5000/health              # once deployed
  ```

## 9. Artifacts produced

Branch `stage-04/provenance-backbone` (`453bfb5`→`e6863bc`, 8 commits):

- **Provenance core:** `aero/provenance/{four_fold,mlflow,db}.py`,
  `aero/provenance/__init__.py`.
- **Config:** `conf/{config.yaml,case/naca0012.yaml,mlflow/default.yaml,
  provenance/default.yaml}`; `aero/cli.py` Hydra wiring + `--allow-dirty`.
- **Migration:** `alembic.ini`, `db/env.py`, `db/script.py.mako`,
  `db/migrations/004_provenance.{sql,py}`,
  `db/provision/aero_databases.sql`.
- **DVC:** `.dvc/config`, `.dvcignore`, `data/references/naca0012/
  naca0012.csv.dvc`.
- **Infra-as-code:** `ansible/roles/aero-vault/`, `ansible/roles/aero-mlflow/`,
  inventory + `site.yml` updates, `scripts/provision_aero_lxc.sh` (LXC 217).
- **Tests/CI:** `tests/stage_04/`, `.github/workflows/provenance-completeness.yml`.
- **Docs:** `ADR-004`, `docs/release/zenodo.md`,
  `docs/runbooks/stage-04-provenance-deploy.md`; CLAUDE.md update.

## 10. Confidence / risk note

- **High confidence:** the in-repo provenance backbone — four-fold tuple
  computation, the strict `ProvenanceTuple`, Hydra compose → `CaseSpec`,
  `config_hash` determinism, the alembic migration. 48 hermetic tests cover it.
- **Medium confidence:** the Ansible roles (`aero-vault`, `aero-mlflow`) and
  the Vault-Agent bootstrap ordering — written to the existing role
  conventions but **not yet executed**; the operator runbook is the first
  real exercise. Expect to iterate on the roles during deployment.
- **Low confidence / operator-owned:** Vault `operator init` / unseal-key
  custody; the Postgres LXC 202 superuser credentials; the Zenodo OAuth.
- **Outstanding risks:** none blocking the in-repo work. The stage is not
  complete until the runbook runs green and the four-tuple is verified
  end-to-end against the live cluster.
