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

PLATFORM-NOT-HUB: only stdlib + pydantic are imported. Torch / JAX / numpy
arrays appear inside ``Sample.features`` as ``tuple[float, ...]`` via the
typed payload; baseline subclasses are responsible for converting at the
fit/predict boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

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
        self._certificate: CertificateOfValidity | None = None

    @property
    def non_commercial(self) -> bool:
        """True iff at least one ``TaintedSample`` has crossed :meth:`ingest`."""
        return self._non_commercial

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
