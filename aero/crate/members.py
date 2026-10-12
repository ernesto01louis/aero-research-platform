"""Member enumeration, archive safety and the ``SHA256SUMS`` file (ADR-047 D1).

A crate is read into memory as ``{path: bytes}`` before anything is parsed, from either a
directory or a ZIP_STORED archive. Everything an attacker or a careless tool could slip in is
refused up front:

- zip-slip (``..``), absolute paths, backslashes, NUL;
- symlinks, devices, FIFOs and other non-regular files;
- duplicate or case-colliding names, Windows device names, OS junk (``.DS_Store``, ``__MACOSX``);
- compressed or encrypted entries, archive comments, prepended data;
- anything outside the closed layout;
- oversize members, too many members.

The reader never extracts to disk.
"""

from __future__ import annotations

import io
import os
import re
import stat
import zipfile
from pathlib import Path

from aero.crate.errors import CrateFormatError, CrateIntegrityError, CratePathError
from aero.crate.model_base import MEMBER_PATH_RE

__all__ = [
    "MAX_MEMBERS",
    "MAX_MEMBER_BYTES",
    "MAX_TOTAL_BYTES",
    "check_member_name",
    "format_sha256sums",
    "pack_members",
    "parse_sha256sums",
    "read_members",
]

MAX_MEMBERS = 64
MAX_MEMBER_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024

SUMS = "SHA256SUMS"
TOP_LEVEL = frozenset(
    {SUMS, "aero-crate.json", "ro-crate-metadata.json", "prov.json", "result.json"}
)
SUBDIRS = frozenset({"configs", "evidence"})
# The two records whose ABSENCE is load-bearing (ADR-045; tests/unit/
# test_adr045_r3_record_stays_absent.py). No crate may carry a member by either name.
FORBIDDEN_BASENAMES = frozenset({"stage20_adr045_r3.json", "stage20_n3_confirmation.json"})
_WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_JUNK = frozenset({".ds_store", "__macosx", "thumbs.db", "desktop.ini"})
_MEMBER_RE = re.compile(MEMBER_PATH_RE)
_SUMS_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


def check_member_name(name: str) -> None:
    """Refuse an unsafe or out-of-layout member name. Raises :class:`CratePathError`."""
    if not name or "\x00" in name or "\\" in name or name.startswith("/") or ":" in name:
        raise CratePathError(f"unsafe member name {name!r}")
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise CratePathError(f"unsafe member path {name!r} (empty, '.' or '..' segment)")
    if any(p.lower() in _JUNK for p in parts):
        raise CratePathError(
            f"{name!r} is operating-system junk; re-pack the crate with `python -m aero.crate pack`"
        )
    if name == SUMS:
        return
    if len(name) > 128 or not _MEMBER_RE.match(name):
        raise CratePathError(f"member name {name!r} is outside format v1's naming rule")
    if any(p.split(".")[0] in _WINDOWS_DEVICES for p in parts):
        raise CratePathError(f"member name {name!r} uses a Windows device name")
    if parts[-1] in FORBIDDEN_BASENAMES:
        raise CratePathError(f"member name {name!r} is an ADR-045 record that must never exist")
    if len(parts) == 1 and name not in TOP_LEVEL:
        raise CratePathError(f"unknown top-level member {name!r}")
    if len(parts) == 2 and parts[0] not in SUBDIRS:
        raise CratePathError(f"unknown member directory {parts[0]!r}")


def _admit(members: dict[str, bytes], name: str, data: bytes, total: list[int]) -> None:
    check_member_name(name)
    folded = name.casefold()
    if any(folded == existing.casefold() for existing in members):
        raise CratePathError(f"duplicate or case-colliding member {name!r}")
    if len(members) >= MAX_MEMBERS:
        raise CratePathError(f"more than {MAX_MEMBERS} members")
    if len(data) > MAX_MEMBER_BYTES:
        raise CratePathError(f"member {name!r} exceeds {MAX_MEMBER_BYTES} bytes")
    total[0] += len(data)
    if total[0] > MAX_TOTAL_BYTES:
        raise CratePathError(f"crate exceeds {MAX_TOTAL_BYTES} bytes in total")
    members[name] = data


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise CratePathError(f"{path.name!r} is not a regular file")
        if st.st_size > MAX_MEMBER_BYTES:
            raise CratePathError(f"member {path.name!r} exceeds {MAX_MEMBER_BYTES} bytes")
        chunks = []
        remaining = MAX_MEMBER_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1 << 20))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_MEMBER_BYTES:
            raise CratePathError(f"member {path.name!r} exceeds {MAX_MEMBER_BYTES} bytes")
        return data
    finally:
        os.close(fd)


def _read_directory(root: Path) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    total = [0]

    def walk(directory: Path, prefix: str, depth: int) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda e: e.name):
                name = f"{prefix}{entry.name}"
                if entry.is_symlink():
                    raise CratePathError(f"{name!r} is a symlink; crates hold regular files only")
                if entry.is_dir(follow_symlinks=False):
                    if depth >= 1 or entry.name not in SUBDIRS:
                        check_member_name(f"{name}/x")  # names the junk/unknown directory
                        raise CratePathError(f"unexpected directory {name!r}")
                    walk(Path(entry.path), f"{name}/", depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    check_member_name(name)
                    _admit(members, name, _read_regular(Path(entry.path)), total)
                else:
                    raise CratePathError(f"{name!r} is not a regular file")

    if root.is_symlink():
        raise CratePathError(f"{root} is a symlink")
    walk(root, "", 0)
    return members


def _read_zip(data: bytes, origin: str) -> dict[str, bytes]:
    if not data.startswith(b"PK\x03\x04"):
        raise CrateFormatError(f"{origin}: not a ZIP archive starting at byte 0")
    if len(data) > MAX_TOTAL_BYTES + 1024 * 1024:
        raise CratePathError(f"{origin}: archive exceeds the size cap")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CrateFormatError(f"{origin}: corrupt ZIP archive: {exc}") from exc
    with archive:
        if archive.comment:
            raise CrateFormatError(f"{origin}: archive comments are forbidden")
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise CratePathError(f"{origin}: more than {MAX_MEMBERS} members")
        if sorted(i.header_offset for i in infos)[:1] not in ([], [0]):
            raise CrateFormatError(f"{origin}: data before the first member")
        members: dict[str, bytes] = {}
        total = [0]
        for info in infos:
            if info.is_dir():
                raise CratePathError(
                    f"{origin}: directory entries are forbidden ({info.filename!r})"
                )
            if info.flag_bits & 0x1:
                raise CratePathError(f"{origin}: encrypted member {info.filename!r}")
            if info.compress_type != zipfile.ZIP_STORED:
                raise CrateFormatError(f"{origin}: member {info.filename!r} is compressed")
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG):
                raise CratePathError(f"{origin}: member {info.filename!r} is not a regular file")
            if info.file_size > MAX_MEMBER_BYTES:
                raise CratePathError(f"{origin}: member {info.filename!r} exceeds the size cap")
            check_member_name(info.filename)
            try:
                content = archive.read(info)
            except (zipfile.BadZipFile, ValueError) as exc:  # CRC mismatch, truncation
                raise CrateIntegrityError(f"{origin}: member {info.filename!r}: {exc}") from exc
            _admit(members, info.filename, content, total)
        return members


def read_members(path: Path) -> dict[str, bytes]:
    """Read a crate (directory or ZIP_STORED archive) into memory, refusing anything unsafe."""
    if path.is_symlink():
        raise CratePathError(f"{path} is a symlink")
    if path.is_dir():
        return _read_directory(path)
    if path.is_file():
        return _read_zip(_read_whole(path), str(path))
    raise CratePathError(f"{path} is neither a crate directory nor a crate archive")


def _read_whole(path: Path) -> bytes:
    size = path.stat().st_size
    if size > MAX_TOTAL_BYTES + 1024 * 1024:
        raise CratePathError(f"{path}: archive exceeds the size cap")
    return path.read_bytes()


def format_sha256sums(digests: dict[str, str]) -> bytes:
    """The coreutils ``sha256sum`` format, path-sorted, LF, one final newline."""
    lines = [f"{digests[name]}  {name}\n" for name in sorted(digests) if name != SUMS]
    return "".join(lines).encode("ascii")


def parse_sha256sums(data: bytes) -> dict[str, str]:
    """Strictly parse ``SHA256SUMS``; the result maps member path to sha256."""
    if not data.endswith(b"\n") or b"\r" in data:
        raise CrateFormatError("SHA256SUMS must use LF line endings and end with a newline")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CrateFormatError("SHA256SUMS must be ASCII") from exc
    out: dict[str, str] = {}
    previous = ""
    for n, line in enumerate(text[:-1].split("\n"), 1):
        m = _SUMS_LINE.match(line)
        if not m:
            raise CrateFormatError(f"SHA256SUMS line {n} is malformed: {line!r}")
        digest, name = m.groups()
        check_member_name(name)
        if name == SUMS or name in out or name <= previous:
            raise CrateFormatError(
                f"SHA256SUMS line {n}: duplicate, self-listed or unsorted {name!r}"
            )
        out[name] = digest
        previous = name
    return out


def pack_members(members: dict[str, bytes]) -> bytes:
    """A deterministic ZIP_STORED archive: sorted names, fixed timestamps and modes, no extras."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(members):
            check_member_name(name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, members[name])
    return buffer.getvalue()
