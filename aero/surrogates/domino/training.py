"""DoMINO training orchestration — the Hydra-configurable Predictor-Corrector recipe.

``train_domino`` is the compute core the on-pod entrypoint
(``scripts/stage09_domino_train.py``) calls inside ``physicsnemo.sif``:

1. build the :class:`~aero.surrogates._common.certificate.ApplicabilityEnvelope`
   from the resolved config;
2. construct the :class:`~aero.surrogates.domino.model.DominoSurrogate`;
3. ``fit`` the no-PC baseline (timed);
4. apply the **Predictor-Corrector** fine-tuning recipe (timed) — PhysicsNeMo
   25.08's ``Y_finetuned = Y_predictor + Y_corrector``, the ~10x end-to-end
   training speedup (Pass 2 §11.3);
5. attempt the smoke->validated cert upgrade (the held-out Cd MAE p95 < 5% gate
   decides — :func:`aero.surrogates.domino.certificate.meets_validated_gate`);
6. return a :class:`DominoTrainingResult` carrying the cert, held-out metrics,
   per-phase timings + the observed speedup factor.

Kept IO-free (no MLflow, no checkpoint write) so it is unit-testable with a fake
engine; the on-pod script owns the MLflow eight-tag logging + checkpoint upload +
the ``surrogate_vv`` cross-check (``aero.vv.surrogate``). PLATFORM-NOT-HUB:
stdlib + ``aero._common`` only; torch/PhysicsNeMo enter via the engine.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aero.surrogates._common.base import Sample, TaintedSample
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)
from aero.surrogates.domino.model import DominoEngine, DominoSurrogate


@dataclass(frozen=True)
class DominoTrainingResult:
    """Everything the on-pod script needs to log + persist a DoMINO run."""

    surrogate: DominoSurrogate
    certificate: CertificateOfValidity
    held_out_metrics: dict[str, MetricQuantiles]
    baseline_seconds: float | None
    pc_seconds: float | None
    speedup_factor: float | None
    predictor_corrector_applied: bool


def _envelope_from_config(envelope_cfg: Mapping[str, Any]) -> ApplicabilityEnvelope:
    """Build the typed envelope from the resolved ``envelope:`` config block."""
    return ApplicabilityEnvelope(
        re_range=tuple(envelope_cfg["re_range"]),
        mach_range=tuple(envelope_cfg["mach_range"]),
        aoa_range_deg=tuple(envelope_cfg["aoa_range_deg"]),
        geometry_class=str(envelope_cfg["geometry_class"]),
    )


def train_domino(
    *,
    resolved_config: Mapping[str, Any],
    data: Iterable[Sample | TaintedSample],
    train_dataset_dvc_hash: str,
    dataset_id: str,
    cases_root: Path | str,
    engine: DominoEngine | None = None,
) -> DominoTrainingResult:
    """Run the baseline + Predictor-Corrector recipe; return the certified result.

    ``resolved_config`` is the OmegaConf->dict of ``conf/surrogate/domino.yaml``
    (``envelope:`` + ``train:`` blocks). ``data`` is the loader's ``Sample``
    stream (DrivAerML — CC-BY-SA, no taint). ``cases_root`` is the DVC-pulled
    surface-mesh directory mounted into the pod.

    The cert lands ``"validated"`` only if the held-out Cd MAE p95 < 5% gate
    passes; otherwise it stays ``"smoke"`` (no tolerance is ever relaxed to
    force the upgrade).
    """
    train_cfg: Mapping[str, Any] = dict(resolved_config.get("train", {}))
    envelope = _envelope_from_config(resolved_config["envelope"])

    surrogate = DominoSurrogate(
        training_dataset_dvc_hash=train_dataset_dvc_hash,
        dataset_id=dataset_id,
        applicability_envelope=envelope,
        cases_root=Path(cases_root),
        engine=engine,
    )

    # 1) no-PC baseline (timed inside the surrogate).
    surrogate.fit(data, **train_cfg)

    # 2) Predictor-Corrector fine-tuning (default ON; the whole point of the stage).
    pc_applied = bool(train_cfg.get("predictor_corrector", True))
    if pc_applied:
        surrogate.fine_tune_predictor_corrector(**train_cfg)

    # 3) attempt the gated smoke->validated upgrade (the metric gate decides).
    attempt_validation = bool(resolved_config.get("surrogate", {}).get("attempt_validation", True))
    cert = surrogate.promote_to_validated() if attempt_validation else surrogate.set_certificate()

    return DominoTrainingResult(
        surrogate=surrogate,
        certificate=cert,
        held_out_metrics=surrogate.held_out_metrics,
        baseline_seconds=surrogate.baseline_seconds,
        pc_seconds=surrogate.pc_seconds,
        speedup_factor=surrogate.speedup_factor,
        predictor_corrector_applied=pc_applied,
    )
