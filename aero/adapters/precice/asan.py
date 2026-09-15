"""Reader for the AddressSanitizer reports a sanitizer-built participant writes (Stage 20).

The flexible arm's CalculiX participant has died five times of ``corrupted double-linked
list``: glibc trips over poisoned heap metadata thousands of coupling windows after the
invalid write that poisoned it (N3 attempt 2 died with the solid quiet for its last 7 698
windows). ``calculix-precice-address.sif`` is the same recipe built with ``-fsanitize=address``
(``containers/calculix-precice.Dockerfile``, ``SANITIZE=address``), and ``ASAN_OPTIONS`` in
the launcher points its reports at ``/case/asan-solid`` -- so a report lands beside the run
as ``<run>/tutorial/asan-solid.<pid>`` and names the write where it HAPPENS.

This module turns that text into a typed record, and classifies every frame by WHO OWNS
THE LINE, because that is the question ADR-045 R6 asks of the result:

* ``adapter`` -- the preCICE CalculiX adapter, which the Dockerfile clones to
  ``/src/calculix-adapter`` and compiles itself. That tree carries its OWN copies of
  ``ccx_2.20.c`` and ``nonlingeo_precice.c``; an ASan frame at ``ccx_2.20.c:<n>`` is
  therefore ours or upstream's depending on its PATH, never on its basename.
* ``calculix-upstream`` -- CalculiX 2.20's own Fortran and C, unpacked to
  ``/src/CalculiX/ccx_2.20/src`` and archived into the binary. Not maintained here.
* ``runtime`` -- libasan's interceptors, glibc, libgfortran, preCICE, MPI, SPOOLES: frames
  with no source file, or with a source path inside a library we did not compile.
* ``unknown`` -- a source path that matches none of the pinned rules, or an unsymbolized
  frame inside our own binary. Classified honestly as such; a verdict never rests on it.

The one report known NOT to be the bug is pinned here by content: the gfortran string
compare reading 12 bytes off a 5-byte ``'NODE'`` literal at ``keystart.f:71`` during deck
parsing. It is a READ of read-only data, it fires on every run including two that
completed 8000 windows, and a read cannot corrupt heap metadata (handoff §6.72,
``168290f``). It is flagged ``known_benign`` and never decides anything.

Everything is stdlib + pydantic (Invariant 1).
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

FrameOwner = Literal["adapter", "calculix-upstream", "runtime", "unknown"]
#: ``other`` is a stack ASan prints for context (a thread's creation, the stack frame an
#: address lies in) -- never a site.
StackRole = Literal["access", "allocated", "freed", "other"]

#: Pinned from ``containers/calculix-precice.Dockerfile``: ``git clone ... /src/calculix-adapter``
#: and ``tar xjf`` into ``/src/CalculiX/ccx_<version>``. The one ASan report already on disk
#: (``hg2007_flexible_foil-20260915-113507/tutorial/asan-solid.2431025``) prints exactly these
#: absolute prefixes: ``/src/CalculiX/ccx_2.20/src/keystart.f:71`` and
#: ``/src/calculix-adapter/ccx_2.20.c:195``.
ADAPTER_SOURCE_PREFIX = "/src/calculix-adapter/"
CALCULIX_SOURCE_PREFIX = "/src/CalculiX/"
#: The participant binary. A frame in it that the symbolizer could not resolve to a source
#: line is ``unknown``, not ``runtime``: it is our code, unread.
PARTICIPANT_BINARY = "/opt/calculix/bin/ccx_preCICE"

#: The adapter tree's own source files (its Makefile's SCCXC / SCCXF / OCCXC lists and the
#: headers they include), used ONLY as a fallback for a frame whose path was recorded
#: relative to the build directory. ``ccx_2.20.c`` and ``CalculiX.h`` are deliberately
#: absent: CalculiX ships files of the same names, so a bare one is ambiguous and stays
#: ``unknown``.
ADAPTER_SOURCE_BASENAMES = frozenset(
    {
        "nonlingeo_precice.c",
        "dyna_precice.c",
        "linstatic_precice.c",
        "CCXHelpers.c",
        "PreciceInterface.c",
        "ConfigReader.cpp",
        "2D3DCoupling.cpp",
        "OutputBuffer.cpp",
        "getflux.f",
        "getkdeltatemp.f",
        "getelementgausspointcoords.f",
        "CCXHelpers.h",
        "PreciceInterface.h",
        "ConfigReader.h",
        "2D3DCoupling.h",
        "OutputBuffer.h",
        "fkYAML.hpp",
    }
)

#: Adapter files that are verbatim-derived copies of CalculiX's own sources (the main
#: program and the two solution drivers). Nearly every heap object of the dynamic step is
#: ``NNEW``/``RENEW``'d from these lines, so an ALLOCATION site here says only that the
#: object was allocated where CalculiX allocates it -- not that we sized it wrongly. The
#: verdict treats an allocation-only attribution to one of these as a human call.
ADAPTER_UPSTREAM_DERIVED_BASENAMES = frozenset(
    {"ccx_2.20.c", "nonlingeo_precice.c", "dyna_precice.c", "linstatic_precice.c"}
)

#: Source paths that belong to libraries we did not compile: libasan's own tree
#: (``../../../../src/libsanitizer/...``) and glibc's (``../sysdeps/...``, ``../csu/...``).
RUNTIME_PATH_MARKERS = (
    "libsanitizer/",
    "../sysdeps/",
    "../csu/",
    "../nptl/",
    "../misc/",
    "../stdlib/",
    "../string/",
    "../io/",
    "../libio/",
    "libgfortran/",
    "/usr/include/",
)

#: CalculiX's own allocator wrappers (``NNEW`` / ``RENEW`` / ``SFREE`` expand to these).
#: Every allocation in the binary -- the adapter's included -- passes through them, so as
#: the FIRST source frame of an allocation or free stack they name the wrapper, never the
#: caller that sized the object. They are treated as runtime for site determination; the
#: frame above them is the line that matters. (A bug inside the wrapper itself would then
#: be attributed to its caller -- recorded here rather than discovered.)
CALCULIX_ALLOCATOR_WRAPPERS = frozenset({"u_calloc.c", "u_malloc.c", "u_realloc.c", "u_free.c"})

#: The known benign report, pinned by (kind, access, site basename, site line).
KNOWN_BENIGN_KIND = "global-buffer-overflow"
KNOWN_BENIGN_ACCESS = "READ"
KNOWN_BENIGN_SITE_BASENAME = "keystart.f"
KNOWN_BENIGN_SITE_LINE = 71

#: Bug classes whose report can explain poisoned heap metadata: the heap-family errors,
#: including the allocator-argument overflows (a garbage size is the classic sizing bug).
#: A WRITE of another class -- a SEGV on a wild pointer, a stack or global overflow -- is a
#: real finding but cannot be the write that poisoned a heap chunk header (ASan would have
#: reported a store into a heap redzone as a heap-family error), and a ``*-param-overlap``
#: is a misuse of an overlapping copy, not an out-of-bounds store. Those are recorded and
#: handed to a human rather than read as the bug.
HEAP_KINDS = frozenset(
    {
        "heap-buffer-overflow",
        "heap-use-after-free",
        "double-free",
        "bad-free",
        "alloc-dealloc-mismatch",
        "new-delete-type-mismatch",
        "calloc-overflow",
        "reallocarray-overflow",
        "pvalloc-overflow",
        "allocation-size-too-big",
        "use-after-poison",
        "container-overflow",
        "negative-size-param",
    }
)

#: Multi-word header wordings whose canonical class only appears on the SUMMARY line
#: (``asan_errors.cpp``); used when a report is cut before its SUMMARY.
_HEADER_KIND_PREFIXES = (
    ("attempting double-free", "double-free"),
    ("attempting free on address which was not malloc", "bad-free"),
    ("calloc parameters overflow", "calloc-overflow"),
    ("reallocarray parameters overflow", "reallocarray-overflow"),
    ("pvalloc parameters overflow", "pvalloc-overflow"),
    ("requested allocation size", "allocation-size-too-big"),
    ("failed to allocate", "mmap-failure"),
    ("failed to mmap", "mmap-failure"),
    ("out of memory", "out-of-memory"),
    ("invalid allocation alignment", "invalid-allocation-alignment"),
    ("attempting to call malloc_usable_size", "bad-malloc_usable_size"),
)

_HEADER_RE = re.compile(r"^==(?P<pid>\d+)==ERROR: AddressSanitizer:?\s+(?P<rest>.+?)\s*$")
_ADDRESS_RE = re.compile(r"(?:on|at) (?:unknown )?(?:address )?(?P<addr>0x[0-9a-fA-F]+)")
_ACCESS_RE = re.compile(
    r"^(?P<access>READ|WRITE) of size (?P<size>\d+) at (?P<addr>0x[0-9a-fA-F]+)"
)
_SIGNAL_ACCESS_RE = re.compile(
    r"^==\d+==The signal is caused by a (?P<access>READ|WRITE|UNKNOWN) memory access"
)
_FRAME_RE = re.compile(r"^\s*#(?P<index>\d+)\s+0x[0-9a-fA-F]+\s+in\s+(?P<body>.+?)\s*$")
_BARE_FRAME_RE = re.compile(r"^\s*#(?P<index>\d+)\s+0x[0-9a-fA-F]+\s+(?P<loc>\(.*\))\s*$")
_BUILDID_RE = re.compile(r"\s*\(BuildId: [0-9a-fA-F]+\)\s*$")
_LOCATION_RE = re.compile(r"^(?P<path>[^()\s].*?):(?P<line>\d+)(?::\d+)?$")
_STACK_ROLE_RE = re.compile(
    r"^(?:previously )?(?P<role>allocated|freed) by thread T\d+(?: \(.*\))? here:\s*$"
)
#: Context sections ASan prints after the stacks that matter; their frames are kept under
#: role ``other`` so they can never become a site.
_OTHER_SECTION_RE = re.compile(
    r"^(?:Thread T\d+(?: \(.*\))? created by T\d+(?: \(.*\))? here:"
    r"|.* is located in stack of thread T\d+.* in frame$"
    r"|This frame has \d+ object\(s\):.*)$"
)
_SUMMARY_RE = re.compile(r"^SUMMARY: AddressSanitizer: (?P<summary>.+?)\s*$")
_ABORTING_RE = re.compile(r"^==\d+==ABORTING\s*$")


class AsanFrame(BaseModel):
    """One symbolized stack frame."""

    model_config = _STRICT

    index: int = Field(..., ge=0)
    function: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1, description="The frame's location text, verbatim.")
    path: str | None = Field(default=None, description="Source path when the frame has one.")
    line: int | None = Field(default=None, ge=0)
    owner: FrameOwner

    @property
    def site_text(self) -> str:
        where = f"{self.path}:{self.line}" if self.path is not None else self.location
        return f"#{self.index} {self.function} at {where} [{self.owner}]"

    @property
    def basename(self) -> str | None:
        return None if self.path is None else PurePosixPath(self.path).name


class AsanStack(BaseModel):
    """One stack in a report: the faulting access, where the object was allocated / freed,
    or context ASan prints alongside (``other``)."""

    model_config = _STRICT

    role: StackRole
    frames: tuple[AsanFrame, ...] = Field(default=())

    @property
    def site(self) -> AsanFrame | None:
        """The first frame that is not runtime -- the line the report NAMES."""
        if self.role == "other":
            return None
        for frame in self.frames:
            if frame.owner != "runtime":
                return frame
        return None


class AsanReport(BaseModel):
    """One ``==pid==ERROR: AddressSanitizer: ...`` report."""

    model_config = _STRICT

    pid: int = Field(..., ge=1)
    kind: str = Field(..., min_length=1, description="Bug class, e.g. heap-buffer-overflow.")
    header: str = Field(..., min_length=1, description="The ERROR line, verbatim.")
    access: str | None = Field(default=None, description="READ / WRITE / UNKNOWN when stated.")
    size: int | None = Field(default=None, ge=0)
    address: str | None = None
    summary: str | None = None
    stacks: tuple[AsanStack, ...] = Field(default=())

    @property
    def access_stack(self) -> AsanStack | None:
        for stack in self.stacks:
            if stack.role == "access":
                return stack
        return None

    @property
    def sites(self) -> tuple[AsanFrame, ...]:
        """The named line of every stack that has one, faulting access first."""
        return tuple(s.site for s in self.stacks if s.site is not None)

    @property
    def owners(self) -> frozenset[str]:
        return frozenset(site.owner for site in self.sites)

    @property
    def known_benign(self) -> bool:
        """The pinned keystart.f:71 READ -- fires on every run, and a read cannot corrupt."""
        if self.kind != KNOWN_BENIGN_KIND or self.access != KNOWN_BENIGN_ACCESS:
            return False
        access = self.access_stack
        site = access.site if access is not None else None
        if site is None or site.path is None:
            return False
        return site.basename == KNOWN_BENIGN_SITE_BASENAME and site.line == KNOWN_BENIGN_SITE_LINE

    @property
    def heap_relevant(self) -> bool:
        """Could this report explain poisoned heap metadata? Heap-family classes only."""
        return self.kind in HEAP_KINDS

    def one_line(self) -> str:
        what = self.kind if self.access is None else f"{self.kind} {self.access}"
        if self.size is not None:
            what += f" of size {self.size}"
        sites = "; ".join(f"{s.role}: {s.site.site_text}" for s in self.stacks if s.site)
        return f"pid {self.pid}: {what} -- {sites or 'no source-level frame'}"


def classify_frame_path(path: str | None) -> FrameOwner:
    """Who owns the source line a frame points at, by the pinned path rules above."""
    if path is None:
        return "runtime"
    # A path that climbs out of its tree is not one either prefix can vouch for -- except
    # the library trees ASan itself prints relative (../sysdeps/..., libsanitizer/...).
    if ("/../" in path or path.startswith("../")) and not any(
        marker in path for marker in RUNTIME_PATH_MARKERS
    ):
        return "unknown"
    if path.startswith(ADAPTER_SOURCE_PREFIX):
        return "adapter"
    if path.startswith(CALCULIX_SOURCE_PREFIX):
        if PurePosixPath(path).name in CALCULIX_ALLOCATOR_WRAPPERS:
            return "runtime"
        return "calculix-upstream"
    if any(marker in path for marker in RUNTIME_PATH_MARKERS):
        return "runtime"
    if (
        not path.startswith("/")
        and "ccx_2.20/src" not in path
        and PurePosixPath(path).name in ADAPTER_SOURCE_BASENAMES
    ):
        return "adapter"
    return "unknown"


def _split_body(body: str) -> tuple[str, str]:
    """``<function> <location>`` -- the location is parenthesised or the last token."""
    if body.endswith(")") and " (" in body:
        head, _, tail = body.rpartition(" (")
        return (head.strip() or "??"), "(" + tail
    if " " in body:
        function, location = body.rsplit(" ", 1)
        return (function.strip() or "??"), location
    return "??", body


def _frame_from_line(line: str) -> AsanFrame | None:
    match = _FRAME_RE.match(line)
    if match is None:
        bare = _BARE_FRAME_RE.match(line)
        if bare is None:
            return None
        location = bare.group("loc")
        owner: FrameOwner = "unknown" if PARTICIPANT_BINARY in location else "runtime"
        return AsanFrame(
            index=int(bare.group("index")), function="??", location=location, owner=owner
        )
    body = _BUILDID_RE.sub("", match.group("body")).strip()
    function, location = _split_body(body)
    path: str | None = None
    line_no: int | None = None
    loc = _LOCATION_RE.match(location)
    if loc is not None:
        path = loc.group("path")
        line_no = int(loc.group("line"))
        owner = classify_frame_path(path)
    elif PARTICIPANT_BINARY in location and function != "_start":
        # Our own binary, unsymbolized: not a library, and not a line we can read.
        owner = "unknown"
    else:
        owner = "runtime"
    return AsanFrame(
        index=int(match.group("index")),
        function=function,
        location=location,
        path=path,
        line=line_no,
        owner=owner,
    )


def _kind_from_header(rest: str) -> str:
    """The bug class from the text after ``AddressSanitizer:`` (fallback; SUMMARY wins)."""
    lowered = rest.strip().lower()
    for prefix, kind in _HEADER_KIND_PREFIXES:
        if lowered.startswith(prefix):
            return kind
    words = rest.split()
    if not words:
        return "unknown"
    if words[0] == "attempting" and len(words) >= 2:
        return words[1].rstrip(":")
    return words[0].rstrip(":")


class _Draft:
    def __init__(self, pid: int, header: str) -> None:
        self.pid = pid
        self.header = header
        rest = re.sub(r"^==\d+==ERROR: AddressSanitizer:?\s*", "", header)
        self.kind = _kind_from_header(rest)
        addr = _ADDRESS_RE.search(rest)
        self.address: str | None = addr.group("addr") if addr else None
        self.access: str | None = None
        self.size: int | None = None
        self.summary: str | None = None
        self.stacks: list[tuple[StackRole, list[AsanFrame]]] = [("access", [])]
        self.collecting = True

    def finish(self) -> AsanReport:
        if self.summary is not None:
            # SUMMARY carries the canonical class name for every report shape.
            canonical = self.summary.split()[0].rstrip(":") if self.summary.split() else ""
            if canonical:
                self.kind = canonical
        stacks = tuple(
            AsanStack(role=role, frames=tuple(frames))
            for role, frames in self.stacks
            if frames or role == "access"
        )
        return AsanReport(
            pid=self.pid,
            kind=self.kind,
            header=self.header,
            access=self.access,
            size=self.size,
            address=self.address,
            summary=self.summary,
            stacks=stacks,
        )


def parse_asan_reports(text: str) -> tuple[AsanReport, ...]:
    """Every report in one ``asan-solid.<pid>`` file, in order.

    With ``halt_on_error=0`` more than one report can land in a file; without
    ``-fsanitize-recover`` the first is also the last. Both shapes parse the same way.
    """
    reports: list[AsanReport] = []
    draft: _Draft | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        header = _HEADER_RE.match(line)
        if header is not None:
            if draft is not None:
                reports.append(draft.finish())
            draft = _Draft(int(header.group("pid")), line.strip())
            continue
        if draft is None:
            continue
        if _ABORTING_RE.match(line):
            reports.append(draft.finish())
            draft = None
            continue
        access = _ACCESS_RE.match(line)
        if access is not None:
            draft.access = access.group("access")
            draft.size = int(access.group("size"))
            draft.address = draft.address or access.group("addr")
            continue
        signal = _SIGNAL_ACCESS_RE.match(line)
        if signal is not None:
            draft.access = signal.group("access")
            continue
        role = _STACK_ROLE_RE.match(line)
        if role is not None:
            draft.stacks.append((role.group("role"), []))  # type: ignore[arg-type]
            draft.collecting = True
            continue
        if _OTHER_SECTION_RE.match(line.strip()):
            draft.stacks.append(("other", []))
            draft.collecting = True
            continue
        summary = _SUMMARY_RE.match(line)
        if summary is not None:
            draft.summary = summary.group("summary")
            draft.collecting = False
            continue
        if not draft.collecting:
            continue
        frame = _frame_from_line(line)
        if frame is not None:
            draft.stacks[-1][1].append(frame)
    if draft is not None:
        reports.append(draft.finish())
    return tuple(reports)


def read_asan_reports(path: Path) -> tuple[AsanReport, ...]:
    """Parse one report file. Binary-safe: a file cut mid-write must still read."""
    return parse_asan_reports(path.read_text(encoding="utf-8", errors="replace"))


def find_asan_reports(case_root: Path, *, log_stem: str = "asan-solid") -> tuple[Path, ...]:
    """The ``<log_stem>.<pid>`` files ASan wrote into the case root, oldest first.

    Ordered by modification time, then by numeric pid -- NOT by name, where
    ``asan-solid.10000`` would sort before ``asan-solid.999``.
    """

    def key(p: Path) -> tuple[float, int, str]:
        suffix = p.name[len(log_stem) + 1 :]
        pid = int(suffix) if suffix.isdigit() else -1
        return (p.stat().st_mtime, pid, p.name)

    return tuple(sorted((p for p in case_root.glob(f"{log_stem}.*") if p.is_file()), key=key))


__all__ = [
    "ADAPTER_SOURCE_BASENAMES",
    "ADAPTER_SOURCE_PREFIX",
    "ADAPTER_UPSTREAM_DERIVED_BASENAMES",
    "CALCULIX_ALLOCATOR_WRAPPERS",
    "CALCULIX_SOURCE_PREFIX",
    "HEAP_KINDS",
    "KNOWN_BENIGN_ACCESS",
    "KNOWN_BENIGN_KIND",
    "KNOWN_BENIGN_SITE_BASENAME",
    "KNOWN_BENIGN_SITE_LINE",
    "PARTICIPANT_BINARY",
    "RUNTIME_PATH_MARKERS",
    "AsanFrame",
    "AsanReport",
    "AsanStack",
    "FrameOwner",
    "StackRole",
    "classify_frame_path",
    "find_asan_reports",
    "parse_asan_reports",
    "read_asan_reports",
]
