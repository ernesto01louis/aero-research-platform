"""Time-accurate (URANS) shaped airfoil — the Stage-16 certification fallback (ADR-029).

Stage 16 established that the loaded (cambered, high-L/D) optimum cannot be certified with
steady `simpleFoam` at the finest grid of the graded family: the steady segregated iteration
enters a violent two-iteration numerical limit cycle (cd sign-crossings; no meaningful
iterative uncertainty), even though the mesh is good and the coarser grids solve. The honest
path is TIME-ACCURATE: run `pimpleFoam` on the SAME graded C-grid family for baseline AND
optimum at matched numerics, time-average the force coefficients over the statistically
steady tail, and measure the sampling uncertainty (`u95_statistical`, NOBM on window means) —
the term the steady path structurally cannot provide (Hard Rule 12).

The spec embeds the steady `CaseSpec`: geometry, graded mesh, k-omega SST and BCs are
byte-identical to the steady claim regime — only time integration differs.
`OpenFOAMSolver.run` already dispatches `pimpleFoam` on `spec.transient`.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from aero.adapters.openfoam._foam_common import (
    RHO_INF,
    U_INF,
    flow_state,
    header,
    transient_fvschemes,
    transient_fvsolution,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.schemas import CaseSpec

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class TransientAirfoilSpec(BaseModel):
    """A time-accurate (pimpleFoam) run of the shaped-airfoil C-grid case (Stage 16)."""

    model_config = _STRICT

    geometry: Literal["transient_airfoil"] = "transient_airfoil"
    base: CaseSpec = Field(
        ..., description="The steady airfoil spec (geometry, graded mesh, turbulence, BCs)."
    )
    # This is a transient case — the adapter runs pimpleFoam, not simpleFoam.
    transient: Literal[True] = Field(default=True)

    # --- transient controls (convective times t* = t U / c) ---
    end_time_convective: float = Field(
        default=100.0,
        gt=0,
        description="Total run length in convective times (transient decay + averaging tail).",
    )
    initial_delta_t_convective: float = Field(
        default=5.0e-4, gt=0, description="Initial dt in convective times (Courant adjusts it)."
    )
    max_courant: float = Field(default=4.0, gt=0, description="Adjustable-timestep Courant cap.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def name(self) -> str:
        """Case name (proxied from the embedded steady spec for `CaseDir` naming)."""
        return self.base.name


def _transient_controldict(spec: TransientAirfoilSpec) -> str:
    b = spec.base
    aoa = math.radians(b.aoa_deg)
    drag_dir = f"({math.cos(aoa):.8f} {math.sin(aoa):.8f} 0)"
    lift_dir = f"({-math.sin(aoa):.8f} {math.cos(aoa):.8f} 0)"
    a_ref = b.chord * b.span
    blunt = b.trailing_edge_thickness > 0.0
    force_patches = "(airfoil airfoil_te)" if blunt else "(airfoil)"
    end_time = spec.end_time_convective * b.chord / U_INF
    return (
        header("dictionary", "controlDict")
        + f"""
application     pimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:.8g};
deltaT          {spec.initial_delta_t_convective * b.chord / U_INF:.8g};
writeControl    adjustableRunTime;
writeInterval   {end_time:.8g};
purgeWrite      2;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;
adjustTimeStep  yes;
maxCo           {spec.max_courant:.8g};

functions
{{
    forceCoeffs1
    {{
        type            forceCoeffs;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         {force_patches};
        rho             rhoInf;
        rhoInf          {RHO_INF};
        magUInf         {U_INF};
        lRef            {b.chord};
        Aref            {a_ref};
        dragDir         {drag_dir};
        liftDir         {lift_dir};
        CofR            (0.25 0 0);
        pitchAxis       (0 0 1);
    }}
}}
"""
    )


def write_transient_airfoil_case(spec: TransientAirfoilSpec, dest: Path) -> None:
    """Write the complete pimpleFoam case: the steady case's mesh/fields + transient control.

    Mesh (`_blockmeshdict`), initial/boundary fields (`_fields`), transport and turbulence
    properties are byte-identical to the steady `write_case` path — the matched-condition
    contract with the steady campaign. Only `controlDict`, `fvSchemes`, `fvSolution` differ
    (time-accurate PIMPLE; Euler + second-order space, the Stage-11 transient path).
    """
    from aero.adapters.openfoam.case_writer import _blockmeshdict, _fields

    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)
    b = spec.base
    nu = flow_state(
        reynolds=b.reynolds, ref_length=b.chord, turbulence_intensity=b.turbulence_intensity
    )["nu"]
    (system / "blockMeshDict").write_text(_blockmeshdict(b), encoding="utf-8")
    (system / "controlDict").write_text(_transient_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(
        transient_fvschemes(turbulence_model=b.turbulence_model), encoding="utf-8"
    )
    (system / "fvSolution").write_text(
        transient_fvsolution(turbulence_model=b.turbulence_model), encoding="utf-8"
    )
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(b.turbulence_model), encoding="utf-8"
    )
    for name, text in _fields(b).items():
        (zero / name).write_text(text, encoding="utf-8")
