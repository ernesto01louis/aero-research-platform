"""CertificateOfValidity — the typed contract Stage 14 agents check.

ADR-008 §D5 ships a 6-month-OR-hash-change expiry policy. A cert is
*current* iff:

* ``now < expires_at`` (the time gate), AND
* ``current_dataset_hash == dataset_hash_at_issue`` (the data gate).

``validate()`` raises :class:`CertExpired` on the first failing gate. The
agent layer (Stage 14) calls ``validate()`` before every
``Surrogate.predict``; on failure it refuses to invoke the model and falls
back to a validated solver (Principle 4). The MLflow run that produced the
training logs the cert as a JSON artifact under ``certificates/<name>.json``
so Stage 14 can re-validate against the snapshot.

Strict pydantic, frozen, ``extra="forbid"``. See
``.claude/rules/fail-loud-pydantic.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A 64-hex sha256 digest, matching the four-fold provenance pattern.
_HASH_RE = r"^[0-9a-f]{64}$"

# Default cert lifetime — ADR-008 §D5; operator approved 2026-05-30.
DEFAULT_CERT_LIFETIME = timedelta(days=180)


class CertExpired(RuntimeError):  # noqa: N818 — domain-natural state name
    """A :class:`CertificateOfValidity` failed :meth:`CertificateOfValidity.assert_current`.

    Raised on either the time gate (``now >= expires_at``) or the data gate
    (training-dataset DVC hash drift). Agents catch this exception, refuse
    to invoke the surrogate, and fall back to a validated solver.
    """


class LicenseAcknowledgmentRequired(RuntimeError):  # noqa: N818 — domain-natural state name
    """A quarantined CC-BY-NC dataset was constructed without acknowledgment.

    Raised by ``DrivAerNetPlusPlusDataset.__init__`` when the caller did not
    pass ``acknowledge_noncommercial=True``. Forces explicit per-use opt-in,
    backed by an MLflow tag. ADR-008 §D4 layer 2 of 3.

    Defined here (not in ``base.py``) so the loader subpackage can import it
    without circular dependency on the surrogate ABC.
    """


class MetricQuantiles(BaseModel):
    """Held-out error quantiles for one scalar metric.

    Quantiles (not just mean) so the cert captures tail behaviour. A 5%
    mean error on Cd is meaningless if the 95th-percentile error is 40% —
    that's a model that's right on average but wrong where it matters.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    p50: float = Field(..., ge=0.0, description="Median absolute error on held-out cases.")
    p95: float = Field(..., ge=0.0, description="95th-percentile absolute error.")
    p99: float = Field(..., ge=0.0, description="99th-percentile absolute error.")
    n_held_out: int = Field(..., ge=1, description="Held-out sample count behind these quantiles.")

    @model_validator(mode="after")
    def _quantiles_monotonic(self) -> MetricQuantiles:
        if not (self.p50 <= self.p95 <= self.p99):
            raise ValueError(
                f"quantiles must satisfy p50 <= p95 <= p99; got "
                f"({self.p50}, {self.p95}, {self.p99})"
            )
        return self


class ApplicabilityEnvelope(BaseModel):
    """Typed bounds on the input distribution the surrogate was trained on.

    Stage 14 agents check the predict-time inputs against this envelope. A
    request outside the envelope is treated like an expired cert: agent
    refuses, falls back to a validated solver. Stage 12's V&V tolerance
    envelope may extend these constraints with output-space bounds; not
    shipped in Stage 08.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )

    re_range: tuple[float, float] = Field(
        ..., description="(min, max) Reynolds number range the training set spans."
    )
    mach_range: tuple[float, float] = Field(
        ..., description="(min, max) Mach number range the training set spans."
    )
    aoa_range_deg: tuple[float, float] = Field(
        ..., description="(min, max) angle-of-attack range in degrees."
    )
    geometry_class: str = Field(
        ...,
        min_length=1,
        description="Geometry family the training set is drawn from (e.g. 'ahmed-body', "
        "'drivaer-notchback', 'naca-4digit').",
    )

    @model_validator(mode="after")
    def _ranges_ordered(self) -> ApplicabilityEnvelope:
        for name, (lo, hi) in (
            ("re_range", self.re_range),
            ("mach_range", self.mach_range),
            ("aoa_range_deg", self.aoa_range_deg),
        ):
            if lo > hi:
                raise ValueError(f"{name} must satisfy lo <= hi; got ({lo}, {hi})")
        return self


class CertificateOfValidity(BaseModel):
    """A signed-by-construction proof a surrogate is fit for a bounded use.

    Required fields shape the agent-layer's contract:

    * ``training_dataset_dvc_hash`` — sha256 of the loader's tracked DVC
      inputs at training time. Drift here flips :meth:`validate` to fail.
    * ``held_out_metrics`` — per-metric :class:`MetricQuantiles`. Stage 09+
      production certs require Cd MAE p95 < 5% to upgrade
      ``cert_status`` from ``"smoke"`` to ``"validated"``.
    * ``applicability_envelope`` — typed input-space constraints.
    * ``cert_status`` — ``"smoke" | "validated" | "production"``. Stage 08
      ships all three baselines as ``"smoke"``; Stage 12 ships the first
      ``"validated"``; Stage 14 productionisation gates on ``"production"``.
    * ``non_commercial`` — propagated automatically from
      :meth:`Surrogate.set_certificate` if any ``TaintedSample`` was seen.
      Authors do NOT set this; the surrogate base class overwrites it.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    surrogate_name: str = Field(
        ..., min_length=1, description="Identifier of the surrogate this cert refers to."
    )
    model_architecture: str = Field(
        ...,
        min_length=1,
        description="Architecture identifier (e.g. 'mlp_baseline', 'fno_smoke', 'mgn_smoke').",
    )
    training_dataset_dvc_hash: str = Field(
        ...,
        pattern=_HASH_RE,
        description="sha256 of `dvc status -c` over the loader's tracked inputs at train time.",
    )
    dataset_id: str = Field(
        ..., min_length=1, description="Source dataset identifier (e.g. 'ahmedml', 'drivaerml')."
    )
    held_out_metrics: dict[str, MetricQuantiles] = Field(
        ..., description="Per-metric held-out error quantiles."
    )
    applicability_envelope: ApplicabilityEnvelope = Field(
        ..., description="Typed bounds on the input distribution."
    )
    cert_status: Literal["smoke", "validated", "production"] = Field(
        ...,
        description="'smoke' = pipeline-only, not for publication; 'validated' = passes V&V "
        "envelope; 'production' = Stage-14-callable.",
    )
    non_commercial: bool = Field(
        ...,
        description="True iff the training set included any CC-BY-NC samples. Auto-propagated "
        "by Surrogate.set_certificate(); authors must not set directly.",
    )
    issued_at: datetime = Field(..., description="UTC timestamp the cert was issued.")
    expires_at: datetime = Field(
        ..., description="UTC timestamp after which validate() fails the time gate."
    )

    @model_validator(mode="after")
    def _times_ordered(self) -> CertificateOfValidity:
        if self.expires_at <= self.issued_at:
            raise ValueError(
                f"expires_at ({self.expires_at}) must be strictly after issued_at "
                f"({self.issued_at})"
            )
        if not self.held_out_metrics:
            raise ValueError("held_out_metrics must contain at least one metric")
        return self

    @classmethod
    def new(
        cls,
        *,
        surrogate_name: str,
        model_architecture: str,
        training_dataset_dvc_hash: str,
        dataset_id: str,
        held_out_metrics: dict[str, MetricQuantiles],
        applicability_envelope: ApplicabilityEnvelope,
        cert_status: Literal["smoke", "validated", "production"],
        non_commercial: bool,
        lifetime: timedelta = DEFAULT_CERT_LIFETIME,
        now: datetime | None = None,
    ) -> CertificateOfValidity:
        """Construct a cert with ``expires_at = issued_at + lifetime`` (default 180 d).

        The 180-day default is ADR-008 §D5: 6 months OR training-dataset
        DVC hash change, whichever first. Callers that want a different
        lifetime pass ``lifetime=...`` explicitly and document the deviation.
        """
        issued = now if now is not None else datetime.now(UTC)
        return cls(
            surrogate_name=surrogate_name,
            model_architecture=model_architecture,
            training_dataset_dvc_hash=training_dataset_dvc_hash,
            dataset_id=dataset_id,
            held_out_metrics=held_out_metrics,
            applicability_envelope=applicability_envelope,
            cert_status=cert_status,
            non_commercial=non_commercial,
            issued_at=issued,
            expires_at=issued + lifetime,
        )

    def assert_current(
        self,
        *,
        current_dataset_hash: str,
        now: datetime | None = None,
    ) -> None:
        """Raise :class:`CertExpired` if the cert is no longer current.

        Two gates, in order:

        1. **Time gate.** ``now >= expires_at`` fails. Forces revalidation
           even on a frozen dataset.
        2. **Data gate.** ``current_dataset_hash != training_dataset_dvc_hash``
           fails. Catches dataset drift between expiries.

        Stage 14's agent layer wraps this in a ``try/except CertExpired``;
        on failure it refuses to invoke the surrogate and falls back to a
        validated solver. CONSTITUTION Invariant 9.

        Named ``assert_current`` (not ``validate``) to avoid colliding with
        ``pydantic.BaseModel.validate`` — pydantic's classmethod has a
        different signature, and shadowing it confuses both mypy strict
        and any code path that calls the inherited classmethod for model
        validation.
        """
        check_time = now if now is not None else datetime.now(UTC)
        if check_time >= self.expires_at:
            raise CertExpired(
                f"certificate for {self.surrogate_name} expired at {self.expires_at.isoformat()} "
                f"(now={check_time.isoformat()})"
            )
        if current_dataset_hash != self.training_dataset_dvc_hash:
            raise CertExpired(
                f"certificate for {self.surrogate_name} was issued against dataset hash "
                f"{self.training_dataset_dvc_hash} but the current hash is "
                f"{current_dataset_hash} — dataset drifted, re-train required"
            )

    def as_mlflow_tags(self) -> dict[str, str]:
        """The cert metadata as MLflow tags (string-valued, per MLflow's API).

        MLflow tags are strings only; numeric metrics ride as JSON values
        the agent layer parses on read. This pairs with the four-fold
        provenance tuple's :meth:`ProvenanceTuple.as_mlflow_tags`.
        """
        return {
            "surrogate_name": self.surrogate_name,
            "model_architecture": self.model_architecture,
            "training_dataset_dvc_hash": self.training_dataset_dvc_hash,
            "dataset_id": self.dataset_id,
            "cert_status": self.cert_status,
            "non_commercial": "true" if self.non_commercial else "false",
            "cert_issued_at": self.issued_at.isoformat(),
            "cert_expires_at": self.expires_at.isoformat(),
        }
