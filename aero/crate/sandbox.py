"""An audit-hook sandbox for the crate CLI (ADR-047 D3): verification touches nothing but the crate.

Once :func:`install` runs, the process refuses:
- network sockets;
- subprocesses, ``exec`` and ``fork``;
- file writes and filesystem mutations outside one explicitly allowed output path (``pack``);
- imports outside stdlib + numpy + pydantic + aero.

Audit hooks cannot be removed, so this is for the CLI process only, never for library callers.
It is defence in depth on top of a reader that does none of these things by design. If a future
change makes the reader reach for the network or a third-party module, the CLI fails loudly
instead of doing it quietly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

__all__ = ["SandboxViolationError", "install"]

_ALLOWED_THIRD_PARTY = frozenset(
    {
        "numpy",
        "pydantic",
        "pydantic_core",
        "annotated_types",
        "typing_extensions",
        "typing_inspection",
        "aero",
    }
)
_DENY_PREFIXES = (
    "socket.",
    "subprocess.",
    "os.exec",
    "os.spawn",
    "os.posix_spawn",
    "os.fork",
    "pty.",
)
_DENY_EXACT = frozenset({"os.system", "os.forkpty", "ctypes.dlopen", "webbrowser.open"})
_MUTATIONS = frozenset(
    {
        "os.remove",
        "os.rename",
        "os.rmdir",
        "os.mkdir",
        "os.truncate",
        "os.chmod",
        "os.symlink",
        "os.link",
        "shutil.rmtree",
    }
)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


class SandboxViolationError(PermissionError):
    """The crate CLI attempted something verification must never do."""


def install(*, allow_write: Path | None = None) -> None:
    """Install the sandbox in THIS process (irreversible). ``allow_write`` is a single file path."""
    sys.dont_write_bytecode = True
    allowed_top = set(sys.stdlib_module_names) | _ALLOWED_THIRD_PARTY
    allowed_path = None if allow_write is None else os.path.realpath(allow_write)

    def _is_allowed_target(path: Any) -> bool:
        if allowed_path is None or not isinstance(path, str | bytes | os.PathLike):
            return False
        return os.path.realpath(os.fsdecode(path)) == allowed_path

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event == "import":
            top = str(args[0]).split(".")[0]
            if top not in allowed_top and not top.startswith("_sysconfigdata"):
                raise ImportError(f"crate sandbox: import of {args[0]!r} is denied")
            return
        if event in _DENY_EXACT or event.startswith(_DENY_PREFIXES):
            raise SandboxViolationError(f"crate sandbox: {event} is denied")
        if event == "open":
            path, mode, flags = args
            if isinstance(mode, str):
                writing = any(c in mode for c in "wax+")
            else:
                writing = isinstance(flags, int) and bool(flags & _WRITE_FLAGS)
            if writing and not _is_allowed_target(path):
                raise SandboxViolationError(f"crate sandbox: writing {path!r} is denied")
            return
        if event in _MUTATIONS and not (args and _is_allowed_target(args[0])):
            raise SandboxViolationError(f"crate sandbox: {event} is denied")

    sys.addaudithook(hook)
