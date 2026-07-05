"""DoMINO production surrogate — NVIDIA PhysicsNeMo's DoMINO behind the protocol.

DoMINO is a *geometry-aware* model: it consumes a car's discretised surface
(a point cloud with normals) and predicts the surface pressure / wall-shear
fields plus the integrated force/moment coefficients. That shape differs from
the Stage-08 scalar baselines (MLP/FNO/MGN), but the platform contract is
identical — DoMINO IS a :class:`~aero.surrogates._common.base.Surrogate`:

* same ``ingest`` / taint / ``set_certificate`` / ``predict`` seams;
* same :class:`~aero.surrogates._common.certificate.CertificateOfValidity` guard
  (CONSTITUTION Invariant 9 — ``predict`` refuses without a current cert);
* same eight-tag provenance (``SurrogateProvenanceTags``).

How the mesh-vs-scalar gap is bridged (ADR-010):

* ``fit`` consumes the loader's ``Sample`` stream for the train/val split, the
  case ids, the integrated-coefficient *targets*, and the CC-BY taint. The
  surface *meshes* are read by ``case_id`` from the DVC-pulled ``cases_root``
  (``data/datasets/drivaerml/cases`` after a ``dvc pull``), NOT from
  ``Sample.features`` (which carries only DrivAerML's 16 scalar descriptors).
* ``predict(features)`` takes a *flattened DoMINO surface input* (the packed
  point-cloud tensor for ONE case) and returns the integrated coefficients
  ``(cd, cl, clf, clr, cs)`` — faithful to DoMINO consuming geometry, and
  conformant to the scalar ``predict`` seam the Stage-14 agent layer types
  against.

The heavy lifting (PhysicsNeMo / torch / PyG / warp) lives behind a swappable
:class:`DominoEngine`. The default :class:`PhysicsNeMoDominoEngine` lazy-imports
PhysicsNeMo and runs inside ``physicsnemo.sif`` on the RunPod pod; its GPU seams
are validated on the first pod run (cluster-gated, the Stage 07/08 pattern).
Host-side tests inject a fake engine to exercise the cert / taint / guard seams
without a 30 GB CUDA environment. This module itself imports only stdlib +
``aero._common`` (PLATFORM-NOT-HUB).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from aero.surrogates._common.base import Sample, Surrogate, TaintedSample
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertificateOfValidity,
    MetricQuantiles,
)
from aero.surrogates.domino.certificate import (
    build_domino_certificate,
    quantiles_from_abs_errors,
)

# DrivAerML's integrated-coefficient target order (DrivAerMLDataset.targets).
TARGET_NAMES: tuple[str, ...] = ("cd", "cl", "clf", "clr", "cs")

# An opaque handle to a trained DoMINO model (a torch module + scalers inside
# the engine). Kept `Any` so no torch type leaks into the platform layer.
DominoModelHandle = Any


class DominoEngineUnavailable(RuntimeError):  # noqa: N818 — domain-natural state name
    """The PhysicsNeMo / torch engine is not importable in this environment.

    DoMINO training + inference run inside ``physicsnemo.sif`` (the NGC
    container, ADR-010). Host-side passes that don't install
    ``aero[physicsnemo-cu12]`` hit this the moment they reach a GPU seam — by
    design. The cert / taint / guard seams are exercised with a fake engine.
    """


@dataclass(frozen=True)
class DominoCase:
    """One training/eval case: its id and integrated-coefficient targets.

    The surface mesh itself is located by ``case_id`` under the engine's
    ``cases_root`` — this struct stays mesh-free so the platform layer never
    touches mesh IO.
    """

    case_id: str
    targets: tuple[float, ...]
    target_names: tuple[str, ...] = TARGET_NAMES


@runtime_checkable
class DominoEngine(Protocol):
    """The PhysicsNeMo-side operations DoMINO needs; swappable for testing."""

    def train(
        self,
        *,
        train_cases: Sequence[DominoCase],
        val_cases: Sequence[DominoCase],
        cases_root: Path,
        hparams: Mapping[str, Any],
    ) -> DominoModelHandle:
        """Train DoMINO from scratch (the no-PC baseline); return a model handle."""

    def fine_tune_predictor_corrector(
        self,
        handle: DominoModelHandle,
        *,
        train_cases: Sequence[DominoCase],
        val_cases: Sequence[DominoCase],
        cases_root: Path,
        hparams: Mapping[str, Any],
    ) -> DominoModelHandle:
        """Apply the Predictor-Corrector fine-tuning recipe; return the new handle."""

    def held_out_abs_errors(
        self,
        handle: DominoModelHandle,
        *,
        val_cases: Sequence[DominoCase],
        cases_root: Path,
    ) -> dict[str, tuple[float, ...]]:
        """Per-metric held-out absolute errors, keyed e.g. ``cd_mae``/``cl_mae``."""

    def predict_coefficients(
        self, handle: DominoModelHandle, surface: tuple[float, ...]
    ) -> tuple[float, ...]:
        """Run the trained net on one packed surface input -> integrated coeffs."""

    def save_checkpoint(self, handle: DominoModelHandle, path: Path) -> None:
        """Persist the trained state_dict + scalers for later retrieval."""


class DominoSurrogate(Surrogate):
    """NVIDIA PhysicsNeMo DoMINO wrapped as a platform :class:`Surrogate`.

    Construction mirrors the Stage-08 baselines (so the ``aero surrogate train``
    CLI builds it uniformly), plus DoMINO-specific knobs:

    * ``cases_root`` — directory of DVC-pulled surface meshes (defaults to the
      value in the training hparams).
    * ``engine`` — the :class:`DominoEngine`; defaults to
      :class:`PhysicsNeMoDominoEngine`.
    """

    def __init__(
        self,
        *,
        training_dataset_dvc_hash: str,
        dataset_id: str,
        applicability_envelope: ApplicabilityEnvelope,
        cases_root: Path | None = None,
        license_id: str = "CC-BY-SA-4.0",
        attribution_required: tuple[str, ...] = (),
        engine: DominoEngine | None = None,
    ) -> None:
        super().__init__()
        self._training_dataset_dvc_hash = training_dataset_dvc_hash
        self._dataset_id = dataset_id
        self._envelope = applicability_envelope
        self._cases_root = cases_root
        self._license_id = license_id
        self._attribution_required = attribution_required
        self._engine = engine
        self._handle: DominoModelHandle | None = None
        self._held_out: dict[str, MetricQuantiles] | None = None
        # Wall-clock seconds for the baseline + PC phases; the speedup factor
        # the bundle asks for is derived from these by the training loop.
        self.baseline_seconds: float | None = None
        self.pc_seconds: float | None = None
        # The fit() split is reused verbatim by the PC phase + final eval.
        self._train_cases: list[DominoCase] = []
        self._val_cases: list[DominoCase] = []
        self._cases_root_resolved: Path | None = None

    # --- engine resolution ----------------------------------------------------
    def _resolved_engine(self) -> DominoEngine:
        if self._engine is None:
            self._engine = PhysicsNeMoDominoEngine()
        return self._engine

    def _resolved_cases_root(self, hparams: Mapping[str, Any]) -> Path:
        root = hparams.get("cases_root", self._cases_root)
        if root is None:
            raise ValueError(
                "DominoSurrogate.fit needs `cases_root` (the DVC-pulled surface-mesh "
                "directory) — pass it in the constructor or the training hparams"
            )
        return Path(root)

    # --- Surrogate seams ------------------------------------------------------
    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        """Train the no-PC DoMINO baseline; cache held-out error quantiles.

        Splits the ``Sample`` stream deterministically (``seed``, ``val_fraction``),
        ingests every sample (taint propagation), and hands the case ids + targets
        to the engine, which reads the meshes from ``cases_root``. The
        Predictor-Corrector phase is a separate call (:meth:`fine_tune_predictor_corrector`)
        so the training loop can time and compare the two.
        """
        import time

        seed = int(hparams.get("seed", 0))
        val_fraction = float(hparams.get("val_fraction", 0.2))

        cases: list[DominoCase] = []
        for sample in data:
            self.ingest(sample)
            cases.append(DominoCase(case_id=sample.case_id, targets=sample.targets))
        if not cases:
            raise ValueError("DominoSurrogate.fit() received no samples")

        train_cases, val_cases = _deterministic_split(cases, val_fraction=val_fraction, seed=seed)
        cases_root = self._resolved_cases_root(hparams)
        engine = self._resolved_engine()

        started = time.monotonic()
        self._handle = engine.train(
            train_cases=train_cases,
            val_cases=val_cases,
            cases_root=cases_root,
            hparams=hparams,
        )
        self.baseline_seconds = time.monotonic() - started
        self._held_out = _quantiles(
            engine.held_out_abs_errors(self._handle, val_cases=val_cases, cases_root=cases_root)
        )
        # Stash the split so the PC phase reuses the exact same held-out cases.
        self._train_cases = train_cases
        self._val_cases = val_cases
        self._cases_root_resolved = cases_root

    def fine_tune_predictor_corrector(self, /, **hparams: Any) -> None:
        """Apply the PhysicsNeMo Predictor-Corrector recipe to the fitted model.

        ``Y_finetuned = Y_predictor + Y_corrector`` (PhysicsNeMo 25.08). Re-evaluates
        the held-out metrics on the SAME split as :meth:`fit` so the cert reflects
        the fine-tuned model. Must be called after :meth:`fit`.
        """
        import time

        if self._handle is None or self._cases_root_resolved is None:
            raise RuntimeError("fine_tune_predictor_corrector() called before fit()")
        engine = self._resolved_engine()
        started = time.monotonic()
        self._handle = engine.fine_tune_predictor_corrector(
            self._handle,
            train_cases=self._train_cases,
            val_cases=self._val_cases,
            cases_root=self._cases_root_resolved,
            hparams=hparams,
        )
        self.pc_seconds = time.monotonic() - started
        self._held_out = _quantiles(
            engine.held_out_abs_errors(
                self._handle, val_cases=self._val_cases, cases_root=self._cases_root_resolved
            )
        )

    def _build_certificate(self) -> CertificateOfValidity:
        if self._held_out is None:
            raise RuntimeError(
                "DominoSurrogate._build_certificate called before fit() — held-out "
                "metrics are not populated."
            )
        # Always smoke here; promote_to_validated() is the only gated upgrade path.
        return build_domino_certificate(
            surrogate_name=type(self).__name__,
            training_dataset_dvc_hash=self._training_dataset_dvc_hash,
            dataset_id=self._dataset_id,
            held_out_metrics=self._held_out,
            applicability_envelope=self._envelope,
            non_commercial=self._non_commercial,
            data_origin=self._data_origin,
            license_id=self._license_id,
            attribution_required=self._attribution_required,
            upgrade_to_validated=False,
        )

    def promote_to_validated(self) -> CertificateOfValidity:
        """Re-issue + cache the cert at ``cert_status="validated"`` IF the gate passes.

        The only path to a "validated" DoMINO cert. Builds with
        ``upgrade_to_validated=True``; :func:`build_domino_certificate` keeps it
        ``"smoke"`` unless held-out Cd MAE p95 < 5%. Re-applies the taint override
        (``Surrogate.set_certificate`` semantics) and caches the result.
        """
        if self._held_out is None:
            raise RuntimeError("promote_to_validated() called before fit()")
        if self._data_origin == "foreign":
            raise ValueError(
                "CONSTITUTION Invariant 11 (NO-SURROGATE-ON-FOREIGN-DATA): cannot promote a "
                "surrogate trained on foreign (automotive/aircraft) data to cert_status='validated'. "
                "It may seed 'smoke' experiments only. Retrain on the platform's own validated CFD."
            )
        cert = build_domino_certificate(
            surrogate_name=type(self).__name__,
            training_dataset_dvc_hash=self._training_dataset_dvc_hash,
            dataset_id=self._dataset_id,
            held_out_metrics=self._held_out,
            applicability_envelope=self._envelope,
            non_commercial=self._non_commercial,
            data_origin=self._data_origin,
            license_id=self._license_id,
            attribution_required=self._attribution_required,
            upgrade_to_validated=True,
        )
        if self._non_commercial and not cert.non_commercial:
            cert = cert.model_copy(update={"non_commercial": True})
        self._certificate = cert
        return cert

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        # Invariant 9 guard FIRST — before any engine work.
        self.certificate()
        if self._handle is None:
            raise RuntimeError("DominoSurrogate.predict called before fit()")
        return self._resolved_engine().predict_coefficients(self._handle, features)

    # --- accessors ------------------------------------------------------------
    @property
    def held_out_metrics(self) -> dict[str, MetricQuantiles]:
        if self._held_out is None:
            raise RuntimeError("held_out_metrics accessed before fit()")
        return dict(self._held_out)

    @property
    def speedup_factor(self) -> float | None:
        """Baseline-vs-PC wall-clock ratio; ``None`` until both phases have run.

        The canonical comparison is time-to-target-RMSE; this ratio is the
        coarse end-to-end proxy the handoff records alongside the per-phase
        seconds (ADR-010).
        """
        if self.baseline_seconds is None or self.pc_seconds is None or self.pc_seconds <= 0:
            return None
        return self.baseline_seconds / self.pc_seconds

    def save_checkpoint(self, path: Path) -> None:
        """Persist the trained model for retrieval (state_dict + scalers)."""
        if self._handle is None:
            raise RuntimeError("save_checkpoint() called before fit()")
        self._resolved_engine().save_checkpoint(self._handle, path)


def _deterministic_split(
    cases: Sequence[DominoCase], *, val_fraction: float, seed: int
) -> tuple[list[DominoCase], list[DominoCase]]:
    """Reproducible train/val partition (numpy RNG, like the Stage-08 baselines)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(cases))
    n_val = max(1, round(val_fraction * len(cases)))
    val_idx = set(int(i) for i in order[:n_val].tolist())
    train = [c for i, c in enumerate(cases) if i not in val_idx]
    val = [c for i, c in enumerate(cases) if i in val_idx]
    return train, val


def _quantiles(abs_errors: Mapping[str, tuple[float, ...]]) -> dict[str, MetricQuantiles]:
    """Convert per-metric absolute-error vectors into cert MetricQuantiles."""
    return {key: quantiles_from_abs_errors(errs) for key, errs in abs_errors.items()}


class PhysicsNeMoDominoEngine:
    """The default engine: NVIDIA PhysicsNeMo DoMINO inside ``physicsnemo.sif``.

    Every method lazy-imports PhysicsNeMo + torch so importing this module stays
    PLATFORM-NOT-HUB clean. The GPU bodies target the PhysicsNeMo 25.08 DoMINO
    reference example; the exact upstream symbols (DGL->PyG migration is current)
    are validated + patched on the FIRST RunPod pod run — cluster-gated, exactly
    as the Stage 07/08 SIF builds were. Until then, a host without
    ``aero[physicsnemo-cu12]`` raises :class:`DominoEngineUnavailable` on use.
    """

    def _require(self) -> Any:
        try:
            import physicsnemo  # noqa: F401
            import torch
        except ImportError as exc:  # pragma: no cover — cluster-gated
            raise DominoEngineUnavailable(
                "PhysicsNeMo/torch unavailable — DoMINO trains inside physicsnemo.sif; "
                "install aero[physicsnemo-cu12] to run the engine outside the SIF"
            ) from exc
        return torch

    def train(
        self,
        *,
        train_cases: Sequence[DominoCase],
        val_cases: Sequence[DominoCase],
        cases_root: Path,
        hparams: Mapping[str, Any],
    ) -> DominoModelHandle:  # pragma: no cover — cluster-gated GPU seam
        self._require()
        raise DominoEngineUnavailable(
            "PhysicsNeMoDominoEngine.train is validated on the first RunPod pod run "
            "(physicsnemo 25.08 DoMINO reference recipe); see scripts/stage09_domino_train.py "
            "and docs/adrs/ADR-010-domino-baseline-surrogate.md"
        )

    def fine_tune_predictor_corrector(
        self,
        handle: DominoModelHandle,
        *,
        train_cases: Sequence[DominoCase],
        val_cases: Sequence[DominoCase],
        cases_root: Path,
        hparams: Mapping[str, Any],
    ) -> DominoModelHandle:  # pragma: no cover — cluster-gated GPU seam
        self._require()
        raise DominoEngineUnavailable(
            "PhysicsNeMoDominoEngine.fine_tune_predictor_corrector is validated on the "
            "first pod run (physicsnemo 25.08 Predictor-Corrector recipe)"
        )

    def held_out_abs_errors(
        self,
        handle: DominoModelHandle,
        *,
        val_cases: Sequence[DominoCase],
        cases_root: Path,
    ) -> dict[str, tuple[float, ...]]:  # pragma: no cover — cluster-gated GPU seam
        self._require()
        raise DominoEngineUnavailable("held_out_abs_errors is validated on the first pod run")

    def predict_coefficients(
        self, handle: DominoModelHandle, surface: tuple[float, ...]
    ) -> tuple[float, ...]:  # pragma: no cover — cluster-gated GPU seam
        self._require()
        raise DominoEngineUnavailable("predict_coefficients is validated on the first pod run")

    def save_checkpoint(
        self, handle: DominoModelHandle, path: Path
    ) -> None:  # pragma: no cover — cluster-gated GPU seam
        torch = self._require()
        torch.save(handle, path)
