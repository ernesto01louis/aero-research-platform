"""The two standards projections of a crate envelope (ADR-047 D5).

* ``ro-crate-metadata.json``: RO-Crate 1.3 JSON-LD conforming to Process Run Crate 0.6. Every
  run with a four-tuple becomes a ``CreateAction`` (also typed ``prov:Activity``), whose
  ``instrument`` is the platform at the run's commit (a ``SoftwareApplication`` /
  ``prov:SoftwareAgent``), with a ``containerImage`` and with its config and four-tuple as
  ``object``. One export ``CreateAction`` generates the crate's own documents.
* ``prov.json``: W3C PROV-JSON (a W3C Member Submission) of the same graph. The relations
  follow the Leo et al. (2024) RO-Crate↔PROV-O mapping:
  - ``object`` → ``used``;
  - ``instrument`` / ``agent`` → ``wasAssociatedWith``;
  - ``result`` → ``wasGeneratedBy``.

Both are pure functions of the envelope, the member digests and the payload. The reader
regenerates them and requires byte equality, so an RO-Crate or PROV consumer always sees
exactly what the typed envelope says. Nothing here fetches a JSON-LD context: the contexts are
URLs compared as strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aero.crate.model import (
    CrateManifest,
    ProvenanceAvailable,
    ProvenanceUnavailable,
    RunRecord,
)
from aero.vv.reportable import ReportableResult

__all__ = [
    "FORMAT_ENTITY",
    "PRC_PROFILE",
    "RO_CRATE_CONTEXT",
    "RO_CRATE_SPEC",
    "WFRUN_CONTEXT",
    "build_prov",
    "build_rocrate",
]

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.3/context"
WFRUN_CONTEXT = "https://w3id.org/ro/terms/workflow-run/context"
RO_CRATE_SPEC = "https://w3id.org/ro/crate/1.3"
PRC_PROFILE = "https://w3id.org/ro/wfrun/process/0.6"
FORMAT_ENTITY = "#aero-result-crate-format-1"
SIF_IMAGE_TYPE = "https://w3id.org/ro/terms/workflow-run#SIFImage"
CRATE_LICENSE = "https://spdx.org/licenses/CC-BY-4.0"
SOFTWARE_LICENSE = "https://spdx.org/licenses/GPL-3.0-or-later"
WRITER = "#aero-crate-writer"
EXPORT = "#export"
REPO_URL = "https://github.com/ernesto01louis/aero-research-platform"

_MEDIA = {"aero-crate.json": "application/json", "prov.json": "application/json"}


@dataclass
class _Graph:
    """The run/entity/agent structure both projections are written from (one enumeration)."""

    used: set[tuple[str, str]] = field(default_factory=set)
    generated: set[tuple[str, str]] = field(default_factory=set)
    associated: set[tuple[str, str]] = field(default_factory=set)
    derived: set[tuple[str, str]] = field(default_factory=set)
    attributed: set[tuple[str, str]] = field(default_factory=set)


def _software_id(sha: str) -> str:
    return f"#software-{sha}"


def _container_id(digest: str) -> str:
    return f"#container-{digest}"


def _person_id(n: int) -> str:
    return f"#creator-{n}"


def _config_path(config_hash: str) -> str:
    return f"configs/{config_hash}.json"


def _available(run: RunRecord) -> ProvenanceAvailable | None:
    return run.provenance if isinstance(run.provenance, ProvenanceAvailable) else None


def _relations(manifest: CrateManifest) -> _Graph:
    g = _Graph()
    persons = [_person_id(i) for i in range(1, len(manifest.creators) + 1)]
    for run in manifest.runs:
        prov = _available(run)
        if prov is None:
            continue
        act = run.action_id
        t = prov.four_tuple
        g.used.add((act, _config_path(t.config_hash)))
        g.used.add((act, _container_id(t.container_sif_sha256)))
        for cref in t.containers:
            g.used.add((act, _container_id(cref.sha256)))
        g.associated.add((act, _software_id(t.git_sha)))
    documents = ["aero-crate.json", "prov.json"]
    if manifest.payload == "reportable-result":
        documents.append("result.json")
    for doc in documents:
        g.generated.add((EXPORT, doc))
        for person in persons:
            g.attributed.add((doc, person))
    g.associated.add((EXPORT, WRITER))
    for person in persons:
        g.associated.add((EXPORT, person))
    for m in manifest.members:
        if m.role == "evidence":
            g.used.add((EXPORT, m.path))
    for ref in manifest.references:
        if ref.role == "source-record" and ref.embedded_as and manifest.payload != "none":
            g.derived.add(("result.json", ref.embedded_as))
    return g


def _pv(pid: str, name: str, value: Any, description: str | None = None) -> dict[str, Any]:
    entity: dict[str, Any] = {"@id": pid, "@type": "PropertyValue", "name": name, "value": value}
    if description:
        entity["description"] = description
    return entity


def build_rocrate(
    manifest: CrateManifest,
    digests: dict[str, tuple[str, int]],
    result: ReportableResult | None,
) -> dict[str, Any]:
    """Return the RO-Crate 1.3 / Process Run Crate 0.6 metadata document (a JSON value).

    ``digests`` maps every member path EXCEPT ``ro-crate-metadata.json`` and ``SHA256SUMS`` to
    ``(sha256, size)``, including ``aero-crate.json`` and ``prov.json``.
    """
    g = _relations(manifest)
    entities: list[dict[str, Any]] = []
    persons = []
    for i, person in enumerate(manifest.creators, 1):
        persons.append({"@id": _person_id(i)})
        entities.append(
            {"@id": _person_id(i), "@type": ["Person", "prov:Person"], "name": person.name}
        )

    media = {m.path: m.media_type for m in manifest.members}
    descriptions = {m.path: m.description for m in manifest.members}
    for path in sorted(digests):
        sha, size = digests[path]
        entities.append(
            {
                "@id": path,
                "@type": ["File", "prov:Entity"],
                "contentSize": str(size),
                "description": descriptions.get(path, _DOC_DESCRIPTIONS.get(path, path)),
                "encodingFormat": media.get(path, _MEDIA.get(path, "application/json")),
                "sha256": sha,
            }
        )
    entities.append(
        {
            "@id": "SHA256SUMS",
            "@type": "File",
            "description": "coreutils `sha256sum -c` manifest of every other member; the crate "
            "digest is the sha256 of this file",
            "encodingFormat": "text/plain",
        }
    )

    action_ids: list[str] = []
    seen_software: set[str] = set()
    seen_containers: dict[str, str] = {}
    for run in manifest.runs:
        action: dict[str, Any] = {
            "@id": run.action_id,
            "description": f"{run.description} (roles: {', '.join(run.roles)})",
            "name": run.run_id,
        }
        action_ids.append(run.action_id)
        if isinstance(run.provenance, ProvenanceUnavailable):
            action["@type"] = ["Action", "prov:Activity"]
            action["actionStatus"] = "http://schema.org/CompletedActionStatus"
            action["disambiguatingDescription"] = "provenance UNAVAILABLE: " + run.provenance.reason
            entities.append(action)
            continue
        prov = run.provenance
        t = prov.four_tuple
        software = _software_id(t.git_sha)
        if software not in seen_software:
            seen_software.add(software)
            entities.append(
                {
                    "@id": software,
                    "@type": ["SoftwareApplication", "prov:SoftwareAgent"],
                    "license": {"@id": SOFTWARE_LICENSE},
                    "name": "aero-research-platform",
                    "softwareVersion": t.git_sha,
                    "version": t.git_sha,
                    "url": f"{REPO_URL}/commit/{t.git_sha}",
                }
            )
        container_names = {cref.sha256: cref.name for cref in t.containers}
        for mref in manifest.references:
            if mref.role == "container" and mref.sha256:
                container_names.setdefault(mref.sha256, mref.locator.rsplit("/", 1)[-1])
        digests_used = [t.container_sif_sha256, *(r.sha256 for r in t.containers)]
        for digest in digests_used:
            cid = _container_id(digest)
            if cid not in seen_containers:
                seen_containers[cid] = digest
                entities.append(
                    {
                        "@id": cid,
                        "@type": "ContainerImage",
                        "additionalType": {"@id": SIF_IMAGE_TYPE},
                        "name": container_names.get(digest, "apptainer.sif"),
                        "sha256": digest,
                    }
                )
        tuple_pvs = []
        for name in ("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash"):
            pid = f"{run.action_id}-{name}"
            tuple_pvs.append({"@id": pid})
            entities.append(_pv(pid, name, getattr(t, name), "four-fold provenance component"))
        objects = [{"@id": _config_path(t.config_hash)}, *tuple_pvs]
        action.update(
            {
                "@type": ["CreateAction", "prov:Activity"],
                "containerImage": {"@id": _container_id(t.container_sif_sha256)},
                "instrument": {"@id": software},
                "object": objects,
                "prov:used": sorted(
                    ({"@id": e} for a, e in g.used if a == run.action_id), key=lambda d: d["@id"]
                ),
                "prov:wasAssociatedWith": [{"@id": software}],
            }
        )
        if result is not None and "record-of-provenance" in run.roles:
            pvs = []
            for i, q in enumerate(result.quantities):
                for attr in ("value", "u95_numerical", "u95_statistical", "u95_input", "u95_total"):
                    pid = f"{run.action_id}-q{i}-{attr}"
                    pvs.append({"@id": pid})
                    entities.append(_pv(pid, f"{q.name}.{attr}", getattr(q, attr), q.units or None))
            action["result"] = pvs
        entities.append(action)

    entities.append(
        {
            "@id": WRITER,
            "@type": ["SoftwareApplication", "prov:SoftwareAgent"],
            "name": "aero.crate writer",
            "softwareVersion": "format-1",
            "version": "format-1",
            "url": f"{REPO_URL}/blob/main/docs/adrs/ADR-047-results-must-travel-result-crates.md",
        }
    )
    export_results = sorted(d for a, d in g.generated if a == EXPORT)
    export_objects = sorted(e for a, e in g.used if a == EXPORT)
    entities.append(
        {
            "@id": EXPORT,
            "@type": ["CreateAction", "prov:Activity"],
            "agent": persons,
            "description": "Export of this result crate from the committed records it cites",
            "endTime": manifest.date_published.isoformat(),
            "instrument": {"@id": WRITER},
            "name": "aero result crate export",
            "object": [{"@id": e} for e in export_objects],
            "prov:generated": [{"@id": d} for d in export_results],
            "prov:used": [{"@id": e} for e in export_objects],
            "prov:wasAssociatedWith": sorted(
                ({"@id": a} for x, a in g.associated if x == EXPORT), key=lambda d: d["@id"]
            ),
            "result": [{"@id": d} for d in export_results],
        }
    )
    action_ids.append(EXPORT)

    gate_ids = []
    for verdict in manifest.validity.verdicts:
        for gate in verdict.gates:
            gid = f"#gate-{verdict.scope}-{gate.name}"
            gate_ids.append(gid)
            pv = _pv(
                gid,
                gate.name,
                gate.observed,
                f"{'GATED (pre-registered)' if gate.gated else 'DIAGNOSTIC (reported, never gated)'}"
                f"; {verdict.scope} {verdict.overall}; passed={str(gate.passed).lower()}; "
                f"{gate.criterion}",
            )
            if isinstance(gate.threshold, tuple):
                pv["minValue"], pv["maxValue"] = gate.threshold
            elif gate.threshold is not None:
                key = "maxValue" if gate.comparator in ("lt", "le") else "minValue"
                pv[key] = gate.threshold
            entities.append(pv)
    limitation_ids = []
    for lim in manifest.validity.limitations:
        lid = f"#limitation-{lim.id}"
        limitation_ids.append(lid)
        entities.append(
            {
                "@id": lid,
                "@type": "CreativeWork",
                "isBasedOn": lim.source.locator,
                "name": lim.id,
                "text": lim.text,
            }
        )
    entities.extend(
        [
            {
                "@id": CRATE_LICENSE,
                "@type": "CreativeWork",
                "identifier": "CC-BY-4.0",
                "name": "Creative Commons Attribution 4.0 International",
            },
            {
                "@id": SOFTWARE_LICENSE,
                "@type": "CreativeWork",
                "identifier": "GPL-3.0-or-later",
                "name": "GNU General Public License v3.0 or later",
            },
            {
                "@id": PRC_PROFILE,
                "@type": ["CreativeWork", "Profile"],
                "name": "Process Run Crate",
                "version": "0.6",
            },
            {
                "@id": FORMAT_ENTITY,
                "@type": ["CreativeWork", "Profile"],
                "name": "aero-result-crate format 1 (ADR-047)",
                "version": "1",
            },
            {
                # The platform, cited by its Zenodo concept DOI. A CreativeWork, not a
                # SoftwareSourceCode: RO-Crate 1.3 reads the latter as a Script, which must be a File
                # in the crate.
                "@id": f"https://doi.org/{manifest.software.concept_doi}",
                "@type": "CreativeWork",
                "identifier": manifest.software.concept_doi,
                "license": {"@id": SOFTWARE_LICENSE},
                "name": manifest.software.name,
                "url": manifest.software.repository,
            },
        ]
    )
    root: dict[str, Any] = {
        "@id": "./",
        "@type": "Dataset",
        "author": persons,
        "citation": {"@id": f"https://doi.org/{manifest.software.concept_doi}"},
        "conformsTo": [{"@id": PRC_PROFILE}, {"@id": FORMAT_ENTITY}],
        "datePublished": manifest.date_published.isoformat(),
        "description": manifest.description,
        "hasPart": [{"@id": p} for p in sorted([*digests, "SHA256SUMS"])],
        "identifier": manifest.crate_id,
        "license": {"@id": CRATE_LICENSE},
        "mentions": [{"@id": i} for i in sorted([*action_ids, *gate_ids, *limitation_ids])],
        "name": manifest.title,
    }
    if manifest.payload == "reportable-result":
        root["mainEntity"] = {"@id": "result.json"}
    descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": RO_CRATE_SPEC},
    }
    ordered = sorted(entities, key=lambda e: str(e["@id"]))
    ids = [e["@id"] for e in ordered]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"duplicate RO-Crate entity ids: {dupes}")
    return {"@context": [RO_CRATE_CONTEXT, WFRUN_CONTEXT], "@graph": [descriptor, root, *ordered]}


_DOC_DESCRIPTIONS = {
    "aero-crate.json": "The typed crate envelope (aero-result-crate format 1, ADR-047)",
    "prov.json": "W3C PROV-JSON projection of this crate's provenance graph",
}


def _q(local: str) -> str:
    return f"crate:{local.lstrip('#')}"


def build_prov(manifest: CrateManifest, digests: dict[str, tuple[str, int]]) -> dict[str, Any]:
    """Return the PROV-JSON document (a JSON value). ``digests`` excludes ``prov.json`` itself."""
    g = _relations(manifest)
    qn = {"$": "prov:SoftwareAgent", "type": "prov:QUALIFIED_NAME"}
    person_t = {"$": "prov:Person", "type": "prov:QUALIFIED_NAME"}
    entity: dict[str, Any] = {}
    for path, (sha, size) in sorted(digests.items()):
        entity[_q(path)] = {"schema:contentSize": size, "schema:sha256": sha}
    entity[_q("prov.json")] = {"prov:label": "this PROV-JSON document"}
    for run in manifest.runs:
        prov = _available(run)
        if prov is None:
            continue
        for digest in (
            prov.four_tuple.container_sif_sha256,
            *(r.sha256 for r in prov.four_tuple.containers),
        ):
            entity[_q(_container_id(digest))] = {"schema:sha256": digest}
    agent: dict[str, Any] = {
        _q(WRITER): {"prov:type": dict(qn), "schema:softwareVersion": "format-1"}
    }
    for i, person in enumerate(manifest.creators, 1):
        agent[_q(_person_id(i))] = {"prov:type": dict(person_t), "schema:name": person.name}
    activity: dict[str, Any] = {}
    for run in manifest.runs:
        record: dict[str, Any] = {"prov:label": run.run_id}
        if isinstance(run.provenance, ProvenanceUnavailable):
            record["schema:description"] = "provenance UNAVAILABLE: " + run.provenance.reason
        else:
            sha = run.provenance.four_tuple.git_sha
            agent[_q(_software_id(sha))] = {"prov:type": dict(qn), "schema:softwareVersion": sha}
        activity[_q(run.action_id)] = record
    activity[_q(EXPORT)] = {
        "prov:endTime": manifest.date_published.isoformat() + "T00:00:00Z",
        "prov:label": "aero result crate export",
    }

    def rel(pairs: set[tuple[str, str]], a_key: str, b_key: str, tag: str) -> dict[str, Any]:
        return {
            f"_:{tag}{i}": {a_key: _q(a), b_key: _q(b)} for i, (a, b) in enumerate(sorted(pairs), 1)
        }

    doc: dict[str, Any] = {
        "prefix": {
            "crate": f"arcp://name,{manifest.crate_id}/",
            "schema": "http://schema.org/",
        },
        "entity": entity,
        "activity": activity,
        "agent": agent,
        "used": rel(g.used, "prov:activity", "prov:entity", "u"),
        "wasGeneratedBy": rel(
            {(e, a) for a, e in g.generated}, "prov:entity", "prov:activity", "g"
        ),
        "wasAssociatedWith": rel(g.associated, "prov:activity", "prov:agent", "w"),
        "wasAttributedTo": rel(g.attributed, "prov:entity", "prov:agent", "t"),
    }
    if g.derived:
        doc["wasDerivedFrom"] = rel(g.derived, "prov:generatedEntity", "prov:usedEntity", "d")
    return doc


def relation_sets(manifest: CrateManifest) -> dict[str, set[tuple[str, str]]]:
    """The relation sets both projections encode (used by the conformance checks)."""
    g = _relations(manifest)
    return {
        "used": g.used,
        "generated": g.generated,
        "associated": g.associated,
        "derived": g.derived,
        "attributed": g.attributed,
    }
