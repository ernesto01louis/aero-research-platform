"""The four-fold provenance contract.

Every CFD or training run the platform produces is identified by a four-tuple
that uniquely maps the run back to the code, data, container, and config state
that produced it:

1. ``git_sha``              — `git rev-parse HEAD` of the repo at submission.
2. ``dvc_input_hash``       — sha256 over the `dvc status -c` of DVC-tracked inputs.
3. ``container_sif_sha256`` — SHA256 of the Apptainer SIF that ran the job.
4. ``config_hash``          — sha256 of the resolved config as canonical JSON.

This module is part of the `aero/` core: it imports stdlib + pydantic only.
The resolved config is passed in as a plain dict (the CLI calls
`OmegaConf.to_container(cfg, resolve=True)` at the Hydra->pydantic boundary),
so no heavy dependency is needed here. See ADR-004.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# A 64-hex sha256 digest; git short/long SHAs are 40 hex, optionally `-dirty`.
_HASH_RE = r"^[0-9a-f]{64}$"
_GIT_SHA_RE = r"^[0-9a-f]{40}(-dirty)?$"


class ProvenanceError(RuntimeError):
    """A component of the four-fold tuple could not be computed.

    Raised loud and caught once, at the CLI boundary — never swallowed with a
    default. A missing provenance component means the run cannot be cited, so
    it must not run. See `.claude/rules/fail-loud-pydantic.md`.
    """


class ProvenanceTuple(BaseModel):
    """The four-fold provenance contract for a single run.

    Strict and frozen: every field is validated against its hash shape on
    construction, so a malformed component fails here rather than landing as a
    silently-wrong MLflow tag.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    git_sha: str = Field(
        ...,
        pattern=_GIT_SHA_RE,
        description="`git rev-parse HEAD`; a `-dirty` suffix marks an --allow-dirty run.",
    )
    dvc_input_hash: str = Field(
        ..., pattern=_HASH_RE, description="sha256 over `dvc status -c` of tracked inputs."
    )
    container_sif_sha256: str = Field(
        ...,
        pattern=_HASH_RE,
        description="SHA256 of the Apptainer SIF, from containers/SHA256SUMS.",
    )
    config_hash: str = Field(
        ..., pattern=_HASH_RE, description="sha256 of the resolved config as canonical JSON."
    )

    def as_mlflow_tags(self) -> dict[str, str]:
        """The four-tuple as the MLflow tag dict logged on every run."""
        return {
            "git_sha": self.git_sha,
            "dvc_input_hash": self.dvc_input_hash,
            "container_sif_sha256": self.container_sif_sha256,
            "config_hash": self.config_hash,
        }


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, raising ProvenanceError if the binary is absent."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise ProvenanceError(f"`{cmd[0]}` not found — cannot compute provenance") from exc


def _dvc_executable() -> str:
    """Locate the `dvc` console script.

    `dvc` ships with the `aero[provenance]` extra, installed into the same
    environment as the running interpreter — so it sits next to
    `sys.executable`. Resolving it there (rather than a bare `dvc`) makes
    provenance work without the venv being on `PATH`.
    """
    candidate = Path(sys.executable).with_name("dvc")
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("dvc")
    if found:
        return found
    raise ProvenanceError("`dvc` not found — install the aero[provenance] extra")


def git_sha(repo_root: Path, *, allow_dirty: bool = False) -> str:
    """Resolve `git rev-parse HEAD`; fail loud on a dirty tree unless allowed.

    A dirty working tree means the SHA does not describe what actually ran.
    Default policy is fail-loud; `--allow-dirty` opts into an explicit
    exploration run, annotating the SHA with a `-dirty` suffix. See ADR-004.
    """
    head = _run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], cwd=repo_root)
    if head.returncode != 0:
        raise ProvenanceError(f"`git rev-parse HEAD` failed: {head.stderr.strip()}")
    sha = head.stdout.strip()

    status = _run(["git", "-C", str(repo_root), "status", "--porcelain"], cwd=repo_root)
    if status.returncode != 0:
        raise ProvenanceError(f"`git status` failed: {status.stderr.strip()}")
    dirty = bool(status.stdout.strip())
    if dirty and not allow_dirty:
        raise ProvenanceError(
            "working tree is dirty — commit, stash, or pass --allow-dirty "
            "to log an exploration run with a `-dirty` SHA tag"
        )
    return f"{sha}-dirty" if dirty else sha


def dvc_input_hash(repo_root: Path) -> str:
    """sha256 over the `dvc status -c` of all DVC-tracked inputs.

    `dvc status -c` compares tracked inputs against the configured remote; its
    JSON output is hashed canonically. An empty status (`{}`) — every input in
    sync with the remote — yields a stable constant, which is correct: it means
    the inputs are exactly the published versions. See ADR-004.
    """
    proc = _run([_dvc_executable(), "status", "-c", "--json"], cwd=repo_root)
    if proc.returncode != 0:
        raise ProvenanceError(
            f"`dvc status -c` failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    try:
        status = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"could not parse `dvc status -c` output: {exc}") from exc
    canonical = json.dumps(status, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def container_sif_sha256(repo_root: Path, container_sif: Path | str) -> str:
    """Look up the SIF's SHA256 in `containers/SHA256SUMS` by basename.

    No `"unknown"` fallback — the Stage 03 shortcut is retired. A SIF without a
    recorded digest is an unprovenanced container and must fail loud.
    """
    name = Path(container_sif).name
    sums = repo_root / "containers" / "SHA256SUMS"
    if not sums.is_file():
        raise ProvenanceError(f"containers/SHA256SUMS not found at {sums}")
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == name:
            return parts[0]
    raise ProvenanceError(f"no SHA256 entry for '{name}' in {sums}")


def config_hash(resolved_config: Mapping[str, Any]) -> str:
    """sha256 of the resolved config serialized as canonical JSON.

    `resolved_config` is the output of `OmegaConf.to_container(cfg,
    resolve=True)` — a plain dict with every interpolation resolved. Canonical
    JSON (sorted keys, no whitespace) makes the hash reproducible across
    machines. See `.claude/rules/fail-loud-pydantic.md`.
    """
    try:
        canonical = json.dumps(dict(resolved_config), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"resolved config is not JSON-serializable: {exc}") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_provenance(
    *,
    repo_root: Path,
    container_sif: Path | str,
    resolved_config: Mapping[str, Any],
    allow_dirty: bool = False,
) -> ProvenanceTuple:
    """Compute the full four-fold provenance tuple, or raise ProvenanceError.

    Called by the CLI *before* the MLflow run is started, so a provenance
    failure aborts before any partially-tagged run exists.

    Note — the signature deviates from the Stage 04 prompt's
    ``compute_provenance(case_dir, container_sif, config_path)``:
    `git`/`dvc` operate on the repo (case dirs live on NFS outside it), so
    `repo_root` replaces `case_dir`; and `config_hash` needs the *resolved*
    config object, not a path, so `resolved_config` replaces `config_path`
    (re-composing from a path risks drift). Recorded in ADR-004.
    """
    return ProvenanceTuple(
        git_sha=git_sha(repo_root, allow_dirty=allow_dirty),
        dvc_input_hash=dvc_input_hash(repo_root),
        container_sif_sha256=container_sif_sha256(repo_root, container_sif),
        config_hash=config_hash(resolved_config),
    )
