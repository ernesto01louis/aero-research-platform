"""Coupled-case specification and materialization of the pinned upstream tutorial.

The platform does not re-author the Turek-Hron FSI3 case. Running the *supported*
upstream tutorial verbatim is what makes the coupling-correctness claim externally
anchored rather than self-referential (ADR-016), so this module's job is to lay that
tutorial down byte-for-byte, prove it is the pinned bytes, and record every deviation
it deliberately makes.

Exactly two deviations are permitted, both declared and both recorded in
``aero-manifest.json`` next to the case:

1. ``<max-time>`` shortened to fit the pre-declared wall-clock budget — enforced
   structurally by :func:`aero.adapters.precice.config.rewrite_max_time`.
2. selecting one of the tutorial's own alternative ``blockMeshDict`` variants as the
   fluid mesh (upstream ships ``blockMeshDict``, ``_refined`` and ``_double_refined`` and
   expects you to choose).

Everything else is verified against the git-tracked per-file digest manifest. That
manifest — not the archive checksum — is the integrity contract, because GitHub codeload
tarballs are not guaranteed byte-stable over time (ADR-036 gate C5).
"""

from __future__ import annotations

import hashlib
import json
import tarfile
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.provenance.four_fold import ProvenanceTuple

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

FluidMeshDict = Literal["blockMeshDict", "blockMeshDict_refined", "blockMeshDict_double_refined"]


class CoupledCaseError(RuntimeError):
    """A coupled case could not be specified or materialized."""


class ParticipantSpec(BaseModel):
    """One preCICE participant: where it runs, what it runs, and in which container."""

    model_config = _STRICT

    name: str = Field(..., min_length=1, description="preCICE participant name (e.g. 'Fluid').")
    workdir: str = Field(
        ...,
        min_length=1,
        description="Directory relative to the coupled case root (e.g. 'fluid-openfoam').",
    )
    command: str = Field(..., min_length=1, description="Command run inside the container.")
    sif: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9._-]+\.sif$",
        description="SIF basename; must resolve in containers/SHA256SUMS.",
    )
    env: Mapping[str, str] = Field(default_factory=dict)
    writable_tmpfs: bool = False
    run_as_uid: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Drop to this uid before running the participant. OpenFOAM REFUSES to compile "
            "a codedFixedValue boundary condition as root -- dynamicCode::checkSecurity's "
            "isAdministrator() check is unconditional in v2412, and allowSystemOperations "
            "does not gate it. The tutorial's inlet is codedFixedValue, and solver SIFs "
            "must run as the LXC root, so the fluid participant would abort at t=0. "
            "Dropping privileges keeps the upstream case byte-identical, which the "
            "alternative (rewriting the inlet as exprFixedValue) would not."
        ),
    )


class TutorialPin(BaseModel):
    """The pinned upstream tutorial: commit, archive digest, and per-file manifest."""

    model_config = _STRICT

    repo: str = Field(default="precice/tutorials", min_length=1)
    branch: str = Field(default="develop", min_length=1)
    commit: str = Field(..., pattern=r"^[0-9a-f]{40}$")
    archive_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    manifest_path: Path = Field(..., description="Git-tracked per-file sha256 manifest.")

    def manifest(self) -> dict[str, str]:
        """Load the manifest as ``{relative path: sha256}``. Fail loud on malformed rows."""
        if not self.manifest_path.is_file():
            raise CoupledCaseError(f"{self.manifest_path}: pin manifest not found")
        entries: dict[str, str] = {}
        for lineno, raw in enumerate(
            self.manifest_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = raw.strip()
            if not line or line.startswith("#") or line == "sha256,path":
                continue
            digest, _, path = line.partition(",")
            if len(digest) != 64 or not path:
                raise CoupledCaseError(f"{self.manifest_path}:{lineno}: malformed row {line!r}")
            entries[path] = digest
        if not entries:
            raise CoupledCaseError(f"{self.manifest_path}: manifest is empty")
        return entries


class CoupledCaseSpec(BaseModel):
    """A partitioned FSI case. Satisfies ``SpecLike`` via ``.name``."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    pin: TutorialPin
    archive_path: Path = Field(..., description="DVC-tracked pinned tutorial archive.")
    tutorial_case: str = Field(default="turek-hron-fsi3", min_length=1)
    participants: tuple[ParticipantSpec, ...] = Field(..., min_length=2)
    container_of_record: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9._-]+\.sif$",
        description="The SIF whose digest becomes the four-tuple's container_sif_sha256.",
    )
    max_time: float = Field(..., gt=0.0, description="The one permitted config override [s].")
    fluid_mesh_dict: FluidMeshDict = "blockMeshDict"
    fluid_participant_dir: str = Field(default="fluid-openfoam", min_length=1)
    wall_clock_ceiling_s: int = Field(..., ge=60, description="Pre-declared budget ceiling.")
    analysis_discard_s: float = Field(
        ...,
        ge=0.0,
        description=(
            "Absolute solver time before which no sample may enter the analysis window. "
            "Pre-registered (ADR-036 S2), never tuned after seeing the record."
        ),
    )
    analysis_min_cycles: int = Field(
        default=4,
        ge=2,
        description="Minimum settled cycles required for a reportable measurement (S3).",
    )
    run_as_uid: int | None = Field(
        default=None,
        ge=1,
        description=(
            "uid the participants run as, and the owner the materialized case is chowned "
            "to. See ParticipantSpec.run_as_uid for why this is necessary."
        ),
    )
    gated: bool = Field(
        default=True,
        description="True for runs that bear a pre-registered verdict; see the validator.",
    )

    @model_validator(mode="after")
    def _container_of_record_is_a_participant(self) -> CoupledCaseSpec:
        """The container of record must be one the case actually runs.

        Stage 19 also refused a GATED run spanning more than one SIF, because
        ``ProvenanceTuple.container_sif_sha256`` was single-valued and a two-SIF
        gated run would have logged a digest describing only half of what ran.
        ADR-038 removed the cause rather than the symptom: the tuple now carries a
        ``containers`` roster, so a multi-container run can be gated *provided its
        provenance names every participating SIF*. That obligation is enforced by
        ``assert_provenance_describes`` at the point provenance is computed — it
        cannot live here, because a spec has no access to the digests.
        """
        sifs = {p.sif for p in self.participants}
        if self.container_of_record not in sifs:
            raise ValueError(
                f"container_of_record {self.container_of_record!r} is not used by any "
                f"participant (participants use: {', '.join(sorted(sifs))})"
            )
        return self

    @property
    def multi_container(self) -> bool:
        return len({p.sif for p in self.participants}) > 1

    @property
    def container_sifs(self) -> tuple[str, ...]:
        """Every distinct SIF this case runs, name-sorted."""
        return tuple(sorted({p.sif for p in self.participants}))

    @property
    def extra_container_sifs(self) -> tuple[str, ...]:
        """SIFs other than the container of record.

        Pass these to ``compute_provenance(extra_container_sifs=...)``; since
        ADR-038 they are resolved to real digests in the tuple's ``containers``
        roster rather than being represented only by their *names* inside
        ``config_hash``, which bound the string ``"calculix-precice.sif"`` but never
        the bytes it named.
        """
        return tuple(sorted({p.sif for p in self.participants} - {self.container_of_record}))

    def participant(self, name: str) -> ParticipantSpec:
        for candidate in self.participants:
            if candidate.name == name:
                return candidate
        known = ", ".join(p.name for p in self.participants)
        raise CoupledCaseError(f"no participant {name!r} in case {self.name!r} (have: {known})")


def assert_provenance_describes(spec: CoupledCaseSpec, provenance: ProvenanceTuple) -> None:
    """Refuse a provenance tuple that describes less than the case actually runs.

    This is the structural guarantee that replaced Stage 19's blanket refusal of
    gated multi-container runs (ADR-038). The rule is now the honest one — a run
    may span any number of SIFs, but its provenance must name **all** of them:

    * a single-SIF case must carry an EMPTY roster (``container_sif_sha256`` alone
      already says everything, and a one-entry roster would make every
      pre-Stage-20 record non-uniform for no gain);
    * a multi-SIF case must carry a roster whose names are exactly the participant
      SIFs — no more, no fewer.

    Call it immediately after ``compute_provenance`` and before anything runs, so a
    mis-described run fails before it produces numbers rather than after.
    """
    expected = set(spec.container_sifs)
    got = {ref.name for ref in provenance.containers}
    if not spec.multi_container:
        if got:
            raise CoupledCaseError(
                f"case {spec.name!r} runs the single container {spec.container_of_record!r} but "
                f"its provenance carries a roster {sorted(got)} — a single-container run must "
                "leave ProvenanceTuple.containers empty"
            )
        return
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise CoupledCaseError(
            f"case {spec.name!r} spans {len(expected)} containers "
            f"({', '.join(sorted(expected))}) but its provenance roster does not match"
            + (f"; missing {missing}" if missing else "")
            + (f"; unexpected {extra}" if extra else "")
            + ". The four-fold tuple must describe everything that ran, or the run is not "
            "reproducible from it (ADR-038)."
        )


class MaterializedFile(BaseModel):
    model_config = _STRICT

    path: str = Field(..., min_length=1, description="Relative to the materialized root.")
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class DeclaredMutation(BaseModel):
    """A deviation from the pinned upstream bytes that the campaign declares up front."""

    model_config = _STRICT

    kind: Literal["max-time", "fluid-mesh-dict"]
    path: str = Field(..., min_length=1)
    detail: str = Field(..., min_length=1)
    before_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    after_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class TutorialTree(BaseModel):
    """The materialized, digest-verified tutorial plus the declared mutations applied."""

    model_config = _STRICT

    root: Path
    case_dir: Path
    pin: TutorialPin
    files: tuple[MaterializedFile, ...] = Field(..., min_length=1)
    mutations: tuple[DeclaredMutation, ...] = ()

    def write_manifest(self, path: Path) -> None:
        """Write ``aero-manifest.json`` — the run's own record of what it laid down."""
        path.write_text(
            json.dumps(
                {
                    "pin": {
                        "repo": self.pin.repo,
                        "branch": self.pin.branch,
                        "commit": self.pin.commit,
                        "archive_sha256": self.pin.archive_sha256,
                    },
                    "case_dir": str(self.case_dir.relative_to(self.root)),
                    "files": [f.model_dump() for f in self.files],
                    "declared_mutations": [m.model_dump() for m in self.mutations],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize_tutorial(
    pin: TutorialPin, *, archive: Path, dest: Path, tutorial_case: str = "turek-hron-fsi3"
) -> TutorialTree:
    """Extract the pinned tutorial into `dest` and verify every file against the manifest.

    The relative layout is preserved exactly: ``solid.py`` opens
    ``'../precice-config.xml'`` and both ``run.sh`` scripts source ``'../../tools/log.sh'``,
    so the case directory and ``tools/`` must be siblings under one root.
    """
    if not archive.is_file():
        raise CoupledCaseError(
            f"{archive}: pinned tutorial archive not found — run `dvc pull` for "
            "data/references/fsi/turek_hron_fsi3/"
        )
    actual = _sha256(archive)
    if actual != pin.archive_sha256:
        raise CoupledCaseError(
            f"{archive}: sha256 {actual[:12]}... does not match the pinned "
            f"{pin.archive_sha256[:12]}... — refusing to run a different tutorial"
        )

    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        # filter="data" refuses absolute paths, "..", links out of the tree and device
        # nodes. The archive is ours, but extraction is the wrong place to be trusting.
        tar.extractall(dest, filter="data")

    expected = pin.manifest()
    files: list[MaterializedFile] = []
    missing: list[str] = []
    mismatched: list[str] = []
    for relative, want in sorted(expected.items()):
        path = dest / relative
        if not path.is_file():
            missing.append(relative)
            continue
        got = _sha256(path)
        if got != want:
            mismatched.append(f"{relative} ({got[:12]}... != {want[:12]}...)")
        files.append(MaterializedFile(path=relative, sha256=got))

    extra = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    unexpected = [p for p in extra if p not in expected]

    problems: list[str] = []
    if missing:
        problems.append(f"{len(missing)} file(s) missing: {', '.join(missing[:5])}")
    if mismatched:
        problems.append(f"{len(mismatched)} file(s) altered: {', '.join(mismatched[:5])}")
    if unexpected:
        problems.append(f"{len(unexpected)} unexpected file(s): {', '.join(unexpected[:5])}")
    if problems:
        raise CoupledCaseError(
            f"{dest}: the materialized tutorial does not match the pinned manifest "
            f"{pin.manifest_path} — " + "; ".join(problems)
        )

    case_dir = dest / tutorial_case
    if not case_dir.is_dir():
        raise CoupledCaseError(
            f"{case_dir}: the archive does not contain the tutorial case {tutorial_case!r}"
        )
    return TutorialTree(root=dest, case_dir=case_dir, pin=pin, files=tuple(files))


def select_fluid_mesh(
    tree: TutorialTree, *, variant: FluidMeshDict, case_dir: Path
) -> TutorialTree:
    """Install one of the tutorial's own ``blockMeshDict`` variants as the fluid mesh.

    ``blockMesh`` reads ``system/blockMeshDict``; upstream ships two alternatives beside
    it and expects the user to choose. Selecting one is a DECLARED mutation (cost, not
    quality — every variant is upstream-authored for this same benchmark), recorded with
    both digests so the bundle shows exactly which mesh produced the numbers.
    """
    system = case_dir / "fluid-openfoam" / "system"
    target = system / "blockMeshDict"
    source = system / variant
    if not source.is_file():
        raise CoupledCaseError(f"{source}: mesh variant {variant!r} is not in the pinned tutorial")
    before = _sha256(target)
    if variant == "blockMeshDict":
        return tree  # upstream default; nothing to install, nothing to declare
    after = _sha256(source)
    target.write_bytes(source.read_bytes())
    return tree.model_copy(
        update={
            "mutations": (
                *tree.mutations,
                DeclaredMutation(
                    kind="fluid-mesh-dict",
                    path=str(target.relative_to(tree.root)),
                    detail=(
                        f"installed the upstream variant {variant!r} as system/blockMeshDict "
                        "(a declared cost/resolution choice among upstream-authored meshes)"
                    ),
                    before_sha256=before,
                    after_sha256=after,
                ),
            )
        }
    )


def record_max_time_mutation(
    tree: TutorialTree, *, path: Path, before_sha256: str, after_sha256: str, max_time: float
) -> TutorialTree:
    """Record the ``<max-time>`` rewrite in the tree's declared-mutation ledger."""
    return tree.model_copy(
        update={
            "mutations": (
                *tree.mutations,
                DeclaredMutation(
                    kind="max-time",
                    path=str(path.relative_to(tree.root)),
                    detail=(
                        f"shortened <max-time> to {max_time:g} s to fit the pre-declared "
                        "wall-clock budget; verified structurally that nothing else changed"
                    ),
                    before_sha256=before_sha256,
                    after_sha256=after_sha256,
                ),
            )
        }
    )
