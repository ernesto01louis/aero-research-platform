"""Non-regression pin on `PreciceCoupledSolver._write_case`, ahead of the Stage-20 refactor.

Stage 20 nests `TutorialPin` under a `source: TutorialSource | AuthoredSource` union,
renames `TutorialTree` to `MaterializedTree`, widens `DeclaredMutation`, and threads
`fluid_participant_dir` through `select_fluid_mesh`. The Stage-19 verdict rests on the
bytes the *current* materialization lays down, so the refactor has to reproduce them —
file for file, digest for digest, and byte for byte in `aero-manifest.json`.

**Committed before the refactor, with the golden captured from pre-refactor code.**
Regenerate with ``python scripts/stage20_capture_stage19_golden.py --fixtures`` (the
goldens themselves are captured by the probe documented in that script).

Two fixtures, deliberately:

* a **tiny committed archive**, which runs in the required unit job and — unlike the real
  gated spec — selects a NON-default `blockMeshDict` variant, so the mutation ledger
  carries two entries and their ORDER is testable. The real spec produces one mutation and
  therefore cannot detect an ordering regression at all;
* the **real FSI3 archive**, DVC-gated. That one is what actually protects the tagged
  Stage-19 record, and as a side effect it is a second, independent copy of the pin
  manifest.

`os.chown` is monkeypatched rather than skipped: `run_as_uid` is `ge=1` so root cannot
pass its own uid, and a CI runner cannot chown to 1000 — but the ORDERING (chown after
digest verification, before the manifest write) is exactly the interesting property, and
it is observable from the call list without ever touching a real inode.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from aero.adapters.precice.case import (
    CoupledCaseSpec,
    DeclaredMutation,
    ParticipantSpec,
    TutorialPin,
)
from aero.adapters.precice.config import PreciceConfigExpectation
from aero.adapters.precice.solver import PreciceCoupledSolver

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "tests" / "stage_20" / "fixtures" / "materialization"
_TINY_ARCHIVE = _FIXTURES / "tiny-tutorial.tar.gz"
_TINY_MANIFEST = _FIXTURES / "tiny_pin_manifest.csv"

_TUTORIALS_COMMIT = "cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e"
_TINY_ARCHIVE_SHA256 = "0d576d1ff7410cf7d272b0cef70c15343f17b3bae95ff68ad986a4ac33079033"
_MAX_TIME = 2.5

#: Every file under the materialized root after `_write_case`, with its ON-DISK digest.
#: A literal, not a computed comparison: the point is to state what the current code
#: produces so that any change to it has to be typed out by a human and justified.
_EXPECTED_TREE: dict[str, str] = {
    "aero-manifest.json": "43f6ed842818eeb1d78c01f5a25a5746de055faa87585fa76262759cd6c9e518",
    "tools/log.sh": "381f34ca5864140d205d18ac8ae254f7f36d8e7038ab706ae8aa600d9c869fd0",
    # Overwritten by `select_fluid_mesh` -> now byte-identical to the refined variant.
    "turek-hron-fsi3/fluid-openfoam/system/blockMeshDict": (
        "53c3045f969b6c4f456ae3f78f99955a6b59362df24101bc85628c643a80f6ae"
    ),
    "turek-hron-fsi3/fluid-openfoam/system/blockMeshDict_refined": (
        "53c3045f969b6c4f456ae3f78f99955a6b59362df24101bc85628c643a80f6ae"
    ),
    # Rewritten by `rewrite_max_time`.
    "turek-hron-fsi3/precice-config.xml": (
        "00fdff014c038975f3fd0b733776f2699eebf402d4f8bc8a5179b6294f500734"
    ),
    "turek-hron-fsi3/solid-nutils/run.sh": (
        "29f865a1a70f82169222f8b8fc7db6ed54137d78717b8d73ca3af74d9c5397be"
    ),
}

#: The as-ACQUIRED digest of `blockMeshDict`, i.e. what upstream shipped. It is what the
#: manifest's `files` entry records and what the mutation's `before_sha256` records — and
#: it is deliberately NOT what is on disk afterwards. See the dedicated test.
_BLOCKMESHDICT_AS_ACQUIRED = "a9ff2ddd03eb3b5728a455ace08a4df9e4f06ce90ea24ee5a55654ebd76193a8"

_EXPECTED_MUTATIONS = (
    DeclaredMutation(
        kind="fluid-mesh-dict",
        path="turek-hron-fsi3/fluid-openfoam/system/blockMeshDict",
        detail=(
            "installed the upstream variant 'blockMeshDict_refined' as system/blockMeshDict "
            "(a declared cost/resolution choice among upstream-authored meshes)"
        ),
        before_sha256=_BLOCKMESHDICT_AS_ACQUIRED,
        after_sha256="53c3045f969b6c4f456ae3f78f99955a6b59362df24101bc85628c643a80f6ae",
    ),
    DeclaredMutation(
        kind="max-time",
        path="turek-hron-fsi3/precice-config.xml",
        detail=(
            "shortened <max-time> to 2.5 s to fit the pre-declared wall-clock budget; "
            "verified structurally that nothing else changed"
        ),
        before_sha256="a9e6c2293f844bf58bba6cc7b79897f125b649a37dead3eea0483f01f5110fef",
        after_sha256="00fdff014c038975f3fd0b733776f2699eebf402d4f8bc8a5179b6294f500734",
    ),
)

_TINY_EXPECTATION = PreciceConfigExpectation(
    participants=("Fluid", "Solid"),
    coupling_scheme="parallel-implicit",
    m2n_kind="sockets",
    time_window_size=1e-3,
    max_iterations=100,
    convergence_limits={"Stress": 1e-4, "Displacement": 1e-4},
    convergence_kinds={
        "Stress": "relative-convergence-measure",
        "Displacement": "relative-convergence-measure",
    },
    watch_points={"Solid/Flap-Tip": (0.6, 0.2)},
    acceleration_kind="IQN-ILS",
)


def _tiny_spec(**overrides: object) -> CoupledCaseSpec:
    fields: dict[str, object] = {
        "name": "tiny_tutorial",
        "pin": TutorialPin(
            commit=_TUTORIALS_COMMIT,
            archive_sha256=_TINY_ARCHIVE_SHA256,
            manifest_path=_TINY_MANIFEST,
        ),
        "archive_path": _TINY_ARCHIVE,
        "tutorial_case": "turek-hron-fsi3",
        "participants": (
            ParticipantSpec(
                name="Fluid", workdir="fluid-openfoam", command="./run.sh", sif="precice-fsi.sif"
            ),
            ParticipantSpec(
                name="Solid", workdir="solid-nutils", command="./run.sh", sif="precice-fsi.sif"
            ),
        ),
        "container_of_record": "precice-fsi.sif",
        "max_time": _MAX_TIME,
        "fluid_mesh_dict": "blockMeshDict_refined",
        "wall_clock_ceiling_s": 172800,
        "analysis_discard_s": 1.0,
        "run_as_uid": 1000,
    }
    fields.update(overrides)
    return CoupledCaseSpec(**fields)  # type: ignore[arg-type]


def _materialize(
    spec: CoupledCaseSpec,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    expectation: PreciceConfigExpectation | None,
) -> tuple[Path, object, list[tuple[str, int, int]]]:
    """Drive the REAL `_write_case`; return (materialized root, tree, chown calls).

    Only `_chown_tree`'s own calls are returned. Running as root, `tarfile.extractall`
    also chowns every member it writes — with `(-1, -1)`, i.e. "leave it alone", because
    the `data` filter strips the archive's recorded ownership. Those are extraction
    mechanics, not the privilege drop under test, and the uid discriminates them exactly.
    """
    calls: list[tuple[str, int, int]] = []
    monkeypatch.setattr(os, "chown", lambda p, u, g: calls.append((str(p), u, g)))
    solver = PreciceCoupledSolver(
        expectation=expectation, host_nfs_root=tmp_path, remote_nfs_root=Path("/mnt/aero")
    )
    case_dir = solver.prepare(spec)
    root = case_dir.host_path / "tutorial"
    dropped = [call for call in calls if call[1] >= 0]
    return root, solver._trees[case_dir.host_path.name], dropped


def _tree_digests(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class TestTheMaterializedBytesAreUnchanged:
    def test_every_file_and_its_digest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, _, _ = _materialize(
            _tiny_spec(), tmp_path, monkeypatch, expectation=_TINY_EXPECTATION
        )
        assert _tree_digests(root) == _EXPECTED_TREE

    def test_the_manifest_bytes_are_the_committed_golden(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`aero-manifest.json` is a published artifact: it ships inside every bundle.

        Compared as a string, not as parsed JSON — key order, indent and the trailing
        newline are all part of what a reviewer downloading an old bundle will diff.
        """
        root, _, _ = _materialize(
            _tiny_spec(), tmp_path, monkeypatch, expectation=_TINY_EXPECTATION
        )
        produced = (root / "aero-manifest.json").read_text(encoding="utf-8")
        assert produced == (_FIXTURES / "golden-aero-manifest.json").read_text(encoding="utf-8")

    def test_the_declared_mutations_are_exactly_these_in_this_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Order matters: mesh selection happens BEFORE the max-time rewrite.

        Swapping them would still produce two mutations and an identical tree on disk, so
        only the ordered tuple catches it.
        """
        _, tree, _ = _materialize(
            _tiny_spec(), tmp_path, monkeypatch, expectation=_TINY_EXPECTATION
        )
        assert tree.mutations == _EXPECTED_MUTATIONS  # type: ignore[attr-defined]

    def test_the_manifest_records_the_as_acquired_digest_not_the_mutated_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The contract, made explicit so it cannot be "fixed" by accident.

        `files` is the record of what upstream shipped and what the pin manifest verified;
        the mutation ledger is the record of what we then changed. The two together let a
        reader reconstruct both states. Making `files` report the post-mutation digest
        would look tidier and would destroy that.
        """
        root, tree, _ = _materialize(
            _tiny_spec(), tmp_path, monkeypatch, expectation=_TINY_EXPECTATION
        )
        target = "turek-hron-fsi3/fluid-openfoam/system/blockMeshDict"
        recorded = {f.path: f.sha256 for f in tree.files}  # type: ignore[attr-defined]
        assert recorded[target] == _BLOCKMESHDICT_AS_ACQUIRED
        assert _EXPECTED_MUTATIONS[0].before_sha256 == _BLOCKMESHDICT_AS_ACQUIRED
        on_disk = hashlib.sha256((root / target).read_bytes()).hexdigest()
        assert on_disk != _BLOCKMESHDICT_AS_ACQUIRED

    def test_the_case_is_chowned_before_the_manifest_is_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ordering pinned without timestamps: the manifest is simply not in the call list.

        `_write_case` chowns the materialized tree to the unprivileged participant uid and
        THEN writes `aero-manifest.json`, so the manifest stays root-owned. That is
        deliberate — the run's own record of what it laid down should not be writable by
        the process it describes.
        """
        root, _, calls = _materialize(
            _tiny_spec(), tmp_path, monkeypatch, expectation=_TINY_EXPECTATION
        )
        chowned = {path for path, _, _ in calls}
        assert all(uid == 1000 and gid == 1000 for _, uid, gid in calls)
        assert str(root) in chowned
        assert str(root / "turek-hron-fsi3" / "precice-config.xml") in chowned
        assert str(root / "aero-manifest.json") not in chowned

    def test_no_chown_when_the_participants_run_as_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, calls = _materialize(
            _tiny_spec(run_as_uid=None), tmp_path, monkeypatch, expectation=_TINY_EXPECTATION
        )
        assert calls == []


class TestTheRealGatedSpec:
    """The DVC-gated sibling — the one that protects the tagged Stage-19 record."""

    @pytest.fixture(scope="class")
    def archive(self) -> Path:
        from aero.vv.fsi.turek_hron_fsi3 import _ARCHIVE, _REFERENCE_DIR

        path = _REPO_ROOT / _REFERENCE_DIR / _ARCHIVE
        if not path.is_file():
            pytest.skip(f"{path} not pulled — run `dvc pull data/references/fsi/turek_hron_fsi3/`")
        return path

    def test_the_gated_fsi3_manifest_is_byte_identical(
        self, archive: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from aero.vv.fsi import TUREK_HRON_FSI3_EXPECTATION
        from aero.vv.fsi.turek_hron_fsi3 import GATED_MAX_TIME, fsi3_case_spec

        spec = fsi3_case_spec(max_time=GATED_MAX_TIME, wall_clock_ceiling_s=172800)
        assert spec.gated, "the golden must be captured on the GATED configuration"
        root, tree, _ = _materialize(
            spec, tmp_path, monkeypatch, expectation=TUREK_HRON_FSI3_EXPECTATION
        )
        produced = (root / "aero-manifest.json").read_text(encoding="utf-8")
        assert produced == (_FIXTURES / "golden-fsi3-aero-manifest.json").read_text(
            encoding="utf-8"
        )
        # The default mesh variant means exactly one declared mutation, and the pin
        # manifest covers 94 files. Both are stated so a silent change to either is named.
        assert [m.kind for m in tree.mutations] == ["max-time"]  # type: ignore[attr-defined]
        assert len(tree.files) == 94  # type: ignore[attr-defined]

    def test_the_golden_agrees_with_the_committed_pin_manifest(self, archive: Path) -> None:
        """A second, independent copy of the pin manifest — cross-checked, not trusted."""
        from aero.vv.fsi.turek_hron_fsi3 import _MANIFEST, _REFERENCE_DIR

        golden = json.loads((_FIXTURES / "golden-fsi3-aero-manifest.json").read_text())
        from_golden = {entry["path"]: entry["sha256"] for entry in golden["files"]}
        pin = TutorialPin(
            commit=_TUTORIALS_COMMIT,
            archive_sha256="0" * 64,
            manifest_path=_REPO_ROOT / _REFERENCE_DIR / _MANIFEST,
        )
        assert from_golden == pin.manifest()
