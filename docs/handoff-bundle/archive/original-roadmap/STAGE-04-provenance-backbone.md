# STAGE-04: Provenance Backbone (revised)

## REQUIREMENTS THIS STAGE DELIVERS

From the project brief §"The provenance contract (four-fold)" and §"Compute
targets and topology" (revised), and Pass 3 §8:

- New `aero_provenance` database in the **existing Postgres LXC 202**, with
  `pgvector` extension enabled if not already present.
- MLflow tracking server deployed on the new `aero-mlflow` LXC, backed by
  Postgres LXC 202 and a local MinIO sidecar.
- MinIO sidecar inside `aero-mlflow` with its data directory pointing at
  `/mnt/aero/mlflow-artifacts/` (TrueNAS NFS). This gives S3 protocol for
  MLflow and DVC while TrueNAS handles durability.
- DVC configured with a remote pointing at `/mnt/aero/dvc-remote/` (TrueNAS
  NFS, S3-protocol via the same MinIO sidecar).
- Apptainer SIF SHA256 hashing automated; signing key handling already in
  place from Stage 02.
- Hydra-based config system added; resolved-config hashing automated.
- The four-fold provenance tuple — (git_sha, dvc_input_hash, container_sif_sha256,
  config_hash) — logged as MLflow tags on every run.
- Postgres table `mlflow_artifact_provenance` for cross-run queries.
- CITATION.cff updated with reserved Zenodo concept DOI; GitHub-Zenodo integration
  enabled.
- ADR-004 documents the provenance contract.

## ROLE

You are turning the bare-bones MLflow logging from Stage 03 into the full,
peer-review-grade provenance backbone. From this stage on, every CFD or training
run logs the four-fold tuple. The walking skeleton is reinforced.

You are extending the **existing** Postgres LXC 202 with a new database; you are
NOT provisioning fresh Postgres. You are running MLflow + MinIO in the new
`aero-mlflow` LXC; you are NOT installing them on the host or on Postgres LXC
202.

## GOAL

1. **In the existing Postgres LXC 202** (additive only):
   - Connect as a Postgres superuser (operator provides credentials path)
   - Verify or create `pgvector` extension at the cluster level
   - Create role `aero_mlflow_user` (full access to `aero_provenance` and
     `aero_mlflow` databases only)
   - Create role `aero_provenance_reader` (read-only on `aero_provenance`)
   - Create database `aero_mlflow` (owned by `aero_mlflow_user`) for MLflow's
     tracking metadata
   - Create database `aero_provenance` (owned by `aero_mlflow_user`) for the
     provenance mirror
   - Verify connectivity from `aero-mlflow` LXC: `psql -h <postgres-202> -U
     aero_mlflow_user -d aero_mlflow -c 'SELECT 1'`
   - **All of the above proposed first, executed only after `approved`.**
     Operator confirms before any `CREATE` on the shared Postgres.
2. **On the new `aero-mlflow` LXC**:
   - Install MinIO via the official `.deb` (or Apptainer SIF; propose). Service
     under systemd. Data directory: `/mnt/aero/mlflow-artifacts/` (NFS from
     TrueNAS, mounted in Stage 02). Buckets created at startup: `aero-mlflow`,
     `aero-dvc`. Endpoint: `http://aero-mlflow:9000`.
   - MinIO credentials in environment from Vault (or `/etc/aero/minio.env` mode
     0600 if Vault not yet stood up — flag this in the handoff).
   - Install MLflow via `pip` or Apptainer SIF (propose). Service under systemd.
     Backend: Postgres LXC 202 (`aero_mlflow` DB). Artifact store: MinIO
     (`s3://aero-mlflow/`). Listen on `aero-mlflow:5000`. Reverse-proxy via
     Caddy on the host for TLS (VPN-only access; no public exposure).
3. Initialize DVC in the repo (if not done in Stage 03):
   - `dvc init`
   - Remote `aero-minio` pointing at `s3://aero-dvc/` with endpoint
     `http://aero-mlflow:9000`
   - Credentials via `dvc remote modify aero-minio access_key_id ...
     secret_access_key ...` using the MinIO service-account credentials (NOT
     root MinIO creds; create a scoped service account)
   - Move the NACA 0012 STL from Stage 03 to DVC tracking: `dvc add
     data/references/naca0012/naca0012.stl && dvc push`
4. Author `aero/provenance/four_fold.py`:
   - `compute_provenance(case_dir: Path, container_sif: Path, config_path: Path)
     -> ProvenanceTuple` (pydantic)
   - `git_sha`: `git rev-parse HEAD`; fail loud if tree is dirty unless
     `--allow-dirty` (tag becomes `<sha>-dirty`)
   - `dvc_input_hash`: sha256 over the sorted list of `dvc status -c` outputs
     for `.dvc`-tracked inputs the case touches
   - `container_sif_sha256`: read from `containers/SHA256SUMS`
   - `config_hash`: sha256 of the resolved Hydra config serialized as canonical
     JSON (`omegaconf.OmegaConf.to_container(cfg, resolve=True)` then
     `json.dumps(..., sort_keys=True, separators=(',', ':'))`)
5. Refactor `aero/provenance/mlflow_basic.py` from Stage 03 into
   `aero/provenance/mlflow.py`:
   - Connects to the remote tracking server (URL from config:
     `http://aero-mlflow:5000`)
   - On every `start_run`, calls `compute_provenance` and sets all four tags
   - Fails loud if any of the four cannot be computed
6. Add Hydra to `aero/cli.py` so `aero run naca0012` resolves a layered config
   into a single dict and serializes it deterministically for hashing.
7. Migrate the OpenFOAM `CaseSpec` (Stage 03) to be Hydra-loadable. Pydantic
   strict validation; Hydra produces the dict, pydantic validates.
8. Author the Postgres migration `db/migrations/004_provenance.sql`:
   ```sql
   CREATE TABLE mlflow_artifact_provenance (
       run_id TEXT PRIMARY KEY,
       git_sha TEXT NOT NULL,
       dvc_input_hash TEXT NOT NULL,
       container_sif_sha256 TEXT NOT NULL,
       config_hash TEXT NOT NULL,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );
   CREATE INDEX idx_provenance_git ON mlflow_artifact_provenance(git_sha);
   CREATE INDEX idx_provenance_dvc ON mlflow_artifact_provenance(dvc_input_hash);
   ```
   Apply via alembic against `aero_provenance` DB on LXC 202. Add
   `aero/provenance/db.py` that mirrors MLflow tags into this table on
   `start_run`.
9. Add `aero[provenance]` extras: `mlflow`, `dvc[s3]`, `boto3`, `hydra-core`,
   `omegaconf`, `psycopg2-binary`, `alembic`.
10. Re-run the NACA 0012 case (from Stage 03) through the new pipeline. Verify:
    - The MLflow run has all four tags
    - The Postgres `mlflow_artifact_provenance` table has the row
    - The artifact (force coefficient log + any output) lands in MinIO under
      `s3://aero-mlflow/<run-id>/`
    - DVC `push` and `fetch` round-trip correctly against the
      `s3://aero-dvc/` remote
11. Enable the GitHub-Zenodo integration. Reserve a concept DOI. Write the DOI
    back into CITATION.cff. Document the workflow in `docs/release/zenodo.md`.
12. Author ADR-004:
    - The four-fold provenance contract (verbatim from the project brief)
    - The dirty-tree policy (default: fail loud; `--allow-dirty` for explicit
      exploration with the `-dirty` suffix on the SHA tag)
    - DVC remote choice (TrueNAS NFS via MinIO sidecar) and rationale (vs a
      separate dedicated MinIO LXC, which we rejected because the NFS-backed
      MinIO inside `aero-mlflow` gives us one less service to maintain while
      TrueNAS handles durability)
    - Hydra config resolution order
    - The decision to extend existing Postgres LXC 202 rather than provision a
      fresh one (rationale: application-agnostic shared platform, additive
      only, operator-explicit consent)
13. Update CLAUDE.md to add: "Every run logs four tags, no exceptions. The
    Postgres mirror lives in the shared LXC 202 — read/writes go through MLflow,
    never direct."
14. Add a CI check `provenance-completeness` that runs the smoke test (NACA
    0012 via the new pipeline) and asserts the MLflow run has all four tags
    populated and the Postgres row exists. Make it a required status check on
    `main`.
15. Tag `v0.0.4`.

## WHY

Provenance must be a contract, not a convention. From Stage 04 onward, every
number the platform produces is *cited-able* with a four-tuple that uniquely
identifies code, data, container, and config state. The Zenodo DOI then makes
the whole thing citable from external papers.

Reusing the existing Postgres LXC 202 (additively, with new DBs and roles)
avoids running parallel Postgres instances on a memory-constrained host. The
shared Postgres is application-agnostic — adding new DBs is purely additive and
zero-risk to the other workloads.

The MinIO sidecar inside `aero-mlflow` backed by TrueNAS NFS is the cleanest
way to satisfy three requirements at once: S3 protocol for MLflow and DVC,
TrueNAS-managed durability, and only one new service to maintain.

Postgres mirroring of MLflow tags enables fast cross-run queries
("show me all runs against container SHA X" or "what runs produced figures for
paper Y"). MLflow's own tag search is slower and lossier.

## HOW

- MLflow's backend Postgres needs the schema initialized. Run `mlflow db upgrade
  postgresql+psycopg2://aero_mlflow_user:...@aero-postgres:5432/aero_mlflow`
  once during the Ansible-driven setup of `aero-mlflow`.
- DVC remote configuration is in `.dvc/config` (committed to git, no
  credentials in it) plus `.dvc/config.local` (gitignored, credentials).
- The MinIO service account for DVC: scope to just the `aero-dvc` bucket
  (read+write). The DVC credentials are *not* root MinIO creds.
- The MinIO service account for MLflow: scope to just the `aero-mlflow` bucket.
- For Hydra config hashing: serialize via `OmegaConf.to_container(cfg,
  resolve=True)` then `json.dumps(..., sort_keys=True, separators=(',', ':'))`
  before sha256. Reproducible across machines.
- Postgres mirror: implement as synchronous insert during MLflow `start_run`
  (simplest; latency negligible). Future-proofing for an async webhook can be
  an ADR if it becomes necessary.
- Dirty-tree policy: default fail-loud. `--allow-dirty` flag annotates the
  MLflow tag (`git_sha: abc123-dirty`) with a prominent warning. Documented in
  ADR-004.

## BEFORE YOU START — READ

- `00-CONTEXT-project-brief.md` (revised compute targets section)
- `STAGE-04-provenance-backbone.md` (this file)
- `docs/handoffs/STAGE-03-*-DONE-*.md`
- ADR-002 (topology), ADR-003 (walking-skeleton out-of-scope list — Stage 04
  lifts the "DVC inputs, full provenance" items)
- `docs/architecture/proxmox-topology.md` (Stage 02 output)

## GUARDRAILS — DO NOT

1. Do NOT log a run with fewer than four provenance tags. Fail loud.
2. Do NOT commit MinIO credentials, MLflow service tokens, or any DB password
   to the repo. Vault or `/etc/aero/*.env` mode 0600.
3. Do NOT expose MLflow UI or MinIO UI publicly. VPN-only.
4. Do NOT use DVC's `--force` to overwrite tracked files in this stage.
5. Do NOT introduce a separate provenance DB schema in addition to MLflow's;
   `mlflow_artifact_provenance` is a *mirror*, not a parallel source of truth.
6. Do NOT allow Hydra to overwrite the `git_sha` or `container_sif_sha256` tags
   from config. Those are computed, never user-supplied.
7. **Do NOT alter any existing Postgres database, role, or extension** on LXC
   202 beyond what's explicitly added. Read the existing `\du`, `\l`, and
   `\dx` output first; document them in the handoff for reference; touch
   nothing outside the new aero objects.
8. Do NOT run `DROP` or `ALTER` against any non-aero object on LXC 202. Ever.
9. Do NOT install MLflow or MinIO on the Proxmox host or on Postgres LXC 202.
   They live in `aero-mlflow`.

## DELIVERABLES

- [ ] Existing Postgres LXC 202 has new `aero_provenance` and `aero_mlflow`
      DBs, owned by `aero_mlflow_user`, with `pgvector` available
- [ ] `aero-provenance_reader` role exists and is read-only
- [ ] `aero-mlflow` LXC runs MLflow + MinIO under systemd
- [ ] MLflow UI reachable on VPN: `curl -sf
      http://aero-mlflow.10.10.10.<x>:5000/health`
- [ ] MinIO operational; `aero-mlflow` and `aero-dvc` buckets exist
- [ ] DVC remote configured; round-trip works: `dvc push && dvc fetch`
- [ ] Tracked NACA 0012 STL: `dvc status` clean
- [ ] NACA 0012 case re-runs through the new pipeline and MLflow shows all
      four tags
- [ ] Postgres `mlflow_artifact_provenance` table populated with the row
- [ ] CITATION.cff has a reserved Zenodo DOI; `cffconvert --validate` passes
- [ ] CI `provenance-completeness` job green, listed as required status check
- [ ] `pytest -q tests/stage_04/` passes
- [ ] ADR-004 committed
- [ ] Post-stage handoff written
- [ ] Tag `v0.0.4`

## PROPOSE FIRST, EXECUTE LATER

Wait for `approved` before:

- The Postgres role names, password handling, and the proposed `CREATE
  DATABASE / CREATE ROLE` SQL block (operator reviews the exact statements)
- Any change to LXC 202's `postgresql.conf` or `pg_hba.conf` (e.g., adding the
  `aero-mlflow` LXC IP to allowed hosts) — operator confirms before edits
- The Zenodo concept DOI reservation (it's permanent)
- The MinIO root credentials and the scoped service accounts (Vault path or
  `/etc/aero/minio.env` path)
- Adding `provenance-completeness` as a required check on `main`
- Any `DROP TABLE`, `DROP DATABASE`, `DROP ROLE` if a prior attempt needs to
  be wiped — never on existing non-aero objects

## POST-STAGE HANDOFF

Required emphases:

- **The four-tuple in action**: paste one example MLflow run's tags into the
  handoff for reference.
- **Postgres LXC 202 inventory snapshot taken at start of stage**: which
  databases, roles, extensions existed BEFORE this stage's additions. So we
  can confirm post-stage that we only added.
- **Schema migration**: explicit `alembic upgrade head` instruction for
  subsequent stages.
- **Credential storage paths** (paths only, never the values): MinIO root, MinIO
  service accounts (DVC + MLflow), Postgres role passwords.
- **Apptainer-over-NFS verdict**: did running MLflow/MinIO with NFS-backed
  storage have issues? Stage 09+ will hit this harder.
- **Open items for Stage 05**: V&V harness must use the four-tuple as the
  "this run" key; design the harness around it.
- **Gotchas**: anything surprising about MLflow + Postgres + MinIO + NFS on a
  memory-constrained host.
