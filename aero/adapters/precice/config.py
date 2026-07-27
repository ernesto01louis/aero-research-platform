"""Typed reader + validator for a preCICE 3.x ``precice-config.xml``.

The platform does not run a coupled case it cannot describe. This module parses the
upstream configuration into frozen pydantic models so that, before any solve, the
campaign can assert *exactly* what it is about to run — participants, coupling scheme,
time-window size, iteration cap, convergence limits, acceleration, and watch-point
coordinates — and fail loud on any drift (ADR-036 gate C1).

Two design points worth knowing:

**Parsing.** ``xml.etree.ElementTree`` and ``xml.dom.minidom`` both REFUSE this file:
preCICE writes element names like ``data:vector``, ``m2n:sockets`` and
``coupling-scheme:parallel-implicit`` where the prefix is *not* a declared XML
namespace, and CPython's ElementTree always drives expat with namespace processing
enabled ("unbound prefix"). We therefore drive :mod:`xml.parsers.expat` directly with
namespace processing off, and build a minimal immutable tree. Stdlib only, no
``defusedxml``: the input is digest-verified against the pinned manifest before it is
parsed (gate C5), and it is never attacker-supplied.

**The single permitted mutation.** A campaign may shorten ``<max-time>`` to fit a
declared wall-clock budget. It may not touch anything else — not ``max-iterations``,
not a convergence limit, not the acceleration. :func:`rewrite_max_time` enforces that
*structurally*: it re-parses what it wrote and asserts the result equals the source
model under a ``max_time``-only update, so loosening any other knob aborts the run
rather than quietly producing an easier problem (ADR-036 gate C2).
"""

from __future__ import annotations

import re
import xml.parsers.expat as expat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

CouplingSchemeKind = Literal[
    "serial-explicit",
    "parallel-explicit",
    "serial-implicit",
    "parallel-implicit",
    "multi",
]


class PreciceConfigError(RuntimeError):
    """A preCICE configuration could not be read, or does not match expectations."""


# --------------------------------------------------------------------------------------
# Minimal immutable XML tree (namespace processing OFF — see the module docstring)
# --------------------------------------------------------------------------------------


class _Element(NamedTuple):
    tag: str
    attrib: Mapping[str, str]
    children: tuple[_Element, ...]

    def find_all(self, tag: str) -> tuple[_Element, ...]:
        return tuple(child for child in self.children if child.tag == tag)

    def find_prefixed(self, prefix: str) -> tuple[_Element, ...]:
        """Children whose tag starts with ``<prefix>:`` (e.g. ``coupling-scheme:``)."""
        return tuple(child for child in self.children if child.tag.startswith(prefix + ":"))

    def find_one(self, tag: str, *, source: Path) -> _Element:
        found = self.find_all(tag)
        if len(found) != 1:
            raise PreciceConfigError(
                f"{source}: expected exactly one <{tag}> inside <{self.tag}>, found {len(found)}"
            )
        return found[0]

    def attr(self, name: str, *, source: Path) -> str:
        try:
            return self.attrib[name]
        except KeyError:
            raise PreciceConfigError(
                f"{source}: <{self.tag}> is missing the required attribute {name!r}"
            ) from None

    def value(self, tag: str, *, source: Path) -> str:
        """The ``value`` attribute of a unique ``<tag value="..."/>`` child."""
        return self.find_one(tag, source=source).attr("value", source=source)

    def optional_value(self, tag: str, *, source: Path) -> str | None:
        found = self.find_all(tag)
        if not found:
            return None
        if len(found) > 1:
            raise PreciceConfigError(
                f"{source}: expected at most one <{tag}> inside <{self.tag}>, found {len(found)}"
            )
        return found[0].attr("value", source=source)


def _parse_xml(text: str, *, source: Path) -> _Element:
    """Parse XML with expat, namespace processing OFF, into an immutable tree."""
    stack: list[tuple[str, Mapping[str, str], list[_Element]]] = []
    root: _Element | None = None

    def start(name: str, attrs: dict[str, str]) -> None:
        stack.append((name, dict(attrs), []))

    def end(name: str) -> None:
        nonlocal root
        tag, attrib, children = stack.pop()
        element = _Element(tag=tag, attrib=attrib, children=tuple(children))
        if stack:
            stack[-1][2].append(element)
        else:
            root = element

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        raise PreciceConfigError(f"{source}: not well-formed XML — {exc}") from exc
    if root is None:
        raise PreciceConfigError(f"{source}: empty document")
    return root


# --------------------------------------------------------------------------------------
# Typed declarations
# --------------------------------------------------------------------------------------


class DataDecl(BaseModel):
    """A ``<data:scalar>`` / ``<data:vector>`` declaration."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    kind: Literal["scalar", "vector"]

    def n_components(self, dimensions: int) -> int:
        return 1 if self.kind == "scalar" else dimensions


class MeshDecl(BaseModel):
    """A ``<mesh>`` declaration. ``use_data`` order is significant — it fixes the
    column order of any watch-point written on this mesh."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    dimensions: int = Field(..., ge=1, le=3)
    use_data: tuple[str, ...] = Field(..., min_length=1)


class WatchPointDecl(BaseModel):
    """A ``<watch-point>``: preCICE writes ``precice-<Participant>-watchpoint-<name>.log``."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    mesh: str = Field(..., min_length=1)
    coordinate: tuple[float, ...] = Field(..., min_length=1)

    @property
    def log_basename_suffix(self) -> str:
        return f"watchpoint-{self.name}.log"


class MappingDecl(BaseModel):
    """A ``<mapping:*>`` declaration (diagnostic detail; not gated)."""

    model_config = _STRICT

    kind: str = Field(..., min_length=1)
    direction: Literal["read", "write"]
    from_mesh: str = Field(..., min_length=1)
    to_mesh: str = Field(..., min_length=1)
    constraint: str = Field(..., min_length=1)
    basis_function: str | None = None
    support_radius: float | None = None


class ParticipantDecl(BaseModel):
    """A ``<participant>`` declaration."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    provide_mesh: tuple[str, ...] = ()
    receive_mesh: tuple[tuple[str, str], ...] = ()  # (mesh, from-participant)
    read_data: tuple[tuple[str, str], ...] = ()  # (data, mesh)
    write_data: tuple[tuple[str, str], ...] = ()  # (data, mesh)
    watch_points: tuple[WatchPointDecl, ...] = ()
    mappings: tuple[MappingDecl, ...] = ()


class ConvergenceMeasureDecl(BaseModel):
    """A ``<*-convergence-measure>`` inside an implicit coupling scheme."""

    model_config = _STRICT

    kind: str = Field(..., min_length=1)
    limit: float = Field(..., gt=0.0)
    data: str = Field(..., min_length=1)
    mesh: str = Field(..., min_length=1)


class AccelerationDecl(BaseModel):
    """An ``<acceleration:*>`` block."""

    model_config = _STRICT

    kind: str = Field(..., min_length=1)
    data: tuple[tuple[str, str], ...] = ()  # (data, mesh)
    preconditioner: str | None = None
    filter_type: str | None = None
    filter_limit: float | None = None
    initial_relaxation: float | None = None
    max_used_iterations: int | None = None
    time_windows_reused: int | None = None


class CouplingSchemeDecl(BaseModel):
    """A ``<coupling-scheme:*>`` block."""

    model_config = _STRICT

    kind: CouplingSchemeKind
    time_window_size: float = Field(..., gt=0.0)
    max_time: float | None = Field(default=None, gt=0.0)
    max_iterations: int | None = Field(default=None, ge=1)
    first: str = Field(..., min_length=1)
    second: str = Field(..., min_length=1)
    exchanges: tuple[tuple[str, str, str, str], ...] = ()  # (data, mesh, from, to)
    convergence_measures: tuple[ConvergenceMeasureDecl, ...] = ()
    acceleration: AccelerationDecl | None = None

    @property
    def implicit(self) -> bool:
        return self.kind in ("serial-implicit", "parallel-implicit", "multi")


class M2NDecl(BaseModel):
    """An ``<m2n:*>`` declaration."""

    model_config = _STRICT

    kind: Literal["sockets", "mpi", "mpi-single", "mpi-multiple-ports"]
    acceptor: str = Field(..., min_length=1)
    connector: str = Field(..., min_length=1)
    exchange_directory: str | None = None


class PreciceConfig(BaseModel):
    """A parsed ``precice-config.xml``, with the source digest that produced it."""

    model_config = _STRICT

    source_path: Path
    source_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    data: tuple[DataDecl, ...] = Field(..., min_length=1)
    meshes: tuple[MeshDecl, ...] = Field(..., min_length=1)
    participants: tuple[ParticipantDecl, ...] = Field(..., min_length=2)
    m2n: tuple[M2NDecl, ...] = Field(..., min_length=1)
    coupling_scheme: CouplingSchemeDecl

    def participant(self, name: str) -> ParticipantDecl:
        for candidate in self.participants:
            if candidate.name == name:
                return candidate
        known = ", ".join(p.name for p in self.participants)
        raise PreciceConfigError(f"no participant {name!r} in {self.source_path} (have: {known})")

    def mesh(self, name: str) -> MeshDecl:
        for candidate in self.meshes:
            if candidate.name == name:
                return candidate
        known = ", ".join(m.name for m in self.meshes)
        raise PreciceConfigError(f"no mesh {name!r} in {self.source_path} (have: {known})")

    def datum(self, name: str) -> DataDecl:
        for candidate in self.data:
            if candidate.name == name:
                return candidate
        known = ", ".join(d.name for d in self.data)
        raise PreciceConfigError(f"no data {name!r} in {self.source_path} (have: {known})")

    def watch_point(self, participant: str, name: str) -> WatchPointDecl:
        for candidate in self.participant(participant).watch_points:
            if candidate.name == name:
                return candidate
        raise PreciceConfigError(
            f"participant {participant!r} declares no watch-point {name!r} in {self.source_path}"
        )

    def watchpoint_columns(self, participant: str, watch_point: str) -> tuple[str, ...]:
        """The column header preCICE will write for this watch-point.

        Derived from the mesh's ``dimensions`` and the ORDER of its ``use-data``
        children. The watch-point parser asserts the file's real header against this
        prediction rather than indexing by position, so an upstream reordering is a
        loud failure instead of a silently transposed signal (ADR-036 gate C4).
        """
        point = self.watch_point(participant, watch_point)
        mesh = self.mesh(point.mesh)
        columns = ["Time"]
        columns += [f"Coordinate{i}" for i in range(mesh.dimensions)]
        for data_name in mesh.use_data:
            datum = self.datum(data_name)
            if datum.kind == "scalar":
                columns.append(datum.name)
            else:
                columns += [f"{datum.name}{i}" for i in range(mesh.dimensions)]
        return tuple(columns)


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------


def _parse_coordinate(raw: str, *, source: Path) -> tuple[float, ...]:
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    if not parts:
        raise PreciceConfigError(f"{source}: empty watch-point coordinate {raw!r}")
    try:
        return tuple(float(p) for p in parts)
    except ValueError as exc:
        raise PreciceConfigError(f"{source}: bad watch-point coordinate {raw!r}") from exc


def _read_participant(element: _Element, *, source: Path) -> ParticipantDecl:
    mappings: list[MappingDecl] = []
    for mapping in element.find_prefixed("mapping"):
        basis = next(
            (child for child in mapping.children if child.tag.startswith("basis-function:")),
            None,
        )
        radius = None if basis is None else basis.attrib.get("support-radius")
        mappings.append(
            MappingDecl(
                kind=mapping.tag.split(":", 1)[1],
                direction=mapping.attr("direction", source=source),  # type: ignore[arg-type]
                from_mesh=mapping.attr("from", source=source),
                to_mesh=mapping.attr("to", source=source),
                constraint=mapping.attr("constraint", source=source),
                basis_function=None if basis is None else basis.tag.split(":", 1)[1],
                support_radius=None if radius is None else float(radius),
            )
        )
    return ParticipantDecl(
        name=element.attr("name", source=source),
        provide_mesh=tuple(e.attr("name", source=source) for e in element.find_all("provide-mesh")),
        receive_mesh=tuple(
            (e.attr("name", source=source), e.attr("from", source=source))
            for e in element.find_all("receive-mesh")
        ),
        read_data=tuple(
            (e.attr("name", source=source), e.attr("mesh", source=source))
            for e in element.find_all("read-data")
        ),
        write_data=tuple(
            (e.attr("name", source=source), e.attr("mesh", source=source))
            for e in element.find_all("write-data")
        ),
        watch_points=tuple(
            WatchPointDecl(
                name=e.attr("name", source=source),
                mesh=e.attr("mesh", source=source),
                coordinate=_parse_coordinate(e.attr("coordinate", source=source), source=source),
            )
            for e in element.find_all("watch-point")
        ),
        mappings=tuple(mappings),
    )


def _read_acceleration(element: _Element, *, source: Path) -> AccelerationDecl:
    preconditioner = element.find_all("preconditioner")
    filters = element.find_all("filter")
    max_used = element.optional_value("max-used-iterations", source=source)
    reused = element.optional_value("time-windows-reused", source=source)
    relaxation = element.optional_value("initial-relaxation", source=source)
    return AccelerationDecl(
        kind=element.tag.split(":", 1)[1],
        data=tuple(
            (e.attr("name", source=source), e.attr("mesh", source=source))
            for e in element.find_all("data")
        ),
        preconditioner=(
            None if not preconditioner else preconditioner[0].attr("type", source=source)
        ),
        filter_type=None if not filters else filters[0].attr("type", source=source),
        filter_limit=None if not filters else float(filters[0].attr("limit", source=source)),
        initial_relaxation=None if relaxation is None else float(relaxation),
        max_used_iterations=None if max_used is None else int(max_used),
        time_windows_reused=None if reused is None else int(reused),
    )


def _read_coupling_scheme(element: _Element, *, source: Path) -> CouplingSchemeDecl:
    participants = element.find_one("participants", source=source)
    measures: list[ConvergenceMeasureDecl] = []
    for child in element.children:
        if not child.tag.endswith("convergence-measure"):
            continue
        measures.append(
            ConvergenceMeasureDecl(
                kind=child.tag,
                limit=float(child.attr("limit", source=source)),
                data=child.attr("data", source=source),
                mesh=child.attr("mesh", source=source),
            )
        )
    accelerations = element.find_prefixed("acceleration")
    if len(accelerations) > 1:
        raise PreciceConfigError(
            f"{source}: {len(accelerations)} acceleration blocks in one coupling scheme"
        )
    max_time = element.optional_value("max-time", source=source)
    max_iterations = element.optional_value("max-iterations", source=source)
    return CouplingSchemeDecl(
        kind=element.tag.split(":", 1)[1],  # type: ignore[arg-type]
        time_window_size=float(element.value("time-window-size", source=source)),
        max_time=None if max_time is None else float(max_time),
        max_iterations=None if max_iterations is None else int(max_iterations),
        first=participants.attr("first", source=source),
        second=participants.attr("second", source=source),
        exchanges=tuple(
            (
                e.attr("data", source=source),
                e.attr("mesh", source=source),
                e.attr("from", source=source),
                e.attr("to", source=source),
            )
            for e in element.find_all("exchange")
        ),
        convergence_measures=tuple(measures),
        acceleration=(
            None if not accelerations else _read_acceleration(accelerations[0], source=source)
        ),
    )


def parse_precice_config(text: str, *, source: Path, sha256: str) -> PreciceConfig:
    """Parse ``precice-config.xml`` text into a :class:`PreciceConfig`."""
    root = _parse_xml(text, source=source)
    if root.tag != "precice-configuration":
        raise PreciceConfigError(
            f"{source}: root element is <{root.tag}>, expected <precice-configuration>"
        )

    data = tuple(
        DataDecl(name=e.attr("name", source=source), kind=e.tag.split(":", 1)[1])  # type: ignore[arg-type]
        for e in root.find_prefixed("data")
    )
    meshes = tuple(
        MeshDecl(
            name=e.attr("name", source=source),
            dimensions=int(e.attr("dimensions", source=source)),
            use_data=tuple(u.attr("name", source=source) for u in e.find_all("use-data")),
        )
        for e in root.find_all("mesh")
    )
    participants = tuple(_read_participant(e, source=source) for e in root.find_all("participant"))
    m2n = tuple(
        M2NDecl(
            kind=e.tag.split(":", 1)[1],  # type: ignore[arg-type]
            acceptor=e.attr("acceptor", source=source),
            connector=e.attr("connector", source=source),
            exchange_directory=e.attrib.get("exchange-directory"),
        )
        for e in root.find_prefixed("m2n")
    )
    schemes = root.find_prefixed("coupling-scheme")
    if len(schemes) != 1:
        raise PreciceConfigError(
            f"{source}: expected exactly one coupling scheme, found {len(schemes)} — "
            "the platform's coupled-run plumbing assumes a single scheme"
        )

    config = PreciceConfig(
        source_path=source,
        source_sha256=sha256,
        data=data,
        meshes=meshes,
        participants=participants,
        m2n=m2n,
        coupling_scheme=_read_coupling_scheme(schemes[0], source=source),
    )
    # Referential integrity: every mesh's use-data and every participant's data must
    # resolve. A dangling name means we have mis-parsed or upstream has drifted; either
    # way the derived watch-point column prediction would be wrong.
    for mesh in config.meshes:
        for name in mesh.use_data:
            config.datum(name)
    for participant in config.participants:
        for name, mesh_name in (*participant.read_data, *participant.write_data):
            config.datum(name)
            config.mesh(mesh_name)
        for point in participant.watch_points:
            resolved = config.mesh(point.mesh)
            if len(point.coordinate) != resolved.dimensions:
                raise PreciceConfigError(
                    f"{source}: watch-point {point.name!r} has "
                    f"{len(point.coordinate)} coordinates but mesh {resolved.name!r} is "
                    f"{resolved.dimensions}-dimensional"
                )
    return config


def read_precice_config(path: Path) -> PreciceConfig:
    """Read and parse a ``precice-config.xml`` from disk, recording its sha256."""
    import hashlib

    raw = path.read_bytes()
    return parse_precice_config(
        raw.decode("utf-8"), source=path, sha256=hashlib.sha256(raw).hexdigest()
    )


# --------------------------------------------------------------------------------------
# Expectations (ADR-036 gate C1)
# --------------------------------------------------------------------------------------


class PreciceConfigExpectation(BaseModel):
    """What a campaign asserts about the configuration BEFORE it runs it."""

    model_config = _STRICT

    participants: tuple[str, ...] = Field(..., min_length=2)
    coupling_scheme: CouplingSchemeKind
    m2n_kind: str = Field(..., min_length=1)
    time_window_size: float = Field(..., gt=0.0)
    max_iterations: int = Field(..., ge=1)
    convergence_limits: Mapping[str, float]
    convergence_kinds: Mapping[str, str] = Field(
        default_factory=dict,
        description=(
            "data name -> measure tag, e.g. 'relative-convergence-measure'. Checked "
            "because a limit of 1e-4 means something entirely different as an ABSOLUTE "
            "measure than as a relative one, and swapping the two would sail past a "
            "limits-only comparison."
        ),
    )
    watch_points: Mapping[str, tuple[float, ...]]  # "Participant/WatchPoint" -> coordinate
    acceleration_kind: str = Field(..., min_length=1)


def assert_config(config: PreciceConfig, expected: PreciceConfigExpectation) -> None:
    """Fail loud on ANY drift from `expected`, listing every mismatch at once.

    Deliberately reports the full set rather than the first failure: when an upstream
    pin moves, knowing all of what changed is what tells you whether the case is still
    the benchmark you pre-registered against.

    ``max_time`` is NOT checked here — it is the one value a campaign may shorten for
    budget (gate C2, :func:`rewrite_max_time`).
    """
    problems: list[str] = []

    got_participants = tuple(sorted(p.name for p in config.participants))
    want_participants = tuple(sorted(expected.participants))
    if got_participants != want_participants:
        problems.append(f"participants {got_participants} != expected {want_participants}")

    scheme = config.coupling_scheme
    if scheme.kind != expected.coupling_scheme:
        problems.append(f"coupling scheme {scheme.kind!r} != expected {expected.coupling_scheme!r}")
    if scheme.time_window_size != expected.time_window_size:
        problems.append(
            f"time-window-size {scheme.time_window_size!r} != expected "
            f"{expected.time_window_size!r}"
        )
    if scheme.max_iterations != expected.max_iterations:
        problems.append(
            f"max-iterations {scheme.max_iterations!r} != expected {expected.max_iterations!r}"
        )
    if scheme.acceleration is None:
        problems.append(f"no acceleration block; expected {expected.acceleration_kind!r}")
    elif scheme.acceleration.kind != expected.acceleration_kind:
        problems.append(
            f"acceleration {scheme.acceleration.kind!r} != expected {expected.acceleration_kind!r}"
        )

    got_kinds = tuple(sorted({m.kind for m in config.m2n}))
    if got_kinds != (expected.m2n_kind,):
        problems.append(f"m2n kinds {got_kinds} != expected ('{expected.m2n_kind}',)")

    got_limits = {m.data: m.limit for m in scheme.convergence_measures}
    if got_limits != dict(expected.convergence_limits):
        problems.append(
            f"convergence limits {got_limits} != expected {dict(expected.convergence_limits)}"
        )
    if expected.convergence_kinds:
        got_kinds_by_data = {m.data: m.kind for m in scheme.convergence_measures}
        if got_kinds_by_data != dict(expected.convergence_kinds):
            problems.append(
                f"convergence measure kinds {got_kinds_by_data} != expected "
                f"{dict(expected.convergence_kinds)}"
            )
    if len(scheme.convergence_measures) != len(got_limits):
        problems.append(
            f"{len(scheme.convergence_measures)} convergence measures collapse to "
            f"{len(got_limits)} data names — two measures on the same data would be "
            "invisible to a data-keyed comparison"
        )

    for key, coordinate in expected.watch_points.items():
        participant_name, _, point_name = key.partition("/")
        try:
            point = config.watch_point(participant_name, point_name)
        except PreciceConfigError as exc:
            problems.append(str(exc))
            continue
        if point.coordinate != tuple(coordinate):
            problems.append(
                f"watch-point {key} at {point.coordinate} != expected {tuple(coordinate)}"
            )

    if problems:
        raise PreciceConfigError(
            f"{config.source_path}: configuration does not match the pre-registered "
            f"expectation ({len(problems)} mismatch(es)):\n  - " + "\n  - ".join(problems)
        )


# --------------------------------------------------------------------------------------
# The single permitted mutation (ADR-036 gate C2)
# --------------------------------------------------------------------------------------

_MAX_TIME_RE = re.compile(r'(<max-time\s+value=")([^"]*)("\s*/>)')


def rewrite_max_time(source: Path, dest: Path, *, max_time: float) -> PreciceConfig:
    """Copy `source` to `dest` with ``<max-time>`` set to `max_time`; verify nothing else moved.

    The verification is structural, not a promise: `dest` is re-parsed and the resulting
    model must equal the source model under a ``max_time``-only update. Editing any other
    knob — ``max-iterations``, a convergence limit, the acceleration — therefore aborts
    the run instead of silently producing an easier problem to solve.
    """
    if max_time <= 0.0:
        raise PreciceConfigError(f"max_time must be positive, got {max_time!r}")
    original = read_precice_config(source)

    text = source.read_text(encoding="utf-8")
    matches = _MAX_TIME_RE.findall(text)
    if len(matches) != 1:
        raise PreciceConfigError(
            f"{source}: found {len(matches)} <max-time value=.../> elements, expected exactly "
            "one — refusing to guess which one bounds the campaign"
        )
    rewritten = _MAX_TIME_RE.sub(rf"\g<1>{max_time!r}\g<3>", text, count=1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rewritten, encoding="utf-8")

    produced = read_precice_config(dest)
    want = original.model_copy(
        update={
            "source_path": produced.source_path,
            "source_sha256": produced.source_sha256,
            "coupling_scheme": original.coupling_scheme.model_copy(update={"max_time": max_time}),
        }
    )
    if produced != want:
        raise PreciceConfigError(
            f"{dest}: rewriting <max-time> changed something else as well — refusing to run. "
            "The ONLY permitted modification to the upstream configuration is max-time "
            "(ADR-036 C2).\n"
            f"  produced: {produced.model_dump_json()}\n"
            f"  expected: {want.model_dump_json()}"
        )
    return produced


def describe(config: PreciceConfig) -> Sequence[str]:
    """Human-readable one-line-per-fact summary, for campaign logs and bundles."""
    scheme = config.coupling_scheme
    lines = [
        f"participants: {', '.join(p.name for p in config.participants)}",
        f"coupling-scheme: {scheme.kind} (first={scheme.first}, second={scheme.second})",
        f"time-window-size: {scheme.time_window_size:g}",
        f"max-time: {'unset' if scheme.max_time is None else format(scheme.max_time, 'g')}",
        f"max-iterations: {scheme.max_iterations}",
    ]
    for measure in scheme.convergence_measures:
        lines.append(
            f"convergence: {measure.kind} {measure.data}@{measure.mesh} <= {measure.limit:g}"
        )
    if scheme.acceleration is not None:
        lines.append(
            f"acceleration: {scheme.acceleration.kind} "
            f"(filter={scheme.acceleration.filter_type}, "
            f"initial-relaxation={scheme.acceleration.initial_relaxation})"
        )
    for connection in config.m2n:
        lines.append(
            f"m2n: {connection.kind} acceptor={connection.acceptor} "
            f"connector={connection.connector} exchange-directory="
            f"{connection.exchange_directory}"
        )
    for participant in config.participants:
        for point in participant.watch_points:
            lines.append(
                f"watch-point: {participant.name}/{point.name} on {point.mesh} at "
                f"{point.coordinate}"
            )
    return tuple(lines)
