#!/usr/bin/env python3
"""Stamp angle-of-attack values into OpenFOAM dictionaries in place.

Replaces the placeholders ``{{U_X}}``, ``{{U_Y}}``, ``{{LIFT_X}}``,
``{{LIFT_Y}}``, ``{{DRAG_X}}``, ``{{DRAG_Y}}`` in the case files with the
projections for a given AoA. Used by the orchestrator-generated run.sh
to specialise the case template at run time.

The aero-research deploy target has Python 3.11 at /usr/bin/python3 and
also a project venv at /opt/aero-venv. This script only needs the stdlib
``math`` so either interpreter works.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

PLACEHOLDERS_BY_FILE: dict[str, list[str]] = {
    "0/U": ["{{U_X}}", "{{U_Y}}"],
    "system/controlDict": ["{{LIFT_X}}", "{{LIFT_Y}}", "{{DRAG_X}}", "{{DRAG_Y}}"],
}


def compute_substitutions(aoa_deg: float) -> dict[str, str]:
    aoa = math.radians(aoa_deg)
    u_x = math.cos(aoa)
    u_y = math.sin(aoa)
    # In 2D the lift vector is perpendicular to the freestream, in the
    # +y direction at AoA=0 (so lift goes up with positive AoA).
    lift_x = -math.sin(aoa)
    lift_y = math.cos(aoa)
    drag_x = math.cos(aoa)
    drag_y = math.sin(aoa)
    return {
        "{{U_X}}": f"{u_x:.10f}",
        "{{U_Y}}": f"{u_y:.10f}",
        "{{LIFT_X}}": f"{lift_x:.10f}",
        "{{LIFT_Y}}": f"{lift_y:.10f}",
        "{{DRAG_X}}": f"{drag_x:.10f}",
        "{{DRAG_Y}}": f"{drag_y:.10f}",
    }


def stamp(case_dir: Path, aoa_deg: float) -> list[Path]:
    subs = compute_substitutions(aoa_deg)
    edited: list[Path] = []
    for rel, placeholders in PLACEHOLDERS_BY_FILE.items():
        path = case_dir / rel
        if not path.exists():
            raise FileNotFoundError(f"case file missing: {path}")
        text = path.read_text()
        for placeholder in placeholders:
            text = text.replace(placeholder, subs[placeholder])
        path.write_text(text)
        edited.append(path)
    return edited


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aoa", type=float, required=True, help="Angle of attack, degrees")
    p.add_argument(
        "--case-dir",
        type=Path,
        default=Path("."),
        help="OpenFOAM case directory (default: cwd)",
    )
    args = p.parse_args()
    edited = stamp(args.case_dir, args.aoa)
    print(f"Stamped AoA={args.aoa} deg into {len(edited)} files:")
    for path in edited:
        print(f"  {path}")


if __name__ == "__main__":
    _cli()
