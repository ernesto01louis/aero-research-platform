#!/usr/bin/env python
"""Compose a moving-case full-``U95`` ReportableResult from a completed run + log it to MLflow.

The Stage-12 end-to-end demonstration: read a completed moving-case run dir's forceCoeffs
history, compute the **cycle-mean metric** + its **batch-means ``u95_statistical``** (the Stage-11
``CycleSamples`` seam -> the Stage-12 estimator), take ``u95_numerical`` from a GCI JSON
(``stage12_cylinder_gci.py``), add ``u95_input`` (reference/digitization), build the experiment
anchor, RSS-compose an :class:`aero.vv.reportable.ReportableResult`, and log it as an MLflow
artifact JSON with the ``u95_*`` metrics + ``validation_tag`` tags.

    # cylinder (thesis-grade GO): response Strouhal anchors the locked limit cycle
    python scripts/stage12_reportable.py oscillating_cylinder_lockin \\
        --run-dir /mnt/aero-nfs/runs/oscillating_cylinder_lockin-<ts> --gci-json data/vv/stage12_cylinder_gci.json

    # foil (CONCERN, non-thesis): over-prediction vs the corrected HG reference
    python scripts/stage12_reportable.py plunging_airfoil_hg2007 --run-dir <dir> --metric cd \\
        --period <T> --u95-input-frac 0.4 --anchor-observed-error 2.0 --no-thesis-grade
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_coeffs(run_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(t, Cd, Cl) from the OpenFOAM forceCoeffs coefficient.dat (columns: Time Cd ... Cl ...)."""
    path = run_dir / "postProcessing" / "forceCoeffs1" / "0" / "coefficient.dat"
    rows: list[tuple[float, float, float]] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = s.split()
        rows.append((float(p[0]), float(p[1]), float(p[4])))
    a = np.asarray(rows, dtype=np.float64)
    return a[:, 0], a[:, 1], a[:, 2]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="UNSTEADY_CASES key")
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--metric", default="cd", choices=["cd", "cl"])
    ap.add_argument(
        "--period", type=float, default=None, help="Cycle period (default: 1/forcing freq)"
    )
    ap.add_argument("--gci-json", type=Path, default=None, help="GCI report -> u95_numerical_abs")
    ap.add_argument(
        "--u95-numerical", type=float, default=0.0, help="Absolute numerical U95 override"
    )
    ap.add_argument("--u95-input-frac", type=float, default=0.0)
    ap.add_argument("--anchor-tolerance", type=float, default=0.03)
    ap.add_argument(
        "--anchor-observed-error",
        type=float,
        default=None,
        help="Observed error vs reference (fraction); default = the cylinder response-Strouhal error",
    )
    ap.add_argument("--anchor-reference", default=None)
    ap.add_argument("--anchor-citation", default=None)
    ap.add_argument(
        "--no-thesis-grade", action="store_true", help="Force 'validated' (e.g. foil CONCERN)"
    )
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    from aero.postprocess._base import Signal
    from aero.postprocess.cycle_detection import detect_cycle_convergence
    from aero.postprocess.frequency import dominant_frequency
    from aero.postprocess.phase_averaging import segment_cycles
    from aero.provenance import compute_provenance
    from aero.vv.reportable import ValidationAnchor
    from aero.vv.reportable_compose import compose_reportable
    from aero.vv.statistical_uncertainty import statistical_uncertainty
    from aero.vv.unsteady import UNSTEADY_CASES

    if args.case not in UNSTEADY_CASES:
        raise SystemExit(f"unknown case {args.case!r}; known: {', '.join(UNSTEADY_CASES)}")
    case = UNSTEADY_CASES[args.case]
    spec = case.case_spec()
    period = args.period if args.period is not None else 1.0 / spec.motion.frequency

    t, cd, cl = _load_coeffs(args.run_dir)
    y = cd if args.metric == "cd" else cl
    samples = segment_cycles(Signal.from_arrays(t, y, name=args.metric), period=period)
    report = detect_cycle_convergence(samples)
    stat = statistical_uncertainty(samples, report)
    tail = samples.per_cycle_mean[report.converged_from_cycle :]
    value = float(np.mean(tail))

    ref = case.reference(_REPO_ROOT)
    if args.anchor_observed_error is not None:
        obs_err = args.anchor_observed_error
    else:
        # cylinder: response Strouhal (D=U=1 -> St=f) vs the forcing frequency
        st_resp = dominant_frequency(Signal.from_arrays(t, cl, name="cl")).frequency
        obs_err = abs(st_resp - spec.motion.frequency) / spec.motion.frequency
    anchor = ValidationAnchor(
        reference=args.anchor_reference or ref.source,
        citation=args.anchor_citation or ref.source,
        tolerance=args.anchor_tolerance,
        observed_error=obs_err,
        passed=obs_err <= args.anchor_tolerance,
    )

    u95_num = args.u95_numerical
    if args.gci_json is not None:
        u95_num = float(json.loads(args.gci_json.read_text())["u95_numerical_abs"])

    prov = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif="openfoam-esi.sif",
        resolved_config=spec.model_dump(mode="json"),
        allow_dirty=args.allow_dirty,
    )
    result = compose_reportable(
        case_name=args.case,
        name=args.metric,
        value=value,
        kind="time_averaged",
        provenance=prov,
        u95_numerical=u95_num,
        stat=stat,
        u95_input_frac=args.u95_input_frac,
        anchor=anchor,
        allow_thesis_grade=not args.no_thesis_grade,
    )

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / f"stage12_reportable_{args.case}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")

    q = result.quantities[0]
    if not args.no_mlflow:
        from aero.provenance.db import resolve_dsn
        from aero.provenance.mlflow import log_artifact, log_metrics, start_provenance_run

        with start_provenance_run(
            tracking_uri="http://192.168.2.234:5000",
            experiment="aero-provenance",
            provenance=prov,
            case_name=args.case,
            db_dsn=resolve_dsn(),
            stage="12",
            extra_tags={
                "validation_tag": result.validation_tag,
                "u95_reliable": "true" if stat.reliable else "false",
                "n_converged_cycles": str(report.n_converged_cycles),
            },
        ):
            log_metrics(
                {
                    q.name: q.value,
                    f"{q.name}_u95_numerical": q.u95_numerical,
                    f"{q.name}_u95_statistical": q.u95_statistical,
                    f"{q.name}_u95_input": q.u95_input,
                    f"{q.name}_u95_total": q.u95_total,
                    "n_eff": stat.n_eff,
                }
            )
            log_artifact(str(out))

    print(
        f"RESULT case={args.case} metric={q.name} value={q.value:.5f} tag={result.validation_tag} "
        f"u95_num={q.u95_numerical:.5g} u95_stat={q.u95_statistical:.5g} u95_input={q.u95_input:.5g} "
        f"u95_total={q.u95_total:.5g} reliable={stat.reliable} anchor_passed={anchor.passed} "
        f"n_conv={report.n_converged_cycles} out={out}"
    )


if __name__ == "__main__":
    main()
