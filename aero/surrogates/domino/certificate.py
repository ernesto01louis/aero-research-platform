"""DoMINO certificate generation + the smoke->validated upgrade gate.

Separated from ``model.py`` per the Stage-09 bundle: this module owns the
*policy* that turns held-out evaluation numbers into a typed
:class:`~aero.surrogates._common.certificate.CertificateOfValidity`, including
the single gate that may upgrade ``cert_status`` from ``"smoke"`` to
``"validated"``.

Centralising the gate here means neither :class:`~aero.surrogates.domino.model.
DominoSurrogate` nor the training loop can hand-wave a "validated" claim — the
only path to ``cert_status="validated"`` is through :func:`build_domino_certificate`
with ``upgrade_to_validated=True`` AND a held-out Cd MAE p95 below the threshold.

The threshold (Cd MAE p95 < 5%) is the contract named in CONSTITUTION Invariant 9
and the ``CertificateOfValidity`` docstring. It is a *surrogate-validation* gate
against held-out DrivAerML — distinct from the solver-V&V / NASA-TMR dashboard
(CONSTITUTION Invariant 5). ADR-010 de-conflates the two: a DoMINO "validated"
cert does NOT require a green TMR dashboard; the ``"production"`` tier (Stage-14
agent-callable) is what stays gated on it.

PLATFORM-NOT-HUB: stdlib + pydantic only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)

# The production-cert gate: DoMINO upgrades smoke->validated iff the held-out
# Cd mean-absolute-error 95th percentile is under 5% (CONSTITUTION Invariant 9).
VALIDATED_CD_P95_THRESHOLD: float = 0.05

# The architecture identifier logged in the cert + the eight provenance tags.
MODEL_ARCHITECTURE: Literal["domino"] = "domino"

# The held-out metric key the gate reads. The training loop logs absolute Cd
# error quantiles under this name; other targets (cl/clf/clr/cs, surface-field
# RMSE) ride alongside but do not gate the upgrade.
CD_METRIC_KEY: str = "cd_mae"


def meets_validated_gate(held_out_metrics: Mapping[str, MetricQuantiles]) -> bool:
    """True iff the held-out Cd MAE p95 is strictly under the 5% threshold.

    Returns ``False`` (not an error) if the Cd metric is absent — a cert with no
    Cd evidence cannot be ``"validated"``.
    """
    cd = held_out_metrics.get(CD_METRIC_KEY)
    return cd is not None and cd.p95 < VALIDATED_CD_P95_THRESHOLD


def build_domino_certificate(
    *,
    surrogate_name: str,
    training_dataset_dvc_hash: str,
    dataset_id: str,
    held_out_metrics: Mapping[str, MetricQuantiles],
    applicability_envelope: ApplicabilityEnvelope,
    non_commercial: bool,
    data_origin: Literal["platform-validated", "foreign"] = "foreign",
    license_id: str = "",
    attribution_required: tuple[str, ...] = (),
    upgrade_to_validated: bool = False,
) -> CertificateOfValidity:
    """Construct DoMINO's certificate from held-out evaluation results.

    ``cert_status`` is ``"smoke"`` unless ``upgrade_to_validated`` is set AND
    :func:`meets_validated_gate` passes; otherwise it stays ``"smoke"`` even if
    the caller asked to upgrade. The ``non_commercial`` taint is passed straight
    through (DrivAerML is CC-BY-SA, so the production path is ``False``; the
    surrogate base class is still the source of truth and re-asserts it in
    :meth:`Surrogate.set_certificate`).
    """
    status: Literal["smoke", "validated", "production"] = "smoke"
    if upgrade_to_validated and meets_validated_gate(held_out_metrics):
        status = "validated"
    return CertificateOfValidity.new(
        surrogate_name=surrogate_name,
        model_architecture=MODEL_ARCHITECTURE,
        training_dataset_dvc_hash=training_dataset_dvc_hash,
        dataset_id=dataset_id,
        held_out_metrics=dict(held_out_metrics),
        applicability_envelope=applicability_envelope,
        cert_status=status,
        non_commercial=non_commercial,
        data_origin=data_origin,
        license_id=license_id,
        attribution_required=attribution_required,
    )


def quantiles_from_abs_errors(abs_errors: tuple[float, ...]) -> MetricQuantiles:
    """Build a :class:`MetricQuantiles` from a sequence of held-out absolute errors.

    Mirrors the nearest-rank quantile convention used by the Stage-08 baselines
    (``aero/surrogates/baselines/mlp_baseline.py``) so the cert's quantiles are
    computed identically across every surrogate.
    """
    import statistics

    if not abs_errors:
        raise ValueError("cannot compute held-out quantiles from an empty error vector")
    errs = sorted(abs_errors)
    n = len(errs)
    p50 = statistics.median(errs)
    p95 = errs[max(0, min(n - 1, round(0.95 * (n - 1))))]
    p99 = errs[max(0, min(n - 1, round(0.99 * (n - 1))))]
    return MetricQuantiles(p50=p50, p95=p95, p99=p99, n_held_out=n)
