"""FNO smoke baseline — Fourier Neural Operator on a 1-D toy field.

The Stage-08 smoke surface for the operator-learning path. Predicts a
synthetic 1-D scalar field (a smoothed step function) from a low-frequency
parameterisation. This is INTENTIONALLY not a real CFD-field surrogate;
Stage 09's PhysicsNeMo FIGConvNet replaces it with a production model on
DrivAerML surface fields.

Same ``Surrogate`` contract as :class:`MLPBaseline` — features are the
flattened 1-D input grid (16 points), targets are the 16-point output
grid. The cert ships at ``cert_status="smoke"``.

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

_GRID = 16  # Stage-08 smoke; production FNO Stage-09+ uses 64 / 128 / 256.


class FNOSmoke(Surrogate):
    """Single-block 1-D Fourier Neural Operator — the smallest FNO that works."""

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
        self._field_errs: tuple[float, ...] | None = None

    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        import torch
        from torch import nn

        modes = int(hparams.get("modes", 4))
        width = int(hparams.get("width", 8))
        lr = float(hparams.get("lr", 1e-3))
        epochs = int(hparams.get("epochs", 200))
        seed = int(hparams.get("seed", 0))

        samples = []
        for sample in data:
            self.ingest(sample)
            samples.append(sample)
        if not samples:
            raise ValueError("FNOSmoke.fit() received no samples")

        # Sample features carry the 4-D AhmedML descriptor; we synthesize a
        # 1-D input field as `cos(k*x + phi)` from the first two features
        # so the FNO has something low-frequency to spectrally fit. The
        # target field is a unit-step at `slant_angle/45` smoothed by the
        # second feature. None of this claims physical fidelity — it just
        # exercises the FNO building blocks end-to-end.
        x = np.linspace(0.0, 1.0, _GRID, dtype=np.float32)

        def synth(s: Sample | TaintedSample) -> tuple[np.ndarray, np.ndarray]:
            k = 1.0 + 2.0 * float(s.features[0]) / 45.0
            phi = float(s.features[1])
            inp = np.cos(k * x + phi).astype(np.float32)
            cut = float(s.features[0]) / 45.0
            out = (1.0 / (1.0 + np.exp(-30.0 * (x - cut)))).astype(np.float32)
            return inp, out

        x_all = np.stack([synth(s)[0] for s in samples])
        y_all = np.stack([synth(s)[1] for s in samples])
        # 80/20 split
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(samples))
        n_val = max(1, len(samples) // 5)
        val_i = set(idx[:n_val].tolist())
        x_tr = x_all[[i for i in range(len(x_all)) if i not in val_i]]
        y_tr = y_all[[i for i in range(len(y_all)) if i not in val_i]]
        x_v = x_all[sorted(val_i)]
        y_v = y_all[sorted(val_i)]

        torch.manual_seed(seed)

        class SpectralConv1d(nn.Module):
            def __init__(self, in_c: int, out_c: int, m: int) -> None:
                super().__init__()
                self.modes = m
                scale = 1.0 / (in_c * out_c)
                self.weight = nn.Parameter(scale * torch.randn(in_c, out_c, m, dtype=torch.cfloat))

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                xf = torch.fft.rfft(x, dim=-1)
                out = torch.zeros(x.size(0), self.weight.size(1), xf.size(-1), dtype=torch.cfloat)
                out[..., : self.modes] = torch.einsum(
                    "bix,iox->box", xf[..., : self.modes], self.weight
                )
                return torch.fft.irfft(out, n=x.size(-1), dim=-1)

        class FNO1d(nn.Module):
            def __init__(self, modes: int, width: int) -> None:
                super().__init__()
                self.lift = nn.Linear(1, width)
                self.spec = SpectralConv1d(width, width, modes)
                self.proj = nn.Linear(width, 1)

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                # x: (B, G) -> (B, G, 1) -> lift -> (B, G, W) -> (B, W, G)
                z = self.lift(x.unsqueeze(-1)).permute(0, 2, 1)
                z = z + self.spec(z)
                z = z.permute(0, 2, 1)
                return self.proj(z).squeeze(-1)

        model = FNO1d(modes, width)
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        x_train_t = torch.from_numpy(x_tr)
        y_train_t = torch.from_numpy(y_tr)
        for _ in range(epochs):
            opt.zero_grad()
            pred = model(x_train_t)
            loss = ((pred - y_train_t) ** 2).mean()
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            pv = model(torch.from_numpy(x_v)).numpy()
        errs = np.abs(pv - y_v).mean(axis=1)  # per-sample mean field error
        self._field_errs = tuple(float(e) for e in errs.tolist())
        self._model = model

    def _build_certificate(self) -> CertificateOfValidity:
        if self._field_errs is None:
            raise RuntimeError("FNOSmoke._build_certificate called before fit()")
        errs = sorted(self._field_errs)
        n = len(errs)
        p50 = statistics.median(errs)
        p95 = errs[max(0, min(n - 1, round(0.95 * (n - 1))))]
        p99 = errs[max(0, min(n - 1, round(0.99 * (n - 1))))]
        return CertificateOfValidity.new(
            surrogate_name=type(self).__name__,
            model_architecture="fno_smoke",
            training_dataset_dvc_hash=self._training_dataset_dvc_hash,
            dataset_id=self._dataset_id,
            held_out_metrics={
                "field_l1": MetricQuantiles(p50=p50, p95=p95, p99=p99, n_held_out=n),
            },
            applicability_envelope=self._envelope,
            cert_status="smoke",
            non_commercial=self._non_commercial,
        )

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        self.certificate()  # Stage-14 runtime guard
        if self._model is None:
            raise RuntimeError("FNOSmoke.predict called before fit()")
        import torch

        x = np.linspace(0.0, 1.0, _GRID, dtype=np.float32)
        k = 1.0 + 2.0 * float(features[0]) / 45.0
        phi = float(features[1])
        inp = np.cos(k * x + phi).astype(np.float32)
        with torch.no_grad():
            y = self._model(torch.from_numpy(inp).unsqueeze(0)).squeeze(0).numpy()
        return tuple(float(v) for v in y.tolist())
