"""ML surrogate scaffolding — Stage 08's protocol + Certificate contract.

A *surrogate* in this platform is a learned mapping from geometry / flow
inputs to flow outputs, paired with a typed `CertificateOfValidity` that
records the training distribution, held-out error quantiles, applicability
envelope, and expiry policy. Stage 14's NeMo Agent Toolkit refuses to call
`Surrogate.predict(...)` without first calling `Surrogate.certificate().
validate()` and routing on the result (CONSTITUTION Invariant 9).

Only stdlib + numpy + pydantic names are imported eagerly (numpy arrived with
the ADR-025 ensemble/calibration/infill aggregation in ``_common/``). Torch /
JAX / PyG live behind the `aero[surrogate-smoke]` extra and are lazy-imported
inside ``baselines/`` and ``_common/loaders/*``. PLATFORM-NOT-HUB.
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
    MetricQuantiles,
)
from aero.surrogates._common.provenance import SurrogateProvenanceTags

__all__ = [
    "ApplicabilityEnvelope",
    "CertExpired",
    "CertificateOfValidity",
    "MetricQuantiles",
    "Sample",
    "Surrogate",
    "SurrogateProtocol",
    "SurrogateProvenanceTags",
    "TaintedSample",
    "UncertifiedSurrogate",
]
