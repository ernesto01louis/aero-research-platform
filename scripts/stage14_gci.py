#!/usr/bin/env python
"""Combined space+time GCI for the flapping-wing case — the ``u95_numerical`` term.

The Stage-14 analogue of ``scripts/stage13_gci.py``, adapted for hover: the Richardson target is
the **WBD-normalised stroke-averaged mean lift coefficient** (a smooth cycle-mean; hover writes
no ``forceCoeffs`` so the flapping loader is used instead of reading ``coefficient.dat``). The
completed base (fine) grid is reused (``--base-run-dir``); only the coarser grids are solved:

  * **spatial** — 2-grid GCI: base vs ``refined(spatial_ratio)`` (O-grid n_radial/n_azimuthal);
  * **temporal** — 2-grid GCI: base vs ``refined_dt(temporal_ratio)`` (Courant cap).

ASME V&V 20 2-grid safety factor Fs=3.0, assumed order p (2 spatial / 1 temporal). GCI is NOT
skipped for this case (unlike a NO-GO): a thesis-grade flapping result requires u95_numerical>0.
Launch detached; writes a JSON report + a RESULT line.

    python scripts/stage14_gci.py flapping_wing_wbd2004 --host aero-dev \\
        --base-run-dir /mnt/aero/runs/flapping_wing_wbd2004-<ts>
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_FS = 3.0  # ASME V&V 20 safety factor for a 2-grid GCI estimate
_P_SPACE = 2.0  # assumed spatial order (2nd-order FV)
_P_TIME = 1.0  # assumed temporal order (pimpleFoam ~1st order)


def _base_mean_cl(base_run_dir: Path, case: object) -> float:
    """Stroke-averaged WBD mean lift coefficient over the converged tail of a completed run."""
    from aero.adapters._base import CaseDir, ResultHandle
    from aero.adapters.openfoam.solver import OpenFOAMSolver

    spec = case.case_spec()  # type: ignore[attr-defined]
    handle = ResultHandle(
        case_dir=CaseDir(
            run_id=base_run_dir.name,
            spec=spec,
            host_path=base_run_dir,
            remote_path=Path("/mnt/aero") / base_run_dir.name,
        ),
        returncode=0,
        output_host_path=base_run_dir / "postProcessing",
    )
    return float(OpenFOAMSolver().load(handle).scalars["mean_lift_coefficient"])


def _gci_2grid(fine: float, coarse: float, *, ratio: float, order: float) -> float:
    """2-grid GCI on the fine grid, as a fraction of |fine| (ASME V&V 20, Fs=3.0)."""
    eps = abs(coarse - fine) / max(abs(fine), 1.0e-12)
    return _FS * eps / (ratio**order - 1.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="FLAPPING_CASES key (e.g. flapping_wing_wbd2004)")
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--timeout", type=int, default=43200)
    ap.add_argument("--base-run-dir", type=Path, required=True, help="Completed base (fine) dir")
    ap.add_argument("--spatial-ratio", type=float, default=1.5)
    ap.add_argument("--temporal-ratio", type=float, default=2.0)
    ap.add_argument("--skip-temporal", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner
    from aero.vv.flapping import FLAPPING_CASES

    if args.case not in FLAPPING_CASES:
        raise SystemExit(f"unknown case {args.case!r}; known: {', '.join(FLAPPING_CASES)}")
    base = FLAPPING_CASES[args.case]
    spec = base.case_spec()

    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )
    runner = BenchmarkRunner(
        solver=solver,
        executor=executor,
        tracking_uri="http://192.168.2.234:5000",
        experiment="aero-provenance",
        db_dsn=None if args.no_mlflow else resolve_dsn(),
        solver_version="OpenFOAM-ESI v2412",
        stage="14",
    )
    prov = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=spec.model_dump(mode="json"),
        allow_dirty=False,
    )

    cl_fine = _base_mean_cl(args.base_run_dir, base)  # reuse the completed base grid

    obs_s = runner.measure_scalar(
        base.refined(args.spatial_ratio),
        "mean_lift_coefficient",
        provenance=prov,
        repo_root=_REPO_ROOT,
    )
    gci_space = _gci_2grid(cl_fine, obs_s.value, ratio=args.spatial_ratio, order=_P_SPACE)

    gci_time = 0.0
    cl_coarse_dt = None
    if not args.skip_temporal:
        obs_t = runner.measure_scalar(
            base.refined_dt(args.temporal_ratio),
            "mean_lift_coefficient",
            provenance=prov,
            repo_root=_REPO_ROOT,
        )
        cl_coarse_dt = obs_t.value
        gci_time = _gci_2grid(cl_fine, cl_coarse_dt, ratio=args.temporal_ratio, order=_P_TIME)

    u95_num_frac = math.sqrt(gci_space**2 + gci_time**2)
    out = {
        "case": args.case,
        "metric": "mean_lift_coefficient",
        "method": "2-grid space+time GCI (base reused), ASME V&V 20 Fs=3.0",
        "git_sha": prov.git_sha,
        "cl_fine": cl_fine,
        "base_run_dir": str(args.base_run_dir),
        "spatial": {
            "ratio": args.spatial_ratio,
            "cl_coarse": obs_s.value,
            "order": _P_SPACE,
            "gci_fraction": gci_space,
        },
        "temporal": {
            "ratio": args.temporal_ratio,
            "cl_coarse": cl_coarse_dt,
            "order": _P_TIME,
            "gci_fraction": gci_time,
        },
        "u95_numerical_fraction": u95_num_frac,
        "u95_numerical_abs": u95_num_frac * abs(cl_fine),
    }
    out_path = (
        Path(args.out) if args.out else _REPO_ROOT / "data" / "vv" / f"stage14_gci_{args.case}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"RESULT case={args.case} gci_space={gci_space:.5f} gci_time={gci_time:.5f} "
        f"u95_numerical_frac={u95_num_frac:.5f} cl_fine={cl_fine:.5f} out={out_path}"
    )


if __name__ == "__main__":
    main()
