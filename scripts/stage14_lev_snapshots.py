#!/usr/bin/env python
"""Leading-edge-vortex (LEV) capture evidence for a flapping-wing overset run (Stage 14).

Deliverable 4: phase-locked vorticity snapshots over one converged stroke, showing the LEV
forming on the wing, staying attached through translation (delayed-stall lift), and shedding at
reversal — the qualitative signature the stroke-averaged force quantifies.

Pipeline (kept in the scripts layer so `aero/` core stays stdlib+numpy+pydantic — PLATFORM-NOT-HUB):

  1. `foamToVTK -ascii -legacy -fields '(vorticity zoneID)'` in the SIF over the last cycle's
     write times (run remotely on the cluster; VTK lands on the shared NFS run dir).
  2. A small pure-numpy legacy-VTK reader (UNSTRUCTURED_GRID: POINTS + CELLS + CELL_DATA).
  3. matplotlib `tricontourf` of omega_z on the component-mesh cell centroids (zoneID==1),
     cropped to a window around the wing, one panel per phase -> a labelled multi-panel PNG.

    python scripts/stage14_lev_snapshots.py flap_base_symmetric \\
        --run-dir /mnt/aero-nfs/runs/flap_base_symmetric --host aero-dev
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SIF = "/opt/aero/containers/openfoam-esi.sif"


def _run_foamtovtk(host: str, remote_run: str, t0: float, t1: float) -> None:
    """Run foamToVTK on the cluster for the [t0, t1] write-time window."""
    inner = (
        f"cd {remote_run} && apptainer exec {_SIF} bash -lc "
        f"\"foamToVTK -ascii -legacy -fields '(vorticity zoneID)' "
        f"-time '{t0:.6g}:{t1:.6g}' > log.foamToVTK 2>&1\""
    )
    subprocess.run(["ssh", host, inner], check=True, timeout=1200)


def _read_legacy_vtk(path: Path) -> dict[str, np.ndarray]:
    """Parse a legacy ASCII VTK UNSTRUCTURED_GRID: cell centroids + cell-data fields.

    Returns ``{"centroids": (nc,3), "vorticity": (nc,3), "zoneID": (nc,)}`` (fields present).
    """
    txt = path.read_text().split("\n")
    i = 0
    points: np.ndarray | None = None
    cells: list[list[int]] = []
    fields: dict[str, np.ndarray] = {}
    n = len(txt)
    while i < n:
        line = txt[i].strip()
        if line.startswith("POINTS"):
            npts = int(line.split()[1])
            vals: list[float] = []
            i += 1
            while len(vals) < npts * 3:
                vals.extend(float(v) for v in txt[i].split())
                i += 1
            points = np.asarray(vals, dtype=np.float64).reshape(npts, 3)
            continue
        if line.startswith("CELLS"):
            ncells = int(line.split()[1])
            i += 1
            read = 0
            while read < ncells:
                parts = [int(v) for v in txt[i].split()]
                if parts:
                    cells.append(parts[1:])  # drop the leading count
                    read += 1
                i += 1
            continue
        if line.startswith("CELL_DATA"):
            i += 1
            continue
        m = re.match(r"(SCALARS|VECTORS)\s+(\S+)", line)
        if m and points is not None:
            kind, name = m.group(1), m.group(2)
            width = 1 if kind == "SCALARS" else 3
            i += 1
            if kind == "SCALARS" and txt[i].strip().startswith("LOOKUP_TABLE"):
                i += 1
            ncells = len(cells)
            vals = []
            while len(vals) < ncells * width and i < n:
                row = txt[i].split()
                if row and not re.match(r"[A-Z_]{3,}", txt[i].strip()):
                    vals.extend(float(v) for v in row)
                    i += 1
                else:
                    break
            arr = np.asarray(vals, dtype=np.float64)
            fields[name] = arr.reshape(ncells, width) if width == 3 else arr
            continue
        i += 1
    assert points is not None, f"no POINTS in {path}"
    centroids = np.asarray([points[c].mean(axis=0) for c in cells], dtype=np.float64)
    out = {"centroids": centroids}
    out.update(fields)
    return out


def _render(vtks: list[Path], out_png: Path, *, window: float, case: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(vtks)
    ncol = min(4, n)
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.2 * ncol, 3.0 * nrow), squeeze=False)
    levels = np.linspace(-20, 20, 21)
    for k, vtk in enumerate(vtks):
        ax = axes[k // ncol][k % ncol]
        d = _read_legacy_vtk(vtk)
        c = d["centroids"]
        wz = d["vorticity"][:, 2] if "vorticity" in d else np.zeros(len(c))
        keep = np.ones(len(c), dtype=bool)
        if "zoneID" in d:  # component (moving) cells only — the near-wing field
            keep = d["zoneID"] > 0.5
        m = keep & (np.abs(c[:, 0]) < window) & (np.abs(c[:, 1]) < window)
        if m.sum() > 10:
            ax.tricontourf(c[m, 0], c[m, 1], np.clip(wz[m], -20, 20), levels=levels, cmap="RdBu_r")
        ax.set_aspect("equal")
        ax.set_xlim(-window, window)
        ax.set_ylim(-window, window)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"phase {k + 1}/{n}", fontsize=8)
    for k in range(n, nrow * ncol):
        axes[k // ncol][k % ncol].axis("off")
    fig.suptitle(f"Stage 14 LEV — spanwise vorticity over one stroke ({case})", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    print(f"wrote {out_png}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="Case name (labels the figure).")
    ap.add_argument("--run-dir", required=True, type=Path, help="Host-side NFS run dir.")
    ap.add_argument("--host", default="aero-dev")
    ap.add_argument(
        "--period", type=float, default=None, help="Stroke period (for the last cycle)."
    )
    ap.add_argument(
        "--window", type=float, default=3.0, help="Half-window (chords) around the wing."
    )
    ap.add_argument("--skip-foamtovtk", action="store_true", help="Reuse existing VTK/ output.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    remote_run = "/mnt/aero" / Path(*args.run_dir.parts[args.run_dir.parts.index("runs") :])
    vtk_dir = args.run_dir / "VTK"
    if not args.skip_foamtovtk:
        # Last converged cycle: infer the window from the written time directories.
        times = sorted(
            float(p.name)
            for p in args.run_dir.iterdir()
            if re.fullmatch(r"\d+(\.\d+)?", p.name) and float(p.name) > 0
        )
        if not times:
            raise SystemExit(f"no time directories in {args.run_dir} — has the solve written?")
        period = args.period if args.period else (times[-1] - times[0])
        t1 = times[-1]
        t0 = t1 - period
        _run_foamtovtk(args.host, str(remote_run), t0, t1)

    vtks = sorted(vtk_dir.glob("*.vtk"), key=lambda p: float(re.findall(r"_(\d+)\.vtk", p.name)[0]))
    if not vtks:
        raise SystemExit(f"no VTK files in {vtk_dir}")
    out = Path(args.out or _REPO_ROOT / "data" / "vv" / f"stage14_lev_{args.case}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    _render(vtks, out, window=args.window, case=args.case)


if __name__ == "__main__":
    main()
