"""Deep-ensemble surrogate — epistemic uncertainty from independently-seeded members (ADR-025).

``EnsembleSurrogate`` wraps N ≥ 2 pre-constructed, untrained members of ANY
:class:`~aero.surrogates._common.base.Surrogate` implementation. ``fit`` holds
out a seeded calibration split, trains each member on the remaining samples
with a per-member seed (``seed + i``), then evaluates the ensemble's predictive
mean / spread on the holdout to cache (a) held-out error quantiles and (b) the
:class:`~aero.surrogates._common.certificate.UncertaintyCalibration` evidence
the certificate carries.

The ensemble is itself a ``Surrogate``: taint (CC-BY-NC) and data-origin
(Invariant 11) propagate at the ensemble level through the inherited
:meth:`~aero.surrogates._common.base.Surrogate.ingest`, exactly as they do for
each member. The cert always ships ``cert_status="smoke"`` — promotion to
``validated`` is a Stage-16 gate (held-out error AND calibration band), not a
constructor decision.

Aggregation is pure numpy; torch/JAX only ever appear inside the members' own
lazy imports (PLATFORM-NOT-HUB).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

from aero.surrogates._common.base import (
    Sample,
    Surrogate,
    SurrogatePrediction,
    TaintedSample,
)
from aero.surrogates._common.calibration import compute_uncertainty_calibration
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
    UncertaintyCalibration,
)


class EnsembleSurrogate(Surrogate):
    """N independently-seeded members; mean prediction + ddof=1 epistemic spread."""

    def __init__(
        self,
        members: Sequence[Surrogate],
        *,
        surrogate_name: str = "ensemble",
        training_dataset_dvc_hash: str,
        dataset_id: str,
        applicability_envelope: ApplicabilityEnvelope,
    ) -> None:
        super().__init__()
        member_tuple = tuple(members)
        if len(member_tuple) < 2:
            raise ValueError(
                f"EnsembleSurrogate needs >= 2 members to estimate epistemic spread; "
                f"got {len(member_tuple)}"
            )
        self._members = member_tuple
        self._surrogate_name = surrogate_name
        self._training_dataset_dvc_hash = training_dataset_dvc_hash
        self._dataset_id = dataset_id
        self._envelope = applicability_envelope
        # Held-out evidence, populated by fit().
        self._errs: tuple[float, ...] | None = None
        self._calibration: UncertaintyCalibration | None = None

    @property
    def n_members(self) -> int:
        return len(self._members)

    # --- Surrogate seams ------------------------------------------------------
    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        """Train every member on a shared split; cache holdout error + calibration.

        Ensemble-level hyperparameters (consumed here, not forwarded):
        ``seed=0`` (member ``i`` trains with ``seed + i``),
        ``calibration_fraction=0.2`` (seeded holdout share),
        ``interval_k=2.0`` (calibration interval half-width, in stds).
        Every other hyperparameter passes through to each member's ``fit``.

        Raises loud on: empty data, inhomogeneous sample widths, a holdout that
        would consume every sample, and (via ``compute_uncertainty_calibration``)
        a collapsed ensemble — members that predict bit-identically on the
        holdout carry no epistemic information and must not be certified.
        """
        seed = int(hparams.pop("seed", 0))
        calibration_fraction = float(hparams.pop("calibration_fraction", 0.2))
        interval_k = float(hparams.pop("interval_k", 2.0))
        if not (0.0 < calibration_fraction < 1.0):
            raise ValueError(f"calibration_fraction must be in (0, 1); got {calibration_fraction}")

        # Buffer the stream — ensemble-level taint/origin propagation happens
        # here; each member re-ingests its own training share below.
        samples: list[Sample | TaintedSample] = []
        for sample in data:
            self.ingest(sample)
            samples.append(sample)
        if len(samples) < 2:
            raise ValueError(
                f"EnsembleSurrogate.fit() needs >= 2 samples (train + calibration holdout); "
                f"got {len(samples)}"
            )
        n_features = len(samples[0].features)
        n_targets = len(samples[0].targets)
        if not all(len(s.features) == n_features and len(s.targets) == n_targets for s in samples):
            raise ValueError("EnsembleSurrogate.fit() got inhomogeneous feature/target widths")

        rng = np.random.default_rng(seed)
        indices = rng.permutation(len(samples))
        n_cal = max(1, round(calibration_fraction * len(samples)))
        if n_cal >= len(samples):
            raise ValueError(
                f"calibration holdout ({n_cal}) would consume all {len(samples)} samples; "
                "lower calibration_fraction or supply more data"
            )
        cal_idx = set(indices[:n_cal].tolist())
        train = [s for i, s in enumerate(samples) if i not in cal_idx]
        holdout = [s for i, s in enumerate(samples) if i in cal_idx]

        for i, member in enumerate(self._members):
            member.fit(train, **{**hparams, "seed": seed + i})
            member.set_certificate()

        # Held-out evaluation of the ensemble (first target — Cd by convention).
        targets = np.asarray([s.targets[0] for s in holdout], dtype=np.float64)
        means = np.empty(len(holdout), dtype=np.float64)
        stds = np.empty(len(holdout), dtype=np.float64)
        for j, s in enumerate(holdout):
            member_matrix = self._member_predictions(s.features)
            means[j] = float(member_matrix[:, 0].mean())
            stds[j] = float(member_matrix[:, 0].std(ddof=1))

        self._calibration = compute_uncertainty_calibration(
            targets.tolist(),
            means.tolist(),
            stds.tolist(),
            interval_k=interval_k,
            basis="deep_ensemble",
        )
        self._errs = tuple(float(e) for e in np.abs(means - targets).tolist())

    def _member_predictions(self, features: tuple[float, ...], /) -> np.ndarray:
        """All member predictions as an (n_members, width) array; fail-loud on width drift."""
        rows = [member.predict(features) for member in self._members]
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError(
                f"ensemble members disagree on output width: {[len(r) for r in rows]} — "
                "members must share one target schema"
            )
        return np.asarray(rows, dtype=np.float64)

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        # Validate the ENSEMBLE cert first (Invariant 9); members were certified in fit().
        self.certificate()
        mean = self._member_predictions(features).mean(axis=0)
        return tuple(float(v) for v in mean.tolist())

    def predict_with_uncertainty(self, features: tuple[float, ...], /) -> SurrogatePrediction:
        self.certificate()
        member_matrix = self._member_predictions(features)
        mean = member_matrix.mean(axis=0)
        std = member_matrix.std(axis=0, ddof=1)
        return SurrogatePrediction(
            mean=tuple(float(v) for v in mean.tolist()),
            epistemic_std=tuple(float(v) for v in std.tolist()),
            basis="deep_ensemble",
            n_members=len(self._members),
        )

    def _build_certificate(self) -> CertificateOfValidity:
        if self._errs is None or self._calibration is None:
            raise RuntimeError(
                "EnsembleSurrogate._build_certificate called before fit() — held-out "
                "evidence is not populated."
            )
        errs = sorted(self._errs)
        n = len(errs)
        p50 = statistics.median(errs)
        p95 = errs[max(0, min(n - 1, round(0.95 * (n - 1))))]
        p99 = errs[max(0, min(n - 1, round(0.99 * (n - 1))))]
        # certificate() on an unfitted member raises UncertifiedSurrogate — loud.
        architectures = dict.fromkeys(
            member.certificate().model_architecture for member in self._members
        )
        member_arch = "|".join(architectures)
        return CertificateOfValidity.new(
            surrogate_name=self._surrogate_name,
            model_architecture=f"deep_ensemble({member_arch}, n={len(self._members)})",
            training_dataset_dvc_hash=self._training_dataset_dvc_hash,
            dataset_id=self._dataset_id,
            held_out_metrics={
                "cd_mae": MetricQuantiles(p50=p50, p95=p95, p99=p99, n_held_out=n),
            },
            applicability_envelope=self._envelope,
            cert_status="smoke",
            non_commercial=self._non_commercial,
            data_origin=self._data_origin,
            ensemble_size=len(self._members),
            uncertainty_calibration=self._calibration,
        )
