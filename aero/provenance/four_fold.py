"""The four-fold provenance contract.

Every CFD or training run the platform produces is identified by a four-tuple
that uniquely maps the run back to the code, data, container, and config state
that produced it:

1. ``git_sha``              — `git rev-parse HEAD` of the repo at submission.
2. ``dvc_input_hash``       — sha256 over the `dvc status -c` of DVC-tracked inputs.
3. ``container_sif_sha256`` — SHA256 of the Apptainer SIF that ran the job.
4. ``config_hash``          — sha256 of the resolved config as canonical JSON.

Since Stage 23 (ADR-052, ADR-053) `compute_provenance` returns a `ProvenanceTupleV2`, which names
the semantics of each term in its required `schemes`. `ProvenanceTuple` is the legacy type: it is
unchanged, byte for byte, because committed result crates and `data/vv` records embed it, and it is
the only tuple that crate format v1 and the payload models accept.

This module is part of the `aero/` core: it imports stdlib + pydantic only.
The resolved config is passed in as a plain dict (the CLI calls
`OmegaConf.to_container(cfg, resolve=True)` at the Hydra->pydantic boundary),
so no heavy dependency is needed here. See ADR-004.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator

# A 64-hex sha256 digest; git short/long SHAs are 40 hex, optionally `-dirty`.
_HASH_RE = r"^[0-9a-f]{64}$"
_GIT_SHA_RE = r"^[0-9a-f]{40}(-dirty)?$"
_SIF_NAME_RE = r"^[A-Za-z0-9._-]+\.sif$"
# A repo-relative POSIX path: no leading slash, no backslash, no empty segment (the `.` and `..`
# segments are refused by DeclaredInput's validator; the pattern engine has no look-ahead).
_REPO_PATH_RE = r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$"

# The per-term schemes (ADR-052 D4). The names are frozen: a change to any computation mints a new
# name, never a new meaning for an old one.
DvcInputHashScheme = Literal["repo-sync-state/v0", "declared-dvc-pointers-md5/v1"]
ContainerDigestScheme = Literal["sha256sums-lookup/v0", "sif-sha256-verified-at-launch/v1"]
DVC_SYNC_STATE_V0: DvcInputHashScheme = "repo-sync-state/v0"
DVC_DECLARED_POINTERS_V1: DvcInputHashScheme = "declared-dvc-pointers-md5/v1"
SIF_SHA256SUMS_LOOKUP_V0: ContainerDigestScheme = "sha256sums-lookup/v0"
SIF_VERIFIED_AT_LAUNCH_V1: ContainerDigestScheme = "sif-sha256-verified-at-launch/v1"

#: The domain separator of the ADR-052 preimage. Every legacy preimage is a JSON object and begins
#: with `{`, so no new value can equal an old one (short of a sha256 collision).
DVC_INPUTS_PREFIX = b"aero.dvc-inputs/v1\n"

#: MLflow refuses longer tag values; a longer `dvc_inputs` is refused here, never truncated.
MLFLOW_TAG_VALUE_LIMIT = 8000


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


def _check_roster(containers: tuple[ContainerRef, ...], container_sif_sha256: str) -> None:
    """The roster rules shared by the legacy and the typed tuple (ADR-038)."""
    if not containers:
        return
    names = [c.name for c in containers]
    if len(names) < 2:
        raise ValueError(
            "ProvenanceTuple.containers describes a MULTI-container run and needs at "
            "least two entries; leave it empty for a single-container run, whose "
            "container_sif_sha256 already says everything there is to say"
        )
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate container names in the roster: {names}")
    if names != sorted(names):
        raise ValueError(f"containers must be name-sorted so the roster is canonical, got {names}")
    if container_sif_sha256 not in {c.sha256 for c in containers}:
        raise ValueError(
            "container_sif_sha256 is not among the roster's digests — the container "
            "of record must be one of the containers that actually ran"
        )


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
        _check_roster(self.containers, self.container_sif_sha256)
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


_STRICT_FROZEN = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_default=True,
)


class TermSchemes(BaseModel):
    """Which definition produced each non-trivial term of a tuple (ADR-052 D4).

    `git_sha` and `config_hash` have one meaning since Stage 04 and carry no scheme.
    """

    model_config = _STRICT_FROZEN

    dvc_input_hash: DvcInputHashScheme
    container_sif_sha256: ContainerDigestScheme


class DeclaredInput(BaseModel):
    """One declared DVC-tracked input: the content address its git-tracked pointer records.

    `path` is the output's repo-relative POSIX path, never the pointer's own `outs[].path` (which
    is relative to the pointer's directory) nor the `.dvc` path (ADR-052 D2).
    """

    model_config = _STRICT_FROZEN

    hash: Literal["md5"] = Field(..., description="DVC-3 plain-byte md5; md5-dos2unix is refused.")
    md5: str = Field(..., pattern=r"^[0-9a-f]{32}$", description="The pointer's `outs[].md5`.")
    path: str = Field(..., pattern=_REPO_PATH_RE, description="Repo-relative POSIX output path.")
    size: int = Field(..., ge=0, description="The pointer's `outs[].size`, in bytes.")

    @model_validator(mode="after")
    def _path_stays_in_the_repository(self) -> DeclaredInput:
        if any(part in {".", ".."} for part in self.path.split("/")):
            raise ValueError(f"declared input path {self.path!r} has a '.' or '..' segment")
        return self


def canonical_dvc_inputs(inputs: Sequence[DeclaredInput]) -> bytes:
    """The canonical JSON `{"inputs": [...]}` of a declared set, sorted by path (ADR-052 D2).

    The same convention as `config_hash` (sorted keys, no whitespace), ASCII only. A path that
    appears twice is refused: it would make two different declarations hash alike.
    """
    entries = sorted((i.model_dump(mode="json") for i in inputs), key=lambda e: e["path"])
    paths = [e["path"] for e in entries]
    if len(set(paths)) != len(paths):
        raise ProvenanceError(f"a declared DVC input is listed more than once: {paths}")
    return json.dumps(
        {"inputs": entries}, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def dvc_inputs_digest(inputs: Sequence[DeclaredInput]) -> str:
    """`dvc_input_hash` under `declared-dvc-pointers-md5/v1`: sha256(prefix + canonical JSON)."""
    return hashlib.sha256(DVC_INPUTS_PREFIX + canonical_dvc_inputs(inputs)).hexdigest()


#: The canonical empty set, `1ef5b7d9…` (ADR-052's golden value; never sha256("{}")).
EMPTY_DVC_INPUTS_DIGEST = dvc_inputs_digest(())


class ProvenanceTupleV2(BaseModel):
    """The four-fold tuple that names the semantics of each term (ADR-052 D4, ADR-053).

    Deliberately NOT a subclass of `ProvenanceTuple`: pydantic accepts a subclass in a field
    typed with its parent and silently drops the extra fields on serialisation, which would strip
    the schemes off a record. An unrelated class is refused there instead, so a v2 tuple can never
    land in a format-v1 crate or a legacy payload model.
    """

    model_config = _STRICT_FROZEN

    git_sha: str = Field(
        ...,
        pattern=_GIT_SHA_RE,
        description="`git rev-parse HEAD`; a `-dirty` suffix marks an --allow-dirty run.",
    )
    dvc_input_hash: str = Field(..., pattern=_HASH_RE, description="See `schemes.dvc_input_hash`.")
    container_sif_sha256: str = Field(
        ..., pattern=_HASH_RE, description="See `schemes.container_sif_sha256`."
    )
    config_hash: str = Field(
        ..., pattern=_HASH_RE, description="sha256 of the resolved config as canonical JSON."
    )
    container_sif_name: str = Field(
        ..., pattern=_SIF_NAME_RE, description="Basename of the container of record."
    )
    containers: tuple[ContainerRef, ...] = Field(
        default=(),
        description="The multi-container roster (ADR-038); empty for a single-container run.",
    )
    dvc_inputs: tuple[DeclaredInput, ...] | None = Field(
        ...,
        description=(
            "The declared inputs the DVC term digests: required (possibly empty) under "
            "declared-dvc-pointers-md5/v1, None under repo-sync-state/v0, which uses no declaration."
        ),
    )
    schemes: TermSchemes

    @model_validator(mode="after")
    def _terms_match_their_schemes(self) -> ProvenanceTupleV2:
        _check_roster(self.containers, self.container_sif_sha256)
        if self.containers:
            named = {c.name: c.sha256 for c in self.containers}
            if named.get(self.container_sif_name) != self.container_sif_sha256:
                raise ValueError(
                    f"container of record {self.container_sif_name!r} is not the roster entry "
                    "carrying container_sif_sha256"
                )
        if self.schemes.dvc_input_hash == DVC_DECLARED_POINTERS_V1:
            if self.dvc_inputs is None:
                raise ValueError(f"{DVC_DECLARED_POINTERS_V1} needs dvc_inputs (possibly empty)")
            if self.dvc_input_hash != dvc_inputs_digest(self.dvc_inputs):
                raise ValueError(
                    "dvc_input_hash is not the ADR-052 digest of dvc_inputs — the hashed set and "
                    "the declared set must be one object"
                )
        elif self.dvc_inputs is not None:
            raise ValueError(
                f"{self.schemes.dvc_input_hash} uses no declaration; dvc_inputs must be None so "
                "the run never reads as 'declared no inputs'"
            )
        return self

    @property
    def multi_container(self) -> bool:
        """True iff this run spanned more than one SIF."""
        return bool(self.containers)

    def container_set_tag(self) -> str:
        """The roster as one canonical line, ``name=sha,name=sha`` (as `ProvenanceTuple`)."""
        return ",".join(f"{c.name}={c.sha256}" for c in self.containers)

    def dvc_inputs_tag(self) -> str | None:
        """The canonical inputs JSON logged as the `dvc_inputs` tag; None under the v0 scheme."""
        if self.dvc_inputs is None:
            return None
        tag = canonical_dvc_inputs(self.dvc_inputs).decode("ascii")
        if len(tag) > MLFLOW_TAG_VALUE_LIMIT:
            raise ProvenanceError(
                f"the dvc_inputs tag is {len(tag)} characters, above MLflow's "
                f"{MLFLOW_TAG_VALUE_LIMIT}; refusing rather than truncating the record"
            )
        return tag

    def as_mlflow_tags(self) -> dict[str, str]:
        """The provenance tags of a run: the four keys in their Stage-04 shapes, plus the schemes.

        Every MLflow path takes its tags from here, including the surrogate paths that bypass
        `start_provenance_run`, so no run can be logged without saying which semantics it has.
        """
        tags = {
            "git_sha": self.git_sha,
            "dvc_input_hash": self.dvc_input_hash,
            "container_sif_sha256": self.container_sif_sha256,
            "config_hash": self.config_hash,
            "container_sif_name": self.container_sif_name,
            "dvc_input_hash_scheme": self.schemes.dvc_input_hash,
            "container_sif_sha256_scheme": self.schemes.container_sif_sha256,
        }
        if self.containers:
            tags["container_sif_set"] = self.container_set_tag()
        inputs_tag = self.dvc_inputs_tag()
        if inputs_tag is not None:
            tags["dvc_inputs"] = inputs_tag
        return tags


#: The scheme tags a typed run always carries, besides the four canonical keys.
SCHEME_TAG_KEYS = ("container_sif_name", "dvc_input_hash_scheme", "container_sif_sha256_scheme")


def _tuple_kind(value: Any) -> str | None:
    if isinstance(value, ProvenanceTupleV2):
        return "v2"
    if isinstance(value, ProvenanceTuple):
        return "legacy"
    if isinstance(value, Mapping):
        return "v2" if "schemes" in value else "legacy"
    return None


#: A tuple of either kind, for in-memory consumers and records that predate Stage 23. Persisted
#: legacy records (no `schemes` key) reload as `ProvenanceTuple`; a v2 tuple keeps its schemes.
AnyProvenanceTuple = Annotated[
    Annotated[ProvenanceTupleV2, Tag("v2")] | Annotated[ProvenanceTuple, Tag("legacy")],
    Discriminator(_tuple_kind),
]


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
    """The `repo-sync-state/v0` DVC term: sha256 of the repo-wide `dvc status -c` (ADR-004).

    It compares the repository's whole DVC cache against the configured remote, on whichever
    machine computes it, and hashes the JSON canonically. It takes no case: it is a sync-state
    digest, not a content address of any input (ADR-052 replaces it). `{}` (sha256 `44136fa3…`)
    is an empty status. Since Stage 23 an empty stdout is refused instead of being read as `{}`:
    with `--json`, dvc always prints the status, so an empty stdout is not a status at all.
    """
    proc = _run([_dvc_executable(), "status", "-c", "--json"], cwd=repo_root)
    if proc.returncode != 0:
        raise ProvenanceError(
            f"`dvc status -c` failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    if not proc.stdout.strip():
        raise ProvenanceError("`dvc status -c --json` printed nothing — no status to hash")
    try:
        status = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"could not parse `dvc status -c` output: {exc}") from exc
    canonical = json.dumps(status, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_SHA256SUMS = Path("containers") / "SHA256SUMS"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def read_sha256sums(repo_root: Path) -> dict[str, str]:
    """Parse `containers/SHA256SUMS` strictly: SIF basename -> digest (Stage 23, ADR-053).

    Blank lines and `#` comment lines are skipped. Every other line must be `<64-hex> <name>`, and
    a name may appear once. The lookup used to take the first two-token line that named the SIF,
    so a two-token comment such as `# containers/SHA256SUMS` would have returned `#` as a digest,
    and a second entry for a rebuilt SIF would have been silently ignored.
    """
    sums = repo_root / _SHA256SUMS
    if not sums.is_file():
        raise ProvenanceError(f"containers/SHA256SUMS not found at {sums}")
    digests: dict[str, str] = {}
    for number, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) != 2 or not _HEX64_RE.match(parts[0]):
            raise ProvenanceError(
                f"{sums}:{number}: not a `<sha256> <name>` entry: {stripped[:80]!r}"
            )
        digest, name = parts
        if name in digests:
            raise ProvenanceError(
                f"{sums}:{number}: {name!r} is listed twice; a rebuilt SIF needs a new name"
            )
        digests[name] = digest
    return digests


def sha256sums_at_head(repo_root: Path) -> None:
    """Refuse a `containers/SHA256SUMS` that differs from `HEAD`'s, even under `--allow-dirty`.

    The digest a run records must be one a committed `SHA256SUMS` contains, or the record names
    a container no commit describes (ADR-053, as ADR-052 D1 requires of declared pointers).
    """
    try:
        head = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"HEAD:{_SHA256SUMS.as_posix()}"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProvenanceError("`git` not found — cannot compute provenance") from exc
    if head.returncode != 0:
        raise ProvenanceError(
            f"containers/SHA256SUMS is not committed at HEAD: {head.stderr.decode().strip()}"
        )
    sums = repo_root / _SHA256SUMS
    if not sums.is_file() or sums.read_bytes() != head.stdout:
        raise ProvenanceError(
            "containers/SHA256SUMS differs from HEAD's; commit it first — a recorded container "
            "digest must be in a committed SHA256SUMS, even for an --allow-dirty run (ADR-053)"
        )


def container_sif_sha256(repo_root: Path, container_sif: Path | str) -> str:
    """Look up the SIF's SHA256 in `containers/SHA256SUMS` by basename.

    No `"unknown"` fallback — the Stage 03 shortcut is retired. A SIF without a
    recorded digest is an unprovenanced container and must fail loud. Since Stage 23 the
    lookup goes through the strict parser (`read_sha256sums`).
    """
    name = Path(container_sif).name
    digest = read_sha256sums(repo_root).get(name)
    if digest is None:
        raise ProvenanceError(f"no SHA256 entry for '{name}' in {repo_root / _SHA256SUMS}")
    return digest


def canonical_config_bytes(resolved_config: Mapping[str, Any]) -> bytes:
    """The exact bytes `config_hash` digests: canonical JSON, sorted keys, no whitespace.

    Exposed (Stage 21, ADR-047) so the result crate can carry the *preimage* of a run's
    `config_hash` -- `sha256(canonical_config_bytes(cfg)) == config_hash(cfg)` by construction --
    instead of a CaseSpec re-derived from today's models, which no longer hashes to what old
    runs recorded (CaseSpec has gained fields since).
    """
    try:
        canonical = json.dumps(dict(resolved_config), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"resolved config is not JSON-serializable: {exc}") from exc
    return canonical.encode("utf-8")


def config_hash(resolved_config: Mapping[str, Any]) -> str:
    """sha256 of the resolved config serialized as canonical JSON.

    `resolved_config` is the output of `OmegaConf.to_container(cfg,
    resolve=True)` — a plain dict with every interpolation resolved. Canonical
    JSON (sorted keys, no whitespace) makes the hash reproducible across
    machines. See `.claude/rules/fail-loud-pydantic.md`.
    """
    return hashlib.sha256(canonical_config_bytes(resolved_config)).hexdigest()


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


def refuse_unported_driver(driver: str) -> NoReturn:
    """Stop a historical stage driver before it records anything (Stage 23, ledgered).

    The Stage 9-20 campaign drivers were written against the legacy tuple. Since ADR-052/053 a
    recorded run needs a declared input set and a launch-checked container, which they do not
    provide, and a run recorded halfway between the two semantics is worse than none. Each one
    calls this first in `main()`; port it (declare its inputs, take the tuple from
    `compute_provenance`) before running it again.
    """
    import sys

    print(
        f"{driver}: refused. This historical stage driver predates the Stage-23 provenance "
        "semantics (ADR-052, ADR-053) and has not been ported; it would record runs whose terms "
        "it cannot state. Port it first (docs/operator/deferred-work-ledger.md, Stage 23).",
        file=sys.stderr,
    )
    raise SystemExit(4)


def compute_provenance(
    *,
    repo_root: Path,
    container_sif: Path | str,
    resolved_config: Mapping[str, Any],
    allow_dirty: bool = False,
    extra_container_sifs: Sequence[Path | str] = (),
) -> ProvenanceTupleV2:
    """Compute the full four-fold provenance tuple, or raise ProvenanceError.

    Since Stage 23 the result is a `ProvenanceTupleV2` that names each term's scheme. The DVC
    term is still `repo-sync-state/v0` (ADR-052 moves it to v1). The container term is
    `sif-sha256-verified-at-launch/v1` (ADR-053): the digest is the committed `SHA256SUMS` entry
    (`containers/SHA256SUMS` must equal `HEAD`'s, even under `allow_dirty`), and every launch of
    the run is guarded against it on the solve host. A run that logs this tuple without a guarded
    launch is refused by the logger that holds it (`assert_launches_guarded`).

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
    sha256sums_at_head(repo_root)
    return ProvenanceTupleV2(
        git_sha=git_sha(repo_root, allow_dirty=allow_dirty),
        dvc_input_hash=dvc_input_hash(repo_root),
        container_sif_sha256=container_sif_sha256(repo_root, container_sif),
        config_hash=config_hash(resolved_config),
        container_sif_name=Path(container_sif).name,
        containers=container_roster(
            repo_root,
            container_of_record=container_sif,
            extra_container_sifs=extra_container_sifs,
        ),
        dvc_inputs=None,
        schemes=TermSchemes(
            dvc_input_hash=DVC_SYNC_STATE_V0, container_sif_sha256=SIF_VERIFIED_AT_LAUNCH_V1
        ),
    )
