"""NVIDIA PhysicsNeMo DoMINO — the platform's first production surrogate (Stage 09).

Public surface:

* :class:`DominoSurrogate` — the :class:`~aero.surrogates._common.base.Surrogate`
  subclass wrapping PhysicsNeMo's DoMINO (``model.py``).
* :func:`train_domino` — the Hydra-configurable baseline + Predictor-Corrector
  training orchestration (``training.py``).
* :func:`build_domino_certificate` + the smoke->validated gate (``certificate.py``).
* :class:`DominoEngine` / :class:`PhysicsNeMoDominoEngine` — the swappable GPU
  backend (real engine runs inside ``physicsnemo.sif``).

Importing this package pulls only stdlib + ``aero._common`` (PLATFORM-NOT-HUB);
torch / PhysicsNeMo / PyG / warp are lazy-imported inside the engine.
"""

from __future__ import annotations

from aero.surrogates.domino.certificate import (
    CD_METRIC_KEY,
    MODEL_ARCHITECTURE,
    VALIDATED_CD_P95_THRESHOLD,
    build_domino_certificate,
    meets_validated_gate,
    quantiles_from_abs_errors,
)
from aero.surrogates.domino.model import (
    TARGET_NAMES,
    DominoCase,
    DominoEngine,
    DominoEngineUnavailable,
    DominoSurrogate,
    PhysicsNeMoDominoEngine,
)
from aero.surrogates.domino.training import DominoTrainingResult, train_domino

__all__ = [
    "CD_METRIC_KEY",
    "MODEL_ARCHITECTURE",
    "TARGET_NAMES",
    "VALIDATED_CD_P95_THRESHOLD",
    "DominoCase",
    "DominoEngine",
    "DominoEngineUnavailable",
    "DominoSurrogate",
    "DominoTrainingResult",
    "PhysicsNeMoDominoEngine",
    "build_domino_certificate",
    "meets_validated_gate",
    "quantiles_from_abs_errors",
    "train_domino",
]
