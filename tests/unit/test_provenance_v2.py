"""The typed provenance tuple and its scheme labels (Stage 23; ADR-052 D4, ADR-053).

Everything here runs in the required unit job, which installs neither mlflow nor psycopg2: both are
replaced by `sys.modules` fakes. The hermetic suites under `tests/stage_04` and `tests/stage_20` ran
in no CI job, which is how their mirror-insert assertion went stale for a whole stage.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from aero.provenance import four_fold
from aero.provenance.four_fold import (
    EMPTY_DVC_INPUTS_DIGEST,
    AnyProvenanceTuple,
    ContainerRef,
    DeclaredInput,
    ProvenanceError,
    ProvenanceTuple,
    ProvenanceTupleV2,
    TermSchemes,
    canonical_dvc_inputs,
    dvc_inputs_digest,
)
from pydantic import BaseModel, TypeAdapter, ValidationError

pytestmark = pytest.mark.stage_23

REPO = Path(__file__).resolve().parents[2]
GIT = "0123456789abcdef0123456789abcdef01234567"
SHA_A, SHA_B, SHA_C = "a" * 64, "b" * 64, "c" * 64

#: Every legacy value recorded before Stage 23 that a new value must never equal.
LEGACY_DVC_VALUES = {
    hashlib.sha256(b"{}").hexdigest(),  # 44136fa3…, the empty status
    "7ec8590f5fb8607da8f64b854ef5a04322408ad76b72f14eea29f3adca66f092",  # data/vv, the crates
}

CFD2 = DeclaredInput(
    hash="md5",
    md5="3bcd781278f36f4d1640dc4665f71d23",
    path="data/references/fsi/turek_hron_fsi3/cylinder_flag.stl",
    size=66684,
)
FSI3 = DeclaredInput(
    hash="md5",
    md5="537c08749493c2d9a0658de508f9416c",
    path="data/references/fsi/turek_hron_fsi3/precice-tutorials-turek-hron-fsi3.tar.gz",
    size=75877,
)
ONERA = DeclaredInput(
    hash="md5",
    md5="4000194f1d7673017f6f8e11757618af",
    path="data/meshes/su2/onera_m6.su2",
    size=5959428,
)

V0 = TermSchemes(dvc_input_hash="repo-sync-state/v0", container_sif_sha256="sha256sums-lookup/v0")
V1 = TermSchemes(
    dvc_input_hash="declared-dvc-pointers-md5/v1",
    container_sif_sha256="sif-sha256-verified-at-launch/v1",
)


def _v2(**overrides: Any) -> ProvenanceTupleV2:
    fields: dict[str, Any] = {
        "git_sha": GIT,
        "dvc_input_hash": SHA_B,
        "container_sif_sha256": SHA_C,
        "config_hash": SHA_A,
        "container_sif_name": "openfoam-esi.sif",
        "dvc_inputs": None,
        "schemes": V0,
    }
    fields.update(overrides)
    return ProvenanceTupleV2(**fields)


# --- ADR-052 D2: the golden values ------------------------------------------------------------


def test_the_golden_digests_of_adr_052() -> None:
    assert EMPTY_DVC_INPUTS_DIGEST == (
        "1ef5b7d9a694e703ccb270937035bdcc006487fa5a5b6fd92ac9c10f94453ec3"
    )
    assert dvc_inputs_digest([CFD2]) == (
        "70b49f18e2fd314d3ec305433d74b4a2be494581fc05453f23b74cd66245e000"
    )
    assert dvc_inputs_digest([FSI3]) == (
        "5234c4dd598c00381ba4732930bef80a42729986d22f0619675ab0ee45c21659"
    )
    assert dvc_inputs_digest([ONERA]) == (
        "25b590aae4b2757b8597f8724297d84ed91a0bbf890ec558a44793fc07557c7f"
    )


def test_the_preimage_bytes_are_exactly_the_published_form() -> None:
    assert canonical_dvc_inputs([]) == b'{"inputs":[]}'
    assert canonical_dvc_inputs([CFD2]) == (
        b'{"inputs":[{"hash":"md5","md5":"3bcd781278f36f4d1640dc4665f71d23",'
        b'"path":"data/references/fsi/turek_hron_fsi3/cylinder_flag.stl","size":66684}]}'
    )
    assert four_fold.DVC_INPUTS_PREFIX == b"aero.dvc-inputs/v1\n"


def test_the_preimage_is_order_free_and_refuses_a_repeated_path() -> None:
    assert dvc_inputs_digest([CFD2, ONERA]) == dvc_inputs_digest([ONERA, CFD2])
    with pytest.raises(ProvenanceError, match="more than once"):
        dvc_inputs_digest([CFD2, CFD2])


def test_the_bare_pointer_path_is_not_the_definition() -> None:
    """`outs[].path` is relative to the pointer's directory; hashing it gives another value."""
    bare = CFD2.model_copy(update={"path": "cylinder_flag.stl"})
    assert dvc_inputs_digest([bare]) != dvc_inputs_digest([CFD2])


def test_no_new_value_equals_a_legacy_value() -> None:
    for value in (EMPTY_DVC_INPUTS_DIGEST, *(dvc_inputs_digest([i]) for i in (CFD2, FSI3, ONERA))):
        assert value not in LEGACY_DVC_VALUES


@pytest.mark.parametrize(
    "path", ["/abs/path.stl", "a/../b.stl", "./a.stl", "a//b.stl", "a\\b.stl", "a/./b.stl", ""]
)
def test_a_declared_path_stays_in_the_repository(path: str) -> None:
    with pytest.raises(ValidationError):
        DeclaredInput(hash="md5", md5="0" * 32, path=path, size=1)


def test_only_plain_byte_md5_is_declarable() -> None:
    with pytest.raises(ValidationError):
        DeclaredInput(hash="md5-dos2unix", md5="0" * 32, path="a.csv", size=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DeclaredInput(hash="md5", md5="0" * 32 + ".dir", path="a", size=1)


# --- ADR-052 D4: the typed tuple ---------------------------------------------------------------


def test_the_v2_tuple_is_not_a_legacy_tuple() -> None:
    """A subclass would be silently narrowed in a legacy field; an unrelated class is refused."""
    assert not issubclass(ProvenanceTupleV2, ProvenanceTuple)

    class _LegacyHolder(BaseModel):
        p: ProvenanceTuple

    with pytest.raises(ValidationError):
        _LegacyHolder(p=_v2())


def test_a_format_v1_crate_refuses_a_v2_tuple() -> None:
    from aero.crate.model import ProvenanceAvailable

    assert ProvenanceAvailable.model_fields["four_tuple"].annotation is ProvenanceTuple
    with pytest.raises(ValidationError):
        ProvenanceAvailable.model_validate(
            {"four_tuple": _v2().model_dump(), "code": {"git_sha": GIT}}
        )


def test_the_v0_dvc_term_carries_no_declaration() -> None:
    with pytest.raises(ValidationError, match="must be None"):
        _v2(dvc_inputs=())


def test_the_v1_dvc_term_must_hash_its_declaration() -> None:
    v1 = _v2(schemes=V1, dvc_inputs=(), dvc_input_hash=EMPTY_DVC_INPUTS_DIGEST)
    assert v1.dvc_inputs == ()
    with pytest.raises(ValidationError, match="needs dvc_inputs"):
        _v2(schemes=V1, dvc_inputs=None, dvc_input_hash=EMPTY_DVC_INPUTS_DIGEST)
    with pytest.raises(ValidationError, match="one object"):
        _v2(schemes=V1, dvc_inputs=(CFD2,), dvc_input_hash=EMPTY_DVC_INPUTS_DIGEST)


def test_the_container_of_record_is_the_roster_entry_with_the_digest() -> None:
    roster = (
        ContainerRef(name="calculix-precice.sif", sha256=SHA_A),
        ContainerRef(name="precice-fsi.sif", sha256=SHA_C),
    )
    _v2(container_sif_name="precice-fsi.sif", containers=roster)
    with pytest.raises(ValidationError, match="container of record"):
        _v2(container_sif_name="calculix-precice.sif", containers=roster)


def test_the_tags_keep_the_four_keys_and_name_the_schemes() -> None:
    tags = _v2().as_mlflow_tags()
    assert {
        k: tags[k] for k in ("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash")
    } == {
        "git_sha": GIT,
        "dvc_input_hash": SHA_B,
        "container_sif_sha256": SHA_C,
        "config_hash": SHA_A,
    }
    assert tags["dvc_input_hash_scheme"] == "repo-sync-state/v0"
    assert tags["container_sif_sha256_scheme"] == "sha256sums-lookup/v0"
    assert tags["container_sif_name"] == "openfoam-esi.sif"
    assert "dvc_inputs" not in tags and "container_sif_set" not in tags

    v1 = _v2(schemes=V1, dvc_inputs=(CFD2,), dvc_input_hash=dvc_inputs_digest([CFD2]))
    assert v1.as_mlflow_tags()["dvc_inputs"] == canonical_dvc_inputs([CFD2]).decode()


def test_an_overlong_dvc_inputs_tag_is_refused_not_truncated() -> None:
    many = tuple(
        DeclaredInput(hash="md5", md5="0" * 32, path=f"data/{'x' * 60}/{i:04d}.bin", size=1)
        for i in range(120)
    )
    v1 = _v2(schemes=V1, dvc_inputs=many, dvc_input_hash=dvc_inputs_digest(many))
    with pytest.raises(ProvenanceError, match="refusing rather than truncating"):
        v1.as_mlflow_tags()


def test_legacy_records_reload_as_legacy_and_v2_keeps_its_schemes() -> None:
    adapter: TypeAdapter[Any] = TypeAdapter(AnyProvenanceTuple)
    record = json.loads((REPO / "data/vv/stage18_turek_hron.json").read_text())["cfd2"][
        "benchmark"
    ]["provenance"]
    assert isinstance(adapter.validate_python(record), ProvenanceTuple)
    v2 = adapter.validate_python(json.loads(_v2().model_dump_json()))
    assert isinstance(v2, ProvenanceTupleV2) and v2.schemes == V0


def test_compute_provenance_labels_both_terms_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both terms v1 since Stage 23: ADR-052 (PR 7) and ADR-053 (PR 6)."""
    checked: list[Path] = []
    monkeypatch.setattr(four_fold, "git_sha", lambda repo_root, allow_dirty=False: GIT)
    monkeypatch.setattr(four_fold, "container_sif_sha256", lambda repo_root, sif: SHA_C)
    monkeypatch.setattr(four_fold, "sha256sums_at_head", checked.append)
    prov = four_fold.compute_provenance(
        repo_root=REPO,
        container_sif="/opt/aero/containers/openfoam-esi.sif",
        resolved_config={},
        dvc_inputs=("data/references/fsi/turek_hron_fsi3/cylinder_flag.stl.dvc",),
    )
    assert isinstance(prov, ProvenanceTupleV2)
    assert prov.schemes == V1
    assert prov.dvc_inputs == (CFD2,)
    assert prov.dvc_input_hash == (
        "70b49f18e2fd314d3ec305433d74b4a2be494581fc05453f23b74cd66245e000"
    )
    assert prov.container_sif_name == "openfoam-esi.sif"
    # SHA256SUMS must equal HEAD's, even for an --allow-dirty run (ADR-053).
    assert checked == [REPO]


def test_the_repository_wide_dvc_status_digest_is_gone() -> None:
    """ADR-052: nothing computes `repo-sync-state/v0` any more, and the declaration is required."""
    import inspect

    assert not hasattr(four_fold, "dvc_input_hash")
    param = inspect.signature(four_fold.compute_provenance).parameters["dvc_inputs"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


# --- the writers: MLflow and the Postgres mirror -------------------------------------------------


class _Cursor:
    def __init__(self, calls: list[tuple[str, tuple[Any, ...]]]) -> None:
        self.calls = calls

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.calls.append((sql, params))


class _Conn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def cursor(self) -> _Cursor:
        return _Cursor(self.calls)

    def close(self) -> None:
        pass


@pytest.fixture
def fake_psycopg2(monkeypatch: pytest.MonkeyPatch) -> _Conn:
    conn = _Conn()
    module = types.ModuleType("psycopg2")
    module.Error = Exception  # type: ignore[attr-defined]
    module.connect = lambda dsn: conn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg2", module)
    return conn


def test_the_mirror_writes_nine_columns_in_order(fake_psycopg2: _Conn) -> None:
    from aero.provenance.db import _INSERT_SQL, mirror_provenance_row

    columns = _INSERT_SQL.split("(", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
    assert columns == [
        "run_id",
        "git_sha",
        "dvc_input_hash",
        "container_sif_sha256",
        "config_hash",
        "container_sif_set",
        "dvc_input_hash_scheme",
        "container_sif_sha256_scheme",
        "dvc_inputs",
    ]
    assert _INSERT_SQL.count("%s") == len(columns)

    mirror_provenance_row(run_id="r0", provenance=_v2(), db_dsn="postgresql://x")
    v1 = _v2(schemes=V1, dvc_inputs=(CFD2,), dvc_input_hash=dvc_inputs_digest([CFD2]))
    mirror_provenance_row(run_id="r1", provenance=v1, db_dsn="postgresql://x")
    (_, p0), (_, p1) = fake_psycopg2.calls
    assert p0 == (
        "r0",
        GIT,
        SHA_B,
        SHA_C,
        SHA_A,
        None,
        "repo-sync-state/v0",
        "sha256sums-lookup/v0",
        None,
    )
    assert p1[6:] == (
        "declared-dvc-pointers-md5/v1",
        "sif-sha256-verified-at-launch/v1",
        canonical_dvc_inputs([CFD2]).decode(),
    )


@pytest.fixture
def fake_mlflow(monkeypatch: pytest.MonkeyPatch, fake_psycopg2: _Conn) -> dict[str, Any]:
    recorded: dict[str, Any] = {}
    module = types.ModuleType("mlflow")

    @contextmanager
    def start_run() -> Iterator[Any]:
        yield types.SimpleNamespace(info=types.SimpleNamespace(run_id="run-1"))

    module.set_tracking_uri = lambda uri: recorded.update(uri=uri)  # type: ignore[attr-defined]
    module.set_experiment = lambda exp: recorded.update(exp=exp)  # type: ignore[attr-defined]
    module.start_run = start_run  # type: ignore[attr-defined]
    module.set_tags = lambda tags: recorded.update(tags=tags)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlflow", module)
    return recorded


def _start(provenance: Any, **kwargs: Any) -> Any:
    from aero.provenance.mlflow import start_provenance_run

    return start_provenance_run(
        tracking_uri="http://aero-mlflow:5000",
        experiment="aero-provenance",
        provenance=provenance,
        case_name="blasius_flat_plate",
        db_dsn="postgresql://x",
        **kwargs,
    )


def test_a_run_is_logged_with_its_schemes(fake_mlflow: dict[str, Any]) -> None:
    with _start(_v2()) as run:
        assert run.info.run_id == "run-1"
    assert fake_mlflow["tags"]["dvc_input_hash_scheme"] == "repo-sync-state/v0"
    assert fake_mlflow["tags"]["case_name"] == "blasius_flat_plate"


def test_a_legacy_tuple_is_never_logged(fake_mlflow: dict[str, Any]) -> None:
    legacy = ProvenanceTuple(
        git_sha=GIT, dvc_input_hash=SHA_B, container_sif_sha256=SHA_C, config_hash=SHA_A
    )
    with pytest.raises(ProvenanceError, match="needs a ProvenanceTupleV2"), _start(legacy):
        pass
    assert "tags" not in fake_mlflow


def test_an_extra_tag_cannot_shadow_a_scheme(fake_mlflow: dict[str, Any]) -> None:
    with (
        pytest.raises(ProvenanceError, match="would overwrite"),
        _start(_v2(), extra_tags={"dvc_input_hash_scheme": "declared-dvc-pointers-md5/v1"}),
    ):
        pass


_PROVENANCE_KEYS = {
    "git_sha",
    "dvc_input_hash",
    "container_sif_sha256",
    "config_hash",
    "container_sif_set",
    *four_fold.SCHEME_TAG_KEYS,
    "dvc_inputs",
}


def test_no_code_sets_provenance_tags_on_an_existing_run() -> None:
    """Relabelling a recorded run is a tag write on an existing run id (ADR-052: never).

    Only `start_provenance_run` writes provenance tags, through the fluent API on the run it
    opened. A client-side `set_tag(run_id, key, ...)` is allowed only for a non-provenance key
    named as a literal (e.g. the CC-BY-NC taint tags of the DrivAerNet++ loader).
    """
    offenders = []
    for path in sorted((REPO / "aero").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "mlflow":
                continue
            where = f"{path.relative_to(REPO)}:{node.lineno}"
            if node.func.attr == "set_tags":
                offenders.append(where)
            elif node.func.attr == "set_tag":
                key = node.args[1] if len(node.args) > 1 else None
                if not (isinstance(key, ast.Constant) and key.value not in _PROVENANCE_KEYS):
                    offenders.append(where)
    assert offenders == [], f"provenance tag writes on an existing run: {offenders}"


# --- the V&V runner and the mesh sweep ---------------------------------------------------------


class _Spec(BaseModel):
    n: int


class _Case:
    name = "fake_case"
    sweep_metric = "cd"
    dvc_inputs: tuple[str, ...] = ()

    def __init__(self, n: int = 1) -> None:
        self._spec = _Spec(n=n)

    def case_spec(self) -> _Spec:
        return self._spec

    def refined(self, ratio: float) -> _Case:
        return _Case(n=round(10 / ratio))  # a larger ratio is a coarser grid


def _tuple_for(case: _Case) -> ProvenanceTupleV2:
    return _v2(
        config_hash=four_fold.config_hash(case.case_spec().model_dump(mode="json")),
        schemes=V1,
        dvc_inputs=(),
        dvc_input_hash=EMPTY_DVC_INPUTS_DIGEST,
    )


def test_the_runner_refuses_a_tuple_of_another_spec() -> None:
    from aero.vv._base import _check_tuple_describes

    case = _Case(n=1)
    _check_tuple_describes(case, _tuple_for(case), REPO)  # type: ignore[arg-type]
    with pytest.raises(ProvenanceError, match="one tuple per solved spec"):
        _check_tuple_describes(case, _tuple_for(_Case(n=2)), REPO)  # type: ignore[arg-type]


def test_the_runner_refuses_a_tuple_whose_inputs_are_not_the_declaration() -> None:
    """ADR-052 D1: the hash names exactly what staging may read, so it must be the declaration."""
    from aero.vv._base import _check_tuple_describes

    case = _Case(n=1)
    undeclared = _tuple_for(case).model_copy(
        update={"dvc_inputs": (CFD2,), "dvc_input_hash": dvc_inputs_digest([CFD2])}
    )
    with pytest.raises(ProvenanceError, match="not the case's declaration"):
        _check_tuple_describes(case, undeclared, REPO)  # type: ignore[arg-type]
    with pytest.raises(ProvenanceError, match="none recorded"):
        _check_tuple_describes(case, _v2(config_hash=_tuple_for(case).config_hash), REPO)  # type: ignore[arg-type]


def test_the_mesh_sweep_computes_one_tuple_per_grid() -> None:
    from aero.vv._base import ScalarObservation
    from aero.vv.mesh_sweep import MeshSweep

    seen: list[tuple[int, str]] = []

    class _Runner:
        def measure_scalar(
            self, case: _Case, metric: str, *, provenance: Any, repo_root: Any
        ) -> Any:
            seen.append((case.case_spec().n, provenance.config_hash))
            n = case.case_spec().n
            return ScalarObservation(metric=metric, value=1.0 + 1.0 / n**2, n_elements=n * n)

    MeshSweep(_Case(), metric="cd").run(  # type: ignore[arg-type]
        _Runner(),  # type: ignore[arg-type]
        provenance_of=_tuple_for,  # type: ignore[arg-type]
        repo_root=REPO,
    )
    assert [n for n, _ in seen] == [10, 8, 6]
    assert len({h for _, h in seen}) == 3, "each grid needs its own config_hash"


# --- the historical drivers ----------------------------------------------------------------------

#: Ported to the typed tuple; every other driver that computes provenance refuses (ledgered).
PORTED_DRIVERS = {"stage11_moving_vv.py", "stage18_turek_hron.py"}


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) == name or getattr(n.func, "attr", None) == name)
    ]


def test_every_unported_driver_refuses_before_it_records() -> None:
    drivers = sorted(
        p
        for p in (REPO / "scripts").glob("*.py")
        if _calls(ast.parse(p.read_text()), "compute_provenance")
    )
    assert {p.name for p in drivers} >= PORTED_DRIVERS
    for path in drivers:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        refused = _calls(tree, "refuse_unported_driver")
        if path.name in PORTED_DRIVERS:
            assert not refused, f"{path.name} is ported and must not refuse"
            continue
        assert refused, f"{path.name} computes provenance but neither is ported nor refuses"
        # The refusal comes first in the function that would record anything.
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            if _calls(fn, "compute_provenance") and fn.name != "main":
                first_calls = [c for s in fn.body[:4] for c in _calls(s, "refuse_unported_driver")]
                main = next(
                    n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"
                )
                in_main = [c for s in main.body[:4] for c in _calls(s, "refuse_unported_driver")]
                assert first_calls or in_main, f"{path.name}:{fn.name} records before refusing"
