"""Seeded bootstrap-GP ensemble member — the Stage-17 own-data surrogate unit (ADR-031).

``GPBootstrapMember`` wraps the Stage-15 pure-numpy
:class:`~aero.optimize.gp.GaussianProcess` as a :class:`~aero.surrogates._common.base.Surrogate`
so it can serve as an :class:`~aero.surrogates._common.ensemble.EnsembleSurrogate` member.
Member diversity — the source of the ensemble's epistemic spread — comes from two
deliberate, seeded mechanisms:

* **bootstrap resampling**: each member fits its GP on a seeded bootstrap draw of its
  training share (the ``seed`` hparam, which ``EnsembleSurrogate.fit`` supplies as
  ``seed + i`` per member);
* **per-member kernel length-scales**: members are constructed with different
  :class:`~aero.optimize.gp.GPConfig` values (Stage 17 uses a 0.20-0.40 spread), so the
  member disagreement carries model-form variance, not just resample variance.

The bootstrap draw is deduplicated before the GP fit: a duplicated (x, y) row carries no
new information for an interpolating GP — keeping multiplicity only shrinks the posterior
variance at that point artificially and degrades the kernel matrix conditioning.

Chosen over torch-MLP members (the ADR-025 smoke-test path) for the Stage-17 corpus:
torch is not installed on the training host, and 3-5 small MLPs on ~40 points in 2-D
calibrate poorly — the held-out ±2·std coverage band is a pre-registered GO gate (C1),
so the member family must be able to pass it honestly. Recorded in ADR-031.

Pure stdlib + numpy + pydantic (PLATFORM-NOT-HUB). NOT re-exported from
``aero/surrogates/__init__.py``: this module imports ``aero.optimize.gp`` while
``aero/optimize/accelerated.py`` imports ``aero.surrogates._common`` — keeping this
module out of the package ``__init__`` keeps the import graph acyclic by construction.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from typing import Any

import numpy as np

from aero.optimize.gp import GaussianProcess, GPConfig
from aero.surrogates._common.base import Sample, Surrogate, TaintedSample
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)


class GPBootstrapMember(Surrogate):
    """One seeded bootstrap-GP regressor of a scalar objective (first target)."""

    def __init__(
        self,
        *,
        gp_config: GPConfig,
        training_dataset_dvc_hash: str,
        dataset_id: str,
        applicability_envelope: ApplicabilityEnvelope,
        metric_name: str = "ld_mae",
    ) -> None:
        super().__init__()
        self._gp_config = gp_config
        self._training_dataset_dvc_hash = training_dataset_dvc_hash
        self._dataset_id = dataset_id
        self._envelope = applicability_envelope
        self._metric_name = metric_name
        self._gp: GaussianProcess | None = None
        self._val_errs: tuple[float, ...] | None = None

    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        """Fit the GP on a seeded bootstrap draw; hold out a seeded validation split.

        Hyperparameters (all consumed here; unknown keys fail loud):
        ``seed=0`` drives BOTH the validation split and the bootstrap draw —
        two members with different seeds see different resamples, which is
        the diversity mechanism; ``val_fraction=0.2`` is the internal split
        the member's own certificate quantiles are measured on (distinct from
        the ensemble-level calibration holdout, which no member ever sees).

        Features are expected in the unit cube (the trust-region/infill
        convention, ADR-032); the target is ``targets[0]`` (the platform's
        first-target scalar convention).
        """
        seed = int(hparams.pop("seed", 0))
        val_fraction = float(hparams.pop("val_fraction", 0.2))
        if hparams:
            raise ValueError(
                f"GPBootstrapMember.fit() got unknown hyperparameters {sorted(hparams)} — "
                "fail-loud: unknown keys always mean drift"
            )
        if not (0.0 < val_fraction < 1.0):
            raise ValueError(f"val_fraction must be in (0, 1); got {val_fraction}")

        samples: list[Sample | TaintedSample] = []
        for sample in data:
            self.ingest(sample)
            samples.append(sample)
        if len(samples) < 3:
            raise ValueError(
                f"GPBootstrapMember.fit() needs >= 3 samples (bootstrap pool + validation "
                f"split); got {len(samples)}"
            )
        n_features = len(samples[0].features)
        if not all(len(s.features) == n_features and len(s.targets) >= 1 for s in samples):
            raise ValueError("GPBootstrapMember.fit() got inhomogeneous feature/target widths")

        rng = np.random.default_rng(seed)
        indices = rng.permutation(len(samples))
        n_val = max(1, round(val_fraction * len(samples)))
        if n_val >= len(samples) - 1:
            raise ValueError(
                f"validation split ({n_val}) would leave < 2 samples to fit on "
                f"(total {len(samples)}); lower val_fraction or supply more data"
            )
        val_idx = indices[:n_val]
        pool_idx = indices[n_val:]

        # Seeded bootstrap draw over the training pool, deduplicated (see module docstring).
        draw = rng.choice(pool_idx, size=pool_idx.size, replace=True)
        fit_idx = np.unique(draw)
        x_fit = np.asarray([samples[i].features for i in fit_idx], dtype=np.float64)
        y_fit = np.asarray([samples[i].targets[0] for i in fit_idx], dtype=np.float64)

        gp = GaussianProcess(self._gp_config)
        gp.fit(x_fit, y_fit)
        self._gp = gp

        x_val = np.asarray([samples[i].features for i in val_idx], dtype=np.float64)
        y_val = np.asarray([samples[i].targets[0] for i in val_idx], dtype=np.float64)
        mean, _ = gp.predict(x_val)
        self._val_errs = tuple(float(e) for e in np.abs(mean - y_val).tolist())

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        # Invariant 9 guard FIRST — before any numerics.
        self.certificate()
        if self._gp is None:
            raise RuntimeError("GPBootstrapMember.predict called before fit()")
        mean, _ = self._gp.predict(np.asarray([features], dtype=np.float64))
        return (float(mean[0]),)

    def _build_certificate(self) -> CertificateOfValidity:
        if self._val_errs is None:
            raise RuntimeError(
                "GPBootstrapMember._build_certificate called before fit() — validation "
                "errors are not populated."
            )
        errs = sorted(self._val_errs)
        n = len(errs)
        p50 = statistics.median(errs)
        p95 = errs[max(0, min(n - 1, round(0.95 * (n - 1))))]
        p99 = errs[max(0, min(n - 1, round(0.99 * (n - 1))))]
        cfg = self._gp_config
        return CertificateOfValidity.new(
            surrogate_name="gp_bootstrap_member",
            model_architecture=f"gp({cfg.kernel}, ls={cfg.length_scale:g})",
            training_dataset_dvc_hash=self._training_dataset_dvc_hash,
            dataset_id=self._dataset_id,
            held_out_metrics={
                self._metric_name: MetricQuantiles(p50=p50, p95=p95, p99=p99, n_held_out=n),
            },
            applicability_envelope=self._envelope,
            cert_status="smoke",
            non_commercial=self._non_commercial,
            data_origin=self._data_origin,
        )
