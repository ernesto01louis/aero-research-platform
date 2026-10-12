"""Stdlib conformance checks for the two projections (ADR-047 D5).

* **RO-Crate 1.3 MUSTs.**
  - The metadata descriptor (``@id``, ``@type`` CreativeWork, ``about``, ``conformsTo``).
  - The Root Data Entity (Dataset, ``name``, ``description``, ``datePublished`` as an ISO-8601
    date string, ``license``).
  - Every data entity linked from the root by ``hasPart``, and every ``hasPart`` target present.
  - ``@context`` referencing the 1.3 context by URL.
* **Process Run Crate 0.6 MUSTs.**
  - The root ``conformsTo`` the profile.
  - At least one ``CreateAction``, each with an ``@id`` and an ``instrument`` that resolves to a
    typed ``SoftwareApplication``.
* **PROV equivalence.** The ``prov:*`` relations written inline in the RO-Crate and the
  relations in ``prov.json`` are the same sets.

The external validator (``roc-validator``) checks the RO-Crate 1.3 base in CI only. Its Process
Run Crate profile is still 0.5 (RO-Crate 1.1), so the 0.6 MUSTs are checked here.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from aero.crate.errors import CrateSemanticError
from aero.crate.projections import PRC_PROFILE, RO_CRATE_CONTEXT, RO_CRATE_SPEC

__all__ = ["check_prov_equivalence", "check_rocrate"]


def _types(entity: dict[str, Any]) -> set[str]:
    t = entity.get("@type", [])
    return {t} if isinstance(t, str) else set(t)


def _ids(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [value["@id"]]
    if isinstance(value, list):
        return [v["@id"] for v in value]
    return []


def check_rocrate(doc: dict[str, Any], member_paths: set[str]) -> None:
    """Raise :class:`CrateSemanticError` unless the RO-Crate 1.3 and PRC 0.6 MUSTs hold."""
    if doc.get("@context") != [RO_CRATE_CONTEXT, "https://w3id.org/ro/terms/workflow-run/context"]:
        raise CrateSemanticError(
            "RO-Crate: @context must reference the 1.3 and workflow-run contexts"
        )
    graph = doc.get("@graph")
    if not isinstance(graph, list):
        raise CrateSemanticError("RO-Crate: @graph must be a list (flattened JSON-LD)")
    by_id: dict[str, dict[str, Any]] = {}
    for entity in graph:
        if not isinstance(entity, dict) or not isinstance(entity.get("@id"), str):
            raise CrateSemanticError("RO-Crate: every entity needs an @id")
        if entity["@id"] in by_id:
            raise CrateSemanticError(f"RO-Crate: duplicate entity {entity['@id']!r}")
        by_id[entity["@id"]] = entity
    desc = by_id.get("ro-crate-metadata.json")
    if desc is None or "CreativeWork" not in _types(desc):
        raise CrateSemanticError(
            "RO-Crate: the metadata descriptor is missing or not a CreativeWork"
        )
    if _ids(desc.get("about")) != ["./"] or _ids(desc.get("conformsTo")) != [RO_CRATE_SPEC]:
        raise CrateSemanticError("RO-Crate: the descriptor must be about './' and conform to 1.3")
    root = by_id.get("./")
    if root is None or "Dataset" not in _types(root):
        raise CrateSemanticError("RO-Crate: the Root Data Entity './' must be a Dataset")
    for key in ("name", "description", "datePublished", "license"):
        if not root.get(key):
            raise CrateSemanticError(f"RO-Crate: the root lacks {key!r}")
    try:
        _dt.date.fromisoformat(root["datePublished"])
    except (TypeError, ValueError) as exc:
        raise CrateSemanticError(
            "RO-Crate: datePublished must be one ISO-8601 date string"
        ) from exc
    parts = set(_ids(root.get("hasPart")))
    if parts != member_paths - {"ro-crate-metadata.json"}:
        raise CrateSemanticError(
            f"RO-Crate: hasPart {sorted(parts)} != the crate's members {sorted(member_paths)}"
        )
    for part in parts:
        if part not in by_id or "File" not in _types(by_id[part]):
            raise CrateSemanticError(f"RO-Crate: hasPart target {part!r} is not a File entity")
    if PRC_PROFILE not in _ids(root.get("conformsTo")):
        raise CrateSemanticError("Process Run Crate: the root must conform to the 0.6 profile")
    actions = [e for e in graph if "CreateAction" in _types(e)]
    if not actions:
        raise CrateSemanticError("Process Run Crate: at least one CreateAction is required")
    for action in actions:
        instruments = _ids(action.get("instrument"))
        if len(instruments) != 1 or "SoftwareApplication" not in _types(
            by_id.get(instruments[0], {})
        ):
            raise CrateSemanticError(
                f"Process Run Crate: action {action['@id']!r} needs one SoftwareApplication instrument"
            )
    mentioned = set(_ids(root.get("mentions")))
    for action in actions:
        if action["@id"] not in mentioned:
            raise CrateSemanticError(
                f"Process Run Crate: action {action['@id']!r} is not in mentions"
            )


def check_prov_equivalence(rocrate: dict[str, Any], prov: dict[str, Any]) -> None:
    """The inline prov:* relations and the PROV-JSON relations must be the same sets."""

    def q(local: str) -> str:
        return f"crate:{local.lstrip('#')}"

    inline_used: set[tuple[str, str]] = set()
    inline_gen: set[tuple[str, str]] = set()
    inline_assoc: set[tuple[str, str]] = set()
    for entity in rocrate["@graph"]:
        act = entity.get("@id", "")
        for target in _ids(entity.get("prov:used")):
            inline_used.add((q(act), q(target)))
        for target in _ids(entity.get("prov:generated")):
            inline_gen.add((q(target), q(act)))
        for target in _ids(entity.get("prov:wasAssociatedWith")):
            inline_assoc.add((q(act), q(target)))

    def pairs(section: str, a: str, b: str) -> set[tuple[str, str]]:
        return {(r[a], r[b]) for r in prov.get(section, {}).values()}

    checks = (
        ("used", inline_used, pairs("used", "prov:activity", "prov:entity")),
        ("wasGeneratedBy", inline_gen, pairs("wasGeneratedBy", "prov:entity", "prov:activity")),
        (
            "wasAssociatedWith",
            inline_assoc,
            pairs("wasAssociatedWith", "prov:activity", "prov:agent"),
        ),
    )
    for name, inline, sidecar in checks:
        if inline != sidecar:
            raise CrateSemanticError(
                f"PROV equivalence: {name} differs between ro-crate-metadata.json and prov.json: "
                f"only inline {sorted(inline - sidecar)}, only sidecar {sorted(sidecar - inline)}"
            )
    declared = (
        set(prov.get("entity", {})) | set(prov.get("activity", {})) | set(prov.get("agent", {}))
    )
    for section in (
        "used",
        "wasGeneratedBy",
        "wasAssociatedWith",
        "wasAttributedTo",
        "wasDerivedFrom",
    ):
        for record in prov.get(section, {}).values():
            for ref in record.values():
                if ref not in declared:
                    raise CrateSemanticError(f"PROV: {section} refers to undeclared {ref!r}")
