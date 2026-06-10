"""Surrogate-vs-CFD V&V cross-check (Stage 09).

The falsifiable evidence behind a surrogate's :class:`CertificateOfValidity`:
predict on held-out cases, compare against the CFD reference, and verify the
cert's claimed envelope. Distinct from the solver-V&V harness (``aero.vv.tmr``
etc.) — see ADR-010. Used for DoMINO in Stage 09; reused for the Stage-10
ensemble.
"""

from __future__ import annotations

from aero.vv.surrogate.compare_surrogate_cfd import (
    DEFAULT_CD_TOLERANCE,
    DEFAULT_TARGET_NAMES,
    SurrogateCaseComparison,
    SurrogateVVCase,
    SurrogateVVReport,
    compare_surrogate_cfd,
)

__all__ = [
    "DEFAULT_CD_TOLERANCE",
    "DEFAULT_TARGET_NAMES",
    "SurrogateCaseComparison",
    "SurrogateVVCase",
    "SurrogateVVReport",
    "compare_surrogate_cfd",
]
