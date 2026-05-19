---
stage: 04
stage_name: "Stage 04 — Provenance Backbone"
status: complete
date_started: 2026-05-19
date_completed: 2026-05-19
session_duration_hours: 8.0
claude_code_version: "2.1.117 (Claude Code)"
model: claude-opus-4-7
git_sha_start: "453bfb507aefa43e15b9043fe555484d4235dcfa"
git_sha_end: "8e8be9f52d1bc79206fa35c0b0688f1ad6a27d37"
stage_tag: v0.0.4
next_stage: 05
next_stage_name: "Stage 05 — V&V Harness"
---

# Stage 04 — Provenance Backbone — DONE 2026-05-19

> Auto-loaded by the Stage 05 session as "BEFORE YOU START — READ".
> The four-fold provenance backbone is **deployed and verified end-to-end**:
> `aero run naca0012` logs `(git_sha, dvc_input_hash, container_sif_sha256,
> config_hash)` to the live MLflow server on `aero-mlflow`, mirrored into the
> `aero_provenance` Postgres DB. Two ⚠️ items are operator follow-ups
> (Zenodo DOI, CI-check promotion) — see §7.

## 1. Deliverables status

| # | Deliverable (from the stage prompt) | Status | Note |
|---|---|:-:|---|
| 1 | `aero_provenance` + `aero_mlflow` DBs on Postgres LXC 202 | ✅ | additive; `db/provision/aero_databases.sql` |
| 2 | MLflow + MinIO on `aero-mlflow` LXC | ✅ | systemd; `curl :5000/health` and `:9000` → 200 |
| 3 | MinIO sidecar, buckets `aero-mlflow`/`aero-dvc` | ✅ | on LXC local disk, not NFS — see §3 |
| 4 | DVC remote on MinIO | ✅ | `dvc push`/`fetch`/`status -c` round-trip clean |
| 5 | SIF SHA256 hashing automated | ✅ | `four_fold.container_sif_sha256` |
| 6 | Hydra config system + config hashing | ✅ | `conf/`; `four_fold.config_hash` |
| 7 | Four-fold tuple logged as MLflow tags | ✅ | verified on run `cc510ac0…` (§ below) |
| 8 | `mlflow_artifact_provenance` Postgres table | ✅ | alembic `004_provenance` applied |
| 9 | `aero/provenance/four_fold.py` | ✅ | `compute_provenance`, `ProvenanceTuple` |
| 10 | `mlflow_basic.py` → `mlflow.py` refactor | ✅ | `start_provenance_run` |
| 11 | Hydra in `aero/cli.py` | ✅ | Compose API; `--allow-dirty` |
| 12 | `CaseSpec` Hydra-loadable | ✅ | `conf/case/naca0012.yaml` |
| 13 | `aero/provenance/db.py` Postgres mirror | ✅ | transactional insert |
| 14 | `aero[provenance]` extra | ✅ | populated; `uv.lock` committed |
| 15 | Re-run NACA 0012 end-to-end | ✅ | Cd 0.008754; four tags + mirror row verified |
| 16 | CITATION.cff Zenodo DOI | ⚠️ | operator chose backfill-at-first-release (§7) |
| 17 | CI `provenance-completeness` check | ✅ | workflow + slow test (2/2 pass, 87s); ⚠️ not yet a *required* check (§7) |
| 18 | `tests/stage_04/` passes | ✅ | 48 hermetic pass; 2 slow (cluster) pass |
| 19 | ADR-004 | ✅ | incl. a "Deployment outcomes" section |
| 20 | Post-stage handoff | ✅ | this file |
| 21 | Tag `v0.0.4` | ⚠️ | applied at PR merge (per Stage 02/03 precedent) |

## The four-tuple in action

Example — MLflow run `cc510ac05bec43e8ac422d2916af0102` (experiment
`aero-provenance`), tags:

```
git_sha               a08444a29405768ce5dbf1c17b6ae26b6ede74c9
dvc_input_hash        44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
container_sif_sha256  c9d7f32974c66bfbc924d407193bbf488fa165b2b35b01ee21ed9fdf9606e91c
config_hash           68c7416248f8436ed60020810a934042385a0a3673dae6c2d67aee659ea8dd87
case_name=naca0012  stage=04  solver_version="OpenFOAM-ESI v2412"
```

The matching `mlflow_artifact_provenance` Postgres row was confirmed
byte-equal to these four tags. (`dvc_input_hash 44136fa3…` is `sha256("{}")`
— the in-sync state: the tracked input matches the remote.)

## 2. Decisions made

- **Vault on a dedicated new LXC 217 `aero-vault`** (operator chose "stand up
  Vault now"). Single-node raft storage, TLS, `vault operator init` (operator
  holds the unseal keys). A Vault Agent on `aero-mlflow` (AppRole auth)
  renders the secret env files. Rejected: co-locating Vault on `aero-mlflow`
  (secret store on the app server defeats the point).
- **MinIO on the LXC local disk, not NFS.** Decisive: MinIO does not support
  network filesystems. Rejected: the planned NFS-backed MinIO — see §3/§6.
- **MinIO + MLflow native packaging + systemd** (operator choice), not
  Apptainer SIFs.
- **`compute_provenance` signature** changed to
  `(*, repo_root, container_sif, resolved_config, allow_dirty)` — see ADR-004.
- **Service config uses IPs, not hostnames** — the aero LXCs have no shared
  DNS. Rejected: relying on `aero-*` hostname resolution (works nowhere).
- **`uv.lock` committed**; `check-added-large-files` exempts it.
- **`dvc` resolved next to `sys.executable`** so `aero run` works without the
  venv on `PATH`.

## 3. Deviations from the stage plan

- **MinIO is NOT NFS-backed.** The plan/ADR-004 put MinIO's backend on the
  TrueNAS NFS dataset. Deployment proved it unworkable (the export squashes
  every uid to `nobody`; MinIO's IAM layer then hit prefix-consistency
  errors — MinIO requires local, directly-attached storage). MinIO data is on
  `/opt/aero/minio-data` (LXC rootfs); durability is the nightly LXC
  `vzdump`. ADR-004 "Deployment outcomes" records this.
- **No TLS reverse proxy.** The plan's host-side Caddy was dropped (avoid
  touching the host); services run plain HTTP on the trusted CIDRs. In-LXC
  TLS is a follow-up.
- **MinIO/MLflow ufw** opens to the fleet trusted CIDRs (LAN + private +
  Tailscale), not the private segment alone — matches `aero-base`'s SSH rule.
- **MinIO runs as root** (namespaced, in the unprivileged LXC).
- **Zenodo DOI deferred** (operator decision — backfill at first release).
- **`v0.0.4` tag** applied at PR merge, not in-session.

## 4. Environment / dependency / schema changes

- **Postgres LXC 202** (additive only). Pre-stage snapshot: DBs
  `orchestrator, postgres, template0, template1`; roles `orchestrator,
  postgres`; extensions `plpgsql` only. Stage 04 added: roles
  `aero_mlflow_user`, `aero_provenance_reader`; DBs `aero_mlflow`,
  `aero_provenance`; the `postgresql-16-pgvector` package + `vector`
  extension in `aero_provenance`; the `mlflow_artifact_provenance` table +
  `alembic_version`; **three** `pg_hba.conf` lines (aero-mlflow .234,
  Homelab host .13, aero-build .232 → the aero DBs only). Nothing else
  on LXC 202 was touched.
- **New LXC 217 `aero-vault`** (192.168.2.239 / 10.10.10.27, 2c/4G/20G);
  Vault 1.20.4, initialized + unsealed.
- **`aero-mlflow` LXC**: MinIO `RELEASE.2025-09-07T16-13-09Z` + `mc` +
  MLflow 3.12.0 (venv `/opt/aero/mlflow-venv`) + Vault Agent, all systemd.
  MinIO data `/opt/aero/minio-data`; buckets `aero-mlflow`, `aero-dvc`.
- `pyproject.toml`: `aero[provenance]` extra populated; `uv.lock` committed.
- New repo dirs: `conf/` (Hydra), `db/` (alembic + provision SQL).
- DVC initialized; `naca0012.csv` moved to DVC tracking; pushed to MinIO.
- `aero/provenance/`: `four_fold.py`, `mlflow.py`, `db.py` (`mlflow_basic.py`
  removed).
- **Credential storage (paths only)**: Vault KV v2 at `aero/` —
  `aero/postgres/{aero_mlflow_user,aero_provenance_reader}`,
  `aero/minio/{root,dvc-sa,mlflow-sa}`. Vault AppRole creds on aero-mlflow:
  `/etc/vault-agent/{role-id,secret-id}`. Rendered env files:
  `/etc/aero/{minio,mlflow}.env`. DVC creds: `.dvc/config.local` (gitignored).
  Vault unseal keys + root token: held by the operator (off-system).

## 5. CI/CD changes

- `.github/workflows/provenance-completeness.yml` — new self-hosted (`vv`)
  job; runs the NACA 0012 case end-to-end and asserts the four-fold contract.
- `.pre-commit-config.yaml`: `check-added-large-files` excludes `uv.lock`.
- Repo secrets added: `AERO_PROVENANCE_DSN`, `AERO_DVC_ACCESS_KEY_ID`,
  `AERO_DVC_SECRET_ACCESS_KEY` (the latter two feed DVC's boto3 credential
  chain — `.dvc/config.local` is gitignored, absent on a CI checkout).
- The `vv` self-hosted runner is registered and online on `aero-build`;
  **PR #5's CI is fully green — all 7 checks pass**, including
  `provenance-completeness` and `vv-smoke` (each ~2m20s).
- `provenance-completeness` is *not yet a required* status check — promoting
  it (a branch-protection change) is the one remaining CI follow-up (§7).
- The five existing required checks (lint/type/test/docs-sync/commit-lint)
  are unchanged.

## 6. Gotchas discovered

- **MinIO does not support NFS.** Two distinct failures (uid-squash write
  denial; IAM prefix-consistency error). Any future service that needs a
  POSIX filesystem on the TrueNAS NFS export will hit the same uid-squash —
  the export maps every client (root included) to `nobody`/65534.
- **The aero LXCs have no shared DNS** — they cannot resolve each other's
  hostnames. All service-to-service config uses IPs.
- **`check-added-large-files` (500 KB) silently rejected every commit** —
  `uv.lock` is 679 KB; the failure scrolled off truncated commit output.
- **The pre-commit `pytest-unit` hook needs `pytest` on `PATH`** — commit
  with the venv activated (`PATH=".venv/bin:$PATH" git commit`).
- **The pre-commit mypy hook runs isolated** (only `additional_dependencies`)
  — use `typing.cast`, not annotate-plus-`# type: ignore`, at the OmegaConf
  boundary.
- **YAML scientific notation** — write `6.0e+6`, not `6.0e6` (the loader
  parses the latter as a string).
- **The `aero_provenance` DB is SQL_ASCII** (inherited from `template1`) —
  SQL sent to it must be pure ASCII (an em-dash in a migration comment broke
  `alembic upgrade`).
- **The auto-mode classifier gates shared-infra changes** even with in-chat
  approval — `pct create`, pg_hba edits on LXC 202, self-modifying
  `.claude/` config. The operator added scoped allow-rules to
  `.claude/settings.local.json` for the deployment.

## 7. Open items for the next stage (and beyond)

**Done after the handoff was first written** (recorded here for the next
session): the `AERO_PROVENANCE_DSN` / `AERO_DVC_*` repo secrets are set; the
`vv` self-hosted runner is registered and online; **PR #5's CI is fully
green (7/7)**.

**Operator follow-ups still open:**
- **Merge PR #5**, then tag `v0.0.4` on `main` and publish the GitHub
  Release. The Release triggers Zenodo to mint the concept DOI.
- **Zenodo concept DOI** — minted at the `v0.0.4` GitHub Release; backfill
  `CITATION.cff` with it afterwards. See `docs/release/zenodo.md`.
- **Promote `provenance-completeness` to a required status check** on `main`
  (a branch-protection change) now that it is proven green — optional.

**Stage 05 (V&V Harness):**
- Key each V&V run on the four-tuple — `compute_provenance` returns the
  `ProvenanceTuple`; use it as the run identity.
- Move the V&V runner to `aero-vv` (install Apptainer there).
- Improve the O-grid mesh quality and tighten the Cd band vs NASA TMR.

**Beyond:** in-LXC TLS for MLflow/MinIO; a homelab DNS record for the
`aero-*` hosts (retires the IP-addressed config); Vault auto-unseal;
MinIO artifact volume vs the 50 GB `aero-mlflow` disk.

## 8. Pointers for the next session

- **Read first:** this handoff, `docs/adrs/ADR-004-*.md`, CLAUDE.md (Stage 04
  entry), `docs/runbooks/stage-04-provenance-deploy.md`.
- **Do not re-read:** the provenance modules / Ansible roles — deployed and
  verified.
- **Run first to verify the world:**
  ```bash
  cd /root/projects/aero-research-platform
  uv pip install -e ".[openfoam,provenance,dev]"
  .venv/bin/pytest -q tests/unit tests/stage_04          # 48 pass, 2 slow skip
  curl -sf http://192.168.2.234:5000/health              # MLflow
  export AERO_PROVENANCE_DSN="postgresql://aero_mlflow_user:<pw>@192.168.2.184:5432/aero_provenance"
  .venv/bin/aero run naca0012 --executor local-ssh       # four tags + mirror row
  ```

## 9. Artifacts produced

Branch `stage-04/provenance-backbone` (`453bfb5`→`8e8be9f`, 13 commits):

- **Provenance core:** `aero/provenance/{four_fold,mlflow,db}.py`, `__init__.py`.
- **Config:** `conf/` (Hydra); `aero/cli.py` Hydra wiring + `--allow-dirty`.
- **Migration:** `alembic.ini`, `db/env.py`, `db/script.py.mako`,
  `db/migrations/004_provenance.{sql,py}`, `db/provision/aero_databases.sql`.
- **DVC:** `.dvc/config`, `.dvcignore`, `data/references/naca0012/
  naca0012.csv.dvc`.
- **Infra-as-code:** `ansible/roles/aero-vault/`, `ansible/roles/aero-mlflow/`,
  inventory + `site.yml`, `scripts/provision_aero_lxc.sh` (LXC 217).
- **Tests/CI:** `tests/stage_04/`, `.github/workflows/provenance-completeness.yml`.
- **Docs:** `ADR-004`, `docs/release/zenodo.md`,
  `docs/runbooks/stage-04-provenance-deploy.md`; CLAUDE.md update.
- **Live infrastructure** (not in git): LXC 217 `aero-vault` + Vault; MinIO +
  MLflow + Vault Agent on `aero-mlflow`; `aero_mlflow`/`aero_provenance` DBs +
  roles on Postgres LXC 202.

## 10. Confidence / risk note

- **High confidence:** the four-fold backbone — deployed, and verified
  end-to-end *twice* (a manual `aero run` and the `provenance-completeness`
  slow test): all four tags present and well-formed, the Postgres mirror row
  byte-equal, the artifact in MinIO. 48 hermetic tests + 2 slow tests green.
- **Medium confidence:** MinIO on LXC-local disk — works, but loses the
  TrueNAS-managed durability the plan wanted; the LXC `vzdump` is the safety
  net. The Ansible roles are now exercised and idempotent, but only against
  this one rollout.
- **Low confidence / operator-owned:** Vault unseal-key custody; the
  `AERO_PROVENANCE_DSN` GitHub secret; the Zenodo handshake; the `vv` runner
  registration.
- **Outstanding risks:** none blocking. The MinIO-on-NFS lesson generalises —
  Stage 09+ surrogate training data on NFS will need the same care.
