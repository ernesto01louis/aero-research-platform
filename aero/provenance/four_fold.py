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
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A 64-hex sha256 digest; git short/long SHAs are 40 hex, optionally `-dirty`.
_HASH_RE = r"^[0-9a-f]{64}$"
_GIT_SHA_RE = r"^[0-9a-f]{40}(-dirty)?$"
_SIF_NAME_RE = r"^[A-Za-z0-9._-]+\.sif$"


class ProvenanceError(RuntimeError):
    """A component of the four-fold tuple could not be computed.

    Raised loud and caught once, at the CLI boundary — never swallowed with a
    default. A missing provenance component means the run cannot be cited, so
    it must not run. See `.claude/rules/fail-loud-pydantic.md`.
    """


class ContainerRef(BaseModel):
    """One container that took part in a run: its SIF basename and its digest."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    name: str = Field(
        ...,
        pattern=_SIF_NAME_RE,
        description="SIF basename as recorded in containers/SHA256SUMS.",
    )
    sha256: str = Field(..., pattern=_HASH_RE, description="SHA256 of that SIF.")


class ProvenanceTuple(BaseModel):
    """The four-fold provenance contract for a single run.

    Strict and frozen: every field is validated against its hash shape on
    construction, so a malformed component fails here rather than landing as a
    silently-wrong MLflow tag.

    Stage 20 (ADR-038) added the optional ``containers`` roster for genuinely
    **multi-container** runs. A partitioned FSI coupling runs OpenFOAM out of
    ``precice-fsi.sif`` and CalculiX out of ``calculix-precice.sif``, so a single
    ``container_sif_sha256`` cannot describe what ran. The field is added rather
    than repurposed: ``container_sif_sha256`` keeps its exact meaning (the
    container of record), so no existing consumer changes behaviour and no
    historical run's tag becomes irreproducible. ``containers`` is empty for
    every single-container run, which is every run before Stage 20 — including
    persisted bundle JSON, which lacks the key and parses via the default.
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
    containers: tuple[ContainerRef, ...] = Field(
        default=(),
        description=(
            "Every container that took part, name-sorted — EMPTY for a single-container "
            "run. Non-empty only when a run genuinely spans more than one SIF, in which "
            "case it must contain the container of record."
        ),
    )

    @model_validator(mode="after")
    def _container_roster_is_complete(self) -> ProvenanceTuple:
        """A non-empty roster must describe a real multi-container run, completely.

        Three ways the roster could lie, all refused here rather than at read time:
        a one-entry roster (a single-container run wearing multi-container clothes),
        duplicate or unsorted names (so the recorded order is canonical and two runs
        of the same set compare equal), and a roster that omits the container of
        record (the tuple would then describe less than what actually ran).
        """
        if not self.containers:
            return self
        names = [c.name for c in self.containers]
        if len(names) < 2:
            raise ValueError(
                "ProvenanceTuple.containers describes a MULTI-container run and needs at "
                "least two entries; leave it empty for a single-container run, whose "
                "container_sif_sha256 already says everything there is to say"
            )
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate container names in the roster: {names}")
        if names != sorted(names):
            raise ValueError(
                f"containers must be name-sorted so the roster is canonical, got {names}"
            )
        if self.container_sif_sha256 not in {c.sha256 for c in self.containers}:
            raise ValueError(
                "container_sif_sha256 is not among the roster's digests — the container "
                "of record must be one of the containers that actually ran"
            )
        return self

    @property
    def multi_container(self) -> bool:
        """True iff this run spanned more than one SIF."""
        return bool(self.containers)

    def container_set_tag(self) -> str:
        """The roster as one canonical, parseable line: ``name=sha,name=sha``.

        Both the MLflow tag value and the Postgres mirror column carry exactly this
        string, so the mirror stays byte-comparable with the tag — which is what the
        provenance-completeness check compares.
        """
        return ",".join(f"{c.name}={c.sha256}" for c in self.containers)

    def as_mlflow_tags(self) -> dict[str, str]:
        """The provenance tags logged on every run.

        The four canonical keys are always present and keep their exact shape, so
        the completeness check and every existing dashboard are unaffected. A
        multi-container run adds a fifth key naming the full roster; a
        single-container run does not, so its tag set is byte-identical to what it
        was before Stage 20.
        """
        tags = {
            "git_sha": self.git_sha,
            "dvc_input_hash": self.dvc_input_hash,
            "container_sif_sha256": self.container_sif_sha256,
            "config_hash": self.config_hash,
        }
        if self.containers:
            tags["container_sif_set"] = self.container_set_tag()
        return tags


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


def container_roster(
    repo_root: Path,
    *,
    container_of_record: Path | str,
    extra_container_sifs: Sequence[Path | str],
) -> tuple[ContainerRef, ...]:
    """Resolve every participating SIF's digest into a canonical, name-sorted roster.

    Returns an empty roster when there are no extras — a single-container run says
    everything it needs to in ``container_sif_sha256`` alone, and manufacturing a
    one-entry roster for it would make every pre-Stage-20 run's record non-uniform
    for no gain.

    Every name goes through `container_sif_sha256`, so an unrecorded SIF fails loud
    here exactly as the container of record always has.
    """
    if not extra_container_sifs:
        return ()
    names = [Path(container_of_record).name, *(Path(s).name for s in extra_container_sifs)]
    if len(set(names)) != len(names):
        raise ProvenanceError(
            f"the same SIF is listed more than once for this run: {names}. Pass each "
            "participating container exactly once; a repeated name would silently "
            "collapse in the roster and understate what ran."
        )
    return tuple(
        ContainerRef(name=name, sha256=container_sif_sha256(repo_root, name))
        for name in sorted(names)
    )


def compute_provenance(
    *,
    repo_root: Path,
    container_sif: Path | str,
    resolved_config: Mapping[str, Any],
    allow_dirty: bool = False,
    extra_container_sifs: Sequence[Path | str] = (),
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

    ``extra_container_sifs`` (Stage 20, ADR-038) names the OTHER containers a
    multi-container run used, e.g. the CalculiX solid participant alongside the
    OpenFOAM fluid one. Omitting it yields exactly the tuple this function has
    always returned.
    """
    return ProvenanceTuple(
        git_sha=git_sha(repo_root, allow_dirty=allow_dirty),
        dvc_input_hash=dvc_input_hash(repo_root),
        container_sif_sha256=container_sif_sha256(repo_root, container_sif),
        config_hash=config_hash(resolved_config),
        containers=container_roster(
            repo_root,
            container_of_record=container_sif,
            extra_container_sifs=extra_container_sifs,
        ),
    )
