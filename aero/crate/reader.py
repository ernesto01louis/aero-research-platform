"""Verify a result crate: hash first, parse strictly, re-derive everything (ADR-047 D3).

``verify_crate`` either returns a :class:`VerifiedCrate` or raises a :class:`CrateError`. It never
returns a partial or best-effort result. It reads only the crate's own bytes: no network, no
JSON-LD context fetching, no subprocess, no import of anything the content names. Its import
closure is stdlib + numpy + pydantic (tests/unit/test_crate_import_isolation.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from aero.crate._canonical import dumps_document, is_fixed_point, loads_strict, sha256_hex
from aero.crate.conformance import check_prov_equivalence, check_rocrate
from aero.crate.errors import (
    CrateExpectationError,
    CrateFormatError,
    CrateIntegrityError,
    CrateSemanticError,
)
from aero.crate.members import SUMS, parse_sha256sums, read_members
from aero.crate.model import RESERVED_DOCUMENTS, CrateManifest
from aero.crate.payload import load_reportable, reportable_document
from aero.crate.projections import build_prov, build_rocrate
from aero.crate.rules import check_validity
from aero.provenance.four_fold import canonical_config_bytes, config_hash
from aero.vv.reportable import ReportableResult

__all__ = ["VerifiedCrate", "verify_crate", "verify_members"]


@dataclass(frozen=True)
class VerifiedCrate:
    """A crate that passed every check. Only :func:`verify_members` constructs one."""

    manifest: CrateManifest
    result: ReportableResult | None
    digest: str
    members: dict[str, bytes]
    origin: str

    def numbers(self) -> dict[str, Any]:
        """Every number the crate carries, floats as ``float.hex``, for bitwise comparison."""
        out: dict[str, Any] = {
            "digest": self.digest,
            "claim_tier": self.manifest.validity.claim_tier,
            "configs": sorted(
                p.removeprefix("configs/").removesuffix(".json")
                for p in self.members
                if p.startswith("configs/")
            ),
            "result": {},
            "gates": {},
        }
        if self.result is not None:
            out["result"] = _typed_leaves(reportable_document(self.result))
        for verdict in self.manifest.validity.verdicts:
            for gate in verdict.gates:
                out["gates"][f"{verdict.scope}/{gate.name}"] = {
                    "gated": gate.gated,
                    "observed": _typed(gate.observed),
                    "passed": gate.passed,
                    "overall": verdict.overall,
                }
        return out


def _typed(value: Any) -> list[Any]:
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, float):
        return ["float", value.hex()]
    if isinstance(value, int):
        return ["int", value]
    if value is None:
        return ["null", None]
    return ["str", value]


def _typed_leaves(obj: Any, path: str = "") -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            out.update(_typed_leaves(v, f"{path}/{k}"))
    elif isinstance(obj, list) and obj:
        for i, v in enumerate(obj):
            out.update(_typed_leaves(v, f"{path}/{i}"))
    elif isinstance(obj, dict | list):
        out[path] = ["empty", "{}" if isinstance(obj, dict) else "[]"]
    else:
        out[path] = _typed(obj)
    return out


def _check_fixity(members: dict[str, bytes], expect_digest: str | None) -> str:
    if SUMS not in members:
        raise CrateIntegrityError("SHA256SUMS is missing")
    sums = parse_sha256sums(members[SUMS])
    listed, present = set(sums), set(members) - {SUMS}
    if listed != present:
        raise CrateIntegrityError(
            f"member set mismatch: unlisted {sorted(present - listed)}, missing {sorted(listed - present)}"
        )
    for name, digest in sums.items():
        if sha256_hex(members[name]) != digest:
            raise CrateIntegrityError(f"sha256 mismatch for {name!r}")
    digest = sha256_hex(members[SUMS])
    if expect_digest is not None and digest != expect_digest:
        raise CrateExpectationError(f"crate digest {digest} != expected {expect_digest}")
    return digest


def _load_manifest(data: bytes) -> CrateManifest:
    parsed = loads_strict(data, what="aero-crate.json")
    try:
        manifest = CrateManifest.model_validate(parsed)
    except ValidationError as exc:
        raise CrateSemanticError(
            f"aero-crate.json is not a valid format-1 envelope:\n{exc}"
        ) from exc
    if dumps_document(json.loads(manifest.model_dump_json())) != data:
        raise CrateFormatError(
            "aero-crate.json is not in canonical form (or carries lossy content)"
        )
    return manifest


def _check_config(path: str, data: bytes) -> str:
    stem = path.removeprefix("configs/").removesuffix(".json")
    if sha256_hex(data) != stem:
        raise CrateIntegrityError(f"{path}: content sha256 != its name")
    parsed = loads_strict(data, what=path)
    if not isinstance(parsed, dict):
        raise CrateFormatError(f"{path}: a config preimage is a JSON object")
    if canonical_config_bytes(parsed) != data:
        raise CrateFormatError(f"{path}: not the canonical config_hash preimage")
    if config_hash(parsed) != stem:
        raise CrateIntegrityError(f"{path}: config_hash(preimage) != its name")
    return stem


def verify_members(
    members: dict[str, bytes], *, expect_digest: str | None = None, origin: str = "<memory>"
) -> VerifiedCrate:
    """Verify an in-memory crate (``{path: bytes}``). See the module docstring."""
    try:
        return _verify(members, expect_digest, origin)
    except CrateExpectationError:
        raise
    except (CrateIntegrityError, CrateFormatError, CrateSemanticError) as exc:
        raise type(exc)(f"{origin}: {exc}") from exc


def _verify(members: dict[str, bytes], expect_digest: str | None, origin: str) -> VerifiedCrate:
    digest = _check_fixity(members, expect_digest)
    for required in RESERVED_DOCUMENTS:
        if required not in members:
            raise CrateIntegrityError(f"{required} is missing")
    manifest = _load_manifest(members["aero-crate.json"])
    table = {m.path: m for m in manifest.members}
    if set(table) != set(members) - RESERVED_DOCUMENTS:
        raise CrateIntegrityError(
            f"members table {sorted(table)} != crate members {sorted(set(members) - RESERVED_DOCUMENTS)}"
        )
    for path, entry in table.items():
        if entry.sha256 != sha256_hex(members[path]) or entry.size != len(members[path]):
            raise CrateIntegrityError(f"members table disagrees with the bytes of {path!r}")

    result: ReportableResult | None = None
    if manifest.payload == "reportable-result":
        result = load_reportable(members["result.json"], mode="crate")
    config_hashes = {_check_config(p, members[p]) for p in table if table[p].role == "config"}

    for ref in manifest.references:
        if ref.embedded_as is None:
            continue
        if ref.embedded_as not in table or table[ref.embedded_as].role != "evidence":
            raise CrateSemanticError(
                f"reference {ref.locator!r} is embedded as a non-evidence member"
            )
        if ref.sha256 is not None and ref.sha256 != table[ref.embedded_as].sha256:
            raise CrateIntegrityError(f"reference {ref.locator!r}: sha256 != the embedded bytes")
        if ref.role == "source-record":
            if result is None:
                raise CrateSemanticError("an evidence-only crate has no source-record to replay")
            legacy = load_reportable(members[ref.embedded_as], mode="legacy", what=ref.embedded_as)
            if legacy != result:
                raise CrateSemanticError(
                    f"result.json is not the faithful import of {ref.embedded_as} ({ref.locator})"
                )

    check_validity(manifest, result, config_hashes)
    for lim in manifest.validity.limitations:
        if lim.kind == "quote" and lim.source.embedded_as is not None:
            text = members[lim.source.embedded_as].decode("utf-8", errors="strict")
            if lim.text not in text:
                raise CrateSemanticError(
                    f"limitation {lim.id!r} is not a verbatim quote of its source"
                )

    digests = {
        p: (sha256_hex(b), len(b))
        for p, b in members.items()
        if p not in (SUMS, "ro-crate-metadata.json", "prov.json")
    }
    prov_doc = build_prov(manifest, digests)
    if dumps_document(prov_doc) != members["prov.json"]:
        raise CrateSemanticError("prov.json is not the projection of aero-crate.json")
    digests["prov.json"] = (sha256_hex(members["prov.json"]), len(members["prov.json"]))
    rocrate_doc = build_rocrate(manifest, digests, result)
    if dumps_document(rocrate_doc) != members["ro-crate-metadata.json"]:
        raise CrateSemanticError("ro-crate-metadata.json is not the projection of aero-crate.json")
    check_rocrate(rocrate_doc, set(members))
    check_prov_equivalence(rocrate_doc, prov_doc)
    assert is_fixed_point(members["ro-crate-metadata.json"], rocrate_doc)
    return VerifiedCrate(
        manifest=manifest, result=result, digest=digest, members=dict(members), origin=origin
    )


def verify_crate(path: str | Path, *, expect_digest: str | None = None) -> VerifiedCrate:
    """Read a crate directory or ``.crate.zip`` from disk and verify it."""
    p = Path(path)
    return verify_members(read_members(p), expect_digest=expect_digest, origin=str(p))
