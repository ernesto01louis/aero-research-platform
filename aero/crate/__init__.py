"""Result crates: the RESULTS-MUST-TRAVEL bundle (Hard Rule 16; ADR-047, format v1).

A result crate is a self-describing directory, or a deterministic ``.crate.zip``, that carries:
- a ``ReportableResult`` with its four-fold provenance and U95 envelope;
- the exact as-hashed config preimage of every run it cites;
- verbatim evidence;
- a typed validity context;
- RO-Crate 1.3 / Process Run Crate 0.6 and W3C PROV-JSON projections.

It verifies, and reads back to the same numbers bit for bit, with nothing installed but
stdlib + numpy + pydantic. No cluster, no DVC remote, no MLflow and no repository are needed.

    python -I -m aero.crate verify crates/<crate_id>        # or a .crate.zip
    sha256sum -c SHA256SUMS                                  # inside a crate, coreutils only
"""

from __future__ import annotations

from aero.crate.errors import (
    CrateError,
    CrateExpectationError,
    CrateFormatError,
    CrateIntegrityError,
    CrateNonFiniteError,
    CratePathError,
    CrateSemanticError,
    LegacyRecordError,
)
from aero.crate.model import FORMAT_NAME, FORMAT_VERSION, CrateManifest
from aero.crate.reader import VerifiedCrate, verify_crate, verify_members
from aero.crate.writer import CrateSpec, EvidenceFile, build_crate, pack_crate, write_crate

__all__ = [
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "CrateError",
    "CrateExpectationError",
    "CrateFormatError",
    "CrateIntegrityError",
    "CrateManifest",
    "CrateNonFiniteError",
    "CratePathError",
    "CrateSemanticError",
    "CrateSpec",
    "EvidenceFile",
    "LegacyRecordError",
    "VerifiedCrate",
    "build_crate",
    "pack_crate",
    "verify_crate",
    "verify_members",
    "write_crate",
]
