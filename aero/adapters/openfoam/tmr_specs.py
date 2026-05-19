"""Typed case specs for the NASA TMR verification geometries.

The Stage-03 `CaseSpec` is airfoil-specific (its `n_surface` /
`farfield_extent_chords` fields are meaningless for a flat plate). Rather than
bloat it with optional-and-ignored fields — which would violate FAIL-LOUD,
where every field must be load-bearing — the TMR geometries get their own
strict-frozen models, joined by a `geometry` discriminator into `TMRCaseSpec`.

Each model drives `tmr_case_writer.write_tmr_case`. `naca0012_verification`
reuses the airfoil `CaseSpec` directly and is not part of this union.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Shared strict config — see .claude/rules/fail-loud-pydantic.md.
_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class FlatPlateSpec(BaseModel):
    """The NASA TMR turbulent flat plate (zero pressure gradient).

    A sharp leading edge at x=0; a no-slip plate from x=0 to `plate_length`; a
    symmetry plane on the lower wall ahead of the plate; freestream above and
    at the inlet; a pressure outlet downstream. The Reynolds number is based on
    `plate_length`.
    Reference: https://turbmodels.larc.nasa.gov/flatplate.html
    """

    model_config = _STRICT

    geometry: Literal["flat_plate"] = "flat_plate"
    name: str = Field(..., min_length=1, description="Case name.")
    reynolds: float = Field(..., gt=0, description="Reynolds number based on plate length.")
    mach: float = Field(..., gt=0, description="Reference Mach number (recorded only).")

    plate_length: float = Field(default=2.0, gt=0, description="No-slip plate length.")
    inlet_length: float = Field(
        default=0.3333333, gt=0, description="Symmetry run upstream of the leading edge."
    )
    domain_height: float = Field(default=1.0, gt=0, description="Domain height above the wall.")
    span: float = Field(default=1.0, gt=0, description="Spanwise extent (one cell, 2D).")
    end_time: int = Field(default=3000, gt=0, description="Max SIMPLE iterations.")
    turbulence_model: Literal["kOmegaSST"] = Field(default="kOmegaSST")

    n_streamwise: int = Field(default=240, gt=3, description="Cells along the plate.")
    n_inlet: int = Field(default=48, gt=3, description="Cells in the upstream symmetry run.")
    n_normal: int = Field(default=120, gt=3, description="Wall-normal cells.")
    first_cell_height: float = Field(
        default=1.0e-6, gt=0, description="Wall-normal first-cell height."
    )
    turbulence_intensity: float = Field(default=0.001, gt=0)


class Bump2DSpec(BaseModel):
    """The NASA TMR 2D bump-in-channel.

    A smooth analytic bump (`tmr_geometry.bump_height_at`) on the lower wall of
    a channel; symmetry ahead of and behind the bump on the lower wall, no-slip
    on the bump itself, freestream inlet/top, pressure outlet.
    Reference: https://turbmodels.larc.nasa.gov/bump.html
    """

    model_config = _STRICT

    geometry: Literal["bump_2d"] = "bump_2d"
    name: str = Field(..., min_length=1, description="Case name.")
    reynolds: float = Field(..., gt=0, description="Reynolds number based on `ref_length`.")
    mach: float = Field(..., gt=0, description="Reference Mach number (recorded only).")
    ref_length: float = Field(default=1.0, gt=0, description="Reynolds-number length scale.")

    bump_height: float = Field(default=0.05, gt=0, description="Peak bump height.")
    bump_length: float = Field(
        default=1.5, gt=0, description="Streamwise length of the bump wall section."
    )
    inlet_length: float = Field(default=10.0, gt=0, description="Channel run upstream of bump.")
    outlet_length: float = Field(default=10.0, gt=0, description="Channel run downstream of bump.")
    domain_height: float = Field(default=5.0, gt=0, description="Channel height.")
    span: float = Field(default=1.0, gt=0, description="Spanwise extent (one cell, 2D).")
    end_time: int = Field(default=3000, gt=0, description="Max SIMPLE iterations.")
    turbulence_model: Literal["kOmegaSST"] = Field(default="kOmegaSST")

    n_bump: int = Field(default=180, gt=3, description="Cells along the bump.")
    n_inlet: int = Field(default=96, gt=3, description="Cells upstream of the bump.")
    n_outlet: int = Field(default=120, gt=3, description="Cells downstream of the bump.")
    n_normal: int = Field(default=120, gt=3, description="Wall-normal cells.")
    first_cell_height: float = Field(
        default=2.0e-6, gt=0, description="Wall-normal first-cell height."
    )
    turbulence_intensity: float = Field(default=0.001, gt=0)


TMRCaseSpec = Annotated[FlatPlateSpec | Bump2DSpec, Field(discriminator="geometry")]
"""Discriminated union of the TMR geometry specs, keyed on `geometry`."""
