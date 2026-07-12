#!/usr/bin/env python
"""Stage-15 rescue probe: find the camber ceiling for STEADY convergence on the base grid.

The Stage-15 optimum (m=0.0745, ~93% of the search-box bound) is loaded enough that the wake goes
mildly unsteady at the finest solvable (base) grid, so steady simpleFoam floors at ~2e-4 and the
matched-grid delta is untrustworthy. This diagnostic sweeps max_camber on the base grid at fixed
AoA and reports the final pressure residual per solve, so we can pick a design-space upper bound
below which the loaded optimum still converges cleanly (< --resid-tol). Diagnostic only — no
provenance / no reported artifact (run with a dirty tree is fine).

    python scripts/stage15_camber_probe.py --host aero-dev --aoa 4 --end-time 5000

Launch detached; prints one PROBE line per camber + a CEILING summary.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument("--case", choices=("laminar", "turbulent"), default="laminar")
    ap.add_argument("--reynolds", type=float, default=3.0e6, help="Re for the turbulent case.")
    ap.add_argument("--aoa", type=float, default=4.0)
    ap.add_argument("--camber-position", type=float, default=0.592640974765251)
    ap.add_argument(
        "--cambers",
        type=str,
        default="0.0,0.02,0.03,0.04,0.05,0.06,0.07",
        help="Comma-separated max_camber values to probe on the base grid.",
    )
    ap.add_argument("--end-time", type=int, default=5000)
    ap.add_argument("--resid-tol", type=float, default=1.0e-4)
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args()

    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.optimize.airfoil_case import ShapedLaminarAirfoil
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil
    from aero.orchestration import LocalSSHExecutor
    from aero.vv._base import BenchmarkRunner

    def build_case(m: float, name: str) -> object:
        if args.case == "turbulent":
            return ShapedTurbulentAirfoil(
                name=name,
                aoa_deg=args.aoa,
                reynolds=args.reynolds,
                max_camber=m,
                camber_position=args.camber_position,
                end_time=args.end_time,
            )
        base = ShapedLaminarAirfoil(
            name=name, aoa_deg=args.aoa, max_camber=m, camber_position=args.camber_position
        )
        return ShapedLaminarAirfoil(
            spec=base.case_spec().model_copy(update={"end_time": args.end_time}), name=name
        )

    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )
    runner = BenchmarkRunner(
        solver=solver,
        executor=executor,
        tracking_uri="unused",
        experiment="unused",
        db_dsn="unused",
        solver_version="OpenFOAM-ESI v2412",
        stage="15",
    )

    cambers = [float(x) for x in args.cambers.split(",")]
    rows = []
    for m in cambers:
        name = f"cp{args.case[:3]}_m{round(m * 1e4):04d}"
        case = build_case(m, name)
        try:
            measured, _mesh, result = runner._drive(case)
            solved = solver.load(result)
            resid = float(solved.final_residual)
            ld = float(measured["ld"])
            conv = resid < args.resid_tol
            rows.append((m, ld, resid, conv))
            print(
                f"PROBE m={m:.4f} L/D={ld:.5f} resid={resid:.2e} "
                f"{'OK' if conv else '!! FLOOR (unsteady)'}",
                flush=True,
            )
        except Exception as exc:  # a diverged/failed solve is itself a ceiling signal
            rows.append((m, float("nan"), float("nan"), False))
            print(f"PROBE m={m:.4f} FAILED: {type(exc).__name__}: {exc}", flush=True)

    converged = [m for (m, _ld, _r, c) in rows if c]
    ceiling = max(converged) if converged else None
    first_floor = next((m for (m, _ld, _r, c) in rows if not c and m > 0.0), None)
    print(
        f"CEILING max_converged_camber={ceiling} first_floor_camber={first_floor} "
        f"(base grid, AoA={args.aoa}, end_time={args.end_time}, tol={args.resid_tol})",
        flush=True,
    )


if __name__ == "__main__":
    main()
