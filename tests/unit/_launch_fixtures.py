"""Shared fakes for the Stage-23 launch guard (ADR-053). Never a recorded run.

Since Stage 23 every `CaseDir` carries its run's `ProvenanceTupleV2`, and every launch pins its
SIF from it. These helpers build that tuple from the committed `containers/SHA256SUMS`, so a
pinned command in a test carries the digest a real run would check, and a byte-pinned test reads
as the command the cluster receives.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aero.adapters._base import CaseDir, SifPin, sif_guard
from aero.provenance.four_fold import (
    ContainerRef,
    ProvenanceTupleV2,
    TermSchemes,
    read_sha256sums,
)

REPO = Path(__file__).resolve().parents[2]

#: The committed digests, by SIF basename.
SUMS = read_sha256sums(REPO)

V1_CONTAINER = TermSchemes(
    dvc_input_hash="repo-sync-state/v0", container_sif_sha256="sif-sha256-verified-at-launch/v1"
)


def run_tuple(
    sif: str = "openfoam-esi.sif",
    *,
    extra: Sequence[str] = (),
    config_hash: str = "a" * 64,
) -> ProvenanceTupleV2:
    """A tuple naming `sif` (and a roster with `extra`) at its committed digest."""
    names = sorted({sif, *extra})
    return ProvenanceTupleV2(
        git_sha="0" * 40,
        dvc_input_hash="b" * 64,
        container_sif_sha256=SUMS[sif],
        config_hash=config_hash,
        container_sif_name=sif,
        containers=tuple(ContainerRef(name=n, sha256=SUMS[n]) for n in names) if extra else (),
        dvc_inputs=None,
        schemes=V1_CONTAINER,
    )


def case_dir(
    spec: Any,
    host: Path,
    *,
    run_id: str = "fake-run",
    remote: Path | None = None,
    provenance: ProvenanceTupleV2 | None = None,
    sif: str = "openfoam-esi.sif",
    extra: Sequence[str] = (),
) -> CaseDir:
    """A `CaseDir` bound to `run_tuple(sif, extra=extra)` unless a tuple is given."""
    return CaseDir(
        run_id=run_id,
        spec=spec,
        host_path=host,
        remote_path=remote if remote is not None else host,
        provenance=provenance if provenance is not None else run_tuple(sif, extra=extra),
    )


def guard(path: str) -> str:
    """The guard prefix a command for the SIF at `path` starts with (its committed digest)."""
    return sif_guard(SifPin(path=path, sha256=SUMS[Path(path).name]))


def pin(path: str) -> SifPin:
    """A pin for the SIF at `path` at its committed digest."""
    return SifPin(path=path, sha256=SUMS[Path(path).name])


def fake_pin(path: str, digest: str = "c" * 64) -> SifPin:
    """A pin for a SIF that is never launched (render-only tests)."""
    return SifPin(path=path, sha256=digest)


def real_sif(directory: Path, name: str, content: bytes = b"not really a SIF\n") -> SifPin:
    """Write a stand-in SIF and pin it at its true digest, so the guard passes on this host."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    return SifPin(path=str(path), sha256=hashlib.sha256(content).hexdigest())
