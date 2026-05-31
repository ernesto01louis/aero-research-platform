"""MLP baseline — smallest Stage-08 surrogate; validates the protocol end-to-end.

Predicts Cd from a small geometry-feature vector (e.g. AhmedML's 4-vector
``(slant_angle_deg, length_ratio, clearance_ratio, front_pillar_radius_m)``).

This baseline is INTENTIONALLY trivial — its job is to shake out:

* :class:`Surrogate` protocol seams (fit/ingest/set_certificate/predict).
* :class:`Sample` / :class:`TaintedSample` taint propagation.
* :class:`SurrogateProvenanceTags` end-to-end MLflow logging.
* The Stage-13 (later) RunPod training entrypoint.

Certificate ships with ``cert_status="smoke"`` and is NOT for publication.
Torch is lazy-imported inside :meth:`fit` and :meth:`predict`.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from typing import Any

import numpy as np

from aero.surrogates._common.base import Sample, Surrogate, TaintedSample
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)


class MLPBaseline(Surrogate):
    """Tiny two-hidden-layer MLP; fits on a CPU subset in seconds."""

    def __init__(
        self,
        *,
        training_dataset_dvc_hash: str,
        dataset_id: str,
        applicability_envelope: ApplicabilityEnvelope,
    ) -> None:
        super().__init__()
        self._training_dataset_dvc_hash = training_dataset_dvc_hash
        self._dataset_id = dataset_id
        self._envelope = applicability_envelope
        # The fitted model + feature/target dimensions land here.
        self._model: Any | None = None
        self._n_features: int | None = None
        self._n_targets: int | None = None
        # Cached held-out error quantiles, populated by fit().
        self._cd_errs: tuple[float, ...] | None = None

    # --- Surrogate seams ------------------------------------------------------
    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        """Train an MLP on the given dataset; cache held-out errors.

        Hyperparameters with sensible defaults (override via Hydra config):
        ``hidden_dim=32``, ``lr=1e-3``, ``epochs=200``, ``val_fraction=0.2``,
        ``seed=0``.
        """
        # Lazy imports — keep platform import path Torch-free.
        import torch
        from torch import nn

        hidden_dim = int(hparams.get("hidden_dim", 32))
        lr = float(hparams.get("lr", 1e-3))
        epochs = int(hparams.get("epochs", 200))
        val_fraction = float(hparams.get("val_fraction", 0.2))
        seed = int(hparams.get("seed", 0))

        # Buffer all samples (the smoke baseline runs on at most a few hundred
        # cases; full-dataset streaming is a Stage-09+ concern).
        samples: list[Sample | TaintedSample] = []
        for sample in data:
            self.ingest(sample)
            samples.append(sample)
        if not samples:
            raise ValueError("MLPBaseline.fit() received no samples")
        n_features = len(samples[0].features)
        n_targets = len(samples[0].targets)
        if not all(len(s.features) == n_features and len(s.targets) == n_targets for s in samples):
            raise ValueError("MLPBaseline.fit() got inhomogeneous feature/target widths")

        rng = np.random.default_rng(seed)
        indices = rng.permutation(len(samples))
        n_val = max(1, round(val_fraction * len(samples)))
        val_idx = set(indices[:n_val].tolist())

        train_x: list[tuple[float, ...]] = []
        train_y: list[tuple[float, ...]] = []
        val_x: list[tuple[float, ...]] = []
        val_y: list[tuple[float, ...]] = []
        for i, s in enumerate(samples):
            (val_x if i in val_idx else train_x).append(s.features)
            (val_y if i in val_idx else train_y).append(s.targets)

        # Per-feature standardization so the MLP doesn't drown in scale skew.
        x_tr = np.asarray(train_x, dtype=np.float32)
        y_tr = np.asarray(train_y, dtype=np.float32)
        x_v = np.asarray(val_x, dtype=np.float32)
        y_v = np.asarray(val_y, dtype=np.float32)
        mu = x_tr.mean(axis=0)
        sigma = x_tr.std(axis=0)
        sigma[sigma < 1e-9] = 1.0
        x_tr = (x_tr - mu) / sigma
        x_v = (x_v - mu) / sigma

        torch.manual_seed(seed)
        model = nn.Sequential(
            nn.Linear(n_features, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_targets),
        )
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()
        x_train_t = torch.from_numpy(x_tr)
        y_train_t = torch.from_numpy(y_tr)
        for _ in range(epochs):
            opt.zero_grad()
            pred = model(x_train_t)
            loss = loss_fn(pred, y_train_t)
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(torch.from_numpy(x_v)).numpy()
        # Held-out errors on the first target (Cd by convention).
        errs = np.abs(val_pred[:, 0] - y_v[:, 0])
        self._cd_errs = tuple(float(e) for e in errs.tolist())
        self._model = (model, mu, sigma)
        self._n_features = n_features
        self._n_targets = n_targets

    def _build_certificate(self) -> CertificateOfValidity:
        if self._cd_errs is None:
            raise RuntimeError(
                "MLPBaseline._build_certificate called before fit() — held-out "
                "errors are not populated."
            )
        errs = sorted(self._cd_errs)
        n = len(errs)
        p50 = statistics.median(errs)
        p95 = errs[max(0, min(n - 1, round(0.95 * (n - 1))))]
        p99 = errs[max(0, min(n - 1, round(0.99 * (n - 1))))]
        return CertificateOfValidity.new(
            surrogate_name=type(self).__name__,
            model_architecture="mlp_baseline",
            training_dataset_dvc_hash=self._training_dataset_dvc_hash,
            dataset_id=self._dataset_id,
            held_out_metrics={
                "cd_mae": MetricQuantiles(p50=p50, p95=p95, p99=p99, n_held_out=n),
            },
            applicability_envelope=self._envelope,
            cert_status="smoke",
            non_commercial=self._non_commercial,
        )

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        # Validate cert first — Stage-14 agent runtime guard.
        self.certificate()
        if self._model is None:
            raise RuntimeError("MLPBaseline.predict called before fit()")
        import torch

        model, mu, sigma = self._model
        x = (np.asarray(features, dtype=np.float32) - mu) / sigma
        with torch.no_grad():
            y = model(torch.from_numpy(x).unsqueeze(0)).squeeze(0).numpy()
        return tuple(float(v) for v in y.tolist())
