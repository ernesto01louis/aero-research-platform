"""The `source` seam's own guarantees — the ones the pre-refactor pins could not express.

`test_stage19_{load_path_unchanged,materialization_is_byte_identical}.py` prove the refactor
changed NOTHING about the Stage-19 bytes or numbers. They landed first, on pre-refactor code,
at `67d8e82`, and neither their fixtures nor their assertions have moved since.

This file is the other half: what the seam now guarantees that it could not before. It has to
land WITH the refactor, because every property here is about code that did not exist an hour
ago.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from aero.adapters.precice.case import (
    CASE_ROOT_DIRNAME,
    AuthoredSource,
    CoupledCaseError,
    CoupledCaseSpec,
    DeclaredMutation,
    MaterializedFile,
    MaterializedTree,
    ParticipantSpec,
    TutorialPin,
    TutorialSource,
)
from aero.adapters.precice.manifest import (
    render_authored_manifest_json,
    render_tutorial_manifest_json,
)
from aero.provenance.four_fold import config_hash
from aero.vv.fsi.turek_hron_fsi3 import fsi3_case_spec

from tests.stage_20._hg2007 import authored_source, authored_spec

pytestmark = pytest.mark.stage_20


def _pin() -> TutorialPin:
    return TutorialPin(commit="a" * 40, archive_sha256="b" * 64, manifest_path=Path("m.csv"))


def _tutorial_source() -> TutorialSource:
    return TutorialSource(pin=_pin(), archive_path=Path("a.tar.gz"))


def _authored_source() -> AuthoredSource:
    """A REAL authored source, from the shared builders.

    Since ADR-037 an authored source carries the complete fluid and solid specs, and they
    must agree on eight numbers plus the whole station list -- so there is no such thing as
    a placeholder one, and a hand-built pair here would drift from the real cross-checks.
    """
    return authored_source()


def _spec(source: TutorialSource | AuthoredSource) -> CoupledCaseSpec:
    """A spec around either source.

    The authored branch goes through the shared builder because
    `CoupledCaseSpec._an_authored_source_describes_these_participants` now binds the source
    to the participants that will actually be launched -- workdirs, the solid's deck name,
    `max_time` and the uids -- so the tutorial path's placeholder participants are no longer
    valid for an authored case.
    """
    if source.kind == "authored":
        return authored_spec(source=source)
    return CoupledCaseSpec(
        name="x",
        source=source,
        max_time=8.0,
        wall_clock_ceiling_s=600,
        analysis_discard_s=4.0,
        participants=(
            ParticipantSpec(name="Fluid", workdir="f", command="true", sif="precice-fsi.sif"),
            ParticipantSpec(name="Solid", workdir="s", command="true", sif="precice-fsi.sif"),
        ),
        container_of_record="precice-fsi.sif",
    )


class TestTheSpecIsSourceAgnostic:
    def test_case_subdir_resolves_for_both_sources(self) -> None:
        assert _spec(_tutorial_source()).case_subdir == "turek-hron-fsi3"
        assert _spec(_authored_source()).case_subdir == "hg2007-flexible-foil"

    def test_tutorial_pin_is_none_for_an_authored_case(self) -> None:
        assert _spec(_tutorial_source()).tutorial_pin == _pin()
        assert _spec(_authored_source()).tutorial_pin is None

    def test_a_stale_spec_dot_pin_is_an_attribute_error_not_a_silent_none(self) -> None:
        """Why the property is `tutorial_pin` and deliberately NOT `pin`.

        A `pin` property returning `None` for an authored case would let every existing
        `spec.pin.commit` call site keep type-checking and fail at runtime deep inside a
        campaign — or worse, flow a `None` into a manifest. An `AttributeError` at import
        or first call is the loud version of the same information.
        """
        with pytest.raises(AttributeError):
            _ = _spec(_tutorial_source()).pin  # type: ignore[attr-defined]


class TestTheTreeCannotBeMadeAmbiguous:
    """The reason `MaterializedTree` carries ONE `source`, not `pin` XOR `authored`."""

    def test_model_copy_bypasses_after_validators_which_is_why_the_xor_shape_was_rejected(
        self,
    ) -> None:
        """The mechanism, demonstrated on the real model.

        `case.py` mutates trees with `model_copy(update=...)` in TWO places
        (`select_fluid_mesh`, `record_max_time_mutation`), and pydantic skips
        `mode="after"` validators on `model_copy`. A nullable `pin`/`authored` pair would
        therefore have had its XOR enforced only at construction, and any helper written by
        analogy with those two could produce a both-set tree. `write_manifest` dispatching
        on `pin is not None` would then emit a tutorial manifest — naming an upstream
        commit — for a case we authored ourselves.

        A single discriminated field has no invariant to bypass. This test pins that the
        idiom really does skip validation, so the argument stays falsifiable.
        """
        tree = _tree(_tutorial_source())
        # Construction runs the after-validator and refuses a bad root ...
        with pytest.raises(ValueError, match="must be the case root directory"):
            MaterializedTree.model_validate({**tree.model_dump(), "root": Path("/runs/elsewhere")})
        # ... but `model_copy(update=...)` sails straight past it. That is the whole point:
        # any invariant expressed as an after-validator is forgeable by the idiom this
        # module already uses twice, so the tree must have no invariant to forge.
        forged = tree.model_copy(update={"root": Path("/runs/elsewhere")})
        assert forged.root.name == "elsewhere"

    def test_the_root_must_be_the_case_root(self) -> None:
        """Or `case_dir` and every mutation path in the manifest gain a prefix."""
        with pytest.raises(ValueError, match="must be the case root directory"):
            MaterializedTree(
                root=Path("/runs/abc"),
                case_dir=Path("/runs/abc/turek-hron-fsi3"),
                source=_tutorial_source(),
                files=(MaterializedFile(path="f", sha256="d" * 64),),
            )


def _tree(source: TutorialSource | AuthoredSource) -> MaterializedTree:
    root = Path("/runs/abc") / CASE_ROOT_DIRNAME
    return MaterializedTree(
        root=root,
        case_dir=root / "turek-hron-fsi3",
        source=source,
        files=(MaterializedFile(path="turek-hron-fsi3/x", sha256="d" * 64),),
    )


class TestTheManifestEmittersAreSchemaVersionedNotFieldVersioned:
    def test_the_tutorial_renderer_needs_no_tree_at_all(self) -> None:
        """It is a free function over primitives, so it is testable without a filesystem.

        That is also what stops it drifting back to `model_dump()`: there is no model in
        scope to dump.
        """
        text = render_tutorial_manifest_json(
            pin=_pin(),
            case_dir_rel="turek-hron-fsi3",
            files=(MaterializedFile(path="a", sha256="1" * 64),),
            mutations=(),
        )
        assert json.loads(text) == {
            "pin": {
                "repo": "precice/tutorials",
                "branch": "develop",
                "commit": "a" * 40,
                "archive_sha256": "b" * 64,
            },
            "case_dir": "turek-hron-fsi3",
            "files": [{"path": "a", "sha256": "1" * 64}],
            "declared_mutations": [],
        }
        assert text.endswith("}\n")

    def test_the_tutorial_schema_refuses_an_authored_mutation(self) -> None:
        """Schema v1 has no way to say "this file replaced nothing", so it must not try."""
        with pytest.raises(CoupledCaseError, match="cannot describe an authored mutation"):
            render_tutorial_manifest_json(
                pin=_pin(),
                case_dir_rel="c",
                files=(MaterializedFile(path="a", sha256="1" * 64),),
                mutations=(
                    DeclaredMutation(
                        kind="authored", path="a", detail="rendered", after_sha256="2" * 64
                    ),
                ),
            )

    def test_the_tutorial_schema_refuses_a_mutation_with_no_before_digest(self) -> None:
        with pytest.raises(CoupledCaseError, match="has no before_sha256"):
            render_tutorial_manifest_json(
                pin=_pin(),
                case_dir_rel="c",
                files=(MaterializedFile(path="a", sha256="1" * 64),),
                mutations=(
                    DeclaredMutation(
                        kind="max-time", path="a", detail="shortened", after_sha256="2" * 64
                    ),
                ),
            )

    def test_the_authored_schema_binds_the_manifest_to_the_hashed_spec(self) -> None:
        """`spec_sha256` is one line proving the manifest and the MLflow tag agree.

        Without it, "the bundle describes the run that produced it" is believed rather
        than checkable.
        """
        spec = _spec(_authored_source())
        digest = config_hash(json.loads(spec.model_dump_json()))
        document = json.loads(
            render_authored_manifest_json(
                source=_authored_source(),
                case_dir_rel="hg2007-flexible-foil",
                files=(MaterializedFile(path="a", sha256="1" * 64),),
                mutations=(
                    DeclaredMutation(
                        kind="authored", path="a", detail="rendered", after_sha256="1" * 64
                    ),
                ),
                spec_sha256=digest,
            )
        )
        assert document["schema"] == 2
        assert document["authored"]["spec_sha256"] == digest
        assert document["declared_mutations"][0]["before_sha256"] is None
        assert "pin" not in document


class TestTheHardCodedFluidDirectoryIsGone:
    def test_select_fluid_mesh_reads_the_directory_it_is_told_to(self, tmp_path: Path) -> None:
        """`case.py:382` hard-coded "fluid-openfoam" while the spec already carried the
        field, so a case whose fluid participant lived elsewhere silently read and wrote
        the wrong directory. It was a carried ledger item from Stage 19.
        """
        from aero.adapters.precice.case import select_fluid_mesh

        root = tmp_path / CASE_ROOT_DIRNAME
        system = root / "turek-hron-fsi3" / "elsewhere" / "system"
        system.mkdir(parents=True)
        (system / "blockMeshDict").write_bytes(b"default")
        (system / "blockMeshDict_refined").write_bytes(b"refined")
        tree = _tree(_tutorial_source()).model_copy(
            update={"root": root, "case_dir": root / "turek-hron-fsi3"}
        )

        out = select_fluid_mesh(
            tree,
            variant="blockMeshDict_refined",
            case_dir=tree.case_dir,
            fluid_participant_dir="elsewhere",
        )
        assert (system / "blockMeshDict").read_bytes() == b"refined"
        assert out.mutations[0].kind == "fluid-mesh-dict"
        assert out.mutations[0].before_sha256 == hashlib.sha256(b"default").hexdigest()


def test_the_fsi3_config_hash_moved_and_this_is_the_new_value() -> None:
    """The refactor's ONE honest divergence — recorded, not papered over (ADR-037).

    Nesting the pin under `source` changes `spec.model_dump()`, and `config_hash` is a
    digest of exactly that. So FSI3's config_hash moved:

        old (tagged Stage-19 record, data/vv/stage19_turek_hron_fsi3.json):
            c524faffcd1b05a39f0f434e94b09c7f62269c2887901cdb8b5a7b7b86fcff7c
        new (this commit onwards):
            3f94f39469b22fc44f43883f8f4c7f5c6447697e890ffd278b1ced16ad6cd69f

    These are DIFFERENT CLAIMS and must not be conflated. The materialized *bytes* are
    proved identical by `test_stage19_materialization_is_byte_identical.py`, whose goldens
    have not moved since `67d8e82`. What moved is the *spec serialization* — the record of
    which inputs produced those bytes. A future re-run of Stage 19 will therefore log a
    different config_hash for a byte-identical case, and the tagged v0.0.19 record stands
    on the old one.
    """
    spec = fsi3_case_spec(max_time=8.0, wall_clock_ceiling_s=172800)
    assert (
        config_hash(json.loads(spec.model_dump_json()))
        == "3f94f39469b22fc44f43883f8f4c7f5c6447697e890ffd278b1ced16ad6cd69f"
    )
