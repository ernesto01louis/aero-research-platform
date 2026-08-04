"""Coupled-case specification and materialization of a coupled case's bytes.

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

Stage 20 adds a SECOND source of bytes. The Heathcote-Gursul flexible-foil case has no
upstream equivalent, so its bytes are *authored* rather than materialized from a pin, and
the integrity contract inverts: instead of "these bytes are the pinned bytes", it becomes
"these bytes are exactly what this spec renders, and re-reading them reproduces the spec".
The two are joined by :class:`CoupledCaseSpec.source`, a discriminated union — one field,
so a tree can never be ambiguous about which contract it is under (ADR-037).
"""

from __future__ import annotations

import hashlib
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

#: The directory, under a run's host path, that holds the coupled case's bytes. It is named
#: "tutorial" for history: Stage 19 laid the upstream tutorial down there, the name appears in
#: both drivers' paths and in the pinned launcher bind string, and renaming it would move
#: `case_dir` and every declared mutation's `path` inside `aero-manifest.json` — i.e. break the
#: goldens that prove the Stage-19 bytes never moved. The name is now source-agnostic.
CASE_ROOT_DIRNAME = "tutorial"


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


class TutorialSource(BaseModel):
    """Bytes that come from a pinned upstream tutorial archive.

    The integrity contract is "these bytes ARE the pinned bytes": every file is verified
    against the git-tracked per-file digest manifest, and only the two declared mutations
    (``max-time``, ``fluid-mesh-dict``) may deviate from it.
    """

    model_config = _STRICT

    kind: Literal["tutorial"] = "tutorial"
    pin: TutorialPin
    archive_path: Path = Field(..., description="DVC-tracked pinned tutorial archive.")
    tutorial_case: str = Field(
        default="turek-hron-fsi3",
        min_length=1,
        description="The case sub-directory INSIDE the tutorial root (not the root itself).",
    )
    fluid_mesh_dict: FluidMeshDict = "blockMeshDict"
    fluid_participant_dir: str = Field(default="fluid-openfoam", min_length=1)


class AuthoredSource(BaseModel):
    """Bytes this platform renders itself, for a case with no upstream equivalent.

    The integrity contract inverts. There is no pin to compare against, so the claim
    becomes "these bytes are exactly what this spec renders, and re-reading them
    reproduces the spec" — which is why every authored writer ships with a re-reader and
    why ``renderer_version`` and ``template_sha256`` are part of the record (ADR-037).
    """

    model_config = _STRICT

    kind: Literal["authored"] = "authored"
    case_dir_name: str = Field(
        ...,
        min_length=1,
        description="The case sub-directory INSIDE the case root, e.g. 'hg2007-flexible-foil'.",
    )
    fluid_participant_dir: str = Field(default="fluid-openfoam", min_length=1)
    solid_participant_dir: str = Field(default="solid-calculix", min_length=1)
    template: str = Field(
        ...,
        min_length=1,
        description="Basename of the committed precice-config.xml template that is rendered.",
    )
    template_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    renderer_version: str = Field(
        ...,
        min_length=1,
        description="Bumped whenever a rendered byte changes, so two bundles are comparable.",
    )


#: Every source of a coupled case's bytes. One field on the spec, discriminated on ``kind`` —
#: NOT a nullable pair, because a nullable pair's XOR invariant is enforced only at
#: construction and ``model_copy(update=...)`` bypasses ``mode="after"`` validators (this
#: module already uses that idiom twice). A forged both-set tree would emit a tutorial
#: manifest naming an upstream pin for a case we authored: a provenance lie produced by a
#: runtime predicate. A single discriminated field cannot be made ambiguous.
CaseSource = TutorialSource | AuthoredSource


class CoupledCaseSpec(BaseModel):
    """A partitioned FSI case. Satisfies ``SpecLike`` via ``.name``."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    source: CaseSource = Field(..., discriminator="kind")
    participants: tuple[ParticipantSpec, ...] = Field(..., min_length=2)
    container_of_record: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9._-]+\.sif$",
        description="The SIF whose digest becomes the four-tuple's container_sif_sha256.",
    )
    max_time: float = Field(..., gt=0.0, description="The one permitted config override [s].")
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
    def case_subdir(self) -> str:
        """The case directory name under :data:`CASE_ROOT_DIRNAME`, whatever the source."""
        source = self.source
        if source.kind == "tutorial":
            return source.tutorial_case
        return source.case_dir_name

    @property
    def fluid_participant_dir(self) -> str:
        return self.source.fluid_participant_dir

    @property
    def tutorial_pin(self) -> TutorialPin | None:
        """The upstream pin, or ``None`` for an authored case.

        Deliberately NOT named ``pin``: a stale ``spec.pin`` must be an ``AttributeError``
        at the call site rather than a silent ``None`` that flows into a manifest.
        """
        source = self.source
        return source.pin if source.kind == "tutorial" else None

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
    """A deviation from the bytes a case started from, declared up front.

    ``before_sha256`` is ``None`` for an authored file, which replaced nothing.
    ``sha256("")`` would have been the convenient placeholder and is exactly wrong: in a
    bundle it reads like a real prior version.
    """

    model_config = _STRICT

    kind: Literal["max-time", "fluid-mesh-dict", "authored"]
    path: str = Field(..., min_length=1)
    detail: str = Field(..., min_length=1)
    before_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    after_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class MaterializedTree(BaseModel):
    """The laid-down, digest-verified case bytes plus the declared mutations applied.

    Carries the *source* rather than a pin, so the manifest emitter is selected by an
    exhaustive match on ``source.kind`` and a third source type in a future stage is a
    type error rather than a silent fall-through to the tutorial schema.
    """

    model_config = _STRICT

    root: Path
    case_dir: Path
    source: CaseSource = Field(..., discriminator="kind")
    files: tuple[MaterializedFile, ...] = Field(..., min_length=1)
    mutations: tuple[DeclaredMutation, ...] = ()

    @model_validator(mode="after")
    def _root_is_the_case_root(self) -> MaterializedTree:
        """``root`` must be the case root, or ``case_dir`` and every mutation path shift.

        ``aero-manifest.json`` records ``case_dir`` and each mutation's ``path`` relative
        to ``root``. If ``root`` were the run directory instead of the case root, every one
        of those strings would gain a ``tutorial/`` prefix and both goldens would move.
        """
        if self.root.name != CASE_ROOT_DIRNAME:
            raise ValueError(
                f"MaterializedTree.root must be the case root directory "
                f"({CASE_ROOT_DIRNAME!r}), got {self.root.name!r}"
            )
        return self


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize_tutorial(source: TutorialSource, *, dest: Path) -> MaterializedTree:
    """Extract the pinned tutorial into `dest` and verify every file against the manifest.

    The relative layout is preserved exactly: ``solid.py`` opens
    ``'../precice-config.xml'`` and both ``run.sh`` scripts source ``'../../tools/log.sh'``,
    so the case directory and ``tools/`` must be siblings under one root.
    """
    pin = source.pin
    archive = source.archive_path
    tutorial_case = source.tutorial_case
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
    return MaterializedTree(root=dest, case_dir=case_dir, source=source, files=tuple(files))


def select_fluid_mesh(
    tree: MaterializedTree, *, variant: FluidMeshDict, case_dir: Path, fluid_participant_dir: str
) -> MaterializedTree:
    """Install one of the tutorial's own ``blockMeshDict`` variants as the fluid mesh.

    ``blockMesh`` reads ``system/blockMeshDict``; upstream ships two alternatives beside
    it and expects the user to choose. Selecting one is a DECLARED mutation (cost, not
    quality — every variant is upstream-authored for this same benchmark), recorded with
    both digests so the bundle shows exactly which mesh produced the numbers.
    """
    system = case_dir / fluid_participant_dir / "system"
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
    tree: MaterializedTree, *, path: Path, before_sha256: str, after_sha256: str, max_time: float
) -> MaterializedTree:
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
