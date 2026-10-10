# Runbook — persistent SSH trust from aero-build (CI runners) to aero-dev

**Applied at:** Stage 20 · **Script:** `scripts/grant_aero_build_ssh_to_aero_dev.sh`
**Hosts:** aero-build (LXC 210, 192.168.2.232) → aero-dev (LXC 211, 192.168.2.233).
Both are aero-owned; nothing outside the aero fleet is touched.

## The problem it solves

The `aero-*` SSH aliases live in `~/.ssh/config.d/aero` **on the Proxmox host** and do not
exist inside the LXCs. The self-hosted GitHub Actions runners (`aero-build-vv`,
`aero-build-vv-2`) run on aero-build as the `aero-admin` user, whose `/etc/hosts` contains
only `192.168.2.232 aero-build`. So from a runner:

```
ssh root@aero-dev   →  Could not resolve hostname   →  ssh exits 255
```

Before Stage 20 the executor returned that 255 unmarked, `OpenFOAMSolver.mesh` logged only
`returncode` and `stdout`, and the failure surfaced as **"blockMesh failed"** — naming the
mesher for a DNS fault. `moving-vv` run 30568971572 (2026-07-30) died that way in 18 s.
Stage 20 made the transport fault loud (`ExecResult.transport_error`); this runbook removes
the fault itself.

**Why it matters beyond tidiness:** aero-build has 8 cores and hosts two runners.
aero-dev has 16 cores, 32 GB, the NFS dataset mount, and the AppArmor inet-socket change
without which every Apptainer `AF_INET` socket is denied (`apptainer-inet-sockets.md`) —
i.e. it is the only box a preCICE socket-m2n run works on at all. And
`test_unsteady_plunging_airfoil`, the Heathcote-Gursul case Stage 20 validates against, has
**never completed in CI** because the only reachable host is the small one.

## What is installed

| # | Where | What |
|---|---|---|
| 1 | aero-build, `aero-admin` | dedicated keypair `~/.ssh/id_ed25519_aero_dev` (comment `aero-build-ci-to-aero-dev`) |
| 2 | aero-build, `aero-admin` | marker-delimited `Host aero-dev` block in `~/.ssh/config` → `192.168.2.233`, `User root`, `IdentitiesOnly yes` |
| 3 | aero-build, `aero-admin` | aero-dev's ed25519 host key pinned in `~/.ssh/known_hosts` |
| 4 | aero-dev, `root` | the public key in `~/.ssh/authorized_keys`, prefixed `from="192.168.2.232"` |

Four deliberate choices:

- **A dedicated key, not the existing `id_ed25519`.** `aero-admin` already holds a key that
  authorises `aero-admin → root@aero-build`. Reusing it would mean revoking this trust also
  breaks the runner's own local path. A separate key revokes cleanly.
- **An ssh config block, not `/etc/hosts`.** ssh is the only consumer, so the change stays
  inside one user's dotfiles rather than becoming host-wide name resolution.
- **`from="192.168.2.232"`.** The key is useless if it leaves aero-build.
- **The host key is pinned, not bypassed.** No `StrictHostKeyChecking=no` anywhere.

## Verify

```bash
ssh aero-build "su - aero-admin -c 'ssh aero-dev \"hostname; nproc\"'"      # → aero-dev, 16
ssh aero-build "su - aero-admin -c 'ssh root@aero-dev true'"                # the executor's form
```

Both forms matter: `LocalSSHExecutor` builds its target as `user@host` (`root@aero-dev`),
while `run_long.sh` accepts either. Then, end to end:

```bash
gh workflow run moving-vv.yml -f case=plunging_airfoil_hg2007
```

## Revert

```bash
scripts/grant_aero_build_ssh_to_aero_dev.sh --revert
```

Removes the `authorized_keys` entry on aero-dev (backing the file up first), the config
block, and the keypair. The host-key pin is left in `known_hosts` — harmless, and removing
it would only reintroduce a TOFU prompt if the trust is ever re-granted.

## When it stops working

| Symptom | Cause | Fix |
|---|---|---|
| `Could not resolve hostname aero-dev` | the config block was removed, or the job runs as a user other than `aero-admin` | re-run the script; confirm the runner's service user with `ps -eo user,comm \| grep Runner.Listener` |
| `Host key verification failed` | aero-dev was rebuilt and has a new host key | re-run the script (step 3 removes the stale entry before re-scanning) |
| `Permission denied (publickey)` | the `from=` restriction no longer matches, i.e. aero-build's IP changed | update `AERO_BUILD_IP` and re-run |
| ssh exits 255 with **empty stderr** | the classic tell for this whole class | `ExecResult.transport_failed` is now set — read the executor's message, it names the cause |
| the job reaches aero-dev but the solve dies on sockets | the AppArmor change is applied to **aero-dev only** and is not persistent across a rebuild | `apptainer-inet-sockets.md` |

## Related

- `scripts/register_second_vv_runner.sh` — why there are two runners
- `docs/operator/apptainer-inet-sockets.md` — the other aero-dev-only prerequisite
- `.github/workflows/moving-vv.yml` — the consumer; **must never become a required check**
- Stage-19 handoff §6.4 — never cancel a self-hosted job to free a runner
