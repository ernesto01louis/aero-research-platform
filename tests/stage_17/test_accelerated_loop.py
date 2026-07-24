"""Stage 17 — the propose/dispose loop: CFD-only incumbents, retrain cadence, stops.

Uses an analytic 2-D objective (no CFD) through a fake EvaluateBatch, real
GPBootstrapMember ensembles for the happy paths, and a deliberately over-promising
fake member for the distrust path. The Invariant-9 gate is exercised with a fake
dataset-hash function.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import pytest
from aero.optimize.accelerated import AcceleratedConfig, SurrogateAcceleratedOptimizer
from aero.optimize.design_space import DesignSpace, DesignVariable
from aero.optimize.gp import GPConfig
from aero.optimize.objective import ObjectiveEval
from aero.provenance.four_fold import ProvenanceTuple
from aero.surrogates._common.base import Sample, Surrogate, TaintedSample
from aero.surrogates._common.certificate import (
    ApplicabilityEnvelope,
    CertExpired,
    CertificateOfValidity,
    MetricQuantiles,
)
from aero.surrogates._common.trust_region import TrustRegionConfig
from aero.surrogates.gp_bootstrap import GPBootstrapMember

pytestmark = pytest.mark.stage_17

_HASH = "0" * 64
_ENVELOPE = ApplicabilityEnvelope(
    re_range=(5.0e5, 5.0e5),
    mach_range=(0.0, 0.0),
    aoa_range_deg=(4.0, 4.0),
    geometry_class="naca-4digit",
)
_SPACE = DesignSpace(
    variables=(
        DesignVariable(name="max_camber", low=0.0, high=0.08),
        DesignVariable(name="camber_position", low=0.2, high=0.6),
    )
)
_PROV = ProvenanceTuple(
    git_sha="a" * 40,
    dvc_input_hash="b" * 64,
    container_sif_sha256="c" * 64,
    config_hash="d" * 64,
)


def _objective_unit(u: np.ndarray) -> float:
    """Smooth 2-D peak at unit (0.7, 0.3) with max 40 (analogous to the L/D surface)."""
    return 40.0 - 60.0 * float((u[0] - 0.7) ** 2 + (u[1] - 0.3) ** 2)


def _objective_physical(x: np.ndarray) -> float:
    return _objective_unit(_SPACE.to_unit(x))


class _RecordingEvaluator:
    """Fake ground-truth CFD: analytic objective, records every design it was asked."""

    def __init__(self, fail_every: int | None = None) -> None:
        self.calls: list[np.ndarray] = []
        self.values: list[float | None] = []
        self._fail_every = fail_every

    def __call__(self, designs: Sequence[np.ndarray]) -> Sequence[ObjectiveEval | None]:
        out: list[ObjectiveEval | None] = []
        for x in designs:
            self.calls.append(np.asarray(x))
            n = len(self.calls)
            if self._fail_every is not None and n % self._fail_every == 0:
                self.values.append(None)
                out.append(None)
                continue
            value = _objective_physical(np.asarray(x))
            self.values.append(value)
            out.append(
                ObjectiveEval(
                    design=tuple(float(v) for v in np.asarray(x)),
                    value=value,
                    provenance=_PROV,
                )
            )
        return out


def _corpus(n: int = 24, *, seed: int = 5) -> list[Sample]:
    rng = np.random.default_rng(seed)
    out: list[Sample] = []
    for i in range(n):
        u = rng.random(2)
        # Keep the corpus AWAY from the peak so the loop has real work to do.
        u = 0.05 + 0.4 * u
        out.append(
            Sample(
                features=(float(u[0]), float(u[1])),
                targets=(_objective_unit(u),),
                case_id=f"c{i:02d}",
                dataset_id="stage17-naca4-ld",
                data_origin="platform-validated",
            )
        )
    return out


def _gp_member(i: int) -> Surrogate:
    scales = (0.20, 0.25, 0.30, 0.35, 0.40)
    return GPBootstrapMember(
        gp_config=GPConfig(kernel="matern52", length_scale=scales[i % len(scales)]),
        training_dataset_dvc_hash=_HASH,
        dataset_id="stage17-naca4-ld",
        applicability_envelope=_ENVELOPE,
        metric_name="ld_mae",
    )


def _optimizer(
    *,
    evaluator: _RecordingEvaluator,
    config: AcceleratedConfig,
    corpus: list[Sample] | None = None,
    member_factory: Any = None,
    hash_fn: Any = None,
) -> SurrogateAcceleratedOptimizer:
    return SurrogateAcceleratedOptimizer(
        space=_SPACE,
        corpus=corpus or _corpus(),
        member_factory=member_factory or _gp_member,
        envelope=_ENVELOPE,
        dataset_id="stage17-naca4-ld",
        dataset_hash_fn=hash_fn or (lambda: _HASH),
        evaluate_batch=evaluator,
        config=config,
    )


def test_budget_stop_and_cfd_only_incumbent() -> None:
    evaluator = _RecordingEvaluator()
    run = _optimizer(evaluator=evaluator, config=AcceleratedConfig(max_cfd_evals=8, seed=1)).run()
    assert run.stop_reason == "budget"
    assert run.n_cfd_evals == 8
    assert len(evaluator.calls) == 8
    # The incumbent is a CFD value: either a corpus target or an evaluator return.
    corpus_values = {s.targets[0] for s in _corpus()}
    evaluated = {v for v in evaluator.values if v is not None}
    assert run.incumbent_value in corpus_values | evaluated
    assert run.n_candidates == run.n_corpus + run.n_cfd_evals


def test_target_stop_reaches_bar() -> None:
    evaluator = _RecordingEvaluator()
    run = _optimizer(
        evaluator=evaluator,
        config=AcceleratedConfig(max_cfd_evals=16, target_value=38.0, seed=0),
    ).run()
    assert run.stop_reason in ("target", "budget")
    if run.stop_reason == "target":
        assert run.incumbent_value >= 38.0
        assert not run.incumbent_from_corpus


def test_zero_marginal_when_corpus_already_at_bar() -> None:
    evaluator = _RecordingEvaluator()
    corpus = [
        *_corpus(),
        Sample(
            features=(0.7, 0.3),
            targets=(40.0,),
            case_id="peak",
            dataset_id="stage17-naca4-ld",
            data_origin="platform-validated",
        ),
    ]
    run = _optimizer(
        evaluator=evaluator,
        config=AcceleratedConfig(target_value=39.5, seed=0),
        corpus=corpus,
    ).run()
    assert run.stop_reason == "target"
    assert run.n_cfd_evals == 0
    assert run.incumbent_from_corpus
    assert not run.records


def test_retrain_every_iteration_and_explore_route_present() -> None:
    evaluator = _RecordingEvaluator()
    run = _optimizer(evaluator=evaluator, config=AcceleratedConfig(max_cfd_evals=8, seed=2)).run()
    assert len(run.records) == 2  # 8 evals / batch of 4
    # Iteration 0 trains on the bare corpus; iteration 1 must see the infill rows.
    assert run.records[0].certificate.dataset_id == "stage17-naca4-ld"
    assert run.records[1].certificate.dataset_id.startswith("stage17-naca4-ld+infill")
    for record in run.records:
        routes = {c.route for c in record.candidates}
        assert "explore" in routes  # the audit arm is never optimized away
        assert len(record.candidates) == len(record.results)


def test_failed_solves_count_against_budget() -> None:
    evaluator = _RecordingEvaluator(fail_every=4)
    run = _optimizer(evaluator=evaluator, config=AcceleratedConfig(max_cfd_evals=8, seed=3)).run()
    assert run.n_cfd_evals == 8  # spent, not refunded (S8)
    n_failed = sum(1 for r in run.records for res in r.results if res is None)
    assert n_failed == 2


def test_invariant9_data_gate_fires_on_hash_drift() -> None:
    hashes = iter(["0" * 64, "1" * 64])
    evaluator = _RecordingEvaluator()
    opt = _optimizer(
        evaluator=evaluator,
        config=AcceleratedConfig(max_cfd_evals=8, seed=0),
        hash_fn=lambda: next(hashes),
    )
    with pytest.raises(CertExpired, match="dataset drifted"):
        opt.run()


class _OverPromisingMember(Surrogate):
    """Predicts a huge objective everywhere (with seed jitter) — exploitation bait."""

    def __init__(self, offset: float) -> None:
        super().__init__()
        self._offset = offset

    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        for sample in data:
            self.ingest(sample)

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        self.certificate()
        return (1000.0 + self._offset + 0.1 * features[0],)

    def _build_certificate(self) -> CertificateOfValidity:
        return CertificateOfValidity.new(
            surrogate_name="overpromiser",
            model_architecture="stub",
            training_dataset_dvc_hash=_HASH,
            dataset_id="stage17-naca4-ld",
            held_out_metrics={"ld_mae": MetricQuantiles(p50=1.0, p95=1.0, p99=1.0, n_held_out=2)},
            applicability_envelope=_ENVELOPE,
            cert_status="smoke",
            non_commercial=False,
            data_origin=self._data_origin,
        )


class _AlwaysWorseEvaluator(_RecordingEvaluator):
    """Ground truth strictly worse than any corpus row — no improvement can reset distrust."""

    def __call__(self, designs: Sequence[np.ndarray]) -> Sequence[ObjectiveEval | None]:
        out: list[ObjectiveEval | None] = []
        for x in designs:
            self.calls.append(np.asarray(x))
            self.values.append(-1000.0)
            out.append(
                ObjectiveEval(
                    design=tuple(float(v) for v in np.asarray(x)),
                    value=-1000.0,
                    provenance=_PROV,
                )
            )
        return out


def test_distrust_stop_on_repeated_reject_floor() -> None:
    evaluator = _AlwaysWorseEvaluator()
    config = AcceleratedConfig(
        max_cfd_evals=100,
        seed=0,
        trust_region=TrustRegionConfig(initial_radius=0.002, min_radius=1e-3, max_radius=0.5),
        max_consecutive_distrust=2,
    )
    run = _optimizer(
        evaluator=evaluator,
        config=config,
        member_factory=lambda i: _OverPromisingMember(float(i)),
    ).run()
    assert run.stop_reason == "distrust"
    # Every distrust iteration re-opened the region on the incumbent.
    floors = [r for r in run.records if r.trust_update and r.trust_update.surrogate_distrusted]
    assert len(floors) >= 2
    assert all(r.trust_recentered for r in floors)


def test_no_trust_region_error_on_non_improving_predictions() -> None:
    """Members that never predict an improvement must yield pure-infill iterations."""

    class _Pessimist(_OverPromisingMember):
        def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
            self.certificate()
            return (-1000.0 + self._offset + 0.1 * features[0],)

    evaluator = _RecordingEvaluator()
    run = _optimizer(
        evaluator=evaluator,
        config=AcceleratedConfig(max_cfd_evals=8, seed=0),
        member_factory=lambda i: _Pessimist(float(i)),
    ).run()  # must not raise TrustRegionError
    assert all(r.trust_update is None for r in run.records)
