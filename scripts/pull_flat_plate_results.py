#!/usr/bin/env python3
"""Pull flat-plate riblet (+ paired smooth-baseline) artifacts from the aero LXC.

Reads the campaign_id from results/02-flat-plate-riblet-bechert/run-log.json,
then for each (surface, s+) pair SCPs:

  /home/aero/ai-projects/flat-plate-{surface}-{s+}-h0.5/case/postProcessing/
  /home/aero/ai-projects/flat-plate-{surface}-{s+}-h0.5/case/log.*
  /home/aero/ai-projects/flat-plate-{surface}-{s+}-h0.5/case/system/*
  /home/aero/ai-projects/flat-plate-{surface}-{s+}-h0.5/case/constant/{transport,turbulence}Properties

Into:

  results/02-flat-plate-riblet-bechert/{surface}-{s+}/

Designed to be idempotent — re-running after each sub-run completes
pulls fresh data without re-fetching everything.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "02-flat-plate-riblet-bechert"
SSH_KEY = "/root/.ssh/id_ed25519_aero_target"
SSH_USER = "aero"
SSH_HOST = "192.168.2.231"
S_PLUS_SWEEP = (5, 10, 15, 17, 20, 25, 30, 35, 40)
SURFACES = ("riblet", "smooth")
H_OVER_S = "0.5"


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


def pull_sub_run(surface: str, s_plus: int) -> dict[str, bool]:
    project = f"flat-plate-{surface}-{s_plus}-h{H_OVER_S}"
    print(f"== Pulling {project} ==")
    remote_case = f"/home/aero/ai-projects/{project}/case"
    local = RESULTS_DIR / f"{surface}-{s_plus}"
    results: dict[str, bool] = {}

    # 1. postProcessing tree (wallShearStress, residuals, yPlus).
    results["postProcessing"] = _rsync_path(f"{remote_case}/postProcessing", local)

    # 2. logs.
    for name in ("log.blockMesh", "log.snappyHexMesh", "log.checkMesh",
                 "log.potentialFoam", "log.simpleFoam", "log.reconstructPar",
                 "log.foamToVTK", "log.surfaceFeatureExtract"):
        _rsync_path(f"{remote_case}/{name}", local)

    # 3. system + constant dicts (for evidence-bundle citation).
    for name in ("controlDict", "fvSchemes", "fvSolution",
                 "decomposeParDict", "blockMeshDict",
                 "snappyHexMeshDict", "meshQualityDict"):
        _rsync_path(f"{remote_case}/system/{name}", local / "system")
    for name in ("transportProperties", "turbulenceProperties"):
        _rsync_path(f"{remote_case}/constant/{name}", local / "constant")

    # 4. VTK output.
    _rsync_path(f"{remote_case}/VTK", local)

    # Sanity check: is wallShearStress.dat present?
    wss_root = local / "postProcessing" / "wallShearStress"
    found = False
    if wss_root.exists():
        for sub in wss_root.iterdir():
            cand = sub / "wallShearStress.dat"
            if cand.exists():
                print(f"  found: {cand}")
                found = True
                break
    results["wallShearStress.dat"] = found
    if not found:
        print(f"  WARNING: no wallShearStress.dat under {wss_root}/*/")
    return results


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--s-plus",
        type=int,
        action="append",
        default=None,
        help="restrict to a single s+ value; default: full sweep",
    )
    p.add_argument(
        "--surface",
        action="append",
        choices=list(SURFACES),
        default=None,
        help="restrict to riblet or smooth; default: both",
    )
    args = p.parse_args()

    s_pluses = tuple(args.s_plus) if args.s_plus else S_PLUS_SWEEP
    surfaces = tuple(args.surface) if args.surface else SURFACES

    summary: dict[str, dict[str, bool]] = {}
    for surface in surfaces:
        for s_plus in s_pluses:
            key = f"{surface}-{s_plus}"
            summary[key] = pull_sub_run(surface, s_plus)

    print()
    print("== Summary ==")
    for key, status in summary.items():
        print(f"  {key}: " + ", ".join(f"{k}={v}" for k, v in status.items()))

    # Exit non-zero if any sub-run is missing its wallShearStress file.
    any_missing = any(not s.get("wallShearStress.dat") for s in summary.values())
    return 1 if any_missing else 0


if __name__ == "__main__":
    sys.exit(_cli())
