#!/usr/bin/env python3
"""Pull NACA 0012 baseline artifacts from the aero LXC.

Reads the campaign_id from results/01-naca0012-baseline/run-log.json,
then for each aoa value SCPs:

  /home/aero/ai-projects/naca0012-baseline-<aoa>/case/postProcessing/
  /home/aero/ai-projects/naca0012-baseline-<aoa>/case/log.*
  /home/aero/ai-projects/naca0012-baseline-<aoa>/case/constant/polyMesh/
  (last only for traceability — large; gated by --include-mesh)

Into:

  results/01-naca0012-baseline/aoa-<aoa>/

Designed to be idempotent — re-running after each run completes pulls
fresh data without re-fetching everything.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "01-naca0012-baseline"
SSH_KEY = "/root/.ssh/id_ed25519_aero_target"
SSH_USER = "aero"
SSH_HOST = "192.168.2.231"
AOAS = (0, 10)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _rsync_path(remote_rel: str, local_dir: Path) -> bool:
    """rsync a remote file or directory into local_dir. Returns True on success."""
    local_dir.mkdir(parents=True, exist_ok=True)
    src = f"{SSH_USER}@{SSH_HOST}:{remote_rel}"
    cmd = [
        "rsync",
        "-az",
        "-e",
        f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no -o BatchMode=yes",
        src,
        str(local_dir) + "/",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  rsync failed ({remote_rel}): {res.stderr.strip()}")
        return False
    return True


def pull_aoa(aoa: int, include_mesh: bool) -> dict[str, bool]:
    print(f"== Pulling AoA={aoa} ==")
    remote_case = f"/home/aero/ai-projects/naca0012-baseline-{aoa}/case"
    local = RESULTS_DIR / f"aoa-{aoa}"
    results: dict[str, bool] = {}

    # 1. postProcessing tree.
    results["postProcessing"] = _rsync_path(f"{remote_case}/postProcessing", local)

    # 2. logs.
    for name in ("log.blockMesh", "log.snappyHexMesh", "log.checkMesh",
                 "log.simpleFoam", "log.reconstructPar", "log.foamToVTK",
                 "log.surfaceFeatureExtract"):
        _rsync_path(f"{remote_case}/{name}", local)

    # 3. controlDict + fvSchemes + fvSolution (for evidence-bundle citation).
    for name in ("controlDict", "fvSchemes", "fvSolution", "decomposeParDict"):
        _rsync_path(f"{remote_case}/system/{name}", local / "system")
    for name in ("transportProperties", "turbulenceProperties"):
        _rsync_path(f"{remote_case}/constant/{name}", local / "constant")

    # 4. (optional) polyMesh.
    if include_mesh:
        results["polyMesh"] = _rsync_path(f"{remote_case}/constant/polyMesh", local / "constant")

    # 5. VTK output.
    _rsync_path(f"{remote_case}/VTK", local)

    # Sanity check: is forceCoeffs1's coefficient.dat present?
    coef = local / "postProcessing" / "forceCoeffs1" / "0" / "coefficient.dat"
    if not coef.exists():
        coef = local / "postProcessing" / "forceCoeffs1" / "0" / "coefficients.dat"
    if not coef.exists():
        coef = local / "postProcessing" / "forceCoeffs1" / "0" / "forceCoeffs.dat"
    results["coefficient.dat"] = coef.exists()
    if not coef.exists():
        print(f"  WARNING: no coefficient(s).dat under {local}/postProcessing/forceCoeffs1/0/")
    else:
        print(f"  found: {coef}")
    return results


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--include-mesh", action="store_true", help="also pull constant/polyMesh (large)")
    p.add_argument("--aoa", type=int, action="append", default=None,
                   help="restrict to a single AoA; default: all configured")
    args = p.parse_args()

    aoas = args.aoa if args.aoa else AOAS
    summary: dict[int, dict[str, bool]] = {}
    for aoa in aoas:
        summary[aoa] = pull_aoa(aoa, args.include_mesh)
    print()
    print("== Summary ==")
    for aoa, status in summary.items():
        print(f"  aoa={aoa}: " + ", ".join(f"{k}={v}" for k, v in status.items()))

    # Exit non-zero if any AoA is missing its coefficient file.
    any_missing = any(not s.get("coefficient.dat") for s in summary.values())
    return 1 if any_missing else 0


if __name__ == "__main__":
    sys.exit(_cli())
