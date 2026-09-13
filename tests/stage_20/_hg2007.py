"""Builders for a small but VALID authored Heathcote-Gursul case.

Shared rather than duplicated, and deliberately so: since ADR-037 an ``AuthoredSource``
carries the complete fluid and solid specs, and they must agree on eight numbers plus the
whole station list. A second, hand-maintained copy of that agreement in another test file
would drift, and the first symptom of the drift would be a test asserting that the
cross-checks work while constructing a case that never exercises them.

The resolution here is deliberately coarse (``n_surface = 20``, 100 coupling windows): these
build cases for *structural* assertions, not for physics. The gated operating point lives in
``aero/vv/fsi/hg2007_flexible_foil.py``.
"""

from __future__ import annotations

from typing import Any

from aero.adapters.openfoam.flexible_foil import FlexibleFoilSpec
from aero.adapters.openfoam.geometry import hg2007_coordinates
from aero.adapters.openfoam.schemas import TeardropPlateSection
from aero.adapters.precice.calculix import CalculiXMaterial, CalculiXSolidSpec
from aero.adapters.precice.case import AuthoredSource, CoupledCaseSpec, ParticipantSpec
from aero.adapters.precice.template import HG2007_TEMPLATE, RENDERER_VERSION, template_sha256
from aero.postprocess.flapping_kinematics import FlappingKinematics

CHORD = 0.090
SPAN = 0.0025
DT = 1.0e-3
MAX_TIME = 0.1
N_SURFACE = 20

#: The two arms of the gated increment differ in exactly this number, and in nothing else.
BC_FLEXIBLE = 0.85e-3
BC_RIGID = 4.23e-3

NOSE_LENGTH = 0.0085
MAX_HALF_THICKNESS = 0.0048
JOIN_X = 0.030

SOLID_DECK_NAME = "hg2007-solid"


def section(b_over_c: float = BC_FLEXIBLE) -> TeardropPlateSection:
    return TeardropPlateSection(
        nose_length=NOSE_LENGTH,
        max_half_thickness=MAX_HALF_THICKNESS,
        join_x=JOIN_X,
        plate_half_thickness=b_over_c * CHORD / 2.0,
    )


def surface_x(sec: TeardropPlateSection, n_surface: int = N_SURFACE) -> tuple[float, ...]:
    """The FLUID's stations with the leading-edge point dropped.

    This is what makes "the solid's wetted curve IS the fluid's" an identity rather than an
    interpolation: the C-grid writer wraps ``2 * n_surface + 1`` points from the same
    generator, and the solid's node columns stand on the same x.
    """
    return tuple(
        float(v)
        for v in hg2007_coordinates(
            2 * n_surface + 1,
            chord=CHORD,
            nose_length=sec.nose_length,
            max_half_thickness=sec.max_half_thickness,
            join_x=sec.join_x,
            plate_half_thickness=sec.plate_half_thickness,
        )[1:, 0]
    )


def fluid(sec: TeardropPlateSection | None = None, **overrides: Any) -> FlexibleFoilSpec:
    sec = sec if sec is not None else section()
    return FlexibleFoilSpec(
        **{
            "name": "hg2007_flexible",
            "u_inf": 0.1,
            "rho": 1000.0,
            "nu": 1.0e-6,
            "chord": CHORD,
            "span": SPAN,
            "section": sec,
            "time_window_size": DT,
            "max_time": MAX_TIME,
            "n_surface": N_SURFACE,
            "n_normal": 20,
            "n_front": 10,
            "n_wake": 16,
            **overrides,
        }
    )


def solid(sec: TeardropPlateSection | None = None, **overrides: Any) -> CalculiXSolidSpec:
    sec = sec if sec is not None else section()
    return CalculiXSolidSpec(
        **{
            "name": SOLID_DECK_NAME,
            "surface_x": surface_x(sec),
            "chord": CHORD,
            "nose_length": sec.nose_length,
            "max_half_thickness": sec.max_half_thickness,
            "join_x": sec.join_x,
            "plate_half_thickness": sec.plate_half_thickness,
            "span": SPAN,
            "plate": CalculiXMaterial(
                name="steel", youngs_modulus=2.05e11, poisson_ratio=0.3, density=7800.0
            ),
            "nose": CalculiXMaterial(
                name="aluminium", youngs_modulus=7.0e10, poisson_ratio=0.33, density=2700.0
            ),
            "time_window_size": DT,
            "max_time": MAX_TIME,
            "kinematics": FlappingKinematics(
                stroke_amplitude=0.0175,
                frequency=0.9857142857142858,
                pitch_amplitude_deg=0.0,
                stroke_plane_deg=90.0,
            ),
            **overrides,
        }
    )


def authored_source(**overrides: Any) -> AuthoredSource:
    sec = section()
    return AuthoredSource(
        **{
            "case_dir_name": "hg2007-flexible-foil",
            "template": HG2007_TEMPLATE,
            "template_sha256": template_sha256(),
            "renderer_version": RENDERER_VERSION,
            "fluid": fluid(sec),
            "solid": solid(sec),
            **overrides,
        }
    )


def participants(**solid_overrides: Any) -> tuple[ParticipantSpec, ...]:
    return (
        ParticipantSpec(
            name="Fluid",
            workdir="fluid-openfoam",
            command="pimpleFoam",
            sif="precice-fsi.sif",
            run_as_uid=1000,
        ),
        ParticipantSpec(
            **{
                "name": "Solid",
                "workdir": "solid-calculix",
                "command": f"ccx_preCICE -i {SOLID_DECK_NAME} -precice-participant Solid",
                "sif": "calculix-precice.sif",
                "run_as_uid": 1000,
                **solid_overrides,
            }
        ),
    )


def authored_spec(**overrides: Any) -> CoupledCaseSpec:
    return CoupledCaseSpec(
        **{
            "name": "hg2007_flexible",
            "source": authored_source(),
            "participants": participants(),
            "container_of_record": "precice-fsi.sif",
            "max_time": MAX_TIME,
            "wall_clock_ceiling_s": 3600,
            "analysis_discard_s": 2.0,
            "analysis_min_cycles": 4,
            "run_as_uid": 1000,
            "gated": False,
            **overrides,
        }
    )
