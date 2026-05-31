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

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

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
        "by Surrogate.set_certificate(); authors must not set directly. Write-once-True: "
        "once flipped to True by any source it cannot be reset to False (model_copy + the "
        "_non_commercial_is_write_once_true validator enforce this).",
    )
    attribution_required: tuple[str, ...] = Field(
        default=(),
        description="Citation strings every publication / artifact / public model description "
        "MUST carry. Populated by the loader when the dataset's licence carries an attribution "
        "obligation (CC-BY-*, including CC-BY-SA + CC-BY-NC). Stage-14 agents log every entry "
        "to MLflow at predict time so the audit trail survives downstream copies.",
    )
    license_id: str = Field(
        default="",
        description="SPDX-ish licence identifier of the most restrictive training-set licence "
        "(e.g. 'CC-BY-NC-4.0' if any sample was CC-BY-NC, else 'CC-BY-SA-4.0', etc.). Empty "
        "string only on smoke / synthetic fixtures.",
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

    @model_validator(mode="after")
    def _surrogate_name_watermark(self) -> CertificateOfValidity:
        """Force the ``_nc`` suffix on any surrogate trained on CC-BY-NC data.

        Watermark is structural: every artifact, MLflow tag, model registry
        entry, and downstream filename carries the ``_nc`` marker so a human
        scanning a directory listing can see at a glance which models bear
        the non-commercial obligation. The cert's `non_commercial` flag is
        the legal contract; this watermark is the visual one.
        """
        if self.non_commercial and not self.surrogate_name.endswith("_nc"):
            raise ValueError(
                f"surrogate_name {self.surrogate_name!r} carries non_commercial=True "
                "but lacks the mandatory '_nc' suffix. Append '_nc' to the surrogate "
                "name so the CC-BY-NC obligation is visually traceable in every "
                "directory listing, MLflow run name and model-registry entry."
            )
        return self

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> CertificateOfValidity:
        """Override `BaseModel.model_copy` to refuse `non_commercial=True → False`.

        Write-once-True: once a cert is issued with `non_commercial=True`,
        no model_copy can flip it back. This is the third structural layer of
        the CC-BY-NC quarantine (after the loader fence + the Surrogate-base
        taint propagation): even if a caller tries to launder a tainted cert
        by re-issuing it with `non_commercial=False`, this guard blocks the
        update at construction time.
        """
        if update and self.non_commercial and update.get("non_commercial") is False:
            raise ValueError(
                "refusing CertificateOfValidity.model_copy update that flips "
                "non_commercial from True → False. The CC-BY-NC obligation is "
                "write-once-True: once a cert is tainted by training-set "
                "exposure to CC-BY-NC data, the taint is permanent. "
                "If you genuinely need a commercial-clean model, retrain on "
                "CC-BY-SA-only datasets and issue a fresh cert."
            )
        return super().model_copy(update=update, deep=deep)

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
        license_id: str = "",
        attribution_required: tuple[str, ...] = (),
        lifetime: timedelta = DEFAULT_CERT_LIFETIME,
        now: datetime | None = None,
    ) -> CertificateOfValidity:
        """Construct a cert with ``expires_at = issued_at + lifetime`` (default 180 d).

        The 180-day default is ADR-008 §D5: 6 months OR training-dataset
        DVC hash change, whichever first. Callers that want a different
        lifetime pass ``lifetime=...`` explicitly and document the deviation.
        """
        issued = now if now is not None else datetime.now(UTC)
        if non_commercial and not surrogate_name.endswith("_nc"):
            surrogate_name = f"{surrogate_name}_nc"
        return cls(
            surrogate_name=surrogate_name,
            model_architecture=model_architecture,
            training_dataset_dvc_hash=training_dataset_dvc_hash,
            dataset_id=dataset_id,
            held_out_metrics=held_out_metrics,
            applicability_envelope=applicability_envelope,
            cert_status=cert_status,
            non_commercial=non_commercial,
            license_id=license_id,
            attribution_required=attribution_required,
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

        Adds the legal-trail fields (``license_id``, ``attribution_required``)
        so every MLflow run captures the upstream licence + citation chain
        without the caller having to remember.
        """
        tags = {
            "surrogate_name": self.surrogate_name,
            "model_architecture": self.model_architecture,
            "training_dataset_dvc_hash": self.training_dataset_dvc_hash,
            "dataset_id": self.dataset_id,
            "cert_status": self.cert_status,
            "non_commercial": "true" if self.non_commercial else "false",
            "cert_issued_at": self.issued_at.isoformat(),
            "cert_expires_at": self.expires_at.isoformat(),
        }
        if self.license_id:
            tags["license_id"] = self.license_id
        if self.attribution_required:
            # Pipe-separated keeps it readable in the MLflow UI; the cert JSON
            # artifact carries the structured list for programmatic access.
            tags["attribution_required"] = " | ".join(self.attribution_required)
        return tags
