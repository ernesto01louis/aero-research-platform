"""Surrogate-accelerated optimization — the surrogate proposes, CFD disposes (ADR-032).

The Stage-17 loop that wires the Stage-15 optimizer substrate through the ADR-025
anti-surrogate-exploitation stack. Per outer iteration:

1. **Retrain + re-certify**: fresh members from ``member_factory``, an
   :class:`~aero.surrogates._common.ensemble.EnsembleSurrogate` fit on
   corpus + accumulated infill rows, a fresh smoke-tier operational certificate
   (the cert of record for the campaign is issued separately, on the committed
   final corpus — see the cert-lifecycle note below).
2. **Invariant-9 gate**: ``cert.assert_current(current_dataset_hash=...)`` once per
   iteration, before any prediction is consumed. The dataset hash is a DVC
   *sync-state* fingerprint (``dvc status -c``), so mid-campaign in-memory infill
   rows are invisible to it — the retrain-every-iteration cadence (L4) is therefore
   loop-enforced, not gate-forced; the gate still catches on-disk corpus drift and
   expiry. Documented honestly in ADR-032.
3. **Propose**: a seeded uniform candidate pool inside the current
   :class:`~aero.surrogates._common.trust_region.TrustRegionPolicy` bounds, ranked by
   uncertainty-routed infill (``rank_infill_candidates`` — top-EI exploit + reserved
   explore fraction).
4. **Dispose**: EVERY selected candidate goes to ground-truth CFD via the
   caller-supplied :class:`EvaluateBatch`. The incumbent is updated from CFD values
   ONLY — a surrogate prediction can never become the incumbent (Invariant 12).
5. **Trust-region update**: the ratio test is fed only the top exploit-routed
   candidate, and only when its predicted mean strictly improves on the incumbent —
   a non-improving prediction must not enter the accept/reject test
   (``TrustRegionError`` doctrine, ADR-025). When the incumbent moved to a design
   other than the trust-region center (an explore candidate won), the state is
   re-centered on the incumbent with radius/counters preserved — recorded in the
   iteration evidence as ``trust_recentered``.
6. **Stop** on: pre-registered target reached (CFD-verified), ground-truth budget
   exhausted, or repeated reject-floor distrust without incumbent improvement
   (→ the pre-registered NO-GO fallback: direct-CFD BO remains the loop of record).

Everything the loop does is captured in frozen :class:`IterationRecord` evidence
(certificate, candidates with routes, CFD evals, trust-region trail) so the campaign
bundle is replayable and auditable. Pure stdlib + numpy + pydantic; mypy strict.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from aero.optimize.design_space import DesignSpace
from aero.optimize.objective import ObjectiveEval
from aero.surrogates._common.base import Sample, Surrogate
from aero.surrogates._common.certificate import ApplicabilityEnvelope, CertificateOfValidity
from aero.surrogates._common.ensemble import EnsembleSurrogate
from aero.surrogates._common.infill import InfillCandidate, rank_infill_candidates
from aero.surrogates._common.trust_region import (
    TrustRegionConfig,
    TrustRegionPolicy,
    TrustRegionState,
    TrustRegionUpdate,
)

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_assignment=True, validate_default=True)


class EvaluateBatch(Protocol):
    """Ground-truth CFD evaluation of a batch of PHYSICAL design vectors.

    The driver supplies concurrency (independent serial solves); tests supply an
    analytic fake. An entry of ``None`` means that solve FAILED — it still counts
    against the ground-truth budget (pre-registered gate S8: failed solves are
    spent evals in both arms), it just contributes no value.
    """

    def __call__(self, designs: Sequence[np.ndarray]) -> Sequence[ObjectiveEval | None]: ...


class AcceleratedConfig(BaseModel):
    """Frozen loop configuration (pre-registered per campaign — gates L1-L5, ADR-032)."""

    model_config = _STRICT

    infill_batch: int = Field(
        default=4, ge=1, description="Candidates per iteration (L2: 3 exploit + 1 explore)."
    )
    explore_fraction: float = Field(default=0.25, ge=0.0, le=1.0)
    candidate_pool: int = Field(
        default=2048, ge=8, description="Uniform pool size inside the trust region (L3)."
    )
    max_cfd_evals: int = Field(default=16, ge=1, description="Marginal ground-truth budget (L5).")
    target_value: float | None = Field(
        default=None,
        description="Stop when the CFD-verified incumbent reaches this objective (the "
        "pre-registered bar); None = run to budget.",
    )
    max_consecutive_distrust: int = Field(
        default=2,
        ge=1,
        description="Reject-floor events without incumbent improvement before the loop "
        "stops and falls back to direct-CFD BO (L5, pre-registered NO-GO path).",
    )
    xi: float = Field(default=0.0, ge=0.0, description="EI exploration offset.")
    seed: int = Field(default=0, description="Drives retrain splits and pool sampling.")
    n_members: int = Field(default=5, ge=2, description="Ensemble member count.")
    calibration_fraction: float = Field(default=0.25, gt=0.0, lt=1.0)
    interval_k: float = Field(default=2.0, gt=0.0)
    trust_region: TrustRegionConfig = Field(default_factory=TrustRegionConfig)


class IterationRecord(BaseModel):
    """Frozen evidence of one propose/dispose iteration (serialized into the bundle)."""

    model_config = _STRICT

    iteration: int = Field(..., ge=0)
    certificate: CertificateOfValidity = Field(
        ..., description="The smoke-tier operational cert this iteration's proposals used."
    )
    candidates: tuple[InfillCandidate, ...] = Field(
        ..., description="The uncertainty-routed batch (route + EI + std evidence)."
    )
    results: tuple[ObjectiveEval | None, ...] = Field(
        ...,
        description="Ground-truth CFD results aligned with `candidates`; None = failed solve "
        "(still budget-spent, S8).",
    )
    trust_update: TrustRegionUpdate | None = Field(
        default=None,
        description="Ratio-test outcome for the top exploit candidate; None when no exploit "
        "candidate predicted an improvement (pure-infill iteration).",
    )
    trust_recentered: bool = Field(
        default=False,
        description="True iff the state was re-centered on a new incumbent that was not the "
        "trust-region-accepted candidate (e.g. an explore candidate won).",
    )
    incumbent_design_unit: tuple[float, ...] = Field(..., min_length=1)
    incumbent_value: float = Field(..., description="CFD-verified incumbent after this iteration.")


class AcceleratedRun(BaseModel):
    """The full campaign trace of one surrogate-accelerated run."""

    model_config = _STRICT

    records: tuple[IterationRecord, ...]
    n_cfd_evals: int = Field(..., ge=0, description="MARGINAL ground-truth solves spent (S4).")
    n_corpus: int = Field(..., ge=0, description="Training-corpus solves (the +N accounting).")
    n_candidates: int = Field(
        ..., ge=1, description="Selection-bias pool: corpus + marginal evals (Invariant 12)."
    )
    incumbent_design_unit: tuple[float, ...] = Field(..., min_length=1)
    incumbent_value: float
    incumbent_from_corpus: bool = Field(
        ..., description="True iff no loop eval beat the best corpus row."
    )
    stop_reason: Literal["target", "budget", "distrust"]


class SurrogateAcceleratedOptimizer:
    """The ADR-025-wired propose/dispose loop (see module docstring)."""

    def __init__(
        self,
        *,
        space: DesignSpace,
        corpus: Sequence[Sample],
        member_factory: Callable[[int], Surrogate],
        envelope: ApplicabilityEnvelope,
        dataset_id: str,
        dataset_hash_fn: Callable[[], str],
        evaluate_batch: EvaluateBatch,
        config: AcceleratedConfig,
        surrogate_name: str = "stage17_ld_ensemble",
        basis: Literal["deep_ensemble", "gp_bootstrap"] = "gp_bootstrap",
        metric_name: str = "ld_mae",
        maximize: bool = True,
    ) -> None:
        if len(corpus) < 4:
            raise ValueError(
                f"surrogate-accelerated optimization needs a trained-from corpus "
                f"(>= 4 samples); got {len(corpus)} — run the corpus campaign first"
            )
        self._space = space
        self._corpus = tuple(corpus)
        self._member_factory = member_factory
        self._envelope = envelope
        self._dataset_id = dataset_id
        self._dataset_hash_fn = dataset_hash_fn
        self._evaluate_batch = evaluate_batch
        self._config = config
        self._surrogate_name = surrogate_name
        self._basis: Literal["deep_ensemble", "gp_bootstrap"] = basis
        self._metric_name = metric_name
        self._maximize = maximize

    # --- internals ------------------------------------------------------------
    def _better(self, a: float, b: float) -> bool:
        return a > b if self._maximize else a < b

    def _retrain(
        self, infill: Sequence[Sample], iteration: int
    ) -> tuple[EnsembleSurrogate, CertificateOfValidity]:
        """Fresh members, fit on corpus + infill, fresh smoke cert, Invariant-9 gate."""
        cfg = self._config
        members = [self._member_factory(i) for i in range(cfg.n_members)]
        dataset_id = self._dataset_id if not infill else f"{self._dataset_id}+infill{len(infill)}"
        current_hash = self._dataset_hash_fn()
        ensemble = EnsembleSurrogate(
            members,
            surrogate_name=self._surrogate_name,
            training_dataset_dvc_hash=current_hash,
            dataset_id=dataset_id,
            applicability_envelope=self._envelope,
            basis=self._basis,
            metric_name=self._metric_name,
        )
        # CalibrationError on a collapsed ensemble propagates — never certified quiet.
        ensemble.fit(
            [*self._corpus, *infill],
            seed=cfg.seed + iteration,
            calibration_fraction=cfg.calibration_fraction,
            interval_k=cfg.interval_k,
        )
        cert = ensemble.set_certificate()
        # Invariant 9: both gates, against a freshly recomputed dataset hash. CertExpired
        # propagates loudly — an accelerated run never proposes on a stale certificate.
        cert.assert_current(current_dataset_hash=self._dataset_hash_fn())
        return ensemble, cert

    def _pool(
        self, policy: TrustRegionPolicy, state: TrustRegionState, iteration: int
    ) -> np.ndarray:
        """Seeded uniform candidate pool inside the trust region (unit cube), (n, d)."""
        rng = np.random.default_rng(self._config.seed * 100_003 + iteration)
        bounds = policy.bounds(state)
        lo = np.asarray([b[0] for b in bounds], dtype=np.float64)
        hi = np.asarray([b[1] for b in bounds], dtype=np.float64)
        u = rng.random((self._config.candidate_pool, len(bounds)))
        return np.asarray(lo + u * (hi - lo), dtype=np.float64)

    # --- the loop ---------------------------------------------------------------
    def run(self) -> AcceleratedRun:
        cfg = self._config
        # Incumbent seeds from the best CORPUS row — every corpus value is itself
        # ground-truth CFD, so the incumbent is CFD-verified from the first moment.
        best_idx = max(
            range(len(self._corpus)),
            key=lambda i: (1.0 if self._maximize else -1.0) * self._corpus[i].targets[0],
        )
        incumbent_unit: tuple[float, ...] = self._corpus[best_idx].features
        incumbent_value: float = self._corpus[best_idx].targets[0]
        incumbent_from_corpus = True

        policy = TrustRegionPolicy(cfg.trust_region)
        state = policy.initial_state(incumbent_unit)

        infill_samples: list[Sample] = []
        records: list[IterationRecord] = []
        n_cfd = 0
        n_infill_total = 0
        consecutive_distrust = 0
        stop_reason: Literal["target", "budget", "distrust"] | None = None

        if cfg.target_value is not None and not self._better(cfg.target_value, incumbent_value):
            # The corpus already contains a design at/past the bar — still a valid
            # (zero-marginal-eval) outcome; recorded honestly.
            stop_reason = "target"

        iteration = 0
        while stop_reason is None:
            ensemble, cert = self._retrain(infill_samples, iteration)

            pool = self._pool(policy, state, iteration)
            means: list[float] = []
            stds: list[float] = []
            designs: list[tuple[float, ...]] = []
            for row in pool:
                features = tuple(float(v) for v in row)
                pred = ensemble.predict_with_uncertainty(features)
                designs.append(features)
                means.append(pred.mean[0])
                if pred.epistemic_std is None:  # unreachable for an ensemble; fail loud anyway
                    raise RuntimeError(
                        "ensemble prediction carried no epistemic_std — cannot uncertainty-route"
                    )
                stds.append(pred.epistemic_std[0])

            n_select = min(cfg.infill_batch, cfg.max_cfd_evals - n_cfd)
            # InfillError on an all-zero-std pool propagates (collapsed ensemble).
            batch = rank_infill_candidates(
                designs,
                means,
                stds,
                current_best=incumbent_value,
                n_select=n_select,
                maximize=self._maximize,
                explore_fraction=cfg.explore_fraction,
                xi=cfg.xi,
            )

            physical = [self._space.from_unit(np.asarray(c.design)) for c in batch]
            results = list(self._evaluate_batch(physical))
            if len(results) != len(batch):
                raise RuntimeError(
                    f"evaluate_batch returned {len(results)} results for {len(batch)} designs"
                )
            n_cfd += len(batch)  # failed solves included — budget honesty (S8)

            value_before = incumbent_value
            incumbent_changed_to: tuple[float, ...] | None = None
            for candidate, result in zip(batch, results, strict=True):
                if result is None:
                    continue
                n_infill_total += 1
                infill_samples.append(
                    Sample(
                        features=candidate.design,
                        targets=(result.value,),
                        case_id=f"infill-{iteration:02d}-{candidate.rank}",
                        dataset_id=self._dataset_id,
                        data_origin="platform-validated",
                    )
                )
                if self._better(result.value, incumbent_value):
                    incumbent_value = result.value
                    incumbent_unit = candidate.design
                    incumbent_changed_to = candidate.design
                    incumbent_from_corpus = False

            # Trust-region ratio test: top exploit candidate only, only when its
            # prediction strictly improves on the PRE-batch incumbent, and only when
            # its ground-truth solve succeeded.
            trust_update: TrustRegionUpdate | None = None
            sign = 1.0 if self._maximize else -1.0
            top_idx = next((i for i, c in enumerate(batch) if c.route == "exploit"), None)
            if top_idx is not None:
                top_exploit = batch[top_idx]
                top_result = results[top_idx]
                predicted_gain = sign * (top_exploit.mean - value_before)
                if top_result is not None and predicted_gain > 0.0:
                    trust_update = policy.update(
                        state,
                        candidate=top_exploit.design,
                        predicted_objective=top_exploit.mean,
                        cfd_objective=top_result.value,
                        best_objective=value_before,
                        maximize=self._maximize,
                    )
                    state = trust_update.state

            improved = self._better(incumbent_value, value_before)
            trust_recentered = False
            if trust_update is not None and trust_update.surrogate_distrusted:
                if improved:
                    consecutive_distrust = 0
                else:
                    consecutive_distrust += 1
                # Reject-floor: re-open the region around the (CFD-verified) incumbent
                # so the post-retrain surrogate is probed at meaningful scale.
                state = policy.initial_state(incumbent_unit)
                trust_recentered = True
            elif incumbent_changed_to is not None and state.center != incumbent_unit:
                # An explore (or non-top-exploit) candidate won: keep radius/counters,
                # move the box to the new CFD-verified incumbent.
                state = TrustRegionState(
                    center=incumbent_unit,
                    radius=state.radius,
                    n_accepts=state.n_accepts,
                    n_rejects=state.n_rejects,
                    consecutive_rejects=state.consecutive_rejects,
                )
                trust_recentered = True

            records.append(
                IterationRecord(
                    iteration=iteration,
                    certificate=cert,
                    candidates=batch,
                    results=tuple(results),
                    trust_update=trust_update,
                    trust_recentered=trust_recentered,
                    incumbent_design_unit=incumbent_unit,
                    incumbent_value=incumbent_value,
                )
            )

            if cfg.target_value is not None and not self._better(cfg.target_value, incumbent_value):
                stop_reason = "target"
            elif n_cfd >= cfg.max_cfd_evals:
                stop_reason = "budget"
            elif consecutive_distrust >= cfg.max_consecutive_distrust:
                stop_reason = "distrust"
            iteration += 1

        return AcceleratedRun(
            records=tuple(records),
            n_cfd_evals=n_cfd,
            n_corpus=len(self._corpus),
            n_candidates=len(self._corpus) + n_cfd,
            incumbent_design_unit=incumbent_unit,
            incumbent_value=incumbent_value,
            incumbent_from_corpus=incumbent_from_corpus,
            stop_reason=stop_reason,
        )
