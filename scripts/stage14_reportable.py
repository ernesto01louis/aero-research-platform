#!/usr/bin/env python
"""Compose a flapping-wing full-U95 mean-lift ReportableResult from a completed run + log it.

The Stage-14 analogue of ``scripts/stage13_reportable.py``. Reads a completed flapping run's
dimensional ``forces`` history, normalises it (WBD; :mod:`aero.postprocess.flapping_forces`),
segments cycles, and composes:

  * the WBD-normalised stroke-averaged **mean lift coefficient** over the converged tail;
  * its batch-means ``u95_statistical`` (on the per-cycle mean-lift series);
  * ``u95_numerical`` from a space+time GCI JSON (``scripts/stage14_gci.py``);
  * ``u95_input`` from the reference (text-sourced WBD means; ~5%), recorded as ``estimated``.

The experiment anchor compares the mean lift against the WBD *experiment* value (the case's
``reference()``) at the pre-registered metric tolerance. Composes + MLflow-logs a
``ReportableResult``; thesis-grade requires a clean (non-dirty) SHA, a passing anchor, and a
reliable statistical estimate — all enforced structurally by the schema.

    python scripts/stage14_reportable.py flapping_wing_wbd2004 \\
        --run-dir /mnt/aero/runs/flapping_wing_wbd2004-<ts> \\
        --gci-json data/vv/stage14_gci_flapping_wing_wbd2004.json --u95-input-frac 0.05
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _cycle_samples_and_mean(run_dir: Path, case: object) -> tuple[object, object, float]:
    """(CycleSamples, CycleConvergenceReport, mean_cl) for the WBD lift over a completed run."""
    from aero.adapters._base import CaseDir, ResultHandle
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.postprocess._base import Signal
    from aero.postprocess.cycle_detection import detect_cycle_convergence
    from aero.postprocess.phase_averaging import segment_cycles

    spec = case.case_spec()  # type: ignore[attr-defined]
    period = spec.motion.period
    handle = ResultHandle(
        case_dir=CaseDir(
            run_id=run_dir.name,
            spec=spec,
            host_path=run_dir,
            remote_path=Path("/mnt/aero") / run_dir.name,
        ),
        returncode=0,
        output_host_path=run_dir / "postProcessing",
    )
    trace = OpenFOAMSolver().flapping_force_trace(handle)
    sig = Signal.from_arrays(np.asarray(trace.t), np.asarray(trace.cl), name="lift_coefficient")
    samples = segment_cycles(sig, period=period)
    report = detect_cycle_convergence(samples)
    mean_cl = float(np.mean(samples.per_cycle_mean[report.converged_from_cycle :]))
    return samples, report, mean_cl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", help="FLAPPING_CASES key (e.g. flapping_wing_wbd2004)")
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--gci-json", type=Path, default=None, help="GCI report -> u95_numerical_abs")
    ap.add_argument("--u95-numerical", type=float, default=0.0)
    ap.add_argument(
        "--u95-input-frac",
        type=float,
        default=0.05,
        help="Fractional reference/model-form U95 (WBD means are text-sourced; ~5%).",
    )
    ap.add_argument(
        "--no-thesis-grade", action="store_true", help="Force 'validated' (e.g. anchor fails)"
    )
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    from aero.provenance import compute_provenance
    from aero.vv.flapping import FLAPPING_CASES
    from aero.vv.reportable import ValidationAnchor
    from aero.vv.reportable_compose import compose_reportable
    from aero.vv.statistical_uncertainty import statistical_uncertainty

    if args.case not in FLAPPING_CASES:
        raise SystemExit(f"unknown case {args.case!r}; known: {', '.join(FLAPPING_CASES)}")
    case = FLAPPING_CASES[args.case]
    spec = case.case_spec()

    samples, report, mean_cl = _cycle_samples_and_mean(args.run_dir, case)
    stat = statistical_uncertainty(samples, report)

    ref = case.reference(_REPO_ROOT)
    cl_ref = ref.scalars["mean_lift_coefficient"]
    (tol,) = (m.tolerance for m in case.metrics() if m.name == "mean_lift_coefficient")
    obs_err = abs(mean_cl - cl_ref) / abs(cl_ref)
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
        name="mean_lift_coefficient",
        value=mean_cl,
        kind="time_averaged",
        provenance=prov,
        u95_numerical=u95_num,
        stat=stat,
        u95_input_frac=args.u95_input_frac,
        u95_input_basis="estimated",  # WBD means are text-sourced (P1d)
        anchor=anchor,
        allow_thesis_grade=not args.no_thesis_grade,
    )

    out = Path(args.out or _REPO_ROOT / "data" / "vv" / f"stage14_reportable_{args.case}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")

    q = result.quantities[0]
    n_tail = len(samples.per_cycle_mean[report.converged_from_cycle :])
    if not args.no_mlflow:
        from aero.provenance.db import resolve_dsn
        from aero.provenance.mlflow import log_artifact, log_metrics, start_provenance_run

        with start_provenance_run(
            tracking_uri="http://192.168.2.234:5000",
            experiment="aero-provenance",
            provenance=prov,
            case_name=args.case,
            db_dsn=resolve_dsn(),
            stage="14",
            extra_tags={
                "validation_tag": result.validation_tag,
                "u95_reliable": "true" if stat.reliable else "false",
                "n_converged_cycles": str(n_tail),
            },
        ):
            log_metrics(
                {
                    "mean_lift_coefficient": q.value,
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
        f"RESULT case={args.case} mean_CL={q.value:.4f} tag={result.validation_tag} "
        f"u95_num={q.u95_numerical:.4f} u95_stat={q.u95_statistical:.4f} "
        f"u95_input={q.u95_input:.4f} u95_total={q.u95_total:.4f} reliable={stat.reliable} "
        f"anchor_passed={anchor.passed} (CL_ref={cl_ref:.3f}, err={obs_err:.1%}) "
        f"n_conv={n_tail} out={out}"
    )


if __name__ == "__main__":
    main()
