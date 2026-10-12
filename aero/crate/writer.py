"""Write a result crate (ADR-047): build every byte in memory, verify it, then publish atomically.

The writer runs the full reader on what it is about to write and refuses to publish anything
that would not verify. It refuses destinations under ``data/vv/``, where the ADR-045 absence pins
and the Stage-20 restart gate look, and it refuses the two ADR-045 record names anywhere.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aero.crate._canonical import dumps_document, sha256_hex
from aero.crate.errors import CratePathError
from aero.crate.members import (
    FORBIDDEN_BASENAMES,
    SUMS,
    check_member_name,
    format_sha256sums,
    pack_members,
    read_members,
)
from aero.crate.model import CrateManifest, MemberEntry, RunRecord
from aero.crate.model_base import Person, Reference
from aero.crate.payload import reportable_document
from aero.crate.projections import build_prov, build_rocrate
from aero.crate.reader import VerifiedCrate, verify_members
from aero.crate.validity import Unavailable, ValidityContext
from aero.provenance.four_fold import canonical_config_bytes
from aero.vv.reportable import ReportableResult

__all__ = ["CrateSpec", "EvidenceFile", "build_crate", "pack_crate", "write_crate"]

# The Stage-20 sentinels stay permanently unfilled; a crate member may not carry them either.
_B_SENTINELS = (
    b"<<B1-PENDING-N3>>",
    b"<<B2-PENDING-ADR040>>",
    b"<<B3-PENDING-CEILING>>",
    b"<<B2-PENDING-I4>>",
)


@dataclass(frozen=True)
class EvidenceFile:
    """A verbatim evidence member (opaque bytes), e.g. a committed source record."""

    name: str
    data: bytes
    media_type: str
    description: str
    license: str | None = None

    @property
    def path(self) -> str:
        return f"evidence/{self.name}"


@dataclass(frozen=True)
class CrateSpec:
    """Everything a crate is built from. Not persisted. The envelope is derived from it."""

    crate_id: str
    title: str
    description: str
    date_published: _dt.date
    creators: tuple[Person, ...]
    runs: tuple[RunRecord, ...]
    validity: ValidityContext
    result: ReportableResult | None
    configs: tuple[Mapping[str, Any], ...] = ()
    evidence: tuple[EvidenceFile, ...] = ()
    references: tuple[Reference, ...] = ()
    unavailable: tuple[Unavailable, ...] = ()
    result_description: str = "The ReportableResult (four-tuple, U95 envelope, claim, tier)"
    config_descriptions: Mapping[str, str] = field(default_factory=dict)


def build_crate(spec: CrateSpec) -> dict[str, bytes]:
    """Return the crate as ``{member path: bytes}``, verified by the reader before it is returned."""
    payload: dict[str, bytes] = {}
    entries: list[MemberEntry] = []
    if spec.result is not None:
        payload["result.json"] = dumps_document(reportable_document(spec.result))
        entries.append(
            _entry(
                "result.json",
                "payload",
                "application/json",
                payload["result.json"],
                spec.result_description,
            )
        )
    for cfg in spec.configs:
        data = canonical_config_bytes(cfg)
        digest = sha256_hex(data)
        path = f"configs/{digest}.json"
        payload[path] = data
        desc = spec.config_descriptions.get(
            digest, "Exact as-hashed config preimage: sha256(this file) == the run's config_hash"
        )
        entries.append(_entry(path, "config", "application/json", data, desc))
    for ev in spec.evidence:
        check_member_name(ev.path)
        payload[ev.path] = ev.data
        entries.append(
            _entry(ev.path, "evidence", ev.media_type, ev.data, ev.description, ev.license)
        )
    if len(payload) != len(entries):
        raise CratePathError("two members share a path")

    manifest = CrateManifest(
        crate_id=spec.crate_id,
        title=spec.title,
        description=spec.description,
        date_published=spec.date_published,
        creators=spec.creators,
        payload="reportable-result" if spec.result is not None else "none",
        runs=spec.runs,
        validity=spec.validity,
        references=spec.references,
        unavailable=spec.unavailable,
        members=tuple(sorted(entries, key=lambda e: e.path)),
    )
    members = dict(payload)
    members["aero-crate.json"] = dumps_document(json.loads(manifest.model_dump_json()))
    digests = {p: (sha256_hex(b), len(b)) for p, b in members.items()}
    members["prov.json"] = dumps_document(build_prov(manifest, digests))
    digests["prov.json"] = (sha256_hex(members["prov.json"]), len(members["prov.json"]))
    members["ro-crate-metadata.json"] = dumps_document(
        build_rocrate(manifest, digests, spec.result)
    )
    members[SUMS] = format_sha256sums({p: sha256_hex(b) for p, b in members.items()})
    for name, data in members.items():
        if any(s in data for s in _B_SENTINELS):
            raise CratePathError(f"member {name!r} carries a Stage-20 B-sentinel")
    verify_members(members, origin=f"<build {spec.crate_id}>")
    return members


def _entry(
    path: str, role: str, media: str, data: bytes, description: str, license: str | None = None
) -> MemberEntry:
    return MemberEntry.model_validate(
        {
            "path": path,
            "role": role,
            "media_type": media,
            "sha256": sha256_hex(data),
            "size": len(data),
            "description": description,
            "license": license,
        }
    )


def _check_destination(dest: Path) -> None:
    parts = dest.resolve().parts
    for i in range(len(parts) - 1):
        if parts[i] == "data" and parts[i + 1] == "vv":
            raise CratePathError(
                f"{dest}: crates are never written under data/vv/ (the ADR-045 absence pins and "
                "the Stage-20 restart gate read that directory)"
            )
    if dest.name in FORBIDDEN_BASENAMES:
        raise CratePathError(f"{dest}: an ADR-045 record name")


def write_crate(
    dest: str | Path, members: Mapping[str, bytes], *, replace: bool = False
) -> VerifiedCrate:
    """Publish a built crate as a directory, atomically. The result is verified from disk."""
    dest = Path(dest)
    _check_destination(dest)
    if dest.exists() and not replace:
        raise CratePathError(f"{dest} exists (pass replace=True for a deliberate rewrite)")
    token = sha256_hex(members[SUMS])[:12]
    tmp = dest.parent / f".{dest.name}.partial-{token}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        for name in sorted(members):
            target = tmp / name
            target.parent.mkdir(exist_ok=True)
            with open(target, "xb") as fh:
                fh.write(members[name])
        verified = verify_members(read_members(tmp), origin=str(tmp))
        if dest.exists():
            backup = dest.parent / f".{dest.name}.replaced-{token}"
            os.replace(dest, backup)
            os.replace(tmp, dest)
            shutil.rmtree(backup)
        else:
            os.replace(tmp, dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return VerifiedCrate(
        manifest=verified.manifest,
        result=verified.result,
        digest=verified.digest,
        members=verified.members,
        origin=str(dest),
    )


def pack_crate(members: Mapping[str, bytes]) -> bytes:
    """The deterministic ``.crate.zip`` form of a crate (ZIP_STORED, fixed metadata, sorted)."""
    verify_members(dict(members), origin="<pack>")
    return pack_members(dict(members))
