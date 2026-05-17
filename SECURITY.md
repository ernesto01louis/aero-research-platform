# Security Policy

## Reporting a vulnerability

Email security issues to **gr7x8mjy5d@privaterelay.appleid.com** with the
subject line `[aero-research-platform security]`. Please **do not** open a
public GitHub issue for vulnerabilities.

Acknowledgement target: 72 h. Triage and fix timeline depends on severity
and pre-existing release schedule.

## Secret-handling policy

1. **No secrets in the repository.** `.env*`, `*.key`, `*.pem`, `*.p12`,
   `*.crt`, and `secrets/` are gitignored. The `gitleaks` pre-commit hook
   and CI scan reject pushes that contain plausible secrets.
2. **No secrets in commit messages, MLflow tags, PR descriptions, or
   container layer history.** Anything that ends up in `git log`, MLflow's
   tag store, Apptainer SIF metadata, or a CI log is permanent.
3. **Vault for everything that isn't local-dev.** A HashiCorp Vault instance
   on the Proxmox host (placeholder: `<vault-host-tbd-in-stage-02>`) holds
   cloud-GPU API keys (RunPod, Lambda Labs, Vast.ai), database credentials
   (Postgres LXC 202, MinIO service accounts, MLflow tracking), MCP-server
   tokens (GitHub PAT, future Postgres), the agentic-layer LLM API key, the
   Apptainer signing private key, and Zenodo API tokens.
4. **Local-dev secrets** live in `.env` (mode 0600, gitignored) for
   convenience; production runs read from Vault.
5. **No reuse across tiers.** RunPod keys for `production` runs are
   separate from `experiment`-tier keys; MinIO root credentials are
   separate from the scoped DVC and MLflow service accounts.

## Threat model

**Actor inventory:**

- Operator (Louis Ernesto Schulte Moredo) — single human developer with full
  repo admin and Proxmox-host root.
- Claude Code agent — elevated actor; can execute Bash, edit files, push
  branches, open PRs, configure branch protection, install host packages.
  Scope-limited by `.claude/settings.json` PreToolUse hooks: blocked from
  `rm -rf` on non-`/tmp` paths, `git push --force*`, `dvc destroy`,
  `DROP TABLE`, `pct destroy`, `qm destroy`, and writes to
  `/etc/network/interfaces`, `/etc/pve/`, `/etc/subuid`, `/etc/subgid`
  without explicit operator approval.
- NVIDIA NeMo Agent Toolkit (post-Stage 14) — autonomous CAE agent; runs
  with dedicated credentials scoped to `experiment` and `opportunistic`
  reliability tiers; cannot launch `production`-tier jobs without
  human-in-the-loop approval via Prefect pause/resume.

**Out of scope for v0.1:**

- Multi-tenant access (single-developer build).
- Adversarial supply-chain attacks against the underlying solvers
  (OpenFOAM, SU2, etc.) — we pin upstream containers by SHA256 and verify
  signatures where available, but full SBOM is post-v0.1.
- DoS against the cloud-GPU providers — cost cap policies (Stage 13)
  bound the blast radius but are not a security control.

## Code-execution surface

- **CI runners** — GitHub-hosted for now; Stage 13 wires a self-hosted
  runner labeled `vv` on the Proxmox `aero-build` LXC. Self-hosted runner
  scope is repo-only (not org-wide) and CODEOWNERS-restricted PRs only.
- **Apptainer SIFs** — built on `aero-build` LXC, signed with the operator's
  private key, SHA256-tracked in `containers/SHA256SUMS`. Image pulls from
  unpinned tags rejected at build time.
- **Cloud-GPU pods** — launched via cost-routed executor (Stage 13); each
  pod runs a single signed SIF with a single command; pods terminated on
  job completion or eviction.

## Responsible disclosure

We acknowledge security reports within 72 h. We commit to:

1. Confirming the vulnerability or explaining why we believe it is not one.
2. Communicating an expected fix timeline.
3. Crediting the reporter in `CHANGELOG.md` and the relevant `v0.0.NN` /
   `v0.1.x` release notes (unless the reporter prefers anonymity).
4. CVE assignment for any vulnerability we judge user-impacting.
