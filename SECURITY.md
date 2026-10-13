# Security Policy

## Supported versions

Security fixes go to the latest release (`v0.1.x` once v0.1.0 is published) and to `main`.
Pre-release stage tags (`v0.0.NN`) are not maintained.

## Reporting a vulnerability

Email security issues to **gr7x8mjy5d@privaterelay.appleid.com** with the
subject line `[aero-research-platform security]`. Please **do not** open a
public GitHub issue for vulnerabilities.

Acknowledgement target: 72 h. Triage and fix timeline depends on severity.

## Secret-handling policy

1. **No secrets in the repository.** `.env*`, `*.key`, `*.pem`, `*.p12`, `*.crt` and `secrets/`
   are gitignored. The `gitleaks` pre-commit hook rejects commits that contain plausible secrets.
   The `secret-scan` workflow re-scans every PR and push to `main` in CI. It is not a required
   check.
2. **No secrets in commit messages, MLflow tags, PR descriptions, or container layer history.**
   Anything that ends up in `git log`, MLflow's tag store, Apptainer SIF metadata, or a CI log is
   permanent.
3. **Vault for everything that isn't local-dev.** HashiCorp Vault on the `aero-vault` LXC (217;
   Stage 04, ADR-004) is the secret store. It holds cloud-GPU API keys, database credentials
   (Postgres LXC 202, MinIO service accounts, MLflow tracking), MCP-server tokens, the Apptainer
   signing passphrase (ADR-012) and the Zenodo API token. Values are injected as environment
   variables at job time. In CI, secrets are scoped to the single step that needs them, never the
   job.
4. **Local-dev secrets** live in `.env` (mode 0600, gitignored) for convenience; production runs
   read from Vault.
5. **No reuse across tiers.** `production`-tier credentials are separate from `experiment`-tier
   ones; MinIO root credentials are separate from the scoped DVC and MLflow service accounts.
6. **Apptainer signing key.** The container-signing keypair lives in the `aero-build` LXC keyring,
   passphrase-protected, with an encrypted-at-rest copy escrowed to the TrueNAS `aero/` dataset.
   The public fingerprint is committed at `containers/SIGNING_KEY_FINGERPRINT.txt`. ADR-012 renders
   the passphrase non-interactively from Vault for `apptainer sign`.

## Threat model

**Actor inventory:**

- **Operator** (Louis Ernesto Schulte Moredo): the single human developer, with full repository
  admin and Proxmox-host root.
- **Claude Code agent**: an elevated actor that can execute shell commands, edit files, push
  branches and open PRs. It is scope-limited by `.claude/settings.json`:
  - a **deny list** blocks `git push --force` / `-f` / `origin +`, `git reset --hard origin/main`,
    `rm -rf` on system paths and the prior-remote clone, `dvc destroy`, and
    `pct destroy|stop` / `qm destroy|stop`;
  - a **PreToolUse hook** (`.claude/hooks/block-dangerous-bash.sh`) blocks SQL `DROP`,
    `--force-with-lease`, `--no-verify` and `--dangerously-skip-permissions`, as well as
    `pct`/`qm destroy|stop` inside compound commands, writes to `/etc/pve/`,
    `/etc/network/interfaces`, `/etc/subuid` and `/etc/subgid`, and destructive verbs over SSH to
    the shared non-aero hosts;
  - a **Stop hook** (`scripts/check_handoff_exists.sh`) refuses to end a session without a valid
    post-stage handoff.

  Destructive operations need the operator's literal `approved` (CLAUDE.md Hard Rule 5). Merging
  a PR, tagging a release and publishing a GitHub Release are operator acts. Hook and permission
  changes are operator-only.
- **There is no autonomous agent layer.** The NeMo Agent Toolkit layer once planned for Stage 14 was
  deferred indefinitely by ADR-013.

**Known integrity limits** (stated in every result crate that is affected):

- `dvc_input_hash` is the sha256 of the DVC remote *sync state* (`dvc status -c`), not a content
  address of the inputs. It shows the inputs were in sync with the remote at run time; it does not
  identify them.
- `container_sif_sha256` is looked up by SIF basename in `containers/SHA256SUMS`. The SIF that
  actually ran is not re-hashed at launch.
- The RunPod transport uses `StrictHostKeyChecking=no` for the frozen GPU path (ADR-013,
  frozen-optional; ledgered).
- A result crate's `SHA256SUMS` gives integrity only. **Authenticity comes from the crate digest**
  (the sha256 of `SHA256SUMS`) published out of band, in the release notes and `crates/README.md`.
  Check it with `python -m aero.crate verify --expect-digests`. Crate signing is deferred.

**Out of scope for v0.1:**

- Multi-tenant access (single-developer build).
- Adversarial supply-chain attacks against the underlying solvers (OpenFOAM, SU2, preCICE,
  CalculiX). Containers are pinned by SHA256, but a container SBOM and image licence scan are
  post-v0.1.
- DoS against the cloud-GPU providers. The cost cap (CONSTITUTION Invariant 8, Stage 07) bounds
  spend, but it is not a security control.

## Code-execution surface

- **CI runners.**
  - GitHub-hosted jobs run on pinned images (`ubuntu-24.04`, `macos-15`, `windows-2025`).
    Actions are SHA-pinned, and Dependabot proposes monthly updates.
  - Two self-hosted runners labelled `vv` run on the `aero-build` LXC (`aero-build-vv`,
    `aero-build-vv-2`), scoped to this repository.
  - The non-required self-hosted PR jobs (`vv-smoke`, `provenance-completeness`) run only for
    branches of this repository, never for forks.
  - The primary control against fork PRs is the repository setting that requires approval before
    workflows run for outside contributors.
  - Self-hosted jobs reap their own long runs (`AERO_RUN_LONG_REAP`) and never cancel a running
    job.
- **Apptainer SIFs** are built on `aero-build` and SHA256-tracked in `containers/SHA256SUMS`.
  Solver SIFs run as the LXC root inside unprivileged LXCs.
- **Cloud-GPU pods** launch through `RunPodExecutor` (Stage 07; frozen-optional). Each pod runs one
  command. Every launch passes `CostCap.check_budget()` first, and pods are terminated in a
  `finally:` block.
- **Result-crate verification** reads untrusted input. `python -I -B -m aero.crate verify|show|numbers`
  runs under an audit-hook sandbox:
  - sockets, subprocesses, writes and imports outside the stdlib + numpy + pydantic + aero allowlist
    are refused;
  - zip members are read in memory, with STORED entries only and path, size and count caps;
  - no JSON-LD context is ever fetched.

## Responsible disclosure

We acknowledge security reports within 72 h. We commit to:

1. Confirming the vulnerability or explaining why we believe it is not one.
2. Communicating an expected fix timeline.
3. Crediting the reporter in `CHANGELOG.md` and the relevant release notes (unless the reporter
   prefers anonymity).
4. CVE assignment for any vulnerability we judge user-impacting.
