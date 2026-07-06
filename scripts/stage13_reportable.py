#!/usr/bin/env python
"""Compose a plunging-foil full-U95 thrust ReportableResult from a completed run + log it.

The Stage-13 unsteady-airfoil composition, reusing the Stage-12 U95 machinery
(``aero/vv/statistical_uncertainty.py`` + ``aero/vv/reportable_compose.py``). Reads a
completed plunging run's forceCoeffs history, segments cycles, and computes:

  * the cycle-mean **thrust coefficient** C_T = -mean(Cd) over the converged tail;
  * its batch-means ``u95_statistical`` (the estimator is sign-symmetric, so it is computed on
    the Cd per-cycle series and applies to C_T unchanged);
  * ``u95_numerical`` from a space+time GCI JSON (``scripts/stage13_gci.py``);
  * ``u95_input`` from the corrected Heathcote-Gursul reference (small at the in-range St 0.2/0.3,
    large at the out-of-range St 0.4).

The experiment anchor compares C_T against the corrected HG reference (``thrust.csv`` via the
case's ``reference()``) at the case's 15% metric tolerance. Demonstrates whether the re-anchored
(and/or transitional) result clears the anchor and improves on the Stage-12 laminar
over-prediction. Composes + MLflow-logs a ``ReportableResult``.

    python scripts/stage13_reportable.py plunging_airfoil_hg2007_st02 \\
        --run-dir /mnt/aero-nfs/runs/plunging_airfoil_hg2007_st02-<ts> \\
        --gci-json data/vv/stage13_gci_plunging_airfoil_hg2007_st02.json --u95-input-frac 0.15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_cd(run_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """(t, Cd) from the forceCoeffs coefficient.dat (columns: Time Cd Cs Cl ...)."""
    path = run_dir / "postProcessing" / "forceCoeffs1" / "0" / "coefficient.dat"
    rows: list[tuple[float, float]] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = s.split()
        rows.append((float(p[0]), float(p[1])))
    a = np.asarray(rows, dtype=np.float64)
    keep = np.concatenate([np.diff(a[:, 0]) > 0.0, [True]])  # strictly-increasing t for the Signal
    a = a[keep]
    return a[:, 0], a[:, 1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="UNSTEADY_CASES key (a plunging variant)")
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--period", type=float, default=None, help="Cycle period (default 1/forcing f)")
    ap.add_argument("--gci-json", type=Path, default=None, help="GCI report -> u95_numerical_abs")
    ap.add_argument("--u95-numerical", type=float, default=0.0)
    ap.add_argument(
        "--u95-input-frac",
        type=float,
        default=0.15,
        help="Fractional reference/model-form U95 (small at in-range St 0.2/0.3).",
    )
    ap.add_argument(
        "--no-thesis-grade", action="store_true", help="Force 'validated' (e.g. anchor fails)"
    )
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    from aero.postprocess._base import Signal
    from aero.postprocess.cycle_detection import detect_cycle_convergence
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

    t, cd = _load_cd(args.run_dir)
    samples = segment_cycles(Signal.from_arrays(t, cd, name="cd"), period=period)
    report = detect_cycle_convergence(samples)
    stat = statistical_uncertainty(samples, report)  # sign-symmetric -> applies to C_T
    tail = samples.per_cycle_mean[report.converged_from_cycle :]
    ct = -float(np.mean(tail))  # thrust coefficient C_T = -mean(Cd)

    ref = case.reference(_REPO_ROOT)
    ct_ref = ref.scalars["thrust_coefficient"]
    (tol,) = (m.tolerance for m in case.metrics() if m.name == "thrust_coefficient")
    obs_err = abs(ct - ct_ref) / abs(ct_ref)
    anchor = ValidationAnchor(
        reference=ref.source,
        citation=ref.source,
        tolerance=tol,
        observed_error=obs_err,
        passed=obs_err <= tol,
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
        name="thrust_coefficient",
        value=ct,
        kind="time_averaged",
        provenance=prov,
        u95_numerical=u95_num,
        stat=stat,
        u95_input_frac=args.u95_input_frac,
        anchor=anchor,
        allow_thesis_grade=not args.no_thesis_grade,
    )

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / f"stage13_reportable_{args.case}.json")
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
            db_dsn=resolve_dsn(),
            run_name=f"stage13-reportable-{args.case}",
            extra_tags={
                "stage": "13",
                "validation_tag": result.validation_tag,
                "u95_reliable": str(stat.reliable),
                "n_converged_cycles": str(len(tail)),
            },
        ):
            log_metrics(
                {
                    "thrust_coefficient": q.value,
                    "u95_numerical": q.u95_numerical,
                    "u95_statistical": q.u95_statistical,
                    "u95_input": q.u95_input,
                    "u95_total": q.u95_total,
                    "n_eff": stat.n_eff,
                    "anchor_observed_error": obs_err,
                }
            )
            log_artifact(str(out))

    print(
        f"RESULT case={args.case} C_T={q.value:.4f} tag={result.validation_tag} "
        f"u95_num={q.u95_numerical:.4f} u95_stat={q.u95_statistical:.4f} "
        f"u95_input={q.u95_input:.4f} u95_total={q.u95_total:.4f} reliable={stat.reliable} "
        f"anchor_passed={anchor.passed} (C_T_ref={ct_ref:.3f}, err={obs_err:.1%}) "
        f"n_conv={len(tail)} out={out}"
    )


if __name__ == "__main__":
    main()
