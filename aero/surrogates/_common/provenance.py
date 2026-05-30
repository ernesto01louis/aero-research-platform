"""SurrogateProvenanceTags — additive composition over the four-fold tuple.

The four-fold provenance contract (``aero.provenance.ProvenanceTuple``) is
immutable per CONSTITUTION Invariant 3. Stage 08 extends it ADDITIVELY:
``SurrogateProvenanceTags`` wraps a ``ProvenanceTuple`` and adds five
surrogate-specific tags Stage 14 queries by:

* ``training_dataset_dvc_hash`` — sha256 over the loader's DVC inputs at
  fit time. Matches the cert's ``training_dataset_dvc_hash``; agents check
  the two are equal before invoking.
* ``model_architecture`` — short identifier (e.g. ``mlp_baseline``,
  ``fno_smoke``, ``mgn_smoke``, ``domino``).
* ``hparam_hash`` — sha256 of the Hydra-resolved hyperparameter dict.
* ``cert_status`` — mirror of ``CertificateOfValidity.cert_status``.
* ``cert_expires_at`` — ISO-8601 expiry, for fast-rejection queries.
* ``non_commercial`` — ``"true" | "false"``, mirror of the cert's taint flag.

Strict pydantic, frozen, ``extra="forbid"``. Lazy-imports MLflow inside
:meth:`log_to_mlflow` (PLATFORM-NOT-HUB).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.provenance.four_fold import ProvenanceTuple

if TYPE_CHECKING:
    from aero.surrogates._common.certificate import CertificateOfValidity

_HASH_RE = r"^[0-9a-f]{64}$"


class SurrogateProvenanceTags(BaseModel):
    """The eight-tag bundle every Stage-08+ surrogate training run logs to MLflow.

    Composition over inheritance: the four-fold ``provenance`` field carries
    the platform-wide contract; the five surrogate-specific fields below are
    additive. The :meth:`as_mlflow_tags` method emits one flat dict for the
    MLflow API.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    provenance: ProvenanceTuple = Field(
        ..., description="The four-fold reproducibility tuple (Invariant 3)."
    )
    training_dataset_dvc_hash: str = Field(
        ...,
        pattern=_HASH_RE,
        description="sha256 over `dvc status -c` for the loader's DVC inputs at fit time.",
    )
    model_architecture: str = Field(..., min_length=1, description="Architecture identifier.")
    hparam_hash: str = Field(
        ..., pattern=_HASH_RE, description="sha256 of the resolved hyperparameter dict."
    )
    cert_status: Literal["smoke", "validated", "production"] = Field(
        ..., description="Mirror of CertificateOfValidity.cert_status."
    )
    cert_expires_at: datetime = Field(
        ..., description="Mirror of CertificateOfValidity.expires_at; UTC."
    )
    non_commercial: bool = Field(..., description="Mirror of the cert's CC-BY-NC taint flag.")

    @classmethod
    def from_certificate(
        cls,
        *,
        provenance: ProvenanceTuple,
        cert: CertificateOfValidity,
        hparam_hash: str,
    ) -> SurrogateProvenanceTags:
        """Build from an issued :class:`CertificateOfValidity` and a hparam hash.

        Pulls ``training_dataset_dvc_hash``, ``model_architecture``,
        ``cert_status``, ``cert_expires_at`` and ``non_commercial`` straight
        from the cert — guarantees the MLflow tags and the cert agree.
        """
        return cls(
            provenance=provenance,
            training_dataset_dvc_hash=cert.training_dataset_dvc_hash,
            model_architecture=cert.model_architecture,
            hparam_hash=hparam_hash,
            cert_status=cert.cert_status,
            cert_expires_at=cert.expires_at,
            non_commercial=cert.non_commercial,
        )

    def as_mlflow_tags(self) -> dict[str, str]:
        """All eight tags as a flat string-valued dict.

        Four from the four-fold tuple, four surrogate-specific. MLflow tags
        are strings; ``cert_expires_at`` rides as ISO-8601 and
        ``non_commercial`` as ``"true" | "false"``.
        """
        tags = self.provenance.as_mlflow_tags()
        tags.update(
            {
                "training_dataset_dvc_hash": self.training_dataset_dvc_hash,
                "model_architecture": self.model_architecture,
                "hparam_hash": self.hparam_hash,
                "cert_status": self.cert_status,
                "cert_expires_at": self.cert_expires_at.isoformat(),
                "non_commercial": "true" if self.non_commercial else "false",
            }
        )
        return tags

    def log_to_mlflow(self, run_id: str) -> None:
        """Set all eight tags on the specified MLflow run.

        Uses :class:`mlflow.MlflowClient` so the run id can be set
        explicitly — :func:`mlflow.set_tag` only operates on the active
        run from the fluent API. Lazy-imports ``mlflow``; the import sits
        behind the ``aero[provenance]`` extra (PLATFORM-NOT-HUB).
        """
        import mlflow

        client = mlflow.MlflowClient()
        for key, value in self.as_mlflow_tags().items():
            client.set_tag(run_id, key, value)


def hparam_hash(hparams: Mapping[str, Any]) -> str:
    """sha256 over the canonical-JSON serialisation of a hyperparameter dict.

    Mirrors :func:`aero.provenance.four_fold.config_hash` — sorted keys, no
    whitespace, so the hash is reproducible across machines and Python
    versions. Useful for both the cert (training-time signature) and the
    MLflow tag (run-time fingerprint).
    """
    canonical = json.dumps(dict(hparams), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
