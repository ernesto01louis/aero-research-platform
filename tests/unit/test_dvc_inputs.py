"""ADR-052 — the declared DVC inputs: the pointer parser, the declaration, the one read path (O-07).

The DVC term is the digest of the `.dvc` pointers a case declares, read as committed, so it is
recomputable from git alone. These tests pin the strict parser against the committed pointers,
every refusal the ADR lists, the declaration table of the registered cases, and that no case
opens a DVC output it did not declare.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from aero.provenance.dvc_inputs import (
    EMPTY_DIGEST,
    PREFIX,
    _dvc_outputs,
    digest,
    parse_pointer,
    read_declared_input,
    resolve_declared,
)
from aero.provenance.four_fold import DeclaredInput, ProvenanceError

from tests.unit._launch_fixtures import REPO, committed_repo, dvc_pointer, git, run_tuple

pytestmark = pytest.mark.stage_23

CFD = "data/references/fsi/turek_hron_fsi3/cylinder_flag.stl.dvc"
FSI3 = "data/references/fsi/turek_hron_fsi3/precice-tutorials-turek-hron-fsi3.tar.gz.dvc"
ONERA = "data/meshes/su2/onera_m6.su2.dvc"

#: ADR-052 D1's declaration table and D2's golden values.
DECLARED = {
    "turek_hron_cfd2": ((CFD,), "70b49f18e2fd314d3ec305433d74b4a2be494581fc05453f23b74cd66245e000"),
    "turek_hron_cfd3": ((CFD,), "70b49f18e2fd314d3ec305433d74b4a2be494581fc05453f23b74cd66245e000"),
    "turek_hron_fsi3": (
        (FSI3,),
        "5234c4dd598c00381ba4732930bef80a42729986d22f0619675ab0ee45c21659",
    ),
    "onera_m6": ((ONERA,), "25b590aae4b2757b8597f8724297d84ed91a0bbf890ec558a44793fc07557c7f"),
}
EMPTY = "1ef5b7d9a694e703ccb270937035bdcc006487fa5a5b6fd92ac9c10f94453ec3"


def _pointers() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "*.dvc"], capture_output=True, text=True, check=True
    )
    return out.stdout.split()


# --- the declaration table ------------------------------------------------------------------


def test_every_registered_case_declares_exactly_the_adr_table() -> None:
    from aero.vv.stacks import registered_cases

    cases = registered_cases()
    assert len(cases) == 25
    for name, case in cases.items():
        pointers, value = DECLARED.get(name, ((), EMPTY))
        assert case.dvc_inputs == pointers, name
        assert digest(resolve_declared(REPO, case.dvc_inputs)) == value, name


def test_the_optimizer_cases_declare_none() -> None:
    from aero.optimize.airfoil_case import ShapedLaminarAirfoil
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil

    assert ShapedLaminarAirfoil.dvc_inputs == () == ShapedTurbulentAirfoil.dvc_inputs


def test_the_prefix_and_the_empty_set() -> None:
    assert PREFIX == b"aero.dvc-inputs/v1\n"
    assert EMPTY_DIGEST == EMPTY == digest(resolve_declared(REPO, ()))
    assert hashlib.sha256(PREFIX + b'{"inputs":[]}').hexdigest() == EMPTY


# --- the strict parser -----------------------------------------------------------------------


@pytest.mark.parametrize("pointer", _pointers())
def test_the_parser_agrees_with_yaml_on_every_committed_pointer(pointer: str) -> None:
    text = (REPO / pointer).read_text(encoding="utf-8")
    (out,) = yaml.safe_load(text)["outs"]
    if str(out["md5"]).endswith(".dir"):
        with pytest.raises(ProvenanceError, match="directory output"):
            parse_pointer(text, pointer=pointer)
        return
    parsed = parse_pointer(text, pointer=pointer)
    base = pointer.rsplit("/", 1)[0]
    assert parsed == DeclaredInput(
        hash=out["hash"], md5=out["md5"], path=f"{base}/{out['path']}", size=out["size"]
    )


_GOOD = dvc_pointer("3bcd781278f36f4d1640dc4665f71d23", 66684, "x.stl").decode()


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (_GOOD.replace("hash: md5", "hash: md5-dos2unix"), "not DVC-3's plain-byte md5"),
        (_GOOD + "  nfiles: 3\n", "directory output"),
        (_GOOD.replace("f71d23", "f71d23.dir"), "directory output"),
        (_GOOD + "  isexec: true\n", "keys"),
        (_GOOD.replace("  hash: md5\n", ""), "keys"),
        (_GOOD + "- md5: 3bcd781278f36f4d1640dc4665f71d23\n", "declares 2 outputs"),
        (_GOOD.replace("path: x.stl", "path: ../x.stl"), "not a plain relative path"),
        (_GOOD.replace("path: x.stl", "path: /etc/x.stl"), "not a plain relative path"),
        (_GOOD.replace("path: x.stl", "path: 'x.stl'"), "not a plain relative path"),
        (_GOOD.replace("size: 66684", "size: 066684"), "not a byte count"),
        (_GOOD.replace("3bcd781278f36f4d", "3BCD781278F36F4D"), "lowercase hex"),
        ("deps:\n" + _GOOD, "exactly one top-level key"),
        (_GOOD + "wdir: ..\n", "not a file-pointer line"),
        (_GOOD.replace("\n", "\r\n"), "CR line endings"),
        (_GOOD + "  size: 1\n", "not a `key: value` line"),
    ],
)
def test_the_parser_refuses_what_the_adr_refuses(text: str, match: str) -> None:
    with pytest.raises(ProvenanceError, match=match):
        parse_pointer(text, pointer="d/x.stl.dvc")


def test_a_remote_is_allowed_and_excluded_from_the_preimage() -> None:
    plain = parse_pointer(_GOOD, pointer="d/x.stl.dvc")
    remote = dvc_pointer("3bcd781278f36f4d1640dc4665f71d23", 66684, "x.stl", remote="aero-nfs")
    assert parse_pointer(remote.decode(), pointer="d/x.stl.dvc") == plain
    assert plain.path == "d/x.stl"


@pytest.mark.parametrize("pointer", ["x.stl", "d/.dvc", "../x.stl.dvc", "/abs/x.stl.dvc"])
def test_only_a_repo_relative_dvc_pointer_is_parsed(pointer: str) -> None:
    with pytest.raises(ProvenanceError):
        parse_pointer(_GOOD, pointer=pointer)


# --- the declaration: pointers as committed ------------------------------------------------


def _repo(tmp_path: Path, data: bytes = b"solid\n") -> Path:
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    repo = committed_repo(
        tmp_path / "repo",
        {
            "d/geo.stl.dvc": dvc_pointer(md5, len(data), "geo.stl"),
            "d/notes.txt": b"git-tracked\n",
            "big/cases.dvc": b"outs:\n- md5: 27bfdbd931aca71be3c3a4bebbf8aac4.dir\n  size: 9\n"
            b"  nfiles: 2\n  hash: md5\n  path: cases\n",
            "dvc.lock": b"schema: '2.0'\nstages:\n  ingest:\n    cmd: x\n    deps:\n"
            b"    - path: scripts/x.sh\n    outs:\n    - path: gen/manifest.json\n"
            b"      hash: md5\n      md5: a6fdd5b6b2a17f574a6f01f0b08cb3d6\n      size: 1\n",
        },
    )
    (repo / "d" / "geo.stl").write_bytes(data)  # DVC-pulled: never in git
    return repo


def test_a_changed_pointer_moves_the_hash(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    before = digest(resolve_declared(repo, ("d/geo.stl.dvc",)))
    (repo / "d" / "geo.stl.dvc").write_bytes(dvc_pointer("0" * 32, 6, "geo.stl"))
    git(repo, "commit", "-q", "-am", "new bytes")
    assert digest(resolve_declared(repo, ("d/geo.stl.dvc",))) != before


def test_a_pointer_that_differs_from_head_is_refused(tmp_path: Path) -> None:
    """Even for an --allow-dirty run: the value must be recomputable from git."""
    repo = _repo(tmp_path)
    (repo / "d" / "geo.stl.dvc").write_bytes(dvc_pointer("0" * 32, 6, "geo.stl"))
    with pytest.raises(ProvenanceError, match="differs from HEAD's"):
        resolve_declared(repo, ("d/geo.stl.dvc",))


@pytest.mark.parametrize(
    ("pointers", "match"),
    [
        (("d/missing.stl.dvc",), "not committed at HEAD"),
        (("dvc.lock",), "dvc.lock"),
        (("d/geo.stl.dvc", "d/geo.stl.dvc"), "declared more than once"),
        ("d/geo.stl.dvc", "the string"),
        (("big/cases.dvc",), "directory output"),
    ],
)
def test_a_declaration_is_refused_unless_it_names_committed_file_pointers(
    tmp_path: Path, pointers: Any, match: str
) -> None:
    with pytest.raises(ProvenanceError, match=match):
        resolve_declared(_repo(tmp_path), pointers)


def test_the_resolved_inputs_are_sorted_by_output_path(tmp_path: Path) -> None:
    repo = committed_repo(
        tmp_path / "r",
        {
            "z/a.dvc": dvc_pointer("1" * 32, 1, "a"),
            "a/z.dvc": dvc_pointer("2" * 32, 2, "z"),
        },
    )
    inputs = resolve_declared(repo, ("z/a.dvc", "a/z.dvc"))
    assert [i.path for i in inputs] == ["a/z", "z/a"]
    assert digest(inputs) == digest(resolve_declared(repo, ("a/z.dvc", "z/a.dvc")))


# --- the one read path -----------------------------------------------------------------------


def test_a_declared_input_is_read_once_and_verified(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    declared = resolve_declared(repo, ("d/geo.stl.dvc",))
    assert read_declared_input(repo, repo / "d" / "geo.stl", declared=declared) == b"solid\n"
    assert read_declared_input(repo, "d/geo.stl", declared=declared) == b"solid\n"


@pytest.mark.parametrize("data", [b"solid!\n", b"SOLID\n"])
def test_bytes_that_differ_from_the_pointer_are_refused(tmp_path: Path, data: bytes) -> None:
    """A size mismatch and a same-size md5 mismatch: workspace edits to declared data."""
    repo = _repo(tmp_path)
    declared = resolve_declared(repo, ("d/geo.stl.dvc",))
    (repo / "d" / "geo.stl").write_bytes(data)
    with pytest.raises(ProvenanceError, match="do not match the declared pointer"):
        read_declared_input(repo, "d/geo.stl", declared=declared)


def test_a_declared_input_that_was_never_pulled_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    declared = resolve_declared(repo, ("d/geo.stl.dvc",))
    (repo / "d" / "geo.stl").unlink()
    with pytest.raises(ProvenanceError, match="dvc pull"):
        read_declared_input(repo, "d/geo.stl", declared=declared)


@pytest.mark.parametrize(
    ("path", "match"),
    [
        ("d/geo.stl", "did not declare"),
        ("big/cases/run_1/x.vtp", "member of the directory output big/cases"),
        ("gen/manifest.json", "dvc.lock"),
        ("d/untracked.txt", "neither git-tracked nor a declared DVC output"),
        ("/etc/hostname", "outside the checkout"),
        ("../elsewhere.stl", "outside the checkout"),
    ],
)
def test_everything_but_a_declared_input_or_a_git_file_is_refused(
    tmp_path: Path, path: str, match: str
) -> None:
    repo = _repo(tmp_path)
    (repo / "d" / "untracked.txt").write_bytes(b"x")
    with pytest.raises(ProvenanceError, match=match):
        read_declared_input(repo, path, declared=())


def test_a_git_tracked_file_reads_as_committed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert read_declared_input(repo, "d/notes.txt", declared=()) == b"git-tracked\n"


def test_the_real_checkout_knows_its_dvc_outputs() -> None:
    outputs = {path for path, _ in _dvc_outputs(REPO)}
    assert "data/references/fsi/turek_hron_fsi3/cylinder_flag.stl" in outputs
    assert "data/datasets/drivaerml/cases" in outputs  # a directory output
    assert "data/datasets/ahmedml/manifest.json" in outputs  # a dvc.lock stage output


# --- every call site declares ----------------------------------------------------------------


def test_every_compute_provenance_call_passes_its_declaration() -> None:
    """mypy covers aero/; this covers the untyped scripts/ and the V&V conftest."""
    sites = [
        *sorted((REPO / "aero").rglob("*.py")),
        *sorted((REPO / "scripts").glob("*.py")),
        REPO / "tests" / "vv" / "conftest.py",
    ]
    missing, found = [], 0
    for path in sites:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and (
                getattr(node.func, "id", None) == "compute_provenance"
                or getattr(node.func, "attr", None) == "compute_provenance"
            ):
                found += 1
                if "dvc_inputs" not in {k.arg for k in node.keywords}:
                    missing.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert found >= 34, found
    assert missing == [], f"compute_provenance without dvc_inputs=: {missing}"


# --- no case opens a DVC output it did not declare ------------------------------------------

_OPENED: list[str] | None = None


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if _OPENED is not None and event == "open" and isinstance(args[0], str | Path):
        _OPENED.append(str(args[0]))


sys.addaudithook(_audit)


def _recording() -> Iterator[list[str]]:
    global _OPENED
    _OPENED = []
    try:
        yield _OPENED
    finally:
        _OPENED = None


def _solver_for(spec: Any, root: Path) -> Any:
    from aero.adapters.precice.case import CoupledCaseSpec

    kinds = {"host_nfs_root": root, "remote_nfs_root": root}
    if isinstance(spec, CoupledCaseSpec):
        from aero.adapters.precice.solver import PreciceCoupledSolver

        return PreciceCoupledSolver(**kinds)
    module = type(spec).__module__
    if ".su2." in module:
        from aero.adapters.su2.solver import SU2Solver

        return SU2Solver(repo_root=REPO, **kinds)
    if ".pyfr." in module:
        from aero.adapters.pyfr.solver import PyFRSolver

        return PyFRSolver(repo_root=REPO, **kinds)
    if ".nekrs." in module:
        from aero.adapters.nekrs.solver import NekRSSolver

        return NekRSSolver(repo_root=REPO, **kinds)
    from aero.adapters.openfoam.solver import OpenFOAMSolver

    return OpenFOAMSolver(**kinds)


def _undeclared_dvc_opens(opened: list[str], declared: tuple[DeclaredInput, ...]) -> list[str]:
    outputs = [path for path, _ in _dvc_outputs(REPO)]
    allowed = {d.path for d in declared}
    hits = []
    for raw in opened:
        try:
            rel = Path(raw).resolve().relative_to(REPO).as_posix()
        except ValueError:
            continue
        if rel in allowed:
            continue
        if any(rel == out or rel.startswith(out + "/") for out in outputs):
            hits.append(rel)
    return hits


def test_no_case_opens_a_dvc_output_it_did_not_declare(tmp_path: Path) -> None:
    """Build the spec, stage the case and read the reference of every case that declares none.

    A frozen case whose assets are absent may refuse at staging; what it may never do is open a
    DVC output nobody declared.
    """
    from aero.vv._base import BenchmarkError
    from aero.vv.stacks import registered_cases

    # Refused, or absent from the checkout (the frozen PyFR assets): never read.
    absent = (ProvenanceError, FileNotFoundError, ValueError, BenchmarkError)
    checked = []
    for name, case in registered_cases().items():
        if case.dvc_inputs:
            continue
        for opened in _recording():
            spec = None
            with contextlib.suppress(*absent):
                spec = case.case_spec()
            if spec is not None:
                with contextlib.suppress(*absent):
                    _solver_for(spec, tmp_path / name).prepare(spec, provenance=run_tuple())
            with contextlib.suppress(*absent):
                case.reference(REPO)
            undeclared = _undeclared_dvc_opens(list(opened), ())
        assert undeclared == [], f"{name} opened undeclared DVC outputs: {undeclared}"
        checked.append(name)
    assert len(checked) == 21


def test_the_audit_sees_an_undeclared_open() -> None:
    """The detector above can fail: an open of a DVC output nobody declared is reported."""
    stl = str(REPO / "data/references/fsi/turek_hron_fsi3/cylinder_flag.stl")
    for opened in _recording():
        _audit("open", (stl, "rb", 0))
        hits = _undeclared_dvc_opens(list(opened), ())
        declared = _undeclared_dvc_opens(list(opened), resolve_declared(REPO, (CFD,)))
    assert hits == ["data/references/fsi/turek_hron_fsi3/cylinder_flag.stl"]
    assert declared == []
