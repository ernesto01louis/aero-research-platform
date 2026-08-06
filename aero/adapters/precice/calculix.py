"""Author the CalculiX solid participant — and read back every claim the deck makes.

Stage 20's solid is a chordwise-flexible foil: a rigid aluminium teardrop leading edge
driven in pure plunge, with a thin steel plate cantilevered off it at ``join_x``. The
pitch is **not** prescribed; it arises from the plate's deformation, which is the whole
point of the Heathcote-Gursul experiment (``reference.md``). Prescribing a pitch schedule
would model a different experiment.

Every writer here ships with a re-reader, because an authored deck has no upstream pin to
be verified against (ADR-037). What makes that worth the code is the failure mode: a
CalculiX deck that is *wrong* almost never crashes. It converges, exits 0, and produces a
plausible-looking deflection. Three such failures are pinned here, all found by reading
upstream's proven ``perpendicular-flap/solid-calculix`` bytes rather than the docs:

* **A missing ``*CLOAD``.** The calculix-adapter injects fluid forces by OVERWRITING a
  ``*CLOAD`` block the deck must already declare as zeros on the interface node set. Omit
  it and the solid runs force-free: the coupling converges (trivially), the plate never
  deflects, and the reported pitch amplitude is zero rather than absent.
* **A too-small ``*STEP, INC``.** CalculiX's default is 100 increments. At tens of
  thousands of coupled windows ccx finishes its step, writes its ``.frd`` and exits
  **zero** — so the supervisor records ``all-exited``, the K2 gate PASSES, and the failure
  only surfaces much later as a short record. ``INC`` is therefore COMPUTED from
  ``max_time / dt``, never copied.
* **A slab whose z-extent is not the fluid's span.** preCICE ``Force`` is an absolute
  force in newtons. Upstream's flap gets away with a ``z in {0,1}`` slab because its fluid
  span is also 1. This foil's span is 2.5 mm, so a 1 m slab is 400x too stiff for the
  force it receives: ``checkMesh`` is happy, the coupling converges, and the pitch
  amplitude comes out at 0.01 degrees. One ``span`` feeds both writers and
  :func:`assert_calculix_deck` re-derives it from the written nodes.

Two modelling facts that are easy to get wrong and expensive to get wrong:

* ``*BOUNDARY Nall, 3`` (upstream's 2-D idiom, a one-element-thick 3-D slab of ``C3D8I``)
  is plane **strain**, not plane stress. The effective modulus is ``E/(1-nu^2)``, so a
  naive ``E b^3/12`` hand-check of the plate stiffness is ~10 % off.
* ``C3D8I``, not ``C3D8``: the incompatible-modes hex is what cures shear locking in a
  thin bending member, which is exactly this plate's regime, and it is what the
  calculix-adapter is actually exercised against.

stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.adapters.openfoam.geometry import hg2007_half_thickness
from aero.postprocess.flapping_kinematics import FlappingKinematics

__all__ = [
    "INTERFACE_NSET",
    "INTERFACE_PATCH",
    "NOSE_NSET",
    "AmplitudeTable",
    "CalculiXAdapterConfig",
    "CalculiXDeck",
    "CalculiXDeckError",
    "CalculiXMaterial",
    "CalculiXSolidSpec",
    "assert_adapter_config",
    "assert_calculix_deck",
    "read_adapter_config",
    "read_calculix_deck",
    "watch_points",
    "write_adapter_config",
    "write_calculix_deck",
]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

#: The interface node set. The calculix-adapter maps its ``patch:`` name to an ``*NSET``
#: by prefixing ``N`` (``patch: surface`` -> ``*NSET,NSET=Nsurface``), so this constant and
#: :data:`INTERFACE_PATCH` are two halves of one contract and are checked against each other.
INTERFACE_PATCH = "surface"
INTERFACE_NSET = "N" + INTERFACE_PATCH

#: The prescribed (kinematically rigid) teardrop node set.
NOSE_NSET = "Nnose"

_ALL_NSET = "Nall"
_PLATE_ELSET = "Eplate"
_NOSE_ELSET = "Enose"
_AMPLITUDE_NAME = "PLUNGE"
_ELEMENT_TYPE = "C3D8I"

#: ``INC`` is sized at this multiple of the number of coupled windows. An implicit
#: coupling re-does a window many times, and ccx counts every attempt, so the margin is
#: over the ITERATION count rather than the window count.
_INC_MARGIN = 10

#: Extra amplitude rows written past ``max_time`` so the final increment can never query
#: beyond the table (the ADR-024 ``tabulated6DoFMotion`` precedent).
_AMPLITUDE_MARGIN_ROWS = 4

_MAIN_DECK_SUFFIX = ".inp"
_MESH_FILE = "all.msh"
_INTERFACE_FILE = "interface.nam"
_NOSE_FILE = "nose.nam"
_AMPLITUDE_FILE = "plunge.amp"

#: CalculiX reads every numeric field of a data line as ``(1:20)`` under an ``f20.0``
#: format, so a field wider than 20 characters is TRUNCATED mid-number and the card is
#: rejected. Measured, not assumed: a first spike of this deck written at ``%.16e``
#: (22 characters) made ccx 2.20 fail every numeric card it read -- *NODE, *ELASTIC,
#: *DENSITY, *AMPLITUDE and *DYNAMIC alike -- with "*ERROR reading ...". At ``%.13e``
#: (19 characters, 14 significant digits) the same deck reads and solves.
_DECK_FIELD_WIDTH = 20
_FLOAT_FORMAT = "{:.13e}"

#: How far a coordinate read back out of the deck may sit from the geometry function.
#: The format carries 14 significant digits, so a 0.09 m chord is written to ~1e-15 m —
#: four orders inside this tolerance, and eleven orders below the 76.5 um plate thickness.
_GEOMETRY_TOLERANCE = 1.0e-12


def _num(value: float) -> str:
    """Format a real for a CalculiX data line, refusing anything the reader would truncate."""
    text = _FLOAT_FORMAT.format(float(value))
    if len(text) > _DECK_FIELD_WIDTH:
        raise CalculiXDeckError(
            f"{text!r} is {len(text)} characters; CalculiX reads numeric fields as (1:20) "
            "and would truncate it mid-number"
        )
    return text


def _round_trips(value: float) -> bool:
    """Whether a real survives the deck format exactly.

    Full double precision needs 17 significant digits, which does not fit in 20 characters
    once a sign and a negative exponent are present -- so a deck simply cannot carry an
    arbitrary double. Values the CAMPAIGN CHOOSES (the time-window size, the end time, the
    span) are therefore required to be exactly representable, which keeps the assertions on
    them exact and costs nothing: those numbers are picked, and picking a clean one is free.
    Values the geometry DERIVES (node coordinates, amplitude rows) cannot be chosen, so they
    are asserted to a tolerance far below anything physically meaningful instead.
    """
    return float(_FLOAT_FORMAT.format(float(value))) == float(value)


class CalculiXDeckError(RuntimeError):
    """A CalculiX deck could not be written, read back, or does not match its spec."""


class CalculiXMaterial(BaseModel):
    """A linear-elastic material. ``density`` is load-bearing: this is a DYNAMIC step."""

    model_config = _STRICT

    name: str = Field(..., min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    youngs_modulus: float = Field(..., gt=0.0, description="E [Pa].")
    poisson_ratio: float = Field(..., gt=0.0, lt=0.5, description="nu [-].")
    density: float = Field(..., gt=0.0, description="rho [kg/m^3].")

    @property
    def plane_strain_modulus(self) -> float:
        """``E / (1 - nu^2)`` — the modulus that governs a ``*BOUNDARY Nall, 3`` slab."""
        return self.youngs_modulus / (1.0 - self.poisson_ratio**2)


class CalculiXSolidSpec(BaseModel):
    """Everything the solid deck is rendered from. Frozen, so a deck has one preimage."""

    model_config = _STRICT

    name: str = Field(..., min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    participant: str = Field(default="Solid", min_length=1)
    mesh_name: str = Field(
        default="Solid-Mesh",
        min_length=1,
        description="Must equal the mesh the rendered precice-config.xml declares.",
    )

    surface_x: tuple[float, ...] = Field(
        ...,
        min_length=3,
        description=(
            "The FLUID's surface x-stations, leading-edge point EXCLUDED. Sharing the "
            "stations is what makes 'the solid's wetted curve is the fluid's' an identity "
            "rather than an interpolation: both call hg2007_half_thickness on the same x."
        ),
    )
    chord: float = Field(..., gt=0.0)
    nose_length: float = Field(..., gt=0.0, description="Elliptical nose length [m].")
    max_half_thickness: float = Field(..., gt=0.0)
    join_x: float = Field(
        ...,
        gt=0.0,
        description=(
            "Where the teardrop reaches plate thickness AND the structural root sits — the "
            "plate is clamped between the two machined LE halves there (reference.md). "
            "Every node at or before it is prescribed."
        ),
    )
    plate_half_thickness: float = Field(..., gt=0.0)
    span: float = Field(
        ...,
        gt=0.0,
        description="Slab z-extent [m]. MUST equal the fluid's span; see the module docstring.",
    )
    n_through_thickness: int = Field(
        default=4,
        ge=2,
        multiple_of=2,
        description=(
            "Elements across the section's thickness. >=2 for a bending member, and EVEN so "
            "a mid-surface node column exists: `_grid` lays nodes at "
            "`eta = linspace(-1, 1, n+1)`, which contains 0.0 only for even `n`. Both "
            "watch-points sit on the mid-surface, and preCICE SNAPS a watch-point to the "
            "nearest mesh vertex without saying so -- at an odd count D0 would silently "
            "become the angle of a surface fibre rather than of the mid-surface, offset by "
            "the plate half-thickness times the local rotation."
        ),
    )

    plate: CalculiXMaterial
    nose: CalculiXMaterial

    time_window_size: float = Field(
        ..., gt=0.0, description="Solid dt [s]; must equal the coupling time-window size."
    )
    max_time: float = Field(..., gt=0.0)
    kinematics: FlappingKinematics

    @model_validator(mode="after")
    def _the_kinematics_are_a_pure_plunge(self) -> CalculiXSolidSpec:
        """Refuse anything but pure plunge of the leading edge.

        The pitch ARISES from the flexibility (reference.md, and the operator decision of
        record). A non-zero ``pitch_amplitude_deg`` here would prescribe it, which models a
        different experiment while producing entirely plausible numbers — so it is refused
        at construction rather than caught by a reviewer.
        """
        if self.kinematics.pitch_amplitude_deg != 0.0:
            raise ValueError(
                "pitch_amplitude_deg must be 0: the plunge is prescribed and the pitch "
                f"arises from the plate's flexibility, but got "
                f"{self.kinematics.pitch_amplitude_deg}"
            )
        if self.kinematics.stroke_plane_deg != 90.0:
            raise ValueError(
                "stroke_plane_deg must be 90 (pure heave, +y): at the default 0 the stroke "
                "is horizontal and evaluate()['vy'] is identically zero, so the deck would "
                f"prescribe no motion at all; got {self.kinematics.stroke_plane_deg}"
            )
        return self

    @model_validator(mode="after")
    def _the_section_is_well_formed(self) -> CalculiXSolidSpec:
        if not 0.0 < self.nose_length < self.join_x < self.chord:
            raise ValueError(
                f"need 0 < nose_length ({self.nose_length}) < join_x ({self.join_x}) "
                f"< chord ({self.chord})"
            )
        if not 0.0 < self.plate_half_thickness < self.max_half_thickness:
            raise ValueError(
                f"need 0 < plate_half_thickness ({self.plate_half_thickness}) < "
                f"max_half_thickness ({self.max_half_thickness})"
            )
        x = np.asarray(self.surface_x, dtype=np.float64)
        if x[0] <= 0.0:
            raise ValueError(
                "surface_x must EXCLUDE the leading-edge point: the section's half-thickness "
                "is zero at x=0, so a station there collapses the whole through-thickness "
                f"node column and every element in it has zero volume. Got x[0]={x[0]!r}"
            )
        if np.any(np.diff(x) <= 0.0):
            raise ValueError("surface_x must be strictly increasing")
        if abs(x[-1] - self.chord) > 1e-12 * self.chord:
            raise ValueError(f"surface_x must end at the chord ({self.chord}), got {x[-1]!r}")
        if x[0] >= self.join_x:
            raise ValueError(
                f"surface_x[0] ({x[0]}) is at or past join_x ({self.join_x}) — the deck would "
                "have no prescribed teardrop region at all"
            )
        return self

    @model_validator(mode="after")
    def _the_chosen_numbers_survive_the_deck_format(self) -> CalculiXSolidSpec:
        """A CalculiX deck cannot carry an arbitrary double; the chosen values must fit.

        See :func:`_round_trips`. Refusing here means ``assert_calculix_deck`` can compare
        the solid's dt against the coupling time-window size EXACTLY -- which is the clause
        that matters, since a solid stepping at a different dt than the coupling still
        converges and still produces numbers.
        """
        unrepresentable = {
            name: value
            for name, value in (
                ("time_window_size", self.time_window_size),
                ("max_time", self.max_time),
                ("span", self.span),
            )
            if not _round_trips(value)
        }
        if unrepresentable:
            raise ValueError(
                f"these values do not survive the deck's {_FLOAT_FORMAT.format(1.0)}-style "
                f"field exactly: {unrepresentable}. CalculiX truncates numeric fields at "
                f"{_DECK_FIELD_WIDTH} characters, so pick round numbers for the values the "
                "campaign chooses (the geometry's derived coordinates are asserted to a "
                "tolerance instead, because they cannot be chosen)."
            )
        return self

    @property
    def n_windows(self) -> int:
        """Coupled time windows in the step (rounded up — a partial window still runs)."""
        return math.ceil(self.max_time / self.time_window_size)

    @property
    def max_increments(self) -> int:
        """``*STEP, INC``. COMPUTED, never copied — see the module docstring."""
        return _INC_MARGIN * self.n_windows

    def half_thickness(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """The section half-thickness — the SAME function the fluid's C-grid writer calls."""
        return hg2007_half_thickness(
            x,
            chord=self.chord,
            nose_length=self.nose_length,
            max_half_thickness=self.max_half_thickness,
            join_x=self.join_x,
            plate_half_thickness=self.plate_half_thickness,
        )


class AmplitudeTable(BaseModel):
    """A ``*AMPLITUDE`` table and how far it strays from the analytic motion."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    n_rows: int = Field(..., ge=2)
    t: tuple[float, ...] = Field(..., min_length=2)
    value: tuple[float, ...] = Field(..., min_length=2)

    @model_validator(mode="after")
    def _same_length(self) -> AmplitudeTable:
        if len(self.t) != len(self.value) or len(self.t) != self.n_rows:
            raise ValueError("amplitude table columns disagree in length")
        return self


class CalculiXDeck(BaseModel):
    """What a written deck actually SAYS, recovered by re-reading it from disk."""

    model_config = _STRICT

    path: Path
    element_type: str
    n_nodes: int = Field(..., ge=8)
    n_elements: int = Field(..., ge=1)
    z_levels: tuple[float, ...] = Field(..., min_length=2)
    nsets: dict[str, int] = Field(..., description="nset name -> node count")
    elsets: dict[str, int]
    materials: dict[str, tuple[float, float, float]] = Field(
        ..., description="name -> (E, nu, rho)"
    )
    section_materials: dict[str, str] = Field(..., description="elset -> material")
    nlgeom: bool
    max_increments: int = Field(..., ge=1)
    dynamic_alpha: float
    dynamic_direct: bool
    dt: float = Field(..., gt=0.0)
    total_time: float = Field(..., gt=0.0)
    cload: tuple[tuple[str, int, float], ...] = Field(..., description="(nset, dof, magnitude)")
    boundaries: tuple[tuple[str, int, int, float | None, str | None], ...] = Field(
        ..., description="(nset, first_dof, last_dof, magnitude, amplitude name)"
    )
    amplitude: AmplitudeTable
    wetted_upper: tuple[tuple[float, float], ...] = Field(
        ..., description="(x, y) of the upper wetted curve, read back from the written nodes."
    )

    @property
    def span(self) -> float:
        """The slab's z-extent, re-derived from the written node coordinates."""
        return max(self.z_levels) - min(self.z_levels)


# --------------------------------------------------------------------------------------
# Mesh construction
# --------------------------------------------------------------------------------------


def _grid(spec: CalculiXSolidSpec) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Node coordinates and the per-station half-thickness.

    The block is structured ``(NX+1) x (NY+1) x 2``: stations along the chord, a uniform
    through-thickness distribution in ``eta in [-1, 1]`` scaled by the LOCAL half-thickness,
    and one element across the span. The section is symmetric, so ``y = eta * t(x)`` walks
    the real wetted curve on both sides by construction.
    """
    x = np.asarray(spec.surface_x, dtype=np.float64)
    t = spec.half_thickness(x)
    eta = np.linspace(-1.0, 1.0, spec.n_through_thickness + 1)
    # (i, j, k) -> row-major with k fastest, matching _node_id below.
    xx = np.repeat(np.repeat(x[:, None], eta.size, axis=1)[:, :, None], 2, axis=2)
    yy = np.repeat((t[:, None] * eta[None, :])[:, :, None], 2, axis=2)
    zz = np.zeros_like(xx)
    zz[:, :, 1] = spec.span
    return np.stack([xx, yy, zz], axis=-1), t


def _node_id(i: int, j: int, k: int, *, n_eta: int) -> int:
    """1-based node id with ``k`` fastest, then ``j``, then ``i``."""
    return 1 + (i * n_eta + j) * 2 + k


def _connectivity(spec: CalculiXSolidSpec) -> list[tuple[int, tuple[int, ...]]]:
    """``C3D8`` connectivity in the canonical right-handed order.

    Local axes: ``xi`` along +x (station), ``eta`` along +y (thickness), ``zeta`` along +z
    (span). Nodes 1-4 are the ``k=0`` face traversed counter-clockwise in x-y, nodes 5-8 the
    ``k=1`` face above them — so ``cross(xi, eta) . zeta > 0`` and every Jacobian is
    positive. (Upstream orders its own hexes differently but equivalently; what matters is
    the handedness, which a written-deck test re-derives from the coordinates.)
    """
    n_eta = spec.n_through_thickness + 1
    elements: list[tuple[int, tuple[int, ...]]] = []
    eid = 0
    for i in range(len(spec.surface_x) - 1):
        for j in range(spec.n_through_thickness):
            eid += 1
            elements.append(
                (
                    eid,
                    (
                        _node_id(i, j, 0, n_eta=n_eta),
                        _node_id(i + 1, j, 0, n_eta=n_eta),
                        _node_id(i + 1, j + 1, 0, n_eta=n_eta),
                        _node_id(i, j + 1, 0, n_eta=n_eta),
                        _node_id(i, j, 1, n_eta=n_eta),
                        _node_id(i + 1, j, 1, n_eta=n_eta),
                        _node_id(i + 1, j + 1, 1, n_eta=n_eta),
                        _node_id(i, j + 1, 1, n_eta=n_eta),
                    ),
                )
            )
    return elements


def _interface_nodes(spec: CalculiXSolidSpec) -> list[int]:
    """The wetted boundary: both faces, the blunt trailing edge, and the truncated nose cap.

    The nose cap (``i = 0``) is included even though it is a truncation artifact rather
    than a real wetted face: the fluid's few leading-edge sliver faces have no other solid
    vertices near them, and a conservative RBF mapping must have somewhere local to put
    their load. Those nodes are prescribed, so including them changes nothing mechanically
    and only improves the mapping's locality.
    """
    n_eta = spec.n_through_thickness + 1
    n_x = len(spec.surface_x)
    ids: set[int] = set()
    for k in (0, 1):
        for i in range(n_x):
            ids.add(_node_id(i, 0, k, n_eta=n_eta))  # lower surface
            ids.add(_node_id(i, spec.n_through_thickness, k, n_eta=n_eta))  # upper surface
        for j in range(n_eta):
            ids.add(_node_id(0, j, k, n_eta=n_eta))  # nose cap
            ids.add(_node_id(n_x - 1, j, k, n_eta=n_eta))  # blunt trailing edge
    return sorted(ids)


def watch_points(spec: CalculiXSolidSpec) -> tuple[tuple[float, float], tuple[float, float]]:
    """The ``(nose, trailing-edge)`` mid-surface points the rendered configuration watches.

    Lives here, beside :func:`_interface_nodes`, rather than in the renderer: a watch-point
    that is not a vertex of ``Solid-Mesh`` is **snapped to the nearest one by preCICE, with
    no diagnostic**, so the coordinate and the node set have to be derived from one place or
    D0 is measured somewhere other than where it was declared. Both points are asserted to
    be interface vertices before they are returned.

    Both sit at ``eta = 0`` -- the mid-surface -- which exists as a node column only because
    ``n_through_thickness`` is required to be even. The nose point samples the PRESCRIBED
    leading-edge plunge (so the kinematics are checkable against the record rather than
    assumed); the TE point carries the D0 deflection.
    """
    nodes, _ = _grid(spec)
    n_eta = spec.n_through_thickness + 1
    mid = spec.n_through_thickness // 2
    last = len(spec.surface_x) - 1
    nose = (float(nodes[0, mid, 0, 0]), float(nodes[0, mid, 0, 1]))
    trailing_edge = (float(nodes[last, mid, 0, 0]), float(nodes[last, mid, 0, 1]))

    interface = set(_interface_nodes(spec))
    missing = [
        f"{label} {point}"
        for label, point, i in (("nose", nose, 0), ("trailing-edge", trailing_edge, last))
        if _node_id(i, mid, 0, n_eta=n_eta) not in interface
    ]
    if missing:
        raise CalculiXDeckError(
            f"watch-point(s) {', '.join(missing)} are not vertices of the interface node set, "
            "so preCICE would snap them to a different node without reporting it"
        )
    return nose, trailing_edge


def _nose_nodes(spec: CalculiXSolidSpec) -> list[int]:
    """Every node at or before ``join_x`` — the fully prescribed teardrop."""
    n_eta = spec.n_through_thickness + 1
    ids: list[int] = []
    for i, x in enumerate(spec.surface_x):
        if x > spec.join_x + 1e-12:
            continue
        for j in range(n_eta):
            ids.extend((_node_id(i, j, 0, n_eta=n_eta), _node_id(i, j, 1, n_eta=n_eta)))
    return sorted(ids)


def _element_sets(spec: CalculiXSolidSpec) -> tuple[list[int], list[int]]:
    """Split elements into nose and plate.

    An element is a NOSE element only if every one of its nodes is prescribed; anything
    with a free node deforms, and everything that deforms is plate (steel). The single
    column straddling ``join_x`` therefore counts as plate, which is correct — the plate
    begins there.
    """
    prescribed = set(_nose_nodes(spec))
    nose: list[int] = []
    plate: list[int] = []
    for eid, nodes in _connectivity(spec):
        (nose if prescribed.issuperset(nodes) else plate).append(eid)
    return nose, plate


def _amplitude_table(spec: CalculiXSolidSpec) -> AmplitudeTable:
    """Sample the prescribed plunge at EXACTLY the coupling time-window size.

    Two reasons for that sampling rate rather than a chosen one. CalculiX interpolates the
    table linearly, and a ``*DYNAMIC, DIRECT`` step evaluates boundary conditions at the
    end of each increment — i.e. at multiples of ``dt`` — so rows placed there are hit
    exactly and the interpolation error at the evaluation points is zero. And where it is
    not zero (a coupling iteration landing mid-window), the residual error is bounded by
    the second derivative over one window, which a written-deck test measures rather than
    assumes.
    """
    n_rows = spec.n_windows + 1 + _AMPLITUDE_MARGIN_ROWS
    t = np.arange(n_rows, dtype=np.float64) * spec.time_window_size
    y = spec.kinematics.evaluate(t)["y"]
    return AmplitudeTable(
        name=_AMPLITUDE_NAME,
        n_rows=n_rows,
        t=tuple(float(v) for v in t),
        value=tuple(float(v) for v in y),
    )


# --------------------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------------------


def _format_nset(name: str, ids: Sequence[int]) -> str:
    lines = [f"*NSET, NSET={name}"]
    for start in range(0, len(ids), 8):
        lines.append(", ".join(str(i) for i in ids[start : start + 8]) + ",")
    return "\n".join(lines) + "\n"


def _format_elset(name: str, ids: Sequence[int]) -> str:
    lines = [f"*ELSET, ELSET={name}"]
    for start in range(0, len(ids), 8):
        lines.append(", ".join(str(i) for i in ids[start : start + 8]) + ",")
    return "\n".join(lines) + "\n"


def _mesh_text(spec: CalculiXSolidSpec) -> str:
    coords, _ = _grid(spec)
    n_eta = spec.n_through_thickness + 1
    lines = [f"*NODE, NSET={_ALL_NSET}"]
    for i in range(coords.shape[0]):
        for j in range(n_eta):
            for k in (0, 1):
                x, y, z = coords[i, j, k]
                lines.append(f"{_node_id(i, j, k, n_eta=n_eta)}, {_num(x)}, {_num(y)}, {_num(z)}")
    lines.append(f"*ELEMENT, TYPE={_ELEMENT_TYPE}, ELSET=Eall")
    for eid, nodes in _connectivity(spec):
        lines.append(f"{eid}, " + ", ".join(str(n) for n in nodes))
    nose, plate = _element_sets(spec)
    text = "\n".join(lines) + "\n"
    if nose:
        text += _format_elset(_NOSE_ELSET, nose)
    text += _format_elset(_PLATE_ELSET, plate)
    return text


def _amplitude_text(table: AmplitudeTable) -> str:
    lines = [f"*AMPLITUDE, NAME={table.name}"]
    lines.extend(f"{_num(t)}, {_num(v)}" for t, v in zip(table.t, table.value, strict=True))
    return "\n".join(lines) + "\n"


def _material_text(material: CalculiXMaterial) -> str:
    return (
        f"*MATERIAL, NAME={material.name}\n"
        f"*ELASTIC\n"
        f"{_num(material.youngs_modulus)}, {_num(material.poisson_ratio)}\n"
        f"*DENSITY\n"
        f"{_num(material.density)}\n"
    )


def _main_deck_text(spec: CalculiXSolidSpec) -> str:
    nose_elements, _ = _element_sets(spec)
    sections = [f"*SOLID SECTION, ELSET={_PLATE_ELSET}, MATERIAL={spec.plate.name}\n"]
    if nose_elements:
        sections.append(f"*SOLID SECTION, ELSET={_NOSE_ELSET}, MATERIAL={spec.nose.name}\n")
    return (
        f"** Stage-20 authored solid participant: {spec.name}\n"
        "** Chordwise-flexible plunging foil (Heathcote & Gursul 2007).\n"
        "** Written by aero.adapters.precice.calculix; every claim below is re-read and\n"
        "** asserted by assert_calculix_deck before the case runs.\n"
        f"*INCLUDE, INPUT={_MESH_FILE}\n"
        f"*INCLUDE, INPUT={_INTERFACE_FILE}\n"
        f"*INCLUDE, INPUT={_NOSE_FILE}\n"
        f"*INCLUDE, INPUT={_AMPLITUDE_FILE}\n"
        f"{_material_text(spec.plate)}"
        f"{_material_text(spec.nose)}"
        f"{''.join(sections)}"
        # INC is computed from max_time/dt: at the default 100 ccx would finish its step
        # mid-run, write its .frd and exit ZERO, and the status gate would pass.
        f"*STEP, NLGEOM, INC={spec.max_increments}\n"
        "*DYNAMIC, ALPHA=0.0, DIRECT\n"
        f"{_num(spec.time_window_size)}, {_num(spec.max_time)}\n"
        "** Plane strain: dof 3 suppressed on the one-element-thick slab (upstream's 2-D\n"
        "** idiom). The effective modulus is therefore E/(1-nu^2).\n"
        "*BOUNDARY\n"
        f"{_ALL_NSET}, 3\n"
        "** The teardrop is kinematically rigid: no chordwise motion, plunge prescribed.\n"
        "*BOUNDARY\n"
        f"{NOSE_NSET}, 1, 1\n"
        f"*BOUNDARY, AMPLITUDE={_AMPLITUDE_NAME}\n"
        f"{NOSE_NSET}, 2, 2, 1.0\n"
        "** Declared as zeros; the calculix-adapter OVERWRITES this block with the fluid\n"
        "** forces. Without it the run is silently force-free.\n"
        "*CLOAD\n"
        f"{INTERFACE_NSET}, 1, 0.0\n"
        f"{INTERFACE_NSET}, 2, 0.0\n"
        f"{INTERFACE_NSET}, 3, 0.0\n"
        "*NODE FILE\n"
        "U\n"
        "*EL FILE\n"
        "S, E\n"
        "** Reaction forces at the prescribed nodes: the solid-side half of the D10 power\n"
        "** closure check (with ALPHA=0 and no damping the identity is exact).\n"
        f"*NODE PRINT, NSET={NOSE_NSET}, TOTALS=ONLY\n"
        "RF\n"
        "*END STEP\n"
    )


def write_calculix_deck(spec: CalculiXSolidSpec, *, dest_dir: Path) -> CalculiXDeck:
    """Write the solid deck, then RE-READ it and assert it against `spec`.

    Returns the re-read deck, so a caller records what the file says rather than what the
    writer meant to say.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / _MESH_FILE).write_text(_mesh_text(spec), encoding="utf-8")
    (dest_dir / _INTERFACE_FILE).write_text(
        _format_nset(INTERFACE_NSET, _interface_nodes(spec)), encoding="utf-8"
    )
    (dest_dir / _NOSE_FILE).write_text(_format_nset(NOSE_NSET, _nose_nodes(spec)), encoding="utf-8")
    (dest_dir / _AMPLITUDE_FILE).write_text(
        _amplitude_text(_amplitude_table(spec)), encoding="utf-8"
    )
    path = dest_dir / (spec.name + _MAIN_DECK_SUFFIX)
    path.write_text(_main_deck_text(spec), encoding="utf-8")

    deck = read_calculix_deck(path)
    assert_calculix_deck(deck, spec)
    return deck


# --------------------------------------------------------------------------------------
# Reading back
# --------------------------------------------------------------------------------------

_KEYWORD_RE = re.compile(r"^\*([A-Z0-9 ]+)(?:,(.*))?$", re.IGNORECASE)


def _keyword_parameters(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    parameters: dict[str, str] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        parameters[key.strip().upper()] = value.strip()
    return parameters


def _expand(path: Path, *, seen: set[Path] | None = None) -> list[tuple[Path, int, str]]:
    """Flatten a deck and its ``*INCLUDE``s into ``(file, lineno, line)``, comments dropped."""
    seen = set() if seen is None else seen
    resolved = path.resolve()
    if resolved in seen:
        raise CalculiXDeckError(f"{path}: circular *INCLUDE")
    seen.add(resolved)
    if not path.is_file():
        raise CalculiXDeckError(f"{path}: deck file not found")
    out: list[tuple[Path, int, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        match = _KEYWORD_RE.match(line)
        if match and match.group(1).strip().upper() == "INCLUDE":
            target = _keyword_parameters(match.group(2)).get("INPUT")
            if not target:
                raise CalculiXDeckError(f"{path}:{lineno}: *INCLUDE without INPUT=")
            out.extend(_expand(path.parent / target, seen=seen))
            continue
        out.append((path, lineno, line))
    return out


def _floats(line: str) -> list[float]:
    try:
        return [float(v) for v in line.split(",") if v.strip()]
    except ValueError as exc:
        raise CalculiXDeckError(f"expected numbers, got {line!r}") from exc


def read_calculix_deck(path: Path) -> CalculiXDeck:
    """Parse a written deck (following ``*INCLUDE``) into what it actually claims."""
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: dict[int, tuple[int, ...]] = {}
    element_type = ""
    nsets: dict[str, list[int]] = {}
    elsets: dict[str, list[int]] = {}
    materials: dict[str, list[float]] = {}
    section_materials: dict[str, str] = {}
    boundaries: list[tuple[str, int, int, float | None, str | None]] = []
    cload: list[tuple[str, int, float]] = []
    amplitude_name = ""
    amplitude_rows: list[tuple[float, float]] = []
    nlgeom = False
    max_increments = 0
    dynamic_alpha = math.nan
    dynamic_direct = False
    dt = 0.0
    total_time = 0.0

    keyword = ""
    parameters: dict[str, str] = {}
    current_material = ""
    dynamic_data_seen = False

    for _source, _lineno, line in _expand(path):
        match = _KEYWORD_RE.match(line)
        if match:
            keyword = match.group(1).strip().upper()
            parameters = _keyword_parameters(match.group(2))
            if keyword == "NODE":
                nsets.setdefault(parameters.get("NSET", ""), [])
            elif keyword == "ELEMENT":
                element_type = parameters.get("TYPE", "")
            elif keyword == "NSET":
                nsets.setdefault(parameters.get("NSET", ""), [])
            elif keyword == "ELSET":
                elsets.setdefault(parameters.get("ELSET", ""), [])
            elif keyword == "MATERIAL":
                current_material = parameters.get("NAME", "")
                materials.setdefault(current_material, [])
            elif keyword == "SOLID SECTION":
                section_materials[parameters.get("ELSET", "")] = parameters.get("MATERIAL", "")
            elif keyword == "AMPLITUDE":
                amplitude_name = parameters.get("NAME", "")
            elif keyword == "STEP":
                nlgeom = "NLGEOM" in parameters
                max_increments = int(parameters.get("INC", "100"))
            elif keyword == "DYNAMIC":
                dynamic_alpha = float(parameters.get("ALPHA", "nan"))
                dynamic_direct = "DIRECT" in parameters
                dynamic_data_seen = False
            continue

        if keyword == "NODE":
            fields = [v.strip() for v in line.split(",") if v.strip()]
            nid = int(fields[0])
            nodes[nid] = (float(fields[1]), float(fields[2]), float(fields[3]))
            nsets.setdefault(parameters.get("NSET", ""), []).append(nid)
        elif keyword == "ELEMENT":
            ids = [int(v) for v in line.split(",") if v.strip()]
            elements[ids[0]] = tuple(ids[1:])
        elif keyword == "NSET":
            nsets[parameters.get("NSET", "")].extend(int(v) for v in line.split(",") if v.strip())
        elif keyword == "ELSET":
            elsets[parameters.get("ELSET", "")].extend(int(v) for v in line.split(",") if v.strip())
        elif keyword in {"ELASTIC", "DENSITY"}:
            materials[current_material].extend(_floats(line))
        elif keyword == "AMPLITUDE":
            reals = _floats(line)
            amplitude_rows.extend((reals[i], reals[i + 1]) for i in range(0, len(reals) - 1, 2))
        elif keyword == "DYNAMIC":
            if not dynamic_data_seen:
                reals = _floats(line)
                dt, total_time = reals[0], reals[1]
                dynamic_data_seen = True
        elif keyword == "BOUNDARY":
            fields = [v.strip() for v in line.split(",") if v.strip()]
            first = int(fields[1])
            last = int(fields[2]) if len(fields) > 2 else first
            magnitude = float(fields[3]) if len(fields) > 3 else None
            boundaries.append((fields[0], first, last, magnitude, parameters.get("AMPLITUDE")))
        elif keyword == "CLOAD":
            fields = [v.strip() for v in line.split(",") if v.strip()]
            cload.append((fields[0], int(fields[1]), float(fields[2])))

    if not nodes or not elements:
        raise CalculiXDeckError(f"{path}: deck declares no nodes or no elements")
    if not amplitude_rows:
        raise CalculiXDeckError(f"{path}: deck declares no *AMPLITUDE table")

    missing = {name: sorted(set(ids) - set(nodes)) for name, ids in nsets.items()}
    dangling = {name: ids for name, ids in missing.items() if ids}
    if dangling:
        raise CalculiXDeckError(f"{path}: node set(s) name nodes that do not exist: {dangling}")

    upper = _wetted_upper(nodes)
    return CalculiXDeck(
        path=path,
        element_type=element_type,
        n_nodes=len(nodes),
        n_elements=len(elements),
        z_levels=tuple(sorted({round(c[2], 15) for c in nodes.values()})),
        nsets={name: len(set(ids)) for name, ids in nsets.items() if name},
        elsets={name: len(set(ids)) for name, ids in elsets.items() if name},
        materials={
            name: (values[0], values[1], values[2])
            for name, values in materials.items()
            if len(values) >= 3
        },
        section_materials=section_materials,
        nlgeom=nlgeom,
        max_increments=max_increments,
        dynamic_alpha=dynamic_alpha,
        dynamic_direct=dynamic_direct,
        dt=dt,
        total_time=total_time,
        cload=tuple(cload),
        boundaries=tuple(boundaries),
        amplitude=AmplitudeTable(
            name=amplitude_name,
            n_rows=len(amplitude_rows),
            t=tuple(row[0] for row in amplitude_rows),
            value=tuple(row[1] for row in amplitude_rows),
        ),
        wetted_upper=upper,
    )


def _wetted_upper(
    nodes: dict[int, tuple[float, float, float]],
) -> tuple[tuple[float, float], ...]:
    """The maximum ``y`` at each ``x`` station on the ``z = min`` face — the upper curve."""
    z_min = min(c[2] for c in nodes.values())
    by_x: dict[float, float] = {}
    for x, y, z in nodes.values():
        if z != z_min:
            continue
        by_x[x] = max(by_x.get(x, -math.inf), y)
    return tuple((x, by_x[x]) for x in sorted(by_x))


# --------------------------------------------------------------------------------------
# The C-family assertions
# --------------------------------------------------------------------------------------


def assert_calculix_deck(deck: CalculiXDeck, spec: CalculiXSolidSpec) -> None:
    """Fail loud on ANY drift between a written deck and its spec, listing every problem.

    Each clause below corresponds to a failure that produces plausible numbers rather than
    a crash; the module docstring explains the three worst.
    """
    problems: list[str] = []

    if deck.element_type != _ELEMENT_TYPE:
        problems.append(
            f"element type {deck.element_type!r} != {_ELEMENT_TYPE!r} — C3D8 shear-locks in a "
            "thin bending member and would under-predict the deflection"
        )
    if not deck.nlgeom:
        problems.append("*STEP is missing NLGEOM")
    if deck.max_increments < _INC_MARGIN * spec.n_windows:
        problems.append(
            f"*STEP INC={deck.max_increments} < {_INC_MARGIN} x {spec.n_windows} windows — "
            "ccx would finish its step mid-run and exit ZERO, and the status gate would pass"
        )
    if deck.dynamic_alpha != 0.0:
        problems.append(f"*DYNAMIC ALPHA={deck.dynamic_alpha!r} != 0.0 (numerical damping)")
    if not deck.dynamic_direct:
        problems.append("*DYNAMIC is missing DIRECT — ccx would choose its own time step")
    if deck.dt != spec.time_window_size:
        problems.append(
            f"*DYNAMIC dt {deck.dt!r} != coupling time-window size {spec.time_window_size!r}"
        )
    if deck.total_time != spec.max_time:
        problems.append(f"*DYNAMIC total time {deck.total_time!r} != max_time {spec.max_time!r}")

    span = deck.span
    if abs(span - spec.span) > 1e-15:
        problems.append(
            f"slab z-extent {span!r} != fluid span {spec.span!r} — preCICE Force is an "
            "absolute force, so a mismatched slab is stiffer or softer by exactly that "
            "ratio while everything still converges"
        )
    if len(deck.z_levels) != 2:
        problems.append(f"slab has {len(deck.z_levels)} z levels, expected exactly 2")

    dofs = {dof for nset, dof, _ in deck.cload if nset == INTERFACE_NSET}
    magnitudes = {mag for nset, _, mag in deck.cload if nset == INTERFACE_NSET}
    if dofs != {1, 2, 3}:
        problems.append(
            f"*CLOAD on {INTERFACE_NSET} declares dofs {sorted(dofs)}, expected [1, 2, 3] — "
            "the adapter OVERWRITES this block, so a missing dof is a silently unloaded axis"
        )
    if magnitudes and magnitudes != {0.0}:
        problems.append(f"*CLOAD magnitudes {sorted(magnitudes)} are not all exactly 0.0")

    if INTERFACE_NSET not in deck.nsets:
        problems.append(f"no *NSET named {INTERFACE_NSET} — the adapter's patch would not resolve")
    if NOSE_NSET not in deck.nsets:
        problems.append(f"no *NSET named {NOSE_NSET} — nothing would prescribe the plunge")

    plane_strain = [b for b in deck.boundaries if b[0] == _ALL_NSET and b[1] == 3]
    if not plane_strain:
        problems.append(f"no *BOUNDARY suppressing dof 3 on {_ALL_NSET} (the 2-D slab idiom)")
    driven = [b for b in deck.boundaries if b[0] == NOSE_NSET and b[4] == _AMPLITUDE_NAME]
    if len(driven) != 1:
        problems.append(
            f"expected exactly one amplitude-driven *BOUNDARY on {NOSE_NSET}, found {len(driven)}"
        )
    elif driven[0][1] != 2 or driven[0][2] != 2 or driven[0][3] != 1.0:
        problems.append(
            f"the driven *BOUNDARY is {driven[0]!r}; expected dof 2 only with magnitude 1.0 "
            "(the amplitude table carries metres)"
        )
    if not any(b[0] == NOSE_NSET and b[1] == 1 and b[3] is None for b in deck.boundaries):
        problems.append(
            f"{NOSE_NSET} dof 1 is not fixed — the prescribed teardrop could drift chordwise"
        )

    if deck.amplitude.name != _AMPLITUDE_NAME:
        problems.append(f"amplitude name {deck.amplitude.name!r} != {_AMPLITUDE_NAME!r}")
    if deck.amplitude.t[-1] < spec.max_time:
        problems.append(
            f"the amplitude table ends at t={deck.amplitude.t[-1]!r} < max_time "
            f"{spec.max_time!r} — the final increments would extrapolate"
        )
    problems.extend(_amplitude_problems(deck, spec))

    for elset, material in deck.section_materials.items():
        if material not in deck.materials:
            problems.append(f"*SOLID SECTION on {elset} names undeclared material {material!r}")
    if deck.section_materials.get(_PLATE_ELSET) != spec.plate.name:
        problems.append(
            f"{_PLATE_ELSET} is made of {deck.section_materials.get(_PLATE_ELSET)!r}, "
            f"expected {spec.plate.name!r}"
        )

    problems.extend(_geometry_problems(deck, spec))

    if problems:
        raise CalculiXDeckError(
            f"{deck.path}: the written deck does not match its spec "
            f"({len(problems)} problem(s)):\n  - " + "\n  - ".join(problems)
        )


def _amplitude_problems(deck: CalculiXDeck, spec: CalculiXSolidSpec) -> list[str]:
    """The table must reproduce the analytic plunge to well inside the plunge amplitude."""
    t = np.asarray(deck.amplitude.t, dtype=np.float64)
    written = np.asarray(deck.amplitude.value, dtype=np.float64)
    analytic = spec.kinematics.evaluate(t)["y"]
    error = float(np.max(np.abs(written - analytic)))
    tolerance = 1.0e-6 * spec.kinematics.stroke_amplitude
    if error > tolerance:
        return [
            f"the amplitude table strays {error:.3e} m from the analytic plunge, over the "
            f"{tolerance:.3e} m allowed"
        ]
    return []


def _geometry_problems(deck: CalculiXDeck, spec: CalculiXSolidSpec) -> list[str]:
    """The solid's wetted curve must BE the fluid's, not an interpolation of it."""
    x = np.asarray([point[0] for point in deck.wetted_upper], dtype=np.float64)
    y = np.asarray([point[1] for point in deck.wetted_upper], dtype=np.float64)
    want_x = np.asarray(spec.surface_x, dtype=np.float64)
    if x.shape != want_x.shape or not np.allclose(x, want_x, rtol=0.0, atol=_GEOMETRY_TOLERANCE):
        return [
            f"the deck's {x.size} x-stations are not the fluid's {want_x.size} — the wetted "
            "curves cannot be compared, let alone equal"
        ]
    want_y = spec.half_thickness(want_x)
    error = float(np.max(np.abs(y - want_y)))
    if error > _GEOMETRY_TOLERANCE:
        return [f"the solid's wetted curve differs from the fluid's by {error:.3e} m"]
    return []


# --------------------------------------------------------------------------------------
# The adapter's config.yml (a ~20-line file; no YAML dependency — Invariant 1)
# --------------------------------------------------------------------------------------


class CalculiXAdapterConfig(BaseModel):
    """The calculix-adapter's ``config.yml``, as written or as read back."""

    model_config = _STRICT

    participant: str = Field(..., min_length=1)
    nodes_mesh: str = Field(..., min_length=1)
    patch: str = Field(..., min_length=1)
    read_data: tuple[str, ...] = Field(..., min_length=1)
    write_data: tuple[str, ...] = Field(..., min_length=1)
    precice_config_file: str = Field(..., min_length=1)

    @property
    def interface_nset(self) -> str:
        """The ``*NSET`` the adapter will look for: its patch name with an ``N`` prefix."""
        return "N" + self.patch


def _adapter_config_text(config: CalculiXAdapterConfig) -> str:
    return (
        "participants:\n"
        "\n"
        f"    {config.participant}:\n"
        "        interfaces:\n"
        f"        - nodes-mesh: {config.nodes_mesh}\n"
        f"          patch: {config.patch}\n"
        f"          read-data: [{', '.join(config.read_data)}]\n"
        f"          write-data: [{', '.join(config.write_data)}]\n"
        "\n"
        f"precice-config-file: {config.precice_config_file}\n"
    )


def write_adapter_config(config: CalculiXAdapterConfig, *, dest: Path) -> CalculiXAdapterConfig:
    """Write ``config.yml`` and re-read it, so the file is what the caller asked for."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_adapter_config_text(config), encoding="utf-8")
    produced = read_adapter_config(dest)
    if produced != config:
        raise CalculiXDeckError(
            f"{dest}: the adapter config did not survive a write/read round trip\n"
            f"  wrote: {config!r}\n  read:  {produced!r}"
        )
    return produced


def read_adapter_config(path: Path) -> CalculiXAdapterConfig:
    """Read the adapter's ``config.yml`` without a YAML dependency.

    The file is ~10 significant lines of a fixed shape, and ``aero/`` core is stdlib +
    numpy + pydantic (Invariant 1). This reads exactly that shape and refuses anything
    else, rather than pretending to be a YAML parser.
    """
    if not path.is_file():
        raise CalculiXDeckError(f"{path}: adapter config not found")
    participant = ""
    fields: dict[str, str] = {}
    precice_config_file = ""
    n_interfaces = 0
    in_participants = False

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 0:
            key, _, value = stripped.partition(":")
            if key == "participants":
                in_participants = True
            elif key == "precice-config-file":
                precice_config_file = value.strip()
                in_participants = False
            else:
                raise CalculiXDeckError(f"{path}:{lineno}: unexpected top-level key {key!r}")
            continue
        if not in_participants:
            raise CalculiXDeckError(f"{path}:{lineno}: indented line outside participants")
        if stripped.endswith(":") and not stripped.startswith("-"):
            name = stripped[:-1].strip()
            if name != "interfaces":
                participant = name
            continue
        item = stripped[1:].strip() if stripped.startswith("-") else stripped
        if stripped.startswith("-"):
            n_interfaces += 1
        key, sep, value = item.partition(":")
        if not sep:
            raise CalculiXDeckError(f"{path}:{lineno}: expected 'key: value', got {stripped!r}")
        fields[key.strip()] = value.strip()

    if n_interfaces != 1:
        raise CalculiXDeckError(
            f"{path}: expected exactly one interface, found {n_interfaces} — the readout "
            "assumes one wetted surface per participant"
        )
    missing = {"nodes-mesh", "patch", "read-data", "write-data"} - set(fields)
    if missing or not participant or not precice_config_file:
        raise CalculiXDeckError(
            f"{path}: incomplete adapter config (missing {sorted(missing)}, "
            f"participant={participant!r}, precice-config-file={precice_config_file!r})"
        )
    return CalculiXAdapterConfig(
        participant=participant,
        nodes_mesh=fields["nodes-mesh"],
        patch=fields["patch"],
        read_data=_yaml_list(fields["read-data"], path=path),
        write_data=_yaml_list(fields["write-data"], path=path),
        precice_config_file=precice_config_file,
    )


def _yaml_list(raw: str, *, path: Path) -> tuple[str, ...]:
    if not (raw.startswith("[") and raw.endswith("]")):
        raise CalculiXDeckError(f"{path}: expected an inline list, got {raw!r}")
    return tuple(item.strip() for item in raw[1:-1].split(",") if item.strip())


def assert_adapter_config(
    config: CalculiXAdapterConfig,
    *,
    spec: CalculiXSolidSpec,
    deck: CalculiXDeck,
    mesh_name: str,
) -> None:
    """Tie the adapter config to the deck it drives and the configuration it couples to."""
    problems: list[str] = []
    if config.participant != spec.participant:
        problems.append(f"participant {config.participant!r} != {spec.participant!r}")
    if config.nodes_mesh != mesh_name:
        problems.append(
            f"nodes-mesh {config.nodes_mesh!r} != the rendered configuration's {mesh_name!r}"
        )
    if config.interface_nset not in deck.nsets:
        problems.append(
            f"patch {config.patch!r} resolves to *NSET {config.interface_nset!r}, which the "
            f"deck does not declare (it has: {sorted(deck.nsets)})"
        )
    if config.read_data != ("Force",):
        problems.append(
            f"read-data {config.read_data} != ('Force',) — the calculix-adapter reads Force, "
            "not Turek-Hron FSI3's Stress"
        )
    if config.write_data != ("Displacement",):
        problems.append(f"write-data {config.write_data} != ('Displacement',)")
    if problems:
        raise CalculiXDeckError(
            "the adapter config does not describe this case "
            f"({len(problems)} problem(s)):\n  - " + "\n  - ".join(problems)
        )
