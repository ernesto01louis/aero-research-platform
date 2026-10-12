"""The ONE JSON encoder and the ONE strict decoder of the result-crate format (ADR-047 D2).

Document members (``aero-crate.json``, ``result.json``, ``ro-crate-metadata.json``, ``prov.json``)
are written as::

    json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\\n"

and every reader requires each document to be a fixed point of that encoder. Floats are written
with ``float.__repr__``, the shortest repr that round-trips. That is platform-independent in
CPython, so the bytes are identical on Linux, macOS and Windows. Pydantic payloads are re-encoded
through this stdlib encoder, never written with pydantic's own JSON tokens, which differ for some
exponents and across pydantic versions.

Parsing is strict. It refuses duplicate keys, ``NaN`` / ``Infinity`` tokens, floats that
overflow to infinity (``1e999`` has no constant token, so ``parse_constant`` alone does not catch
it), a BOM, CR characters, invalid UTF-8, and nesting deeper than :data:`MAX_DEPTH`.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from aero.crate.errors import CrateFormatError, CrateNonFiniteError

__all__ = [
    "MAX_DEPTH",
    "dumps_document",
    "is_fixed_point",
    "json_equal",
    "loads_strict",
    "sha256_hex",
]

MAX_DEPTH = 64


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps_document(obj: Any) -> bytes:
    """Encode a JSON document member in the format-v1 canonical form (ASCII, LF, final newline)."""
    try:
        text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
    except ValueError as exc:  # allow_nan=False raises ValueError on NaN/inf
        raise CrateNonFiniteError(f"non-finite number in a crate document: {exc}") from exc
    return (text + "\n").encode("ascii")


def _refuse_constant(token: str) -> Any:
    raise CrateNonFiniteError(f"non-finite JSON token {token!r} is forbidden in a crate")


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise CrateNonFiniteError(f"JSON number {token!r} overflows to a non-finite float")
    return value


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CrateFormatError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _depth(obj: Any, level: int = 1) -> int:
    if level > MAX_DEPTH:
        raise CrateFormatError(f"JSON nesting deeper than {MAX_DEPTH}")
    if isinstance(obj, dict):
        return max((_depth(v, level + 1) for v in obj.values()), default=level)
    if isinstance(obj, list):
        return max((_depth(v, level + 1) for v in obj), default=level)
    return level


def loads_strict(data: bytes, *, what: str) -> Any:
    """Parse one member's bytes as strict JSON, or raise :class:`CrateFormatError`."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise CrateFormatError(f"{what}: a byte-order mark is forbidden")
    if b"\r" in data:
        raise CrateFormatError(f"{what}: CR characters are forbidden (LF line endings only)")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CrateFormatError(f"{what}: not valid UTF-8: {exc}") from exc
    try:
        obj = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_refuse_constant,
            parse_float=_finite_float,
        )
    except CrateFormatError:
        raise
    except RecursionError as exc:
        raise CrateFormatError(f"{what}: JSON nesting too deep") from exc
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        raise CrateFormatError(f"{what}: not valid JSON: {exc}") from exc
    _depth(obj)
    return obj


def is_fixed_point(data: bytes, obj: Any) -> bool:
    """True iff re-encoding the parsed ``obj`` reproduces ``data`` byte for byte."""
    return dumps_document(obj) == data


def json_equal(a: Any, b: Any) -> bool:
    """Structural JSON equality that distinguishes int/float/bool and compares floats bitwise.

    ``-0.0`` and ``0.0`` are different; ``1`` and ``1.0`` are different. This is "same numbers"
    in the strict sense the round trip requires.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return bool(a.hex() == b.hex())
    if isinstance(a, dict):
        return bool(a.keys() == b.keys()) and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return bool(len(a) == len(b)) and all(json_equal(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)
