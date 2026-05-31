"""MeshGraphNet smoke baseline — PyG MessagePassing on a synthetic graph.

The Stage-08 smoke surface for the GNN path. Builds a tiny chain graph
per sample (8 nodes, 7 edges) where node features encode the sample's
descriptor vector and the target is a scalar regressed at the final node.
This is INTENTIONALLY not a real CFD surface-mesh GNN; Stage 09's
X-MeshGraphNet on DrivAerML surface meshes is the production model.

PyG is the global GNN library choice (ADR-008 §D6). All torch / PyG
imports are lazy.

Demonstrates the tainted-sample flow: when fed
:class:`~aero.surrogates._common.base.TaintedSample` instances (the
quarantined DrivAerNet++ loader yields these), :meth:`fit` flips
:attr:`Surrogate._non_commercial`, and the issued
:class:`CertificateOfValidity` carries ``non_commercial=True``.
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

_N_NODES = 8  # Stage-08 smoke; Stage-09+ X-MGN ranges into 10^5-10^6 nodes.


class MGNSmoke(Surrogate):
    """MeshGraphNet smoke — PyG MessagePassing on a fixed chain graph."""

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
        self._model: Any | None = None
        self._cd_errs: tuple[float, ...] | None = None
        self._n_features: int | None = None

    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        import torch
        from torch import nn
        from torch_geometric.nn import MessagePassing

        hidden = int(hparams.get("hidden", 16))
        lr = float(hparams.get("lr", 1e-3))
        epochs = int(hparams.get("epochs", 200))
        seed = int(hparams.get("seed", 0))

        samples = []
        for sample in data:
            self.ingest(sample)
            samples.append(sample)
        if not samples:
            raise ValueError("MGNSmoke.fit() received no samples")
        n_features = len(samples[0].features)
        n_targets = len(samples[0].targets)
        if n_targets != 1:
            raise ValueError(f"MGNSmoke expects single-scalar targets (got n_targets={n_targets})")
        self._n_features = n_features

        # Fixed chain edge index used by every sample's graph.
        # Bidirectional chain: 0<->1<->2<->...<->N-1.
        src = list(range(_N_NODES - 1)) + list(range(1, _N_NODES))
        dst = list(range(1, _N_NODES)) + list(range(_N_NODES - 1))
        edge_index = torch.tensor([src, dst], dtype=torch.long)

        torch.manual_seed(seed)

        class MGNLayer(MessagePassing):
            def __init__(self, h: int) -> None:
                super().__init__(aggr="mean")
                self.f = nn.Sequential(nn.Linear(2 * h, h), nn.ReLU(), nn.Linear(h, h))

            def message(self, x_i: torch.Tensor, x_j: torch.Tensor) -> torch.Tensor:
                return self.f(torch.cat([x_i, x_j], dim=-1))

            def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
                return x + self.propagate(edge_index, x=x)

        class MGNet(nn.Module):
            def __init__(self, in_dim: int, h: int) -> None:
                super().__init__()
                self.lift = nn.Linear(in_dim, h)
                self.layer = MGNLayer(h)
                self.proj = nn.Linear(h, 1)

            def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
                # x: (N, in_dim) -> (N, h) -> (N, h) -> (N, 1) -> read at root node 0
                z = self.lift(x)
                z = self.layer(z, edge_index)
                z = self.proj(z)
                return z[0]

        model = MGNet(n_features, hidden)
        opt = torch.optim.Adam(model.parameters(), lr=lr)

        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(samples))
        n_val = max(1, len(samples) // 5)
        val_i = set(idx[:n_val].tolist())

        def to_graph(s: Sample | TaintedSample) -> torch.Tensor:
            # Same descriptor vector at every node — the chain GNN then propagates
            # contextual information. Synthetic but exercises message passing.
            x = np.tile(np.asarray(s.features, dtype=np.float32), (_N_NODES, 1))
            return torch.from_numpy(x)

        for _ in range(epochs):
            opt.zero_grad()
            loss = torch.tensor(0.0)
            n = 0
            for i, s in enumerate(samples):
                if i in val_i:
                    continue
                pred = model(to_graph(s), edge_index)
                target = torch.tensor([float(s.targets[0])])
                loss = loss + (pred - target) ** 2
                n += 1
            loss = loss / max(1, n)
            loss.backward()
            opt.step()

        model.eval()
        errs: list[float] = []
        with torch.no_grad():
            for i in sorted(val_i):
                s = samples[i]
                pred = float(model(to_graph(s), edge_index).item())
                errs.append(abs(pred - float(s.targets[0])))
        self._cd_errs = tuple(errs)
        self._model = (model, edge_index)

    def _build_certificate(self) -> CertificateOfValidity:
        if self._cd_errs is None:
            raise RuntimeError("MGNSmoke._build_certificate called before fit()")
        errs = sorted(self._cd_errs)
        n = len(errs)
        p50 = statistics.median(errs)
        p95 = errs[max(0, min(n - 1, round(0.95 * (n - 1))))]
        p99 = errs[max(0, min(n - 1, round(0.99 * (n - 1))))]
        return CertificateOfValidity.new(
            surrogate_name=type(self).__name__,
            model_architecture="mgn_smoke",
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
        self.certificate()  # Stage-14 runtime guard
        if self._model is None:
            raise RuntimeError("MGNSmoke.predict called before fit()")
        import torch

        model, edge_index = self._model
        x = np.tile(np.asarray(features, dtype=np.float32), (_N_NODES, 1))
        with torch.no_grad():
            y = float(model(torch.from_numpy(x), edge_index).item())
        return (y,)
