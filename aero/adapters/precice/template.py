"""Render a committed, digest-pinned ``precice-config.xml`` template — and re-read it.

An authored case has no upstream pin, so its integrity claim has to be built rather than
inherited. The claim this module implements is:

    the configuration a run executes is this committed template with EXACTLY these
    tokens substituted, and every substituted value is observable in the parsed model.

Three things make that a claim rather than a hope:

1. **The template's bytes are pinned.** ``read_template`` verifies the file against
   ``templates/SHA256SUMS`` on every read (the same shape as
   ``aero.provenance.four_fold.container_sif_sha256``), and the digest also travels in
   ``AuthoredSource.template_sha256``, i.e. into the run's manifest. So every value that
   is *not* a token — ``max-iterations``, both convergence limits, every IQN-ILS knob —
   cannot be loosened without moving a digest that ships in the bundle. That is the
   authored analogue of ADR-036 gate C2.
2. **The token set is asserted, not assumed.** :func:`render_precice_config` refuses
   unless the tokens found in the template are exactly :data:`_TOKENS`, so adding a
   placeholder to the template without teaching the renderer about it — or dropping one
   the renderer still fills — is a loud failure rather than an unsubstituted ``@TOKEN@``
   in a running case.
3. **The render is closed by a re-read.** :func:`write_precice_config` writes, re-reads
   from disk, and asserts the parsed model against an expectation *derived from the same
   values* (:func:`hg2007_expectation`). A token that renders into a place preCICE parses
   differently than we think fails there, before any solve.

This is deliberately NOT an XML writer. Emitting the configuration programmatically
would mean the bytes that run are the output of code that can drift; substituting into
committed, digest-pinned bytes means they cannot.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.precice.config import (
    CouplingSchemeKind,
    MappingExpectation,
    MeshExpectation,
    ParticipantDataExpectation,
    PreciceConfig,
    PreciceConfigError,
    PreciceConfigExpectation,
    assert_config,
    read_precice_config,
)

__all__ = [
    "HG2007_TEMPLATE",
    "NOSE_WATCH_POINT_NAME",
    "RENDERER_VERSION",
    "TEMPLATES_DIR",
    "TE_WATCH_POINT_NAME",
    "PreciceConfigValues",
    "hg2007_expectation",
    "read_template",
    "render_precice_config",
    "template_sha256",
    "write_precice_config",
]

TEMPLATES_DIR = Path(__file__).parent / "templates"

#: Basename of the Stage-20 authored coupling template.
HG2007_TEMPLATE = "hg2007-precice-config.xml.in"

#: Bumped whenever a rendered byte changes, so two bundles are comparable at a glance.
#: It rides in ``AuthoredSource.renderer_version`` and therefore in the manifest.
RENDERER_VERSION = "1"

#: The NAMES of the two watch-points the template declares on ``Solid-Mesh`` -- distinct
#: from the ``@NOSE_WATCH_POINT@`` token, which carries their COORDINATES. Named here
#: because the template's bytes carry them and the readout opens the files preCICE derives
#: from them (``precice-Solid-watchpoint-<name>.log``): a mismatch is a FileNotFoundError at
#: the END of a multi-day run, which is the most expensive moment to learn about a typo.
NOSE_WATCH_POINT_NAME = "Nose"
TE_WATCH_POINT_NAME = "Trailing-Edge"

#: Every token the renderer knows. The template must contain exactly this set.
_TOKENS = frozenset(
    {
        "SUPPORT_RADIUS",
        "NOSE_WATCH_POINT",
        "TE_WATCH_POINT",
        "EXCHANGE_DIRECTORY",
        "TIME_WINDOW_SIZE",
        "MAX_TIME",
    }
)

_TOKEN_RE = re.compile(r"@([A-Z][A-Z0-9_]*)@")

# --- Pinned in the template's bytes, asserted from here. Both copies must agree, which
# --- is what makes "the expectation describes the template" checkable rather than stated.
_PARTICIPANTS = ("Fluid", "Solid")
_COUPLING_SCHEME: CouplingSchemeKind = "parallel-implicit"
_M2N_KIND = "sockets"
_MAX_ITERATIONS = 50
_CONVERGENCE_LIMIT = 5.0e-3
_CONVERGENCE_KIND = "relative-convergence-measure"
_ACCELERATION_KIND = "IQN-ILS"
_ACCELERATION_FILTER_TYPE = "QR2"
_ACCELERATION_FILTER_LIMIT = 1.0e-2
_ACCELERATION_INITIAL_RELAXATION = 0.5
_ACCELERATION_MAX_USED_ITERATIONS = 100
_ACCELERATION_TIME_WINDOWS_REUSED = 15
_BASIS_FUNCTION = "compact-polynomial-c6"
_FLUID_MESH = "Fluid-Mesh"
_SOLID_MESH = "Solid-Mesh"


class PreciceConfigValues(BaseModel):
    """The rendered token values — the entire varying surface of an authored config."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )

    time_window_size: float = Field(
        ...,
        gt=0.0,
        description="Coupling time-window size [s]; the fluid and solid dt must both equal it.",
    )
    max_time: float = Field(..., gt=0.0, description="Coupled end time [s].")
    support_radius: float = Field(
        ...,
        gt=0.0,
        description=(
            "RBF (compact-polynomial-c6) support radius [m]. Upstream's literal '1.' is one "
            "metre — eleven chords on this 0.09 m foil — so it is a token here, chosen from "
            "the interface spacing by the deck writer rather than inherited."
        ),
    )
    nose_watch_point: tuple[float, float] = Field(
        ...,
        description=(
            "Solid-Mesh point that samples the PRESCRIBED leading-edge motion. It measures "
            "the plunge the solid actually executed, which is what makes the prescribed "
            "kinematics checkable against the record instead of assumed."
        ),
    )
    te_watch_point: tuple[float, float] = Field(
        ...,
        description="Solid-Mesh point at the plate trailing edge; carries the D0 deflection.",
    )
    exchange_directory: str = Field(
        default="..",
        min_length=1,
        description="m2n socket rendezvous directory, relative to each participant's workdir.",
    )

    def tokens(self) -> dict[str, str]:
        """The token substitutions, formatted so a re-read reproduces these floats exactly.

        ``repr`` on a Python float round-trips, and the config parser goes through
        ``float(...)``, so ``assert_config``'s equality checks are exact rather than
        approximate — a token that renders lossily fails the round trip loudly.
        """
        return {
            "SUPPORT_RADIUS": repr(self.support_radius),
            "NOSE_WATCH_POINT": _coordinate(self.nose_watch_point),
            "TE_WATCH_POINT": _coordinate(self.te_watch_point),
            "EXCHANGE_DIRECTORY": self.exchange_directory,
            "TIME_WINDOW_SIZE": repr(self.time_window_size),
            "MAX_TIME": repr(self.max_time),
        }


def _coordinate(point: tuple[float, float]) -> str:
    return ";".join(repr(component) for component in point)


def _template_digests() -> dict[str, str]:
    """Parse ``templates/SHA256SUMS`` (``sha256sum`` format, ``#`` comments allowed)."""
    sums = TEMPLATES_DIR / "SHA256SUMS"
    if not sums.is_file():
        raise PreciceConfigError(f"{sums}: template digest file not found")
    digests: dict[str, str] = {}
    for lineno, raw in enumerate(sums.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            raise PreciceConfigError(f"{sums}:{lineno}: malformed row {line!r}")
        digests[parts[1]] = parts[0]
    if not digests:
        raise PreciceConfigError(f"{sums}: no template digests recorded")
    return digests


def template_sha256(name: str = HG2007_TEMPLATE) -> str:
    """The RECORDED digest of a committed template (not the file's current digest)."""
    digests = _template_digests()
    try:
        return digests[name]
    except KeyError:
        known = ", ".join(sorted(digests)) or "(none)"
        raise PreciceConfigError(
            f"no digest recorded for template {name!r} in {TEMPLATES_DIR / 'SHA256SUMS'} "
            f"(have: {known})"
        ) from None


def read_template(name: str = HG2007_TEMPLATE) -> str:
    """Read a committed template, verifying its bytes against ``templates/SHA256SUMS``.

    Verified on EVERY read rather than once at import: the cost is a few microseconds and
    it means an edited working tree cannot render a configuration that the manifest will
    describe with the recorded digest.
    """
    recorded = template_sha256(name)
    path = TEMPLATES_DIR / name
    if not path.is_file():
        raise PreciceConfigError(f"{path}: template not found")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != recorded:
        raise PreciceConfigError(
            f"{path}: template digest {actual} != recorded {recorded}. The committed "
            "template has been edited; a rendered configuration would no longer be the "
            "one the manifest and AuthoredSource.template_sha256 describe."
        )
    return raw.decode("utf-8")


def render_precice_config(values: PreciceConfigValues, *, template: str = HG2007_TEMPLATE) -> str:
    """Substitute `values` into the digest-verified `template`.

    Refuses unless the tokens found in the template are EXACTLY the ones this renderer
    knows — an unknown token would render as a literal ``@NAME@`` into a running case,
    and an unused one means the renderer is filling something the template no longer has.
    """
    text = read_template(template)
    found = frozenset(_TOKEN_RE.findall(text))
    if found != _TOKENS:
        missing = sorted(_TOKENS - found)
        unknown = sorted(found - _TOKENS)
        raise PreciceConfigError(
            f"{TEMPLATES_DIR / template}: token set mismatch — "
            f"template lacks {missing or '[]'}, renderer does not know {unknown or '[]'}"
        )

    rendered = text
    for token, replacement in values.tokens().items():
        rendered = rendered.replace(f"@{token}@", replacement)

    leftover = sorted(set(_TOKEN_RE.findall(rendered)))
    if leftover:
        raise PreciceConfigError(
            f"{TEMPLATES_DIR / template}: unsubstituted token(s) {leftover} after rendering"
        )
    return rendered


def hg2007_expectation(values: PreciceConfigValues) -> PreciceConfigExpectation:
    """The full expectation for a rendered HG2007 configuration.

    Derived from the same `values` the renderer substitutes, so the C-family claim —
    "every rendered token is observable in the parsed model" — is closed by construction
    rather than maintained by hand in two places. Everything else in it mirrors what the
    template's pinned bytes say; the pair disagreeing is a test failure, not a run-time
    surprise.
    """
    return PreciceConfigExpectation(
        participants=_PARTICIPANTS,
        coupling_scheme=_COUPLING_SCHEME,
        m2n_kind=_M2N_KIND,
        time_window_size=values.time_window_size,
        max_iterations=_MAX_ITERATIONS,
        convergence_limits={
            "Displacement": _CONVERGENCE_LIMIT,
            "Force": _CONVERGENCE_LIMIT,
        },
        convergence_kinds={
            "Displacement": _CONVERGENCE_KIND,
            "Force": _CONVERGENCE_KIND,
        },
        watch_points={
            "Solid/Nose": values.nose_watch_point,
            "Solid/Trailing-Edge": values.te_watch_point,
        },
        acceleration_kind=_ACCELERATION_KIND,
        max_time=values.max_time,
        data_kinds={"Force": "vector", "Displacement": "vector"},
        meshes={
            _FLUID_MESH: MeshExpectation(dimensions=2, use_data=("Force", "Displacement")),
            _SOLID_MESH: MeshExpectation(dimensions=2, use_data=("Displacement", "Force")),
        },
        participant_data={
            "Fluid": ParticipantDataExpectation(
                read_data=(("Displacement", _FLUID_MESH),),
                write_data=(("Force", _FLUID_MESH),),
            ),
            "Solid": ParticipantDataExpectation(
                read_data=(("Force", _SOLID_MESH),),
                write_data=(("Displacement", _SOLID_MESH),),
            ),
        },
        mappings=(
            MappingExpectation(
                kind="rbf",
                direction="write",
                from_mesh=_FLUID_MESH,
                to_mesh=_SOLID_MESH,
                constraint="conservative",
                basis_function=_BASIS_FUNCTION,
                support_radius=values.support_radius,
            ),
            MappingExpectation(
                kind="rbf",
                direction="read",
                from_mesh=_SOLID_MESH,
                to_mesh=_FLUID_MESH,
                constraint="consistent",
                basis_function=_BASIS_FUNCTION,
                support_radius=values.support_radius,
            ),
        ),
        acceleration_data=(("Displacement", _SOLID_MESH), ("Force", _SOLID_MESH)),
        acceleration_preconditioner=None,  # assert ABSENT — upstream's flap declares none
        acceleration_filter_type=_ACCELERATION_FILTER_TYPE,
        acceleration_filter_limit=_ACCELERATION_FILTER_LIMIT,
        acceleration_initial_relaxation=_ACCELERATION_INITIAL_RELAXATION,
        acceleration_max_used_iterations=_ACCELERATION_MAX_USED_ITERATIONS,
        acceleration_time_windows_reused=_ACCELERATION_TIME_WINDOWS_REUSED,
        m2n_exchange_directory=values.exchange_directory,
        exchanges=(
            ("Force", _SOLID_MESH, "Fluid", "Solid"),
            ("Displacement", _SOLID_MESH, "Solid", "Fluid"),
        ),
        first_participant="Fluid",
        second_participant="Solid",
    )


def write_precice_config(
    values: PreciceConfigValues,
    *,
    dest: Path,
    template: str = HG2007_TEMPLATE,
) -> PreciceConfig:
    """Render to `dest`, re-read it from disk, and assert it against `values`.

    Returns the parsed configuration — which carries the written file's own sha256, so
    the caller records what it actually wrote rather than what it meant to write.
    """
    rendered = render_precice_config(values, template=template)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rendered, encoding="utf-8")
    produced = read_precice_config(dest)
    assert_config(produced, hg2007_expectation(values))
    return produced
