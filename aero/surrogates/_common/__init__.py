"""Shared surrogate scaffolding — protocol, Certificate, provenance, loaders.

This subpackage holds everything that is NOT a concrete model architecture:
the `Surrogate` protocol, the `CertificateOfValidity` Pydantic model, the
`Sample` / `TaintedSample` discriminated union that propagates the CC-BY-NC
boundary from `loaders/non_commercial/` into the certificate, and the
`SurrogateProvenanceTags` helper that composes the four-fold provenance
contract from `aero.provenance` with surrogate-specific MLflow tags.

PLATFORM-NOT-HUB: only stdlib + pydantic are imported eagerly.
"""

from __future__ import annotations

from aero.surrogates._common.base import (
    Sample,
    Surrogate,
    SurrogateProtocol,
    TaintedSample,
    UncertifiedSurrogate,
)
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertExpired,
    CertificateOfValidity,
    LicenseAcknowledgmentRequired,
    MetricQuantiles,
)
from aero.surrogates._common.provenance import SurrogateProvenanceTags

__all__ = [
    "ApplicabilityEnvelope",
    "CertExpired",
    "CertificateOfValidity",
    "LicenseAcknowledgmentRequired",
    "MetricQuantiles",
    "Sample",
    "Surrogate",
    "SurrogateProtocol",
    "SurrogateProvenanceTags",
    "TaintedSample",
    "UncertifiedSurrogate",
]
