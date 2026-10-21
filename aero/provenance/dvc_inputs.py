"""The declared DVC inputs of a run: the strict pointer parser and the one read path (ADR-052).

Since Stage 23 `dvc_input_hash` is a content address of the `.dvc`-tracked inputs a case
**declares** (scheme `declared-dvc-pointers-md5/v1`): each output's repo-relative path, md5 and
size, read from its git-tracked pointer at `HEAD`. No `dvc` binary, remote, cache or credential
is involved, so the value is the same on every machine and recomputable from git alone.

Three functions carry the contract:

- `parse_pointer` reads one DVC-3 file pointer, strictly and with the stdlib only (a core module
  may not load `yaml` or `dvc`): exactly one `outs` entry with `hash: md5`, `md5`, `path`, `size`
  and an optional `remote` (excluded from the preimage). Directory outputs, md5-dos2unix
  pointers, unknown keys and paths that leave the pointer's directory are refused.
- `resolve_declared` turns a case's declaration (pointer paths) into the run's inputs. A pointer
  must be committed at `HEAD` and the working copy must equal it, even for an `--allow-dirty`
  run, or the recorded value would not be recomputable from git.
- `read_declared_input` is the one read path for a DVC-tracked file. It returns the bytes of a
  declared input after checking their md5 and size against the pointer, and refuses an
  undeclared DVC output, a member of a directory output, a `dvc.lock` stage output, and a file
  that is neither git-tracked nor declared (an absolute path outside the checkout is covered by
  neither `git_sha` nor `dvc_input_hash`).

Core module: stdlib + pydantic only (PLATFORM-NOT-HUB).
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from aero.provenance.four_fold import (
    DVC_INPUTS_PREFIX,
    EMPTY_DVC_INPUTS_DIGEST,
    DeclaredInput,
    ProvenanceError,
    dvc_inputs_digest,
)

__all__ = [
    "EMPTY_DIGEST",
    "PREFIX",
    "DeclaredInputs",
    "digest",
    "parse_pointer",
    "read_declared_input",
    "resolve_declared",
]

#: The domain separator of the preimage, and the digest of the empty declaration (`1ef5b7d9…`).
PREFIX = DVC_INPUTS_PREFIX
EMPTY_DIGEST = EMPTY_DVC_INPUTS_DIGEST

#: A run's resolved inputs, sorted by output path.
DeclaredInputs = tuple[DeclaredInput, ...]

digest = dvc_inputs_digest

_POINTER_SUFFIX = ".dvc"
_REQUIRED_KEYS = frozenset({"hash", "md5", "path", "size"})
_OPTIONAL_KEYS = frozenset({"remote"})
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")
_SIZE_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._+-]+$")
_LOCK_PATH_RE = re.compile(r"^\s+- path: (\S+)$")


def _refuse(message: str) -> ProvenanceError:
    return ProvenanceError(f"{message} (ADR-052)")


def _check_segments(path: str, *, what: str) -> None:
    segments = path.split("/")
    if not path or any(not _SEGMENT_RE.match(s) or s in {".", ".."} for s in segments):
        raise _refuse(f"{what} {path!r} is not a plain relative path inside the repository")


# --- the pointer parser ------------------------------------------------------------------------


def parse_pointer(text: str, *, pointer: str) -> DeclaredInput:
    """Parse one git-tracked DVC-3 file pointer into the input it declares.

    `pointer` is the pointer's repo-relative path; the output path is resolved against its
    directory, so the result's `path` is the output's repo-relative path (ADR-052 D2).
    """
    _check_segments(pointer, what="pointer")
    if not pointer.endswith(_POINTER_SUFFIX) or posixpath.basename(pointer) == _POINTER_SUFFIX:
        raise _refuse(f"{pointer!r} is not a `.dvc` file pointer")
    if "\r" in text:
        raise _refuse(f"{pointer}: CR line endings are not a DVC pointer DVC wrote")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != "outs:":
        raise _refuse(f"{pointer}: a file pointer has exactly one top-level key, `outs`")
    entries: list[dict[str, str]] = []
    for number, line in enumerate(lines[1:], start=2):
        if line.startswith("- "):
            entries.append({})
            body = line[2:]
        elif line.startswith("  ") and entries:
            body = line[2:]
        else:
            raise _refuse(f"{pointer}:{number}: not a file-pointer line: {line!r}")
        key, sep, value = body.partition(": ")
        if not sep or not value or value != value.strip() or key in entries[-1]:
            raise _refuse(f"{pointer}:{number}: not a `key: value` line DVC writes: {line!r}")
        entries[-1][key] = value
    if len(entries) != 1:
        raise _refuse(f"{pointer}: declares {len(entries)} outputs; a declarable pointer has one")
    entry = entries[0]
    if "nfiles" in entry or entry.get("md5", "").endswith(".dir"):
        raise _refuse(f"{pointer}: a directory output is not declarable under this scheme")
    keys = set(entry)
    if keys - _OPTIONAL_KEYS != _REQUIRED_KEYS:
        raise _refuse(
            f"{pointer}: keys {sorted(keys)}; a declarable pointer has exactly "
            f"{sorted(_REQUIRED_KEYS)} and optionally `remote`"
        )
    if entry["hash"] != "md5":
        raise _refuse(f"{pointer}: `hash: {entry['hash']}` is not DVC-3's plain-byte md5")
    if not _MD5_RE.match(entry["md5"]):
        raise _refuse(f"{pointer}: md5 {entry['md5']!r} is not 32 lowercase hex digits")
    if not _SIZE_RE.match(entry["size"]):
        raise _refuse(f"{pointer}: size {entry['size']!r} is not a byte count")
    _check_segments(entry["path"], what=f"{pointer}: output")
    if "remote" in entry:
        _check_segments(entry["remote"], what=f"{pointer}: remote")
    return DeclaredInput(
        hash="md5",
        md5=entry["md5"],
        path=posixpath.join(posixpath.dirname(pointer), entry["path"]),
        size=int(entry["size"]),
    )


# --- git ----------------------------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args], capture_output=True, check=False
        )
    except FileNotFoundError as exc:
        raise ProvenanceError("`git` not found — cannot resolve the declared inputs") from exc


def _git_tracked(repo_root: Path, rel: str) -> bool:
    return _git(repo_root, "ls-files", "--error-unmatch", "--", rel).returncode == 0


# --- the declaration ---------------------------------------------------------------------------


def resolve_declared(repo_root: Path, pointers: Sequence[str]) -> DeclaredInputs:
    """The inputs a declaration names, from its pointers as committed at `HEAD`.

    Refused: a pointer not committed at `HEAD`; a working copy that differs from `HEAD`'s (even
    for an `--allow-dirty` run); `dvc.lock`; a pointer or an output listed twice.
    """
    if isinstance(pointers, str):
        raise _refuse(
            f"dvc_inputs must be a sequence of pointer paths, got the string {pointers!r}"
        )
    if len(set(pointers)) != len(pointers):
        raise _refuse(f"a pointer is declared more than once: {list(pointers)}")
    inputs: list[DeclaredInput] = []
    for pointer in pointers:
        _check_segments(pointer, what="pointer")
        if posixpath.basename(pointer) == "dvc.lock":
            raise _refuse("a `dvc.lock` stage output is not declarable under this scheme")
        head = _git(repo_root, "show", f"HEAD:{pointer}")
        if head.returncode != 0:
            raise _refuse(f"{pointer}: the declared pointer is not committed at HEAD")
        working = repo_root / pointer
        if not working.is_file() or working.read_bytes() != head.stdout:
            raise _refuse(
                f"{pointer}: the declared pointer differs from HEAD's; commit it first — the "
                "recorded value must be recomputable from git, even for an --allow-dirty run"
            )
        inputs.append(parse_pointer(head.stdout.decode("utf-8"), pointer=pointer))
    paths = [i.path for i in inputs]
    if len(set(paths)) != len(paths):
        raise _refuse(f"two declared pointers name the same output: {sorted(paths)}")
    return tuple(sorted(inputs, key=lambda i: i.path))


# --- the one read path -------------------------------------------------------------------------


def _repo_relative(repo_root: Path, path: Path | str) -> str:
    candidate = Path(path)
    target = Path(os.path.abspath(candidate if candidate.is_absolute() else repo_root / candidate))
    for root in (Path(os.path.abspath(repo_root)), repo_root.resolve()):
        try:
            return target.relative_to(root).as_posix()
        except ValueError:
            continue
    raise _refuse(
        f"{path}: outside the checkout {repo_root}, so covered by neither git_sha nor "
        "dvc_input_hash; put it in git or DVC and declare it"
    )


def _dvc_outputs(repo_root: Path) -> list[tuple[str, str]]:
    """Every DVC output of the checkout as `(repo-relative path, owner)` — read leniently.

    Strictness is not the point here: this only has to recognise a DVC output, including the
    directory and `dvc.lock` outputs the strict parser refuses to declare.
    """
    outputs: list[tuple[str, str]] = []
    listed = _git(repo_root, "ls-files", "-z", "--", f"*{_POINTER_SUFFIX}", "dvc.lock")
    for raw in listed.stdout.split(b"\0"):
        owner = raw.decode("utf-8")
        if not owner:
            continue
        text = (
            (repo_root / owner).read_text(encoding="utf-8") if (repo_root / owner).is_file() else ""
        )
        if posixpath.basename(owner) == "dvc.lock":
            in_outs = False
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.endswith(":") and not stripped.startswith("-"):
                    in_outs = stripped == "outs:"
                    continue
                match = _LOCK_PATH_RE.match(line)
                if in_outs and match:
                    outputs.append((posixpath.normpath(match.group(1)), owner))
            continue
        base = posixpath.dirname(owner)
        for line in text.splitlines():
            key, sep, value = line.strip().removeprefix("- ").partition(": ")
            if sep and key == "path":
                outputs.append((posixpath.normpath(posixpath.join(base, value)), owner))
    return outputs


def read_declared_input(
    repo_root: Path, path: Path | str, *, declared: Sequence[DeclaredInput]
) -> bytes:
    """Read one file a run stages or a case reads, through the declaration (ADR-052 D1).

    Returns the verified bytes of a declared input from one read, or the bytes of a git-tracked
    file that is no DVC output. Everything else is refused with `ProvenanceError`.
    """
    rel = _repo_relative(repo_root, path)
    match = next((d for d in declared if d.path == rel), None)
    if match is not None:
        target = repo_root / rel
        if not target.is_file():
            raise _refuse(f"{rel}: the declared input is not in the checkout — `dvc pull` it")
        data = target.read_bytes()
        actual = hashlib.md5(data, usedforsecurity=False).hexdigest()
        if len(data) != match.size or actual != match.md5:
            raise _refuse(
                f"{rel}: {len(data)} bytes with md5 {actual} do not match the declared pointer "
                f"({match.size} bytes, md5 {match.md5}); refusing to read different bytes"
            )
        return data
    for output, owner in _dvc_outputs(repo_root):
        if rel == output:
            if posixpath.basename(owner) == "dvc.lock":
                raise _refuse(f"{rel}: a `dvc.lock` stage output is not declarable")
            raise _refuse(f"{rel}: a DVC output ({owner}) this run did not declare")
        if rel.startswith(output + "/"):
            raise _refuse(f"{rel}: a member of the directory output {output} ({owner})")
    if not _git_tracked(repo_root, rel):
        raise _refuse(f"{rel}: neither git-tracked nor a declared DVC output")
    return (repo_root / rel).read_bytes()
