#!/usr/bin/env python3
"""Stage 08 — build `manifest.json` by joining a dataset's two root CSVs.

The four public ML-CFD datasets (AhmedML / WindsorML / DrivAerML on
Hugging Face; DrivAerNet++ on Harvard Dataverse) all publish two
top-level CSVs that share a per-run ``run`` key:

* ``geo_parameters_all.csv`` — geometric descriptors.
* ``force_mom_all.csv`` — integrated coefficients (Cd, Cl, ...).

This script joins them on ``run`` and emits the ``manifest.json`` the
aero loader's strict-pydantic ``*Case`` model consumes. The per-dataset
column mapping (upstream column name → aero field name) lives in the
``_LAYOUT`` table below; populate the corresponding entry before adding
support for a new dataset.

Per-run STL files are NOT consulted here — they're pulled separately by
the ``scripts/download_*.sh`` scripts and consumed by Stage-09's DoMINO
training pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Final

# Each entry maps:
#   "geo_csv"      → the basename of the upstream geometric-parameter CSV
#   "fm_csv"       → the basename of the upstream force-moment CSV
#   "run_col"      → the join-key column name in BOTH csvs
#   "geo_to_aero"  → upstream geometric column → aero field name
#   "fm_to_aero"   → upstream force-moment column → aero field name
#
# Columns NOT listed in either translation table are dropped silently.
_LAYOUT: Final[dict[str, dict[str, object]]] = {
    "ahmedml": {
        "geo_csv": "geo_parameters_all.csv",
        "fm_csv": "force_mom_all.csv",
        "run_col": "run",
        "geo_to_aero": {
            "body-length": "body_length",
            "body-height": "body_height",
            "body-width": "body_width",
            "front-arc-diameter": "front_arc_diameter",
            "slant-angle-length": "slant_angle_length",
            "slant-angle-height": "slant_angle_height",
            "slant-surface-length": "slant_surface_length",
            "slant-angle-degrees": "slant_angle_degrees",
        },
        "fm_to_aero": {
            "cd": "cd",
            "cl": "cl",
        },
    },
    "windsorml": {
        "geo_csv": "geo_parameters_all.csv",
        "fm_csv": "force_mom_all.csv",
        "run_col": "run",
        "geo_to_aero": {
            "ratio_length_back_fast": "ratio_length_back_fast",
            "ratio_height_nose_windshield": "ratio_height_nose_windshield",
            "ratio_height_fast_back": "ratio_height_fast_back",
            "side_taper": "side_taper",
            "clearance": "clearance",
            "bottom_taper_angle": "bottom_taper_angle",
            "frontal_area": "frontal_area",
        },
        "fm_to_aero": {
            "cd": "cd",
            "cs": "cs",
            "cl": "cl",
            "cmy": "cmy",
        },
    },
    "drivaerml": {
        "geo_csv": "geo_parameters_all.csv",
        "fm_csv": "force_mom_all.csv",
        "run_col": "Run",  # DrivAerML's geo CSV uses capital R; the fm CSV uses lowercase
        "geo_to_aero": {
            "Vehicle_Length": "vehicle_length",
            "Vehicle_Width": "vehicle_width",
            "Vehicle_Height": "vehicle_height",
            "Front_Overhang": "front_overhang",
            "Front_Planview": "front_planview",
            "Hood_Angle": "hood_angle",
            "Approach_Angle": "approach_angle",
            "Windscreen_Angle": "windscreen_angle",
            "Greenhouse_Tapering": "greenhouse_tapering",
            "Backlight_Angle": "backlight_angle",
            "Decklid_Height": "decklid_height",
            "Rearend_tapering": "rearend_tapering",
            "Rear_Overhang": "rear_overhang",
            "Rear_Diffusor_Angle": "rear_diffusor_angle",
            "Vehicle_Ride_Height": "vehicle_ride_height",
            "Vehicle_Pitch": "vehicle_pitch",
        },
        "fm_to_aero": {
            "cd": "cd",
            "cl": "cl",
            "clf": "clf",
            "clr": "clr",
            "cs": "cs",
        },
    },
    # DrivAerNet++ is on Harvard Dataverse with a different layout; pending
    # the operator's first pull (the Dataverse REST listing names the files
    # differently from the HF datasets).
    "drivaernet_plus_plus": {
        "geo_csv": "",
        "fm_csv": "",
        "run_col": "",
        "geo_to_aero": {},
        "fm_to_aero": {},
    },
}


def _strip(s: str) -> str:
    """Strip whitespace + a trailing comma if the CSV's space-padded."""
    return s.strip().lstrip(",").rstrip(",").strip()


def _read_csv_by_run(
    path: Path, run_col: str, column_map: dict[str, str]
) -> dict[str, dict[str, str]]:
    """Read a CSV; key by the run column; project columns through `column_map`.

    The upstream CSVs sometimes ship space-padded headers (e.g. " cd"),
    so all column names are stripped before lookup.
    """
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise RuntimeError(f"{path} has no header row")
        stripped = {_strip(c): c for c in reader.fieldnames}
        if run_col not in stripped:
            raise RuntimeError(f"{path} has no {run_col!r} column (available: {sorted(stripped)})")
        for row in reader:
            row_stripped: dict[str, str] = {
                _strip(k): _strip(v) for k, v in row.items() if k is not None
            }
            run = row_stripped[run_col]
            if not run:
                continue
            projected: dict[str, str] = {}
            for upstream_col, aero_col in column_map.items():
                stripped_col = _strip(upstream_col)
                if stripped_col not in row_stripped:
                    raise RuntimeError(
                        f"{path} row run={run}: expected column "
                        f"{stripped_col!r} for aero field {aero_col!r}"
                    )
                projected[aero_col] = row_stripped[stripped_col]
            out[run] = projected
    return out


def _emit_pending(dataset: str, out: Path) -> int:
    """Refuse to emit a manifest until the dataset's _LAYOUT is filled in."""
    print(
        f"ERROR: dataset '{dataset}' has no verified _LAYOUT mapping in\n"
        f"  scripts/build_dataset_manifest.py:_LAYOUT[{dataset!r}]\n"
        "\n"
        "Populate `geo_csv`, `fm_csv`, `run_col`, `geo_to_aero` and `fm_to_aero`\n"
        "after inspecting the upstream dataset's root-level CSVs; the aero\n"
        f"loader's *Case model (aero/surrogates/_common/loaders/{dataset}.py)\n"
        "is the target schema. Re-run after the table is populated.\n"
        f"\n  ({out} is intentionally NOT written until then.)",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=sorted(_LAYOUT))
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    layout = _LAYOUT[args.dataset]
    if not layout["geo_csv"] or not layout["fm_csv"]:
        return _emit_pending(args.dataset, args.out)

    geo_path = args.dataset_dir / str(layout["geo_csv"])
    fm_path = args.dataset_dir / str(layout["fm_csv"])
    if not geo_path.is_file():
        print(f"ERROR: {geo_path} not found", file=sys.stderr)
        return 2
    if not fm_path.is_file():
        print(f"ERROR: {fm_path} not found", file=sys.stderr)
        return 2

    run_col = str(layout["run_col"])
    geo_map = layout["geo_to_aero"]
    fm_map = layout["fm_to_aero"]
    assert isinstance(geo_map, dict) and isinstance(fm_map, dict)

    geo_by_run = _read_csv_by_run(geo_path, run_col, geo_map)
    # The fm csv may use a different case ("run" vs "Run"); try both.
    try:
        fm_by_run = _read_csv_by_run(fm_path, run_col, fm_map)
    except RuntimeError:
        fm_by_run = _read_csv_by_run(fm_path, run_col.lower(), fm_map)

    rows: list[dict[str, str | float]] = []
    common_runs = sorted(
        set(geo_by_run) & set(fm_by_run), key=lambda r: int(r) if r.isdigit() else r
    )
    for run in common_runs:
        row: dict[str, str | float] = {"case_id": f"{args.dataset}-{run}"}
        for aero_field, raw in {**geo_by_run[run], **fm_by_run[run]}.items():
            try:
                row[aero_field] = float(raw)
            except ValueError:
                row[aero_field] = raw
        rows.append(row)

    args.out.write_text(json.dumps(rows, indent=2))
    print(
        f"wrote {len(rows)} rows to {args.out} "
        f"(geo: {len(geo_by_run)}, fm: {len(fm_by_run)}, joined: {len(common_runs)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
