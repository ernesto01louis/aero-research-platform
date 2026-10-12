"""The result-crate exception family (ADR-047). Every refusal is a :class:`CrateError`."""

from __future__ import annotations

__all__ = [
    "CrateError",
    "CrateExpectationError",
    "CrateFormatError",
    "CrateIntegrityError",
    "CrateNonFiniteError",
    "CratePathError",
    "CrateSemanticError",
    "LegacyRecordError",
]


class CrateError(ValueError):
    """A result crate was refused. FAIL-LOUD: there is never a partial or best-effort read."""


class CrateIntegrityError(CrateError):
    """Fixity failed: a hash, size, member set or expected crate digest does not match."""


class CrateExpectationError(CrateIntegrityError):
    """The crate verified, but its digest is not the one the caller expected (out-of-band check)."""


class CrateFormatError(CrateError):
    """A member is not in the exact byte format v1 requires (strict JSON, canonical form, …)."""


class CrateSemanticError(CrateError):
    """The content is well-formed but inconsistent: a cross-file rule or validity rule failed."""


class CrateNonFiniteError(CrateFormatError):
    """A non-finite number (NaN, ±inf) where format v1 forbids one."""


class CratePathError(CrateError):
    """An unsafe or forbidden member name, archive entry, or write destination."""


class LegacyRecordError(CrateError):
    """A committed ``data/vv`` record cannot be imported faithfully (e.g. schema drift)."""
