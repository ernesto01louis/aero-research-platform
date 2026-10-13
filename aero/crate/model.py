"""The typed envelope of a result crate: ``aero-crate.json`` (``CrateManifest``, ADR-047 D1/D4).

The envelope is the single source of truth. ``ro-crate-metadata.json`` and ``prov.json`` are
deterministic projections of it, regenerated and compared byte for byte on read. The payload
(``result.json``) and the config preimages are separate members, pinned by sha256 in
:attr:`CrateManifest.members`.
"""

from __future__ import annotations

import datetime as _dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from aero.crate.model_base import (
    CRATE_CONFIG,
    CRATE_ID_RE,
    HEX40_RE,
    HEX64_RE,
    MEMBER_PATH_RE,
    Person,
    Reference,
)
from aero.crate.validity import Unavailable, ValidityContext
from aero.provenance.four_fold import ProvenanceTuple

__all__ = [
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "CodeIdentity",
    "CrateManifest",
    "MemberEntry",
    "ProvenanceAvailable",
    "ProvenanceUnavailable",
    "RunRecord",
    "SoftwareRef",
]

FORMAT_NAME = "aero-result-crate"
FORMAT_VERSION = 1

_UUID4_ACTION_RE = r"^#[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"

RunRole = Literal[
    "record-of-provenance",
    "cfd-verification",
    "grid-family",
    "forward-validation",
    "contributing",
]


class MemberEntry(BaseModel):
    """One payload / config / evidence member, pinned by sha256 and size."""

    model_config = CRATE_CONFIG

    path: str = Field(..., pattern=MEMBER_PATH_RE)
    role: Literal["payload", "config", "evidence"]
    media_type: str = Field(..., pattern=r"^[a-z]+/[a-z0-9.+-]+$")
    sha256: str = Field(..., pattern=HEX64_RE)
    size: int = Field(..., ge=0)
    description: str = Field(..., min_length=1)
    license: str | None = Field(
        default=None, description="SPDX id when this member's licence differs from the crate's."
    )


class CodeIdentity(BaseModel):
    """Which code produced a run, and whether anyone else can check it out."""

    model_config = CRATE_CONFIG

    git_sha: str = Field(..., pattern=HEX40_RE, description="Never -dirty.")
    equivalent_tag: str | None = Field(default=None, pattern=r"^v\d+\.\d+\.\d+$")
    equivalent_tag_commit: str | None = Field(default=None, pattern=HEX40_RE)
    equivalence: Literal[
        "is-tag-commit", "code-trees-identical", "code-trees-differ", "not-established"
    ]
    differing_paths: tuple[str, ...] = ()
    publicly_resolvable: bool
    public_refs: tuple[str, ...] = Field(
        default=(), description="Refs on the public remote that contain git_sha."
    )

    @model_validator(mode="after")
    def _consistent(self) -> CodeIdentity:
        if (self.equivalent_tag is None) != (self.equivalent_tag_commit is None):
            raise ValueError("equivalent_tag and equivalent_tag_commit go together")
        if self.equivalence != "not-established" and self.equivalent_tag is None:
            raise ValueError(f"equivalence {self.equivalence!r} needs an equivalent_tag")
        if self.equivalence == "is-tag-commit" and self.git_sha != self.equivalent_tag_commit:
            raise ValueError("is-tag-commit but git_sha != equivalent_tag_commit")
        if (self.equivalence == "code-trees-differ") != bool(self.differing_paths):
            raise ValueError("differing_paths is required iff equivalence is code-trees-differ")
        if self.publicly_resolvable != bool(self.public_refs):
            raise ValueError("a publicly resolvable commit names the public refs that hold it")
        return self


class ProvenanceAvailable(BaseModel):
    model_config = CRATE_CONFIG

    status: Literal["available"] = "available"
    four_tuple: ProvenanceTuple
    code: CodeIdentity

    @model_validator(mode="after")
    def _code_matches(self) -> ProvenanceAvailable:
        if self.four_tuple.git_sha.endswith("-dirty"):
            raise ValueError("a dirty-tree run cannot be crated: its code is not reproducible")
        if self.code.git_sha != self.four_tuple.git_sha:
            raise ValueError("code.git_sha != four_tuple.git_sha")
        return self


class ProvenanceUnavailable(BaseModel):
    """A run whose four-tuple was never recorded. Declared, never defaulted."""

    model_config = CRATE_CONFIG

    status: Literal["unavailable"] = "unavailable"
    missing: tuple[
        Literal["git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash"], ...
    ] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    code_at_tag: str | None = Field(default=None, pattern=r"^v\d+\.\d+\.\d+$")

    @model_validator(mode="after")
    def _unique(self) -> ProvenanceUnavailable:
        if len(set(self.missing)) != len(self.missing):
            raise ValueError("missing lists a field twice")
        return self


class RunRecord(BaseModel):
    """One solver run the crate cites. It projects to a CreateAction in the RO-Crate."""

    model_config = CRATE_CONFIG

    run_id: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    action_id: str = Field(..., pattern=_UUID4_ACTION_RE)
    roles: tuple[RunRole, ...] = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    provenance: Annotated[
        ProvenanceAvailable | ProvenanceUnavailable, Field(discriminator="status")
    ]

    @model_validator(mode="after")
    def _roles(self) -> RunRecord:
        if len(set(self.roles)) != len(self.roles):
            raise ValueError(f"run {self.run_id!r} repeats a role")
        if isinstance(self.provenance, ProvenanceUnavailable) and (
            {"record-of-provenance", "cfd-verification"} & set(self.roles)
        ):
            raise ValueError(
                f"run {self.run_id!r} has no four-tuple, so it cannot be the record of "
                "provenance or the CFD verification"
            )
        return self


class SoftwareRef(BaseModel):
    """The software the crate's runs were produced by (the platform, cited by concept DOI)."""

    model_config = CRATE_CONFIG

    name: Literal["aero-research-platform"] = "aero-research-platform"
    repository: Literal["https://github.com/ernesto01louis/aero-research-platform"] = (
        "https://github.com/ernesto01louis/aero-research-platform"
    )
    concept_doi: Literal["10.5281/zenodo.20292712"] = "10.5281/zenodo.20292712"
    license: Literal["GPL-3.0-or-later"] = "GPL-3.0-or-later"


class CrateManifest(BaseModel):
    """``aero-crate.json``."""

    model_config = CRATE_CONFIG

    format: Literal["aero-result-crate"] = "aero-result-crate"
    format_version: Literal[1] = 1
    crate_id: str = Field(..., pattern=CRATE_ID_RE)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    date_published: _dt.date = Field(
        ..., description="Fixed by the exporter, never wall-clock, so rewriting is idempotent."
    )
    license: Literal["CC-BY-4.0"] = Field(
        default="CC-BY-4.0", description="Licence of the crate's content (operator decision D3)."
    )
    creators: tuple[Person, ...] = Field(..., min_length=1)
    software: SoftwareRef = SoftwareRef()
    payload: Literal["reportable-result", "none"]
    runs: tuple[RunRecord, ...] = Field(..., min_length=1)
    validity: ValidityContext
    references: tuple[Reference, ...] = ()
    unavailable: tuple[Unavailable, ...] = ()
    members: tuple[MemberEntry, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _structure(self) -> CrateManifest:
        paths = [m.path for m in self.members]
        if paths != sorted(paths) or len(set(paths)) != len(paths):
            raise ValueError("members must be unique and path-sorted")
        if any(p in _RESERVED for p in paths):
            raise ValueError(f"members may not list the reserved documents {sorted(_RESERVED)}")
        payloads = [m for m in self.members if m.role == "payload"]
        if self.payload == "reportable-result":
            if [m.path for m in payloads] != ["result.json"]:
                raise ValueError("a reportable-result crate has exactly one payload: result.json")
        elif payloads:
            raise ValueError("an evidence-only crate (payload='none') has no payload member")
        for m in self.members:
            if m.role == "config" and not (
                m.path.startswith("configs/") and m.path.endswith(".json")
            ):
                raise ValueError(f"config member {m.path!r} must be configs/<config_hash>.json")
            if m.role == "evidence" and not m.path.startswith("evidence/"):
                raise ValueError(f"evidence member {m.path!r} must live under evidence/")
        run_ids = [r.run_id for r in self.runs]
        actions = [r.action_id for r in self.runs]
        if len(set(run_ids)) != len(run_ids) or len(set(actions)) != len(actions):
            raise ValueError("run ids and action ids must be unique")
        return self


# Members the envelope cannot pin (they are, or depend on, the envelope itself).
_RESERVED = frozenset({"SHA256SUMS", "aero-crate.json", "ro-crate-metadata.json", "prov.json"})
RESERVED_DOCUMENTS = _RESERVED
