"""DrivAerNet++ loader (CC-BY-NC-4.0) — QUARANTINED.

DrivAerNet++ is a 4 000-car DrivAer-family dataset with full pressure and
wall-shear-stress fields. It is licensed CC-BY-NC-4.0; artifacts trained on
it carry that constraint and cannot be reused commercially.

Three-layer defence (ADR-008 §D4):

1. **Structural separator** — the loader lives under
   :mod:`aero.surrogates._common.loaders.non_commercial`; the
   ``non-commercial-fence.yml`` CI workflow rejects PRs that import from
   this subpackage without producing ``non_commercial=True`` or carrying a
   ``# non-commercial: justified`` pragma.
2. **Constructor guard** — :class:`DrivAerNetPlusPlusDataset` requires
   ``acknowledge_noncommercial=True`` at ``__init__`` time and raises
   :class:`LicenseAcknowledgmentRequired` otherwise.
3. **Tainted-sample union** — ``__getitem__`` yields
   :class:`~aero.surrogates._common.base.TaintedSample`, which flips
   :attr:`Surrogate._non_commercial` via :meth:`Surrogate.ingest` on the
   first sample through, propagating into the issued
   :class:`CertificateOfValidity` with ``non_commercial=True``.

An MLflow side-effect helper (:func:`log_acknowledgment`) writes
``non_commercial=true`` and ``license_id=CC-BY-NC-4.0`` to the active run
so the audit trail survives the run.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from aero.surrogates._common.base import TaintedSample
from aero.surrogates._common.certificate import LicenseAcknowledgmentRequired
from aero.surrogates._common.loaders import DatasetLoaderError

DATASET_ID: Final[str] = "drivaernet_plus_plus"
LICENSE_ID: Final[str] = "CC-BY-NC-4.0"
DVC_PATH: Final[Path] = Path("data/datasets/drivaernet_plus_plus")


def log_acknowledgment(run_id: str) -> None:
    """Tag the active MLflow run with the non-commercial acknowledgment.

    Lazy-imports ``mlflow`` (PLATFORM-NOT-HUB). Called once per dataset
    construction by the training entrypoint, not by the loader itself, so
    the loader stays MLflow-free for unit tests.
    """
    import mlflow

    client = mlflow.MlflowClient()
    client.set_tag(run_id, "non_commercial", "true")
    client.set_tag(run_id, "license_id", LICENSE_ID)
    client.set_tag(run_id, "dataset_id", DATASET_ID)


class DrivAerNetPlusPlusCase(BaseModel):
    """One DrivAerNet++ case row from the upstream ``manifest.json``."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    case_id: str = Field(..., min_length=1)
    body_type: str = Field(..., min_length=1)
    frontal_area_m2: float = Field(..., gt=0.0)
    body_length_m: float = Field(..., gt=0.0)
    cd: float = Field(..., ge=0.0)


_BODY_CODES: Final[dict[str, float]] = {
    "notchback": 0.0,
    "fastback": 1.0,
    "estateback": 2.0,
}


class DrivAerNetPlusPlusDataset:
    """Quarantined CC-BY-NC loader; yields :class:`TaintedSample`.

    Construction requires ``acknowledge_noncommercial=True``; otherwise
    raises :class:`LicenseAcknowledgmentRequired` at ``__init__`` time
    (fail-loud at construction, not at first ``__getitem__``).
    """

    dataset_id = DATASET_ID
    license_id = LICENSE_ID
    dvc_path = DVC_PATH

    def __init__(
        self,
        *,
        repo_root: Path,
        acknowledge_noncommercial: bool = False,
    ) -> None:
        if not acknowledge_noncommercial:
            raise LicenseAcknowledgmentRequired(
                "DrivAerNet++ is licensed CC-BY-NC-4.0; pass "
                "acknowledge_noncommercial=True to confirm artifacts trained "
                "on it carry the non-commercial constraint"
            )
        manifest_path = repo_root / DVC_PATH / "manifest.json"
        if not manifest_path.is_file():
            raise DatasetLoaderError(
                f"DrivAerNet++ manifest missing at {manifest_path}; run "
                f"`dvc pull data/datasets/drivaernet_plus_plus/manifest.json` first"
            )
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._cases: list[DrivAerNetPlusPlusCase] = [
            DrivAerNetPlusPlusCase.model_validate(row) for row in raw
        ]

    def __len__(self) -> int:
        return len(self._cases)

    def __getitem__(self, index: int, /) -> TaintedSample:
        c = self._cases[index]
        try:
            body_code = _BODY_CODES[c.body_type]
        except KeyError as exc:
            raise DatasetLoaderError(
                f"unknown DrivAerNet++ body_type '{c.body_type}' in case {c.case_id}"
            ) from exc
        return TaintedSample(
            features=(body_code, c.frontal_area_m2, c.body_length_m),
            targets=(c.cd,),
            case_id=c.case_id,
            dataset_id=DATASET_ID,
            license_id=LICENSE_ID,
        )

    def __iter__(self) -> Iterator[TaintedSample]:
        for i in range(len(self)):
            yield self[i]
