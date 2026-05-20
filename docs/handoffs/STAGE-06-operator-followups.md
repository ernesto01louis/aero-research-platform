# Stage 06 — Operator Follow-ups (Tutorial)

The Stage-06 handoff is `partial`. Five follow-up items are operator actions —
two of them must happen before any PR can merge to `main` (see §0). This file
is the copy-pasteable runbook.

Status snapshot at handoff time:

- PR open: <https://github.com/ernesto01louis/aero-research-platform/pull/8>
- Branch: `stage-06/su2-adapter`
- Tag pending: `v0.0.6` (apply after merge)
- ONERA M6 turbulent mesh: ✅ mirrored to DVC remote (see §0c)
- ONERA M6 Cp reference data: ⚠️ pending (§2)
- SU2 SIF: ⚠️ not built (§1)
- Branch protection: 🔴 **broken — fix immediately (§0a)**

---

## §0a — URGENT: fix `main` branch protection (I left it broken)

During the wrap-up I added two required status-check contexts with the **wrong
names**; the Claude auto-mode classifier then blocked the cleanup PATCH for
security. The contexts I added do not match any actual job name, so they will
**never report a status** — which means **every PR to `main` is blocked from
merging** until you remove them.

The two broken contexts to delete:

- `import-platform-only — import aero with no extras`
- `vv-required`

The two **correct** contexts to add (the real job names from the workflow
files):

- `import aero with no extras`        ← from `.github/workflows/import-platform-only.yml`
- `vv-required — stage-gated V&V`     ← from `.github/workflows/vv-required.yml`

Run, from your shell (any cwd; uses your authenticated `gh`):

```bash
# 1. Confirm current state (you should see the two broken contexts).
gh api repos/ernesto01louis/aero-research-platform/branches/main/protection/required_status_checks/contexts

# 2. Remove the broken ones.
gh api -X DELETE \
  repos/ernesto01louis/aero-research-platform/branches/main/protection/required_status_checks/contexts \
  --input - <<'JSON'
{"contexts":["import-platform-only — import aero with no extras","vv-required"]}
JSON

# 3. Add the correct ones.
gh api -X POST \
  repos/ernesto01louis/aero-research-platform/branches/main/protection/required_status_checks/contexts \
  --input - <<'JSON'
{"contexts":["import aero with no extras","vv-required — stage-gated V&V"]}
JSON

# 4. Re-verify; you should now see exactly seven contexts:
#    ruff, mypy (strict on aero/), pytest unit (py3.12),
#    README STATUS block consistency, enforce Conventional Commits ...,
#    import aero with no extras, vv-required — stage-gated V&V
gh api repos/ernesto01louis/aero-research-platform/branches/main/protection/required_status_checks/contexts
```

This is the §5 follow-up rolled together with the cleanup of the bad state.
Once those two correct contexts are listed, both Stage-05's `vv-required` and
Stage-06's `import-platform-only` are required checks on `main`.

---

## §0b — quick sanity check that PR #8 sees the right contexts

```bash
gh pr checks 8 --repo ernesto01louis/aero-research-platform
```

You should see ruff / mypy / pytest unit / README STATUS / commit-lint
running, plus `import aero with no extras` (new). `vv-required — stage-gated
V&V` runs only when the PR touches `aero/adapters/**`, `aero/vv/**`,
`conf/case/**`, or `pyproject.toml` — Stage 06 obviously does, so it will run.
`vv-smoke` runs but is **not** required (its self-hosted runner may be
offline).

---

## §0c — ONERA M6 mesh: already done

Already on `stage-06/su2-adapter`:

- `data/meshes/su2/onera_m6.su2` — fetched from
  `su2code/Tutorials/compressible_flow/Turbulent_ONERAM6/mesh_ONERAM6_turb_hexa_43008.su2`,
  5.96 MB, BSD-licensed.
- `data/meshes/su2/onera_m6.su2.dvc` (committed) — md5
  `4000194f1d7673017f6f8e11757618af`.
- Pushed to the `aero-minio` DVC remote (`s3://aero-dvc`).

Future fresh clones pull it with `dvc pull data/meshes/su2/onera_m6.su2`.

---

## §1 — Build the SU2 v8 SIF

This needs ~30–60 minutes of CPU on `aero-build` (longer than the 10-minute
Bash-tool ceiling in my sessions, so the operator runs it). The build is
two-step (ADR-006): rootless `buildah` source-compiles SU2 into an OCI image
where network is available (`slirp4netns`), then `apptainer` builds the SIF
from the OCI archive `%post`-filesystem-only.

`buildah` is **not yet installed** on `aero-build` — install it once.

```bash
# All commands below run on aero-build as root, unless noted.
ssh root@aero-build

# 1. One-off: install buildah (apt-get works inside aero-build; the LXC has
#    MASQUERADE egress per the Proxmox topology).
apt-get update
apt-get install -y --no-install-recommends buildah

# 2. Sanity-check the toolchain. Both must be present.
command -v buildah && command -v apptainer

# 3. (Optional) confirm the signing keypair file the build script expects.
ls -l /root/.config/aero/signing.env

# 4. Make sure the aero NFS dataset is mounted at /mnt/aero (SIFs publish to
#    /mnt/aero/containers/) — this is the dataset from TrueNAS VM 104.
df -h /mnt/aero

# 5. Clone the repo with the stage-06 branch (or git-pull if you already have
#    it). The script reads the def + dockerfile from the repo path you pass.
cd /tmp
git clone --branch stage-06/su2-adapter \
    https://github.com/ernesto01louis/aero-research-platform.git
cd aero-research-platform

# 6. Build the SIF. ~30–60 minutes — use tmux so the SSH session can drop.
tmux new -s su2-build
# inside tmux:
./scripts/build_su2_sif.sh v8.1.0 "$(pwd)"
# detach: Ctrl-b d
# re-attach:  tmux attach -t su2-build

# 7. When it finishes, capture the SHA256 line the script prints, e.g.
#    <sha256>  su2-v8.sif
# Also record the SU2 commit SHA the build labelled into the image, for ADR-006:
apptainer exec /mnt/aero/containers/su2-v8.sif cat /opt/su2/.su2-commit
```

Append the SHA256 to the manifest (run **from your dev box**, not aero-build):

```bash
cd /path/to/aero-research-platform
git checkout stage-06/su2-adapter
git pull
# Replace <sha> with the line from step 7 above.
echo "<sha>  su2-v8.sif" >> containers/SHA256SUMS
git add containers/SHA256SUMS
git commit -m "feat(stage-06): publish su2-v8 SIF SHA256"
git push
```

Note: `provenance-completeness` will reject any SU2 MLflow run whose
`container_sif_sha256` is not in this manifest — that's the correct fail-loud
behaviour. Don't relax it.

If `buildah` itself somehow can't open sockets on aero-build (rare; should
work via slirp4netns), the fallback is to run §1 on any other Linux host with
rootless buildah/podman, then `scp` the resulting OCI archive
(`/tmp/su2-v8-oci.tar`) and the SIF over to `/mnt/aero/containers/`.

---

## §2 — Mirror the ONERA M6 Cp reference data

The Schmitt-Charpin / ONERA TR-1 (1979) experimental data isn't in clean
machine-readable form upstream. The four standard span stations needed for
Stage-06 validation are η = 0.20, 0.44, 0.65, 0.80; for the test to pass you
need at least the η = 0.44 station at the path

```
data/references/transonic/onera_m6/cp_station_0.44.csv
```

with `x_over_c,cp` columns. Two paths:

### §2a — Digitize from the AGARD AR-138 / Schmitt-Charpin tabulation

The canonical paper tabulations are in:

- AGARD Advisory Report No. 138 (1979), Appendix B — tables of Cp vs x/c at
  each span station, both surfaces.
- Schmitt, V. & Charpin, F., "Pressure distributions on the ONERA-M6-wing at
  transonic Mach numbers", ONERA TR-1, in *Experimental Data Base for
  Computer Program Assessment*, AGARD-AR-138.

Type the η = 0.44 table into a CSV. Header is `x_over_c,cp`; one row per
point; upper-surface and lower-surface points each as their own x/c entry.
Sort ascending in x/c. Save as `data/references/transonic/onera_m6/
cp_station_0.44.csv`. Optionally do η = 0.20, 0.65, 0.80 too — the harness
will not use them until the case's `evaluate()` is extended to compare all
four (§3 below has that on the punch list).

### §2b — Pull from an existing digitization

There are several public digitizations of the same tables; if you find one
with a clear CC/BSD/public-domain license, mirror it. NASA's CFL3D test suite
(at <https://nasa.github.io/CFL3D/>) carries an ONERA M6 verification case
with reference Cp at a few stations — that source is acceptable to mirror
under government-work / public-domain licence; include a `source:` line in
the CSV header comment.

### §2c — Track via DVC, exactly like the mesh

```bash
cd /path/to/aero-research-platform
# After writing the CSV file:
.venv/bin/dvc add data/references/transonic/onera_m6/cp_station_0.44.csv
git add data/references/transonic/onera_m6/cp_station_0.44.csv.dvc \
        data/references/transonic/onera_m6/.gitignore
git commit -m "feat(stage-06): mirror Schmitt-Charpin Cp at eta=0.44"
.venv/bin/dvc push                    # push to s3://aero-dvc
git push
```

Update `data/references/transonic/onera_m6/reference.md` with the source
citation and the exact paper/table the CSV was extracted from.

---

## §3 — Run the SU2 TMR + transonic cluster suite

Depends on §1 (SIF) and optionally §2 (ONERA Cp). Run on `aero-build` or
`aero-vv`.

```bash
ssh root@aero-build
cd /tmp/aero-research-platform   # or wherever you cloned

# Need the env vars from Stage 04.
export AERO_PROVENANCE_DSN="$AERO_PROVENANCE_DSN"          # from Vault / .env
export AWS_ACCESS_KEY_ID="$AERO_DVC_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$AERO_DVC_SECRET_ACCESS_KEY"

# Install both solver extras + provenance + vv (the venv you may already have
# from Stage 05 needs the new su2 extra).
uv venv --python 3.12 --clear
uv pip install -e ".[openfoam,su2,provenance,vv,dev]"

# A — the three SU2 TMR cases (flat plate, 2D bump, NACA 0012 verification)
.venv/bin/pytest -m "stage_06 and vv and slow and not mesh_sweep" --run-slow -v \
    tests/vv/test_tmr_naca0012_su2.py \
    tests/vv/test_tmr_flat_plate_su2.py \
    tests/vv/test_tmr_bump_2d_su2.py

# B — the transonic cases (slow; nightly-only in CI but you can run on demand)
.venv/bin/pytest -m "stage_06 and vv and slow" --run-slow -v \
    tests/vv/test_transonic_naca0012.py \
    tests/vv/test_transonic_onera_m6.py
# ONERA M6 will skip until §2's Cp data + the 3D wing-slice extraction land.

# C — the cross-solver comparison (headline Stage-06 V&V deliverable).
#     CLI integration is a Stage-07 stretch; for now drive from Python:
.venv/bin/python - <<'PY'
from pathlib import Path
from aero.adapters.openfoam import OpenFOAMSolver
from aero.adapters.su2 import SU2Solver
from aero.orchestration import LocalSSHExecutor
from aero.provenance import compute_provenance
from aero.provenance.db import resolve_dsn
from aero.vv import BenchmarkRunner
from aero.vv.tmr import NACA0012Verification
from aero.vv.cross_solver_compare import compare_solvers, write_report

repo = Path("/tmp/aero-research-platform")
nfs_host, nfs_remote = Path("/mnt/aero-nfs"), Path("/mnt/aero")
exec_ = LocalSSHExecutor(host="aero-build", ssh_user="root", repo_root=repo)
dsn = resolve_dsn()
common = dict(
    executor=exec_, tracking_uri="http://192.168.2.234:5000",
    experiment="aero-provenance", db_dsn=dsn, stage="06",
)
of_runner = BenchmarkRunner(
    solver=OpenFOAMSolver(host_nfs_root=nfs_host, remote_nfs_root=nfs_remote),
    solver_version="OpenFOAM-ESI v2412", **common,
)
su_runner = BenchmarkRunner(
    solver=SU2Solver(host_nfs_root=nfs_host, remote_nfs_root=nfs_remote, repo_root=repo),
    solver_version="SU2 v8", **common,
)
case = NACA0012Verification()
spec = case.case_spec()
of_prov = compute_provenance(repo_root=repo, container_sif="openfoam-esi.sif",
                             resolved_config=spec.model_dump(mode="json"))
su_prov = compute_provenance(repo_root=repo, container_sif="su2-v8.sif",
                             resolved_config=spec.model_dump(mode="json"))
report = compare_solvers(case, openfoam_runner=of_runner, su2_runner=su_runner,
                         openfoam_provenance=of_prov, su2_provenance=su_prov,
                         repo_root=repo)
write_report(report, repo / "docs" / "cross-solver" / "stage-06")
print(report.to_markdown())
PY
```

Update the `xfail` markers in `tests/vv/test_tmr_*_su2.py` as cases pass —
remove the decorator only when the test is genuinely green. Don't relax the
tolerances (guardrail 2).

---

## §4 — Promote the SIF SHA to the provenance manifest

Done as the last step of §1 — included here for the index.

---

## §5 — Promote `import-platform-only` and `vv-required` to required checks

**Already attempted in this session; see §0a above for the cleanup +
correct-context PATCH commands.**

---

## §6 — Merge PR #8, tag `v0.0.6`, publish the Release

Only after §0a is fixed (otherwise the bogus required contexts block merge).
Once all five real required checks are green (`ruff`, `mypy (strict on
aero/)`, `pytest unit (py3.12)`, `README STATUS block consistency`,
`enforce Conventional Commits on PR title and every commit`) plus the two
new ones (`import aero with no extras`, `vv-required — stage-gated V&V`):

```bash
gh pr merge 8 --repo ernesto01louis/aero-research-platform \
              --squash \
              --subject "feat(stage-06): SU2 v8 adapter and Solver protocol generalisation" \
              --delete-branch

# Tag the release commit on main. Pull first.
git checkout main && git pull
git tag -a v0.0.6 -m "Stage 06 — SU2 v8 adapter and Solver protocol generalisation"
git push origin v0.0.6

# Publish the GitHub Release with the CHANGELOG section as the body.
gh release create v0.0.6 \
    --title "v0.0.6 — Stage 06: SU2 v8 adapter (partial)" \
    --notes-file <(awk '/^## \[0\.0\.6\]/,/^## \[0\.0\.5\]/' CHANGELOG.md \
                   | sed '$d')
```

Squash-merge is the precedent the previous five stage tags set; the
`enforce-linear-history` branch protection rule requires no merge commits on
`main`.

---

## §7 — Stage-05 leftovers (still open)

The three Stage-05 headline V&V open items (§7 of the Stage-05 handoff)
remain — Stage 06 deliberately did not touch them (operator decision,
2026-05-19):

- **NACA 0012 trailing-edge pressure drag.** Restructure the TE block
  topology so the ~28 severely-non-orthogonal faces at the sharp TE
  disappear; target Cd within 3 % of 0.008120.
- **Flat-plate reference data.** Replace the White-correlation Cf with the
  TMR-published CFL3D / FUN3D Cf distribution under
  `data/references/tmr/flat_plate/cf.csv`. (The Stage-05 §0 fix pass already
  mirrored the actual TMR data — confirm this is current.)
- **2D bump solve quality.** Already switched to PCG/DIC in Stage 05 §0;
  remaining work is reaching `1e-6` residual and tightening the Cp/Cf error.

These are tracked outside Stage 06; they appear in the Stage-05 handoff §7
and remain on the next operator iteration's plate.
