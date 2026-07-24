"""Surrogate ABC + protocol, and the Sample / TaintedSample discriminated union.

Three concrete shapes ship here:

* ``Sample`` / ``TaintedSample`` — discriminated Pydantic union keyed on
  ``kind: Literal["commercial", "non_commercial"]``. ``__getitem__`` on a
  CC-BY-SA dataset (AhmedML, WindsorML, DrivAerML) yields ``Sample``;
  ``__getitem__`` on the quarantined ``DrivAerNetPlusPlusDataset`` yields
  ``TaintedSample``. ``Surrogate.fit()`` accepts either, but as soon as one
  ``TaintedSample`` crosses the training boundary the internal
  ``_non_commercial`` flag flips and ``certificate()`` constructs the
  ``CertificateOfValidity`` with ``non_commercial=True`` — refusing any
  caller's attempt to override it. This is the second of the three quarantine
  layers (constructor guard / structural separator / tainted batch — see
  ADR-008 §D4).

* ``Surrogate`` — abstract base class that surrogate baselines and Stage-09+
  production models inherit from. Implements the ``ingest`` /
  ``set_certificate`` flow and the ``predict`` guard (raises
  :class:`UncertifiedSurrogate` if no current cert exists), and declares
  ``fit`` / ``_build_certificate`` as abstract.

* ``SurrogateProtocol`` — structural typing alias the agent layer (Stage 14)
  types against. Subclassing ``Surrogate`` is the canonical implementation
  path; ``SurrogateProtocol`` exists so a future plugin author can satisfy
  the contract without inheriting.

* ``SurrogatePrediction`` / ``UncertaintyAwareSurrogateProtocol`` (ADR-025) —
  the additive epistemic-uncertainty seam. ``Surrogate.predict_with_uncertainty``
  ships a default that wraps ``predict`` and honestly reports "no uncertainty
  model" (``basis="none"``, ``epistemic_std=None``); ensemble / MC-dropout
  subclasses override it. The Stage-16 surrogate-in-the-loop optimizer consumes
  this seam for trust-region bounding and uncertainty-routed infill.

PLATFORM-NOT-HUB: only stdlib + pydantic are imported. Torch / JAX / numpy
arrays appear inside ``Sample.features`` as ``tuple[float, ...]`` via the
typed payload; baseline subclasses are responsible for converting at the
fit/predict boundary.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from aero.surrogates._common.certificate import CertificateOfValidity


class UncertifiedSurrogate(RuntimeError):  # noqa: N818 — domain-natural state name
    """A surrogate's :meth:`Surrogate.predict` was called without a current cert.

    Raised loud — never swallowed. CONSTITUTION Invariant 9 says no agent
    invocation may bypass ``Surrogate.certificate().assert_current()``;
    this exception is what enforces that contract at runtime, in addition
    to the Stage-14 static check.
    """


class _SampleBase(BaseModel):
    """Shared payload shape for training samples.

    ``features`` and ``targets`` are tuples of floats — Pydantic-strict and
    JSON-round-trippable. Baselines convert to ``torch.Tensor`` / ``jax.numpy``
    arrays at the fit/predict boundary; the protocol stays platform-neutral.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    features: tuple[float, ...] = Field(..., description="Geometry / flow input vector.")
    targets: tuple[float, ...] = Field(..., description="Held-out scalar targets (e.g. Cd, Cl).")
    case_id: str = Field(..., min_length=1, description="Source case identifier.")
    dataset_id: str = Field(..., min_length=1, description="Source dataset name.")
    data_origin: Literal["platform-validated", "foreign"] = Field(
        default="foreign",
        description="Provenance of this sample (CONSTITUTION Invariant 11, NO-SURROGATE-ON-"
        "FOREIGN-DATA). 'foreign' = a corpus the platform did not generate and validate "
        "(automotive / transport-aircraft); 'platform-validated' = the platform's own validated "
        "CFD. A surrogate that ingests ANY 'foreign' sample cannot be issued a 'validated' or "
        "'production' certificate. Defaults to 'foreign' (fail-closed): the platform's own CFD "
        "must opt in explicitly; every foreign loader also sets it explicitly (data-origin fence).",
    )


class Sample(_SampleBase):
    """A training sample drawn from a permissively-licensed dataset.

    ``kind == "commercial"`` means the source dataset's licence (CC-BY-SA,
    Apache-2, BSD, etc.) does not restrict downstream commercial reuse of
    artifacts trained on it. AhmedML, WindsorML and DrivAerML produce these.
    """

    kind: Literal["commercial"] = "commercial"


class TaintedSample(_SampleBase):
    """A training sample drawn from a CC-BY-NC dataset (DrivAerNet++).

    The discriminator ``kind == "non_commercial"`` is what
    :meth:`Surrogate.ingest` watches for. One tainted sample anywhere in the
    training stream is sufficient to flip the surrogate's internal
    ``_non_commercial`` flag, which ``certificate()`` then propagates into the
    issued :class:`~aero.surrogates._common.certificate.CertificateOfValidity`.
    """

    kind: Literal["non_commercial"] = "non_commercial"
    license_id: str = Field(
        default="CC-BY-NC-4.0",
        description="SPDX-ish identifier of the upstream non-commercial licence.",
    )


class SurrogatePrediction(BaseModel):
    """One prediction, with epistemic uncertainty where the surrogate supports it.

    ``basis`` is a discriminated evidence label (the ADR-023 pattern: typed
    evidence over free floats):

    * ``"none"`` — the surrogate has no uncertainty model. ``epistemic_std``
      is ``None`` — honestly absent, NEVER a fabricated zero. Downstream
      consumers (infill routing, trust-region bookkeeping) treat ``None`` as
      "cannot uncertainty-route" and fail loud rather than treating an
      uncertainty-blind surrogate as perfectly certain.
    * ``"deep_ensemble"`` — ``epistemic_std`` is the ddof=1 population std
      over ``n_members`` independently-seeded members (ADR-025).
    * ``"mc_dropout"`` — reserved; ledgered in ADR-025, no producer yet.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    mean: tuple[float, ...] = Field(
        ..., min_length=1, description="Predicted target vector (same width as predict())."
    )
    epistemic_std: tuple[float, ...] | None = Field(
        default=None,
        description="Per-target epistemic std (model uncertainty). None iff basis='none'.",
    )
    basis: Literal["none", "deep_ensemble", "mc_dropout"] = Field(
        ..., description="How the uncertainty was produced. 'none' = no uncertainty model."
    )
    n_members: int = Field(
        default=1,
        ge=1,
        description="Ensemble members / MC samples behind the estimate; 1 iff basis='none'.",
    )

    @model_validator(mode="after")
    def _uncertainty_consistent(self) -> SurrogatePrediction:
        for v in self.mean:
            if not math.isfinite(v):
                raise ValueError(f"mean contains a non-finite value ({v})")
        if self.basis == "none":
            if self.epistemic_std is not None:
                raise ValueError(
                    "basis='none' forbids epistemic_std: a surrogate without an uncertainty "
                    "model must report None, not a fabricated std"
                )
            if self.n_members != 1:
                raise ValueError(f"basis='none' requires n_members=1; got {self.n_members}")
            return self
        if self.epistemic_std is None:
            raise ValueError(f"basis={self.basis!r} requires epistemic_std; got None")
        if self.n_members < 2:
            raise ValueError(
                f"basis={self.basis!r} requires n_members >= 2; got {self.n_members} — "
                "a single member cannot estimate epistemic spread"
            )
        if len(self.epistemic_std) != len(self.mean):
            raise ValueError(
                f"epistemic_std width ({len(self.epistemic_std)}) must match mean width "
                f"({len(self.mean)})"
            )
        for v in self.epistemic_std:
            if not math.isfinite(v) or v < 0.0:
                raise ValueError(f"epistemic_std must be finite and >= 0; got {v}")
        return self


@runtime_checkable
class SurrogateProtocol(Protocol):
    """Structural protocol the Stage-14 agent layer types against.

    Concrete surrogates subclass :class:`Surrogate` (which satisfies this
    protocol). This Protocol exists so a future external plugin can satisfy
    the contract without inheriting from the ABC.
    """

    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None: ...

    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]: ...

    def certificate(self) -> CertificateOfValidity: ...


@runtime_checkable
class UncertaintyAwareSurrogateProtocol(SurrogateProtocol, Protocol):
    """Structural protocol for surrogates that expose epistemic uncertainty (ADR-025).

    A NEW protocol name rather than a method added to :class:`SurrogateProtocol`
    — extending the existing runtime-checkable protocol would silently break
    every structural (non-inheriting) implementer. ``Surrogate`` subclasses
    satisfy this protocol automatically via the base-class default; the
    distinction matters only for external plugins that implement the contract
    structurally.
    """

    def predict_with_uncertainty(self, features: tuple[float, ...], /) -> SurrogatePrediction: ...


class Surrogate(ABC):
    """Abstract base for every concrete surrogate model in the platform.

    Subclasses implement :meth:`fit` and :meth:`_build_certificate`. The
    base class owns:

    * The CC-BY-NC taint flag (``_non_commercial``), flipped by
      :meth:`ingest` the first time a ``TaintedSample`` passes through.
    * The cached current cert (``_certificate``), populated by
      :meth:`set_certificate` after a successful fit.
    * The :meth:`predict` guard that refuses to run without a current
      validated cert (CONSTITUTION Invariant 9).
    """

    def __init__(self) -> None:
        self._non_commercial: bool = False
        self._data_origin: Literal["platform-validated", "foreign"] = "platform-validated"
        self._certificate: CertificateOfValidity | None = None

    @property
    def non_commercial(self) -> bool:
        """True iff at least one ``TaintedSample`` has crossed :meth:`ingest`."""
        return self._non_commercial

    @property
    def data_origin(self) -> Literal["platform-validated", "foreign"]:
        """'foreign' iff any ingested sample was 'foreign' (write-once toward foreign).

        CONSTITUTION Invariant 11: a 'foreign'-origin surrogate cannot be certified
        'validated'/'production' — the certificate's schema validator refuses it.
        """
        return self._data_origin

    def ingest(self, sample: Sample | TaintedSample, /) -> None:
        """Update internal state from one training sample.

        ``fit`` implementations call this on every sample they process. The
        only side-effect is flipping :attr:`non_commercial` when a
        ``TaintedSample`` is seen — there is no opt-out. The discriminated
        union is the contract; subclasses that inspect ``sample.kind``
        directly should use :func:`isinstance` (mypy strict does not narrow
        through ``getattr(sample, "kind", None)`` — Stage-07 gotcha §6).
        """
        if isinstance(sample, TaintedSample):
            self._non_commercial = True
        # Write-once toward 'foreign': one foreign sample taints the whole surrogate (Invariant 11).
        if sample.data_origin == "foreign":
            self._data_origin = "foreign"

    @abstractmethod
    def fit(self, data: Iterable[Sample | TaintedSample], /, **hparams: Any) -> None:
        """Train on the dataset. Subclasses must call :meth:`ingest` on every sample."""

    @abstractmethod
    def _build_certificate(self) -> CertificateOfValidity:
        """Construct a fresh :class:`CertificateOfValidity` from the fit's state.

        Called by :meth:`set_certificate` after fit completes. Subclasses
        must populate ``training_dataset_dvc_hash``, ``held_out_metrics``,
        ``applicability_envelope``, and ``cert_status``. They MUST NOT set
        ``non_commercial`` directly — :meth:`set_certificate` overrides any
        author-supplied value with the taint flag.
        """

    def set_certificate(self) -> CertificateOfValidity:
        """Build, taint-correct, and cache the post-fit certificate.

        After ``fit`` completes, the surrogate calls this once. The taint
        flag is the source of truth for ``non_commercial`` — if any
        ``TaintedSample`` crossed :meth:`ingest`, the cached cert is built
        with ``non_commercial=True`` regardless of what
        :meth:`_build_certificate` returned.
        """
        cert = self._build_certificate()
        if self._non_commercial and not cert.non_commercial:
            cert = cert.model_copy(update={"non_commercial": True})
        # Invariant 11: propagate a 'foreign' taint into the cert. If the cert is validated/
        # production this raises in the cert validator — a foreign-origin surrogate must never
        # have carried a publication-grade cert in the first place (fail-loud).
        if self._data_origin == "foreign" and cert.data_origin != "foreign":
            cert = cert.model_copy(update={"data_origin": "foreign"})
        self._certificate = cert
        return cert

    def certificate(self) -> CertificateOfValidity:
        """Return the current cached certificate.

        Raises :class:`UncertifiedSurrogate` if :meth:`set_certificate` has
        not yet been called. The agent layer (Stage 14) calls
        ``certificate().assert_current()`` before every predict; if either step
        fails, the agent refuses to invoke the model.
        """
        if self._certificate is None:
            raise UncertifiedSurrogate(
                f"{type(self).__name__} has no current certificate — call set_certificate() "
                "after fit() completes"
            )
        return self._certificate

    @abstractmethod
    def predict(self, features: tuple[float, ...], /) -> tuple[float, ...]:
        """Predict on a single input vector.

        Subclasses must call :meth:`certificate` (NOT :attr:`_certificate`
        directly) at the top of every implementation so the
        :class:`UncertifiedSurrogate` guard fires before any GPU work.
        """

    def predict_with_uncertainty(self, features: tuple[float, ...], /) -> SurrogatePrediction:
        """Predict with epistemic uncertainty where the surrogate supports it (ADR-025).

        Default implementation wraps :meth:`predict` and reports
        ``basis="none"`` / ``epistemic_std=None`` — an honest "this surrogate
        has no uncertainty model", never a fabricated zero std. The
        :class:`UncertifiedSurrogate` guard fires through the wrapped
        :meth:`predict` call. Ensemble / MC-dropout subclasses override.
        """
        return SurrogatePrediction(mean=self.predict(features), basis="none")
