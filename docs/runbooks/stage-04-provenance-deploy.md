# Runbook — Stage 04 Provenance Backbone deployment

Operator-run deployment of the Stage 04 infrastructure. The in-repo backbone
(code, migration, Ansible roles, tests, CI) is already committed; this runbook
stands up the live services. Run it from the Proxmox host as root, in
`/root/projects/aero-research-platform`, on the `stage-04/provenance-backbone`
branch.

The auto-mode classifier blocks the Claude Code agent from executing
shared-Proxmox / shared-Postgres changes, so these steps are operator-run.
After Step 10, hand the Zenodo concept DOI back to the agent to finalize.

**Secrets:** never paste unseal keys, the root token, or passwords into the
repo, a commit, or the chat. Hold them in a password manager.

---

## Step 1 — Provision the aero-vault LXC (217)

```bash
cd /root/projects/aero-research-platform
bash scripts/provision_aero_lxc.sh
```

Idempotent — LXCs 210-216 are skipped; only 217 `aero-vault`
(192.168.2.239 / 10.10.10.27) is created and started.

## Step 2 — Deploy Vault

```bash
cd ansible
ansible-playbook site.yml --limit aero-vault --tags base,vault --check   # dry run
ansible-playbook site.yml --limit aero-vault --tags base,vault           # apply
```

## Step 3 — Initialize and unseal Vault

```bash
ssh root@aero-vault
export VAULT_ADDR=https://aero-vault:8200 VAULT_SKIP_VERIFY=true
vault operator init -key-shares=5 -key-threshold=3
#  >>> SAVE the 5 unseal keys + initial root token to a password manager <<<
vault operator unseal   # run 3x with 3 distinct unseal keys
vault login <root-token>
```

## Step 4 — Seed Vault (secrets + AppRole)

Still on `aero-vault`, logged in with the root token. Pick strong values
(examples use `openssl rand -base64 24`); record them in the password manager.

```bash
vault secrets enable -path=aero kv-v2

vault kv put aero/postgres/aero_mlflow_user        password='<PW_MLFLOW>'
vault kv put aero/postgres/aero_provenance_reader  password='<PW_READER>'
vault kv put aero/minio/root      user='aero-minio-root' password='<MINIO_ROOT_PW>'
vault kv put aero/minio/dvc-sa    access_key='<DVC_AK>'    secret_key='<DVC_SK>'
vault kv put aero/minio/mlflow-sa access_key='<MLFLOW_AK>' secret_key='<MLFLOW_SK>'

# read policy for the Vault Agent
vault policy write aero-mlflow - <<'EOF'
path "aero/data/*" { capabilities = ["read"] }
EOF

# AppRole for the aero-mlflow Vault Agent
vault auth enable approle
vault write auth/approle/role/aero-mlflow \
    token_policies=aero-mlflow token_ttl=1h token_max_ttl=4h secret_id_ttl=0
vault read  -field=role_id   auth/approle/role/aero-mlflow/role-id       > /tmp/role-id
vault write -f -field=secret_id auth/approle/role/aero-mlflow/secret-id  > /tmp/secret-id
```

Place the AppRole credentials on `aero-mlflow` (the role's first task asserts
they exist):

```bash
ssh root@aero-mlflow 'mkdir -p /etc/vault-agent && chmod 0750 /etc/vault-agent'
scp /tmp/role-id /tmp/secret-id root@aero-mlflow:/etc/vault-agent/
ssh root@aero-mlflow 'chmod 0600 /etc/vault-agent/role-id /etc/vault-agent/secret-id'
rm /tmp/role-id /tmp/secret-id
```

Also migrate the Stage 02 OpenFOAM signing-key escrow into Vault (optional this
session; keep the TrueNAS copy until verified):
`vault kv put aero/signing/openfoam-key key=@<escrow-file>`.

## Step 5 — Create the aero databases on the shared Postgres LXC 202

**Review `db/provision/aero_databases.sql` before running** — it is additive
only (two new DBs, two new roles; touches nothing else). Run as a Postgres
superuser:

```bash
psql -h 192.168.2.184 -U <superuser> -d postgres \
     -v pw_mlflow="'<PW_MLFLOW>'" \
     -v pw_reader="'<PW_READER>'" \
     -f db/provision/aero_databases.sql
```

Add one `pg_hba.conf` line on LXC 202 authorizing aero-mlflow's LAN IP, then
reload:

```
# /etc/postgresql/*/main/pg_hba.conf  — append:
host  aero_mlflow,aero_provenance  aero_mlflow_user  192.168.2.234/32  scram-sha-256
```
```bash
# on LXC 202:
systemctl reload postgresql
```

Verify from aero-mlflow:
```bash
ssh root@aero-mlflow "psql 'postgresql://aero_mlflow_user:<PW_MLFLOW>@192.168.2.184:5432/aero_mlflow' -c 'SELECT 1'"
```

## Step 6 — Initialize MLflow's backend schema

```bash
ssh root@aero-mlflow \
  "PGPW='<PW_MLFLOW>' /opt/aero/mlflow-venv/bin/mlflow db upgrade \
   postgresql://aero_mlflow_user:\$PGPW@192.168.2.184:5432/aero_mlflow"
```
(Run after Step 7's venv exists, or re-run; `mlflow db upgrade` is idempotent.)

## Step 7 — Deploy MinIO + MLflow

```bash
cd ansible
ansible-playbook site.yml --limit aero-mlflow --tags mlflow --check   # dry run
ansible-playbook site.yml --limit aero-mlflow --tags mlflow           # apply
```

Then create the two MinIO service accounts with the keys written to Vault in
Step 4 (MinIO must be running first):

```bash
ssh root@aero-mlflow
set -a; . /etc/aero/minio.env; set +a
mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc admin user svcacct add local "$MINIO_ROOT_USER" \
    --access-key '<DVC_AK>'    --secret-key '<DVC_SK>'
mc admin user svcacct add local "$MINIO_ROOT_USER" \
    --access-key '<MLFLOW_AK>' --secret-key '<MLFLOW_SK>'
systemctl restart mlflow
```

Verify: `curl -sf http://aero-mlflow:5000/health` and
`mc ls local` shows `aero-mlflow/` and `aero-dvc/`.

## Step 8 — Apply the provenance migration

```bash
export AERO_PROVENANCE_DSN="postgresql://aero_mlflow_user:<PW_MLFLOW>@192.168.2.184:5432/aero_provenance"
.venv/bin/alembic upgrade head
# grant the reader SELECT on the now-existing table:
psql "$AERO_PROVENANCE_DSN" -c \
  "GRANT SELECT ON ALL TABLES IN SCHEMA public TO aero_provenance_reader;"
```

## Step 9 — DVC remote credentials + round-trip

```bash
.venv/bin/dvc remote modify --local aero-minio access_key_id     '<DVC_AK>'
.venv/bin/dvc remote modify --local aero-minio secret_access_key '<DVC_SK>'
.venv/bin/dvc push
.venv/bin/dvc fetch && .venv/bin/dvc status -c
```

## Step 10 — End-to-end verification

```bash
export AERO_PROVENANCE_DSN="postgresql://aero_mlflow_user:<PW_MLFLOW>@192.168.2.184:5432/aero_provenance"
.venv/bin/aero run naca0012 --executor local-ssh
```

Expect the four tags on the MLflow run and a matching Postgres row:
```bash
psql "postgresql://aero_provenance_reader:<PW_READER>@192.168.2.184:5432/aero_provenance" \
  -c "SELECT * FROM mlflow_artifact_provenance ORDER BY created_at DESC LIMIT 1;"
```

## Step 11 — CI secret + Zenodo

- **GitHub repo secret:** add `AERO_PROVENANCE_DSN` (the libpq DSN) so the
  `provenance-completeness` workflow can run.
- **Zenodo** (see `docs/release/zenodo.md`): sign in with the repo's GitHub
  account, enable the `aero-research-platform` integration, reserve the
  **concept DOI**. Then hand the DOI back to the Claude Code agent — it writes
  it into `CITATION.cff`, validates with `cffconvert`, and finalizes Stage 04.

---

## Deploy-order dependencies

```
Step 1 (LXC) -> 2 (Vault) -> 3 (init/unseal) -> 4 (seed Vault + AppRole)
                                                      |
Step 5 (Postgres DBs) ---------------------------------+--> 7 (MinIO+MLflow)
                                                      |        |
                                              6 (mlflow db) <---+
                                                               |
                                          8 (alembic) <- 7 ;  9 (DVC) <- 7
                                                               |
                                                       10 (end-to-end) <- 8,9
```
