#!/usr/bin/env python3
"""Stage 08 — build `manifest.json` from a per-run-CSV-backed dataset.

Called by the four ``scripts/download_*.sh`` mirror scripts after the
per-run files land. Walks ``cases/run_*/force_mom_*.csv``, extracts the
columns the aero loader's strict-pydantic ``*Case`` model expects, and
writes a single JSON array consumed by the loader's ``manifest.json``
path.

**Scope limitation — schema mapping is a Stage 09 prerequisite.** The
upstream CSV column conventions vary per dataset and have not been
verified at the row-by-row level in this session. The Stage-08 loader
schema (e.g. AhmedML's ``slant_angle_deg / length_ratio /
clearance_ratio / front_pillar_radius_m``) is the platform-side contract;
the *mapping* from upstream column names to those fields needs first-byte
verification at script-run time.

This builder fails loud with a clear message rather than emit a manifest
that would silently pass Pydantic validation with stub values. The
operator runs it once after the first dataset pull, inspects one CSV,
updates the per-dataset ``_COLUMN_MAP`` block, and re-runs. Stage 09's
DoMINO training is the first time the manifest is actually consumed for
prediction, so this gate is the right shape for the seam.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Final

# Per-dataset upstream-CSV → aero-schema field mappings. Each value is a
# dict of `aero_field → upstream_column`; an empty mapping means "schema
# not yet verified" and the builder exits non-zero with a guidance
# message.
_COLUMN_MAP: Final[dict[str, dict[str, str]]] = {
    # TODO(stage-09 prereq): inspect cases/run_1/force_mom_1.csv on the
    # first AhmedML pull and populate this map with the upstream column
    # names. Loader expects:
    #   case_id (constructed from run number), slant_angle_deg,
    #   length_ratio, clearance_ratio, front_pillar_radius_m, cd
    "ahmedml": {},
    # TODO(stage-09 prereq): same procedure for WindsorML. Loader expects:
    #   case_id, yaw_deg, ride_height_m, rear_end_type, cd
    "windsorml": {},
    # TODO(stage-09 prereq): same procedure for DrivAerML. Loader expects:
    #   case_id, body_type, frontal_area_m2, body_length_m,
    #   wheel_treatment, cd, drag_area_cda
    "drivaerml": {},
    # TODO(stage-09 prereq): Harvard Dataverse listing carries different
    # metadata than the HF datasets. Loader expects:
    #   case_id, body_type, frontal_area_m2, body_length_m, cd
    "drivaernet_plus_plus": {},
}


def _emit_schema_pending(dataset: str, out: Path) -> int:
    """Refuse to emit a manifest until the upstream column map is filled in."""
    print(
        f"ERROR: dataset '{dataset}' has no verified column mapping in\n"
        f"  scripts/build_dataset_manifest.py:_COLUMN_MAP[{dataset!r}]\n"
        f"\n"
        f"Stage-08 ships the loader contract + the dataset bytes, but the\n"
        f"upstream-CSV → aero-schema mapping is a per-dataset post-process\n"
        f"that needs first-byte verification. To unblock:\n"
        f"  1. Pick any cases/run_X/force_mom_X.csv from the pulled bytes.\n"
        f"  2. Inspect its header row: `head -1 cases/run_1/force_mom_1.csv`.\n"
        f"  3. Populate _COLUMN_MAP[{dataset!r}] with `aero_field: csv_col`\n"
        f"     pairs that match the loader's *Case Pydantic model in\n"
        f"     aero/surrogates/_common/loaders/{dataset}.py.\n"
        f"  4. Re-run this script.\n"
        f"\n"
        f"Until then, `{out}` is intentionally NOT written so that the\n"
        f"aero loader fails loud with a missing-manifest error rather\n"
        f"than running predictions on stub values.",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=sorted(_COLUMN_MAP))
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    column_map = _COLUMN_MAP[args.dataset]
    if not column_map:
        return _emit_schema_pending(args.dataset, args.out)

    cases_dir = args.dataset_dir / "cases"
    if not cases_dir.is_dir():
        print(f"ERROR: cases dir missing: {cases_dir}", file=sys.stderr)
        return 2

    rows: list[dict[str, str | float]] = []
    for run_dir in sorted(cases_dir.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        run_idx = run_dir.name.removeprefix("run_")
        csvs = list(run_dir.glob("force_mom_*.csv"))
        if not csvs:
            continue
        with csvs[0].open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first = next(iter(reader), None)
            if first is None:
                continue
            row: dict[str, str | float] = {"case_id": f"{args.dataset}-{run_idx}"}
            for aero_field, csv_col in column_map.items():
                raw = first.get(csv_col)
                if raw is None:
                    print(
                        f"ERROR: {csvs[0]} missing column {csv_col!r} expected for "
                        f"aero_field {aero_field!r}",
                        file=sys.stderr,
                    )
                    return 2
                try:
                    row[aero_field] = float(raw)
                except ValueError:
                    row[aero_field] = raw
            rows.append(row)

    args.out.write_text(json.dumps(rows, indent=2))
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
