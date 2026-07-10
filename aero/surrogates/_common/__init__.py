"""Shared surrogate scaffolding — protocol, Certificate, provenance, loaders.

This subpackage holds everything that is NOT a concrete model architecture:
the `Surrogate` protocol, the `CertificateOfValidity` Pydantic model, the
`Sample` / `TaintedSample` discriminated union that propagates the CC-BY-NC
boundary from `loaders/non_commercial/` into the certificate, and the
`SurrogateProvenanceTags` helper that composes the four-fold provenance
contract from `aero.provenance` with surrogate-specific MLflow tags.

PLATFORM-NOT-HUB: only stdlib + numpy + pydantic are imported eagerly
(numpy arrived with the ADR-025 ensemble/calibration aggregation).
"""

from __future__ import annotations

from aero.surrogates._common.base import (
    Sample,
    Surrogate,
    SurrogatePrediction,
    SurrogateProtocol,
    TaintedSample,
    UncertaintyAwareSurrogateProtocol,
    UncertifiedSurrogate,
)
from aero.surrogates._common.calibration import (
    CalibrationError,
    compute_uncertainty_calibration,
    nominal_coverage,
)
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertExpired,
    CertificateOfValidity,
    LicenseAcknowledgmentRequired,
    MetricQuantiles,
    UncertaintyCalibration,
)
from aero.surrogates._common.ensemble import EnsembleSurrogate
from aero.surrogates._common.provenance import SurrogateProvenanceTags

__all__ = [
    "ApplicabilityEnvelope",
    "CalibrationError",
    "CertExpired",
    "CertificateOfValidity",
    "EnsembleSurrogate",
    "LicenseAcknowledgmentRequired",
    "MetricQuantiles",
    "Sample",
    "Surrogate",
    "SurrogatePrediction",
    "SurrogateProtocol",
    "SurrogateProvenanceTags",
    "TaintedSample",
    "UncertaintyAwareSurrogateProtocol",
    "UncertaintyCalibration",
    "UncertifiedSurrogate",
    "compute_uncertainty_calibration",
    "nominal_coverage",
]
