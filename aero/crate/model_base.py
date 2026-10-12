"""Shared building blocks of the crate models: the strict config, id patterns, references."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CRATE_CONFIG",
    "CRATE_ID_RE",
    "HEX40_RE",
    "HEX64_RE",
    "MEMBER_PATH_RE",
    "Person",
    "Reference",
]

# Strict, frozen, finite. No computed fields anywhere in the crate models: every value in
# aero-crate.json is stored, and every derived value is re-checked by a validator.
CRATE_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_default=True,
    allow_inf_nan=False,
)

CRATE_ID_RE = r"^stage\d{2}-[a-z0-9-]{3,60}$"
HEX40_RE = r"^[0-9a-f]{40}$"
HEX64_RE = r"^[0-9a-f]{64}$"
# A member path: at most two lowercase segments, e.g. "result.json" or "configs/<hash>.json".
MEMBER_PATH_RE = r"^[a-z0-9][a-z0-9._-]{0,94}(/[a-z0-9][a-z0-9._-]{0,94})?$"


class Person(BaseModel):
    """A creator, by name only. ORCIDs live in CITATION.cff / .zenodo.json, never in crate bytes."""

    model_config = CRATE_CONFIG

    name: str = Field(..., min_length=1)


class Reference(BaseModel):
    """A pointer to a source: a repo file at a commit, an ADR, a DOI, a container, a git ref."""

    model_config = CRATE_CONFIG

    role: Literal[
        "source-record",
        "superseded-record",
        "handoff",
        "adr",
        "preregistration",
        "git-ref",
        "container",
        "dataset",
        "reference-data",
        "code",
    ]
    locator: str = Field(..., min_length=1, description="Repo path, URL, DOI or ref name.")
    commit: str | None = Field(default=None, pattern=HEX40_RE)
    lines: str | None = Field(default=None, pattern=r"^\d+(-\d+)?$")
    sha256: str | None = Field(default=None, pattern=HEX64_RE)
    embedded_as: str | None = Field(
        default=None, pattern=MEMBER_PATH_RE, description="Member path if embedded verbatim."
    )
