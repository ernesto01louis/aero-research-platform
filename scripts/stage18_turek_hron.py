"""Stage-18 campaign driver — Turek-Hron rigid-flag CFD on the ingested external STL.

Ingest -> Q-gate -> mesh fallback ladder (M/F gates) -> CFD2 (+ optional CFD3) ->
validate against Turek & Hron (2006) -> bundle. Clean-tree provenance: commit code
first, run without touching the repo, write the bundle at END only. Detached long
jobs via run_long.sh; pass --timeout (mesh+solve ceiling, seconds).

THE PRE-REGISTERED GATE BLOCK (ADR-034 — the ADR is the source of record; this
docstring is the operational copy; any drift between the two is a bug):

Q — ingestion quality (post-repair surface, QualityGateConfig defaults):
  Q1 watertight (0 boundary edges). Q2 edge-manifold + orientation-consistent +
  0 duplicate faces. Q3 0 self-intersecting non-adjacent pairs (eps 1e-9*bbox-diag,
  touching counts; a skipped check FAILS). Q4 0 degenerate triangles (repeated index
  or area < 1e-12*bbox-diag^2). Q5 thinnest declared feature (flag thickness 0.02 m,
  published spec, cross-checked by V1) >= 2 x the rung's background cell size; the
  generic min-edge/altitude proxy is reported, never gated.
R — repair bounds (opt-in; outside bounds = left broken for Q):
  R1 merge tol <= 1e-6*bbox-diag. R2 planar ear-clip holes only, <= 32 edges/hole,
  <= 8 holes. R3 every action ledgered (RepairAction).
M — mesh quality (checkMesh, MeshQualityGate defaults, ONE gate for all rungs):
  M1 "Mesh OK" (0 failed checks). M2 max non-ortho <= 65. M3 max skewness <= 4.
  M4 0 negative-volume cells. M5 >= 1000 cells.
  D1 diagnostics (never gated): aspect ratio, min volume, cell counts, layer coverage.
F — fallback ladder (DEFAULT_LADDER):
  F1 R0 = h 0.005 + 2 layers; R1 = h 0.005, no layers; R2 = h 0.0075, no layers.
  F2 first rung passing M1-M5 wins; every attempt recorded.
  F3 all rungs fail => loud NO-GO with the full report (the deliverable is then the
  ingestion + gate + ladder, documented honestly).
  F4 the gate is constructed once; no rung alters thresholds.
  F5 quasi-2D: one-cell slab at target resolution, castellate+snap (no volumetric
  refinement), flattenMesh, empty front/back; pre-declared fallback CONSTRUCTION:
  4-cell slab + symmetryPlane (a caveat, not a gate change).
V — end-to-end validation (Turek & Hron 2006, coefficient-normalized,
    Cd = F / (0.5 rho Ubar^2 D), D = 0.1):
  V1 ingested extents within 0.001 m of the published geometry (channel 2.5 x 0.41,
  cylinder r 0.05 at (0.2, 0.2), flag 0.35 x 0.02 ending at x = 0.6).
  V2 CFD2 converged. V3 CFD2 cd within 5 %, cl within 10 %.
  V4 four-fold provenance (clean tree) + MLflow per gated solve; surface_sha256 in
  config_hash; STL DVC-tracked.
  V5 (stretch, CFD3 within budget): mean cd 5 %, lift frequency 5 %, lift amplitude
  15 %; mean lift diagnostic only. Skipping CFD3 on budget is NOT a NO-GO.
VERDICT: GO <=> Q and (some rung passes M under F) and V1-V4. Budget: aero-dev only,
serial; CFD2 --timeout 14400; CFD3 --cfd3-timeout 43200.
Contingencies (pre-registered): exprFixedValue unavailable => inlet_bc "mapped"
(mechanism, not a gate change; the --preflight smoke decides); unusable extraction =>
ADR-033 §7 fallback acquisition with weaker-externality disclosure.

Usage:
  python scripts/stage18_turek_hron.py --preflight            # infra smoke (cube STL)
  python scripts/stage18_turek_hron.py --timeout 14400        # CFD2 campaign
  python scripts/stage18_turek_hron.py --skip-cfd3            # CFD2 only
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from aero.adapters._base import CaseDir, MeshHandle, ResultHandle, SolveResult, WallDistribution
from aero.adapters.openfoam import OpenFOAMSolver
from aero.adapters.openfoam.external_geometry import ExternalGeometrySpec
from aero.adapters.openfoam.robust_mesh import (
    DEFAULT_LADDER,
    MeshLadderReport,
    mesh_with_ladder,
)
from aero.geometry import (
    GeometryError,
    IngestConfig,
    IngestedGeometry,
    RepairConfig,
    TriSurface,
    ingest,
    write_stl,
)
from aero.orchestration import LocalSSHExecutor
from aero.provenance.four_fold import compute_provenance
from aero.vv._base import BenchmarkRunner
from aero.vv.external_geometry.turek_hron_cfd import TurekHronCFD2, TurekHronCFD3

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STL_DEFAULT = _REPO_ROOT / "data" / "references" / "fsi" / "turek_hron_fsi3" / "cylinder_flag.stl"
_TRACKING_URI = "http://192.168.2.234:5000"
_FLAG_THICKNESS = 0.02  # published Turek-Hron flag thickness [m] — the Q5 feature
# V1 published extents of the cylinder+flag union in the channel [m].
_V1_EXPECTED = {"x_min": 0.15, "x_max": 0.60, "y_min": 0.15, "y_max": 0.25}
_V1_TOL = 0.001  # 1 % of the cylinder diameter


def _detect_roots() -> tuple[Path, Path]:
    host = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    return host, Path("/mnt/aero")


class _PreMeshedSolver:
    """SolverProtocol shim: hand the ladder's already-gated mesh to BenchmarkRunner.

    The runner's prepare/mesh calls return the winning rung's case verbatim, so the
    solve runs on the EXACT mesh that passed the M-gate (no re-mesh, no drift);
    run/load delegate to the real adapter.
    """

    def __init__(self, inner: OpenFOAMSolver, case_dir: CaseDir, handle: MeshHandle) -> None:
        self._inner = inner
        self._case_dir = case_dir
        self._handle = handle

    def prepare(self, case: Any) -> CaseDir:
        return self._case_dir

    def mesh(self, case_dir: CaseDir, executor: Any) -> MeshHandle:
        return self._handle

    def run(self, case_dir: CaseDir, executor: Any) -> ResultHandle:
        return self._inner.run(case_dir, executor)

    def load(self, result: ResultHandle) -> SolveResult:
        return self._inner.load(result)

    def wall_distribution(
        self, result: ResultHandle, *, patch: str, u_inf: float = 1.0
    ) -> WallDistribution:
        return self._inner.wall_distribution(result, patch=patch, u_inf=u_inf)


def _check_v1_metrology(record: IngestedGeometry) -> tuple[bool, dict[str, float]]:
    """V1: ingested x/y extents vs the published geometry (abs tol 0.001 m)."""
    lo, hi = record.quality.bbox_min, record.quality.bbox_max
    measured = {"x_min": lo[0], "x_max": hi[0], "y_min": lo[1], "y_max": hi[1]}
    ok = all(abs(measured[k] - v) <= _V1_TOL for k, v in _V1_EXPECTED.items())
    return ok, measured


def _check_q5(base_cell_size: float) -> bool:
    """Q5: flag thickness >= 2 x cell size, for the WORST (coarsest) ladder rung."""
    coarsest = max(r.cell_size_factor for r in DEFAULT_LADDER)
    return 2.0 * base_cell_size * coarsest <= _FLAG_THICKNESS


def _run_test(
    *,
    case: TurekHronCFD2 | TurekHronCFD3,
    spec: ExternalGeometrySpec,
    solver: OpenFOAMSolver,
    executor: LocalSSHExecutor,
    allow_dirty: bool,
    log_mlflow: bool,
) -> dict[str, Any]:
    """Ladder-mesh + solve + validate one Turek-Hron test; returns the bundle piece."""
    print(f"[{case.name}] mesh ladder (rungs: {', '.join(r.name for r in DEFAULT_LADDER)}) ...")
    try:
        case_dir, handle, ladder = mesh_with_ladder(
            solver=solver,
            executor=executor,
            spec=spec,
            sif_path=solver.sif_path,
        )
    except GeometryError as exc:
        report: MeshLadderReport | None = getattr(exc, "ladder_report", None)
        print(f"[{case.name}] NO-GO — {exc}")
        return {
            "status": "no-go",
            "error": str(exc),
            "ladder": report.model_dump(mode="json") if report else None,
        }
    winning_spec = case_dir.spec
    assert isinstance(winning_spec, ExternalGeometrySpec)
    print(
        f"[{case.name}] rung {ladder.passed_rung} passed "
        f"(h={winning_spec.base_cell_size:.4g}, run={case_dir.run_id})"
    )

    provenance = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=winning_spec.model_dump(mode="json"),
        allow_dirty=allow_dirty,
    )
    if log_mlflow:
        from aero.provenance.db import resolve_dsn

        db_dsn = resolve_dsn()
    else:
        db_dsn = "unused"
    runner = BenchmarkRunner(
        solver=_PreMeshedSolver(solver, case_dir, handle),
        executor=executor,
        tracking_uri=_TRACKING_URI,
        experiment="aero-provenance",
        db_dsn=db_dsn,
        solver_version="OpenFOAM-ESI v2412",
        stage="18",
    )
    gated_case: TurekHronCFD2 | TurekHronCFD3 = type(case)(winning_spec)
    print(f"[{case.name}] solving ({'pimpleFoam' if spec.transient else 'simpleFoam'}) ...")
    result = runner.run(
        gated_case, provenance=provenance, repo_root=_REPO_ROOT, log_mlflow=log_mlflow
    )
    for m in result.metrics:
        print(
            f"[{case.name}]   {m.name}: measured={m.measured:.6g} ref={m.reference:.6g} "
            f"err={m.error:.2%} tol={m.tolerance:.0%} -> {'PASS' if m.passed else 'FAIL'}"
        )
    return {
        "status": result.status,
        "ladder": ladder.model_dump(mode="json"),
        "winning_rung": ladder.passed_rung,
        "run_id": case_dir.run_id,
        "n_elements": result.n_elements,
        "benchmark": json.loads(result.to_json()),
    }


def _preflight_box() -> TriSurface:
    """A small closed box spanning the slab — infra smoke only, NOT the deliverable."""
    lo = np.array([0.28, 0.18, -0.02])
    hi = np.array([0.33, 0.23, 0.06])
    corners = np.array(
        [
            [lo[0], lo[1], lo[2]],
            [hi[0], lo[1], lo[2]],
            [hi[0], hi[1], lo[2]],
            [lo[0], hi[1], lo[2]],
            [lo[0], lo[1], hi[2]],
            [hi[0], lo[1], hi[2]],
            [hi[0], hi[1], hi[2]],
            [lo[0], hi[1], hi[2]],
        ]
    )
    faces = np.array(
        [
            (0, 2, 1),
            (0, 3, 2),
            (4, 5, 6),
            (4, 6, 7),
            (0, 1, 5),
            (0, 5, 4),
            (2, 3, 7),
            (2, 7, 6),
            (0, 4, 7),
            (0, 7, 3),
            (1, 2, 6),
            (1, 6, 5),
        ],
        dtype=np.int64,
    )
    return TriSurface(corners, faces)


def _preflight(host: str, timeout: int, inlet_bc: str) -> int:
    """End-to-end infra smoke on a tiny box STL: snappy pipeline + inlet BC probe."""
    from aero.adapters.openfoam.mesh_quality import MeshQualityGate
    from aero.adapters.openfoam.robust_mesh import MeshLadderRung

    tmp = Path(tempfile.mkdtemp(prefix="stage18-preflight-"))
    stl = tmp / "box.stl"
    write_stl(_preflight_box(), stl)
    record = ingest(stl)
    print(f"[preflight] box ingested: watertight={record.quality.watertight}")

    host_root, remote_root = _detect_roots()
    solver = OpenFOAMSolver(host_nfs_root=host_root, remote_nfs_root=remote_root)
    executor = LocalSSHExecutor(
        host=host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=timeout
    )

    for bc in [inlet_bc, "mapped"] if inlet_bc == "expr" else [inlet_bc]:
        spec = ExternalGeometrySpec(
            name=f"stage18-preflight-{bc}",
            surface_source=str(stl),
            surface_name="box",
            surface_sha256=record.surface_sha256,
            base_cell_size=0.02,
            inlet_bc=bc,  # type: ignore[arg-type]
            steady_iterations=60,
        )
        try:
            case_dir, _, ladder = mesh_with_ladder(
                solver=solver,
                executor=executor,
                spec=spec,
                sif_path=solver.sif_path,
                gate=MeshQualityGate(),
                rungs=(MeshLadderRung(name="PF", cell_size_factor=1.0, n_surface_layers=0),),
            )
        except GeometryError as exc:
            print(f"[preflight] mesh FAILED ({bc}): {exc}")
            return 1
        print(f"[preflight] mesh ok ({bc}); rung {ladder.passed_rung}; running 60 iters ...")
        result = solver.run(case_dir, executor)
        if result.returncode == 0:
            coeff = list((case_dir.host_path / "postProcessing").rglob("coefficient.dat"))
            print(f"[preflight] SOLVE OK with inlet_bc={bc!r}; forceCoeffs written: {bool(coeff)}")
            print(f"[preflight] RESULT: use --inlet-bc {bc}")
            return 0
        log_tail = result.solver_log[-3000:]
        if "Unknown" in log_tail and bc == "expr":
            print("[preflight] exprFixedValue rejected by the SIF — trying 'mapped' ...")
            continue
        print(f"[preflight] solve FAILED (rc={result.returncode}); log tail:\n{log_tail}")
        return 1
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="aero-dev")
    parser.add_argument("--timeout", type=int, default=14400, help="CFD2 mesh+solve ceiling [s].")
    parser.add_argument("--cfd3-timeout", type=int, default=43200)
    parser.add_argument("--stl", type=Path, default=_STL_DEFAULT)
    parser.add_argument("--repair", action="store_true", help="Enable the declared repair pass.")
    parser.add_argument("--inlet-bc", choices=("expr", "mapped"), default="expr")
    parser.add_argument("--skip-cfd3", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument(
        "--out", type=Path, default=_REPO_ROOT / "data" / "vv" / "stage18_turek_hron.json"
    )
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    if args.preflight:
        return _preflight(args.host, args.timeout, args.inlet_bc)

    bundle: dict[str, Any] = {"stage": 18, "adr": "ADR-034"}

    # --- Q gates (ingestion) --------------------------------------------------
    config = IngestConfig(repair=RepairConfig() if args.repair else None)
    try:
        record = ingest(args.stl, config=config)
    except GeometryError as exc:
        print(f"[ingest] Q-GATE FAILED (loud NO-GO): {exc}")
        bundle["ingestion"] = {"status": "refused", "error": str(exc)}
        args.out.write_text(json.dumps(bundle, indent=2) + "\n")
        return 1
    bundle["ingestion"] = record.model_dump(mode="json")
    print(
        f"[ingest] Q-gates passed: {record.n_faces} faces, sha={record.surface_sha256[:12]}..., "
        f"repairs={len(record.repairs)}"
    )

    # --- V1 metrology + Q5 feature floor -------------------------------------
    v1_ok, measured = _check_v1_metrology(record)
    bundle["v1_metrology"] = {"passed": v1_ok, "measured": measured, "expected": _V1_EXPECTED}
    print(f"[V1] extents {measured} -> {'PASS' if v1_ok else 'FAIL'}")
    cfd2 = TurekHronCFD2()
    spec2 = cfd2.case_spec().model_copy(update={"inlet_bc": args.inlet_bc})
    q5_ok = _check_q5(spec2.base_cell_size)
    bundle["q5_feature_floor"] = {
        "passed": q5_ok,
        "flag_thickness": _FLAG_THICKNESS,
        "base_cell_size": spec2.base_cell_size,
    }
    print(f"[Q5] flag 0.02 >= 2 x h x coarsest-rung -> {'PASS' if q5_ok else 'FAIL'}")
    if not (v1_ok and q5_ok):
        args.out.write_text(json.dumps(bundle, indent=2) + "\n")
        print("VERDICT: NO-GO (pre-mesh gates failed)")
        return 1

    # --- CFD2 (gated) ---------------------------------------------------------
    host_root, remote_root = _detect_roots()
    solver = OpenFOAMSolver(host_nfs_root=host_root, remote_nfs_root=remote_root)
    executor = LocalSSHExecutor(
        host=args.host, ssh_user="root", repo_root=_REPO_ROOT, long_timeout_s=args.timeout
    )
    bundle["cfd2"] = _run_test(
        case=cfd2,
        spec=spec2,
        solver=solver,
        executor=executor,
        allow_dirty=args.allow_dirty,
        log_mlflow=not args.no_mlflow,
    )

    # --- CFD3 (stretch, budget-gated) -----------------------------------------
    if args.skip_cfd3:
        bundle["cfd3"] = {"status": "skipped", "reason": "budget (pre-declared; not a NO-GO)"}
    else:
        executor3 = LocalSSHExecutor(
            host=args.host,
            ssh_user="root",
            repo_root=_REPO_ROOT,
            long_timeout_s=args.cfd3_timeout,
        )
        cfd3 = TurekHronCFD3()
        spec3 = cfd3.case_spec().model_copy(update={"inlet_bc": args.inlet_bc})
        bundle["cfd3"] = _run_test(
            case=cfd3,
            spec=spec3,
            solver=solver,
            executor=executor3,
            allow_dirty=args.allow_dirty,
            log_mlflow=not args.no_mlflow,
        )

    # --- verdict --------------------------------------------------------------
    go = bundle["cfd2"].get("status") == "pass" and v1_ok and q5_ok
    bundle["verdict"] = {
        "go": go,
        "rule": "GO <=> Q and (rung passes M under F) and V1-V4 (ADR-034)",
        "cfd3_reported": bundle["cfd3"].get("status") not in (None, "skipped"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, indent=2) + "\n")
    print(f"bundle -> {args.out}")
    print(f"VERDICT: {'GO' if go else 'NO-GO'}")
    print("NEXT: commit the bundle (clean tree first), then the handoff.")
    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
