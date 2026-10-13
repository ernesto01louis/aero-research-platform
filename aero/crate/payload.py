"""The payload rule: ``result.json`` holds a ``ReportableResult`` LOSSLESSLY (ADR-047 D3).

The platform's ``model_dump_json()`` writes the computed fields (``u95_total``, ``delta``,
``u95_delta``, ``required_margin``, …). ``extra='forbid'`` rejects them on load, so before Stage 21
no committed ``ReportableResult`` reloaded as written. ``result.json`` deliberately keeps them, so
it stays human-readable. The reader therefore:

1. removes each computed key, guided by the model's type annotations, to get the stored fields;
2. validates the stored fields strictly (``extra='forbid'``, after-validators, finite floats);
3. re-dumps the model and requires the file to be a **lossless subset** of that re-dump:
   - every leaf in the file is present with the same JSON type and the same value, floats
     compared bit for bit;
   - so every computed value must recompute exactly;
   - the only keys allowed to appear in the re-dump alone are listed with their exact default
     in an ADR-governed allowlist.

In crate mode that allowlist is empty for format v1, so a crate's ``result.json`` must equal its
re-dump exactly. In legacy mode, used to import committed ``data/vv`` records, it holds the
fields added to the schema after those records were written.
"""

from __future__ import annotations

import json
import types
import typing
from collections.abc import Mapping
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, ValidationError

from aero.crate._canonical import json_equal, loads_strict
from aero.crate.errors import CrateSemanticError, LegacyRecordError
from aero.vv.reportable import ReportableResult

__all__ = [
    "CRATE_ADDED_FIELDS",
    "LEGACY_ADDED_FIELDS",
    "load_reportable",
    "reportable_document",
    "strip_computed",
]

# Keys that may appear ONLY in the re-dump, with their exact default value. "*" matches one
# list index. Format v1 crates: none. Grows only by ADR, and each entry must equal the real
# field default (tests/unit/test_crate_legacy.py checks).
CRATE_ADDED_FIELDS: Mapping[tuple[str, ...], Any] = {}

# Fields added to the ReportableResult schema after committed data/vv records were written:
# ProvenanceTuple.containers (Stage 20, ADR-038) and ReportableQuantity.u95_input_basis
# (Stage 14, review P1d; its default 'skipped' is only admissible where u95_input == 0, which
# the model's own validator enforces).
LEGACY_ADDED_FIELDS: Mapping[tuple[str, ...], Any] = {
    ("provenance", "containers"): [],
    ("optimization", "cfd_verified", "containers"): [],
    ("quantities", "*", "u95_input_basis"): "skipped",
}


def _is_model(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _union_members(tp: Any) -> tuple[Any, ...] | None:
    origin = get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        return get_args(tp)
    return None


def _strip(tp: Any, data: Any) -> Any:
    """Return ``data`` with every computed-field key removed, guided by the annotation ``tp``."""
    if get_origin(tp) is typing.Annotated:
        return _strip(get_args(tp)[0], data)
    members = _union_members(tp)
    if members is not None:
        if data is None and type(None) in members:
            return None
        models = [m for m in members if _is_model(m)]
        if not models:
            return data
        if len(models) == 1:
            return _strip(models[0], data)
        # A discriminated union on 'source' (DeltaU95): pick the member whose default matches.
        if isinstance(data, dict) and "source" in data:
            for model in models:
                field = model.model_fields.get("source")
                if field is not None and field.default == data["source"]:
                    return _strip(model, data)
        raise CrateSemanticError(f"cannot resolve a union of {models} for {data!r:.80}")
    if _is_model(tp):
        if not isinstance(data, dict):
            return data  # leave the type error to model validation
        computed = set(tp.model_computed_fields)
        out: dict[str, Any] = {}
        for key, value in data.items():
            if key in computed:
                continue
            field = tp.model_fields.get(key)
            out[key] = value if field is None else _strip(field.annotation, value)
        return out
    origin = get_origin(tp)
    if origin is tuple and isinstance(data, list):
        args = get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return [_strip(args[0], v) for v in data]
        return [_strip(a, v) for a, v in zip(args, data, strict=False)]
    if origin in (list, dict) and isinstance(data, list | dict):
        return data
    return data


def strip_computed(data: Mapping[str, Any]) -> dict[str, Any]:
    stripped = _strip(ReportableResult, dict(data))
    assert isinstance(stripped, dict)
    return stripped


def _leaves(obj: Any, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    out: dict[tuple[str, ...], Any] = {}
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            out.update(_leaves(v, (*path, k)))
    elif isinstance(obj, list) and obj:
        for i, v in enumerate(obj):
            out.update(_leaves(v, (*path, str(i))))
    else:
        out[path] = obj  # scalars, and empty containers as leaves
    return out


def _allowed(path: tuple[str, ...], value: Any, allow: Mapping[tuple[str, ...], Any]) -> bool:
    for pattern, default in allow.items():
        if len(pattern) == len(path) and all(
            p in ("*", s) for p, s in zip(pattern, path, strict=True)
        ):
            return json_equal(value, default)
    return False


def _covered_by(
    path: tuple[str, ...], allow: Mapping[tuple[str, ...], Any]
) -> tuple[str, ...] | None:
    """The allowlisted subtree root that ``path`` falls under, if any."""
    for pattern in allow:
        n = len(pattern)
        if len(path) >= n and all(p in ("*", s) for p, s in zip(pattern, path[:n], strict=True)):
            return path[:n]
    return None


def reportable_document(result: ReportableResult) -> Any:
    """The JSON value ``result.json`` carries: the model's full dump, computed fields included."""
    return json.loads(result.model_dump_json())


def load_reportable(
    data: bytes, *, mode: Literal["crate", "legacy"], what: str = "result.json"
) -> ReportableResult:
    """Strictly load a ``ReportableResult`` and prove the bytes lossless (see the module docstring)."""
    parsed = loads_strict(data, what=what)
    if not isinstance(parsed, dict):
        raise CrateSemanticError(f"{what}: top level must be a JSON object")
    try:
        result = ReportableResult.model_validate(strip_computed(parsed))
    except ValidationError as exc:
        err = LegacyRecordError if mode == "legacy" else CrateSemanticError
        raise err(f"{what}: not a valid ReportableResult under today's schema:\n{exc}") from exc
    redump = reportable_document(result)
    allow = LEGACY_ADDED_FIELDS if mode == "legacy" else CRATE_ADDED_FIELDS
    file_leaves = _leaves(parsed)
    dump_leaves = _leaves(redump)
    for path, value in file_leaves.items():
        if path not in dump_leaves or not json_equal(value, dump_leaves[path]):
            got = dump_leaves.get(path, "<absent>")
            raise CrateSemanticError(
                f"{what}: {'/'.join(path)} = {value!r} is not reproduced by the model "
                f"(re-dump has {got!r}); the record is lossy, forged, or a computed value "
                "does not recompute bit for bit"
            )
    extra_roots: dict[tuple[str, ...], Any] = {}
    for path in dump_leaves.keys() - file_leaves.keys():
        root = _covered_by(path, allow)
        if root is None:
            raise CrateSemanticError(
                f"{what}: {'/'.join(path)} is missing from the file but present in the model "
                "(a missing computed value, or a field not in the ADR-047 added-fields allowlist)"
            )
        extra_roots[root] = None
    for root in extra_roots:
        node: Any = redump
        for part in root:
            node = node[int(part)] if isinstance(node, list) else node[part]
        if not _allowed(root, node, allow):
            raise CrateSemanticError(
                f"{what}: added field {'/'.join(root)} = {node!r} is not its default"
            )
    return result
