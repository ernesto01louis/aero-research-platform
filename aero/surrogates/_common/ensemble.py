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
each member. The cert built by ``fit``/``set_certificate`` always ships
``cert_status="smoke"``; the ONLY upgrade path is the gated
:meth:`EnsembleSurrogate.promote_to_validated` (held-out error AND calibration
band, own-data only — Stage-17 gates C1/C2/C4, ADR-031/032), never a
constructor decision.

``basis`` labels the member family honestly: ``"deep_ensemble"`` for NN
members (ADR-025 default), ``"gp_bootstrap"`` for seeded bootstrap-resampled
GP members (Stage 17, ADR-031). ``metric_name`` names the held-out MAE metric
key in the cert (``"cd_mae"`` default; Stage 17 uses ``"ld_mae"``).

Aggregation is pure numpy; torch/JAX only ever appear inside the members' own
lazy imports (PLATFORM-NOT-HUB).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from typing import Any, Literal

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


class PromotionRefused(RuntimeError):  # noqa: N818 — domain-natural state name
    """A gated ``promote_to_validated`` call failed one of its pre-registered gates.

    Raised loud with the failing gate named — never a silent keep-smoke. The
    caller (a stage driver) records the refusal as campaign evidence; the
    NO-GO fallback is direct-CFD BO, not a quieter certificate.
    """


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
        basis: Literal["deep_ensemble", "gp_bootstrap"] = "deep_ensemble",
        metric_name: str = "cd_mae",
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
        self._basis: Literal["deep_ensemble", "gp_bootstrap"] = basis
        self._metric_name = metric_name
        # Held-out evidence, populated by fit().
        self._errs: tuple[float, ...] | None = None
        self._calibration: UncertaintyCalibration | None = None
        self._calibration_case_ids: tuple[str, ...] = ()

    @property
    def n_members(self) -> int:
        return len(self._members)

    @property
    def calibration_case_ids(self) -> tuple[str, ...]:
        """The case_ids of the held-out split the calibration evidence was measured on.

        Provenance for the certificate's ``uncertainty_calibration``: these are
        the cases NO member trained on, so the coverage/z evidence is genuinely
        out-of-sample. Empty until :meth:`fit` runs.
        """
        return self._calibration_case_ids

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
        self._calibration_case_ids = tuple(s.case_id for s in holdout)

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
            basis=self._basis,
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
            basis=self._basis,
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
            model_architecture=f"{self._basis}({member_arch}, n={len(self._members)})",
            training_dataset_dvc_hash=self._training_dataset_dvc_hash,
            dataset_id=self._dataset_id,
            held_out_metrics={
                self._metric_name: MetricQuantiles(p50=p50, p95=p95, p99=p99, n_held_out=n),
            },
            applicability_envelope=self._envelope,
            cert_status="smoke",
            non_commercial=self._non_commercial,
            data_origin=self._data_origin,
            ensemble_size=len(self._members),
            uncertainty_calibration=self._calibration,
        )

    def promote_to_validated(
        self,
        *,
        max_metric_p95: float,
        coverage_min: float = 0.85,
        coverage_max: float = 1.0,
    ) -> CertificateOfValidity:
        """Re-issue + cache the cert at ``cert_status="validated"`` IF every gate passes.

        The only path to a ``"validated"`` ensemble cert (mirrors the DoMINO
        pattern, ADR-010, but fail-loud): raises :class:`PromotionRefused`
        naming the first failing gate instead of silently keeping ``"smoke"``.
        Gates (pre-registered per campaign, ADR-032; never relaxed after data
        exists):

        * held-out ``|error|`` p95 <= ``max_metric_p95`` (accuracy gate, C2);
        * calibration ``empirical_coverage`` in ``[coverage_min, coverage_max]``
          (C1; the collapsed-ensemble refusal C3 already fired in ``fit``);
        * ``data_origin == "platform-validated"`` (Invariant 11, C4 — also
          structurally unconstructible via the cert validator).
        """
        if self._errs is None or self._calibration is None:
            raise RuntimeError("promote_to_validated() called before fit()")
        if self._data_origin == "foreign":
            raise PromotionRefused(
                "CONSTITUTION Invariant 11 (NO-SURROGATE-ON-FOREIGN-DATA): cannot promote an "
                "ensemble trained on foreign data to cert_status='validated'. It may seed "
                "'smoke' experiments only. Retrain on the platform's own validated CFD."
            )
        smoke = self.certificate()
        quantiles = smoke.held_out_metrics[self._metric_name]
        if quantiles.p95 > max_metric_p95:
            raise PromotionRefused(
                f"accuracy gate failed: held-out {self._metric_name} p95 = {quantiles.p95:.6g} "
                f"> pre-registered bar {max_metric_p95:.6g} (n_held_out={quantiles.n_held_out})"
            )
        coverage = self._calibration.empirical_coverage
        if not (coverage_min <= coverage <= coverage_max):
            raise PromotionRefused(
                f"calibration gate failed: empirical ±{self._calibration.interval_k:g}·std "
                f"coverage = {coverage:.4f} outside pre-registered band "
                f"[{coverage_min}, {coverage_max}] (n_held_out={self._calibration.n_held_out})"
            )
        cert = smoke.model_copy(update={"cert_status": "validated"})
        # Frozen-model copy skips validators, so re-validate explicitly: the
        # Invariant-11 foreign-cannot-be-validated guard must fire on every path.
        cert = CertificateOfValidity.model_validate(cert.model_dump())
        self._certificate = cert
        return cert
