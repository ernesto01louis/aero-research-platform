"""Dataset loader scaffolding — base protocol + dataset-hash helper.

Public dataset loaders live in this subpackage. Each loader exposes the
:class:`DatasetLoader` protocol:

* ``__len__`` / ``__getitem__`` — Pythonic dataset interface; the
  ``__getitem__`` return type discriminates the licence boundary:

  - CC-BY-SA loaders (AhmedML, WindsorML, DrivAerML) yield
    :class:`~aero.surrogates._common.base.Sample`.
  - The quarantined CC-BY-NC loader (DrivAerNet++) lives under
    :mod:`aero.surrogates._common.loaders.non_commercial` and yields
    :class:`~aero.surrogates._common.base.TaintedSample`.

* ``dvc_path`` — the repo-relative path to the loader's DVC-tracked data
  root (e.g. ``data/datasets/ahmedml``). The :func:`dataset_hash` helper
  hashes ``dvc status -c`` over this path, producing the value that lands
  in both the :class:`CertificateOfValidity` and the
  :class:`SurrogateProvenanceTags`.

* ``license_id`` — SPDX-ish licence identifier. Stage 14 routes on this
  alongside the cert's ``non_commercial`` flag.

PLATFORM-NOT-HUB: only stdlib + pydantic + ``aero.provenance``-side helpers
are imported eagerly. ``numpy.load`` / ``h5py`` / mesh IO live behind
``aero[surrogate-smoke]`` and are imported inside concrete loader bodies.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, runtime_checkable

from aero.surrogates._common.base import Sample, TaintedSample


class DatasetLoaderError(RuntimeError):
    """A dataset loader could not satisfy its contract.

    Raised on: missing local DVC checkout, malformed manifest, `dvc status`
    failure, or any condition where ``dataset_hash`` cannot be computed.
    Fail loud — never substitute a placeholder hash.
    """


@runtime_checkable
class DatasetLoader(Protocol):
    """Structural protocol every public-dataset loader satisfies.

    Concrete loaders are small (~100 LoC) — they parse one upstream
    artifact format and yield :class:`Sample` (or
    :class:`TaintedSample` for the quarantined subpackage). The protocol is
    intentionally narrower than torch's ``Dataset`` because the platform
    core stays torch-free; baseline subclasses wrap the loader's
    ``__iter__`` into a ``torch.utils.data.DataLoader`` at the
    fit-boundary.
    """

    dataset_id: str
    license_id: str
    dvc_path: Path

    def __len__(self) -> int: ...

    def __getitem__(self, index: int, /) -> Sample | TaintedSample: ...

    def __iter__(self) -> Iterable[Sample | TaintedSample]: ...


def _dvc_executable() -> str:
    """Locate the `dvc` console script (mirrors ``aero.provenance.four_fold``).

    Resolved next to ``sys.executable`` first so the venv binary is found
    without ``PATH`` manipulation; falls back to ``shutil.which``.
    """
    candidate = Path(sys.executable).with_name("dvc")
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("dvc")
    if found:
        return found
    raise DatasetLoaderError("`dvc` not found — install the aero[provenance] extra")


def dataset_hash(repo_root: Path, dvc_path: Path | str) -> str:
    """sha256 over `dvc status -c <dvc_path>` for one loader's tracked inputs.

    Restricting ``dvc status -c`` to ``dvc_path`` (rather than the
    whole-repo flavour in ``aero.provenance.four_fold.dvc_input_hash``)
    gives each loader its own data-state fingerprint. The cert stores this
    value as ``training_dataset_dvc_hash``; the validate-time
    ``current_dataset_hash`` is recomputed at agent-invocation time.

    Returning an *empty status* digest (the hash of ``{}``) is the
    intended in-sync result, NOT an error — it means the loader's tracked
    files match the remote.
    """
    cmd = [_dvc_executable(), "status", "-c", "--json", str(dvc_path)]
    try:
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise DatasetLoaderError("`dvc` binary disappeared mid-run") from exc
    if proc.returncode != 0:
        raise DatasetLoaderError(
            f"`dvc status -c {dvc_path}` failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    try:
        status = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise DatasetLoaderError(f"could not parse `dvc status -c` output: {exc}") from exc
    canonical = json.dumps(status, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "DatasetLoader",
    "DatasetLoaderError",
    "dataset_hash",
]
