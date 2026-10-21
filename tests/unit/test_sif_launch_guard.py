"""ADR-053 — the SIF is re-hashed on the solve host before every launch (O-08).

The guard is shell that runs in front of `apptainer exec`, so most of these tests run it: a fake
executor executes the command in a local `bash`, with a fake `apptainer` on `PATH` that records
each invocation, against a stand-in SIF in a temp directory. A matching SIF launches exactly once;
a same-name swap, a missing file, or a SIF the tuple does not name never reaches apptainer, and
the refusal is a `ProvenanceError`, never a solver failure.
"""

from __future__ import annotations

import ast
import hashlib
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
from aero.adapters._base import (
    SIF_REFUSED_EXIT,
    SifPin,
    assert_launches_guarded,
    build_apptainer_exec,
    raise_if_container_refused,
    sif_guard,
)
from aero.adapters.openfoam.schemas import CaseSpec
from aero.adapters.openfoam.solver import OpenFOAMSolver
from aero.orchestration._base import ExecResult
from aero.provenance import four_fold
from aero.provenance.four_fold import (
    ProvenanceError,
    ProvenanceTupleV2,
    read_sha256sums,
    sha256sums_at_head,
)
from pydantic import BaseModel, ValidationError

from tests.unit._launch_fixtures import REPO, SUMS, V1_CONTAINER, case_dir, run_tuple

pytestmark = pytest.mark.stage_23

_SPEC = CaseSpec(name="naca0012", reynolds=6.0e6, mach=0.15, aoa_deg=0.0)

# Stands in for `apptainer exec [flags] --bind SRC:TGT SIF bash -lc 'CMD'`: records the call,
# then runs CMD with the bind target rewritten to the source, as the container would see it.
_FAKE_APPTAINER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AERO_FAKE_APPTAINER_LOG"
shift
src=
while [[ "${1:-}" == --* ]]; do
  if [[ "$1" == "--bind" ]]; then src="${2%%:*}"; shift 2; else shift; fi
done
shift
shift 2
exec bash -c "${1//\\/case/$src}"
"""

# A blockMesh that writes what OpenFOAMSolver.mesh checks for.
_FAKE_BLOCKMESH = """#!/usr/bin/env bash
mkdir -p constant/polyMesh && : > constant/polyMesh/points && echo "  nCells: 42"
"""


def _executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class _LocalBash:
    """An `Executor` that runs the command in a local bash: the guard really executes."""

    def __init__(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _executable(bin_dir / "apptainer", _FAKE_APPTAINER)
        _executable(bin_dir / "blockMesh", _FAKE_BLOCKMESH)
        self.apptainer_log = tmp_path / "apptainer.calls"
        self.env = dict(
            os.environ,
            PATH=f"{bin_dir}:{os.environ['PATH']}",
            AERO_FAKE_APPTAINER_LOG=str(self.apptainer_log),
        )
        self.commands: list[str] = []
        self.results: list[ExecResult] = []

    def run(self, command: str, **kwargs: Any) -> ExecResult:
        self.commands.append(command)
        proc = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=60,
            check=False,
        )
        result = ExecResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_s=0.0,
            host="local-bash",
        )
        self.results.append(result)
        return result

    @property
    def apptainer_calls(self) -> list[str]:
        if not self.apptainer_log.is_file():
            return []
        return self.apptainer_log.read_text(encoding="utf-8").splitlines()


def _sif(tmp_path: Path, name: str = "openfoam-esi.sif", content: bytes = b"sif v1\n") -> Path:
    path = tmp_path / "containers" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _tuple(name: str, digest: str) -> ProvenanceTupleV2:
    return ProvenanceTupleV2(
        git_sha="0" * 40,
        dvc_input_hash="b" * 64,
        container_sif_sha256=digest,
        config_hash="a" * 64,
        container_sif_name=name,
        dvc_inputs=None,
        schemes=V1_CONTAINER,
    )


def _openfoam(tmp_path: Path, sif: Path) -> tuple[OpenFOAMSolver, Any]:
    # The NFS roots coincide, so the bind source is a real local directory.
    solver = OpenFOAMSolver(sif_path=str(sif), host_nfs_root=tmp_path, remote_nfs_root=tmp_path)
    spec = CaseSpec(name="naca0012", reynolds=6.0e6, mach=0.15, aoa_deg=0.0)
    digest = hashlib.sha256(sif.read_bytes()).hexdigest()
    return solver, solver.prepare(spec, provenance=_tuple(sif.name, digest))


# --- through a real adapter -------------------------------------------------------------------


def test_a_matching_sif_launches_exactly_once_and_says_so(tmp_path: Path) -> None:
    sif = _sif(tmp_path)
    solver, case = _openfoam(tmp_path, sif)
    executor = _LocalBash(tmp_path)

    mesh = solver.mesh(case, executor)  # type: ignore[arg-type]

    assert mesh.ok and mesh.n_elements == 42
    assert len(executor.apptainer_calls) == 1
    (command,) = executor.commands
    assert command.count("apptainer exec ") == 1
    digest = hashlib.sha256(sif.read_bytes()).hexdigest()
    (result,) = executor.results
    assert f"AERO-SIF-VERIFIED sha256={digest} path={sif}" in result.stderr.splitlines()
    assert case.guarded_launches == 1


def test_the_verified_line_is_in_the_launchs_captured_output(tmp_path: Path) -> None:
    sif = _sif(tmp_path)
    digest = hashlib.sha256(sif.read_bytes()).hexdigest()
    result = _LocalBash(tmp_path).run(
        build_apptainer_exec(
            expected=SifPin(path=str(sif), sha256=digest),
            case_bind_source=str(tmp_path),
            command="true",
        )
    )
    assert result.returncode == 0
    assert result.stderr.splitlines()[0] == f"AERO-SIF-VERIFIED sha256={digest} path={sif}"
    raise_if_container_refused(result)  # a verified launch is not a refusal


def test_a_same_name_swap_is_refused_before_apptainer_starts(tmp_path: Path) -> None:
    """The case a basename lookup cannot see: a SIF rebuilt under the name it was recorded as."""
    sif = _sif(tmp_path)
    solver, case = _openfoam(tmp_path, sif)
    sif.write_bytes(b"sif v2, same name\n")
    executor = _LocalBash(tmp_path)

    with pytest.raises(ProvenanceError, match="AERO-SIF-REFUSED expected="):
        solver.mesh(case, executor)  # type: ignore[arg-type]

    assert executor.apptainer_calls == []
    assert not (case.host_path / "constant" / "polyMesh" / "points").exists()


def test_a_missing_sif_is_refused(tmp_path: Path) -> None:
    sif = _sif(tmp_path)
    solver, case = _openfoam(tmp_path, sif)
    sif.unlink()
    executor = _LocalBash(tmp_path)
    with pytest.raises(ProvenanceError, match="AERO-SIF-REFUSED"):
        solver.mesh(case, executor)  # type: ignore[arg-type]
    assert executor.apptainer_calls == []


def test_the_refusal_is_exit_86_with_one_line_naming_the_digest_and_path(tmp_path: Path) -> None:
    sif = _sif(tmp_path)
    pin = SifPin(path=str(sif), sha256="0" * 64)
    result = _LocalBash(tmp_path).run(
        build_apptainer_exec(expected=pin, case_bind_source=str(tmp_path), command="true")
    )
    assert result.returncode == SIF_REFUSED_EXIT == 86
    assert result.stderr.strip() == f"AERO-SIF-REFUSED expected={'0' * 64} path={sif}"


def test_a_solver_the_tuple_does_not_name_is_refused_before_any_command(tmp_path: Path) -> None:
    """`aero run --solver su2` with the OpenFOAM SIF configured used to record the OpenFOAM
    digest while SU2 ran. The pin is refused before a command is built."""
    from aero.adapters.su2.solver import SU2Solver

    solver = SU2Solver(host_nfs_root=tmp_path, remote_nfs_root=tmp_path)
    spec = CaseSpec(name="naca0012", reynolds=6.0e6, mach=0.15, aoa_deg=0.0)
    case = solver.prepare(spec, provenance=run_tuple("openfoam-esi.sif"))
    executor = _LocalBash(tmp_path)
    with pytest.raises(ProvenanceError, match=r"'su2-v8\.sif' is not a container"):
        solver.run(case, executor)  # type: ignore[arg-type]
    assert executor.commands == []
    assert case.guarded_launches == 0


# --- the pin and the guard bytes --------------------------------------------------------------


def test_the_roster_pins_each_of_its_containers_and_nothing_else(tmp_path: Path) -> None:
    case = case_dir(_SPEC, tmp_path, sif="precice-fsi.sif", extra=("calculix-precice.sif",))
    fluid = case.pin("/opt/aero/containers/precice-fsi.sif")
    solid = case.pin("/opt/aero/containers/calculix-precice.sif")
    assert (fluid.sha256, solid.sha256) == (SUMS["precice-fsi.sif"], SUMS["calculix-precice.sif"])
    assert case.guarded_launches == 2
    with pytest.raises(ProvenanceError, match=r"calculix-precice-adr045\.sif"):
        case.pin("/opt/aero/containers/calculix-precice-adr045.sif")
    assert case.guarded_launches == 2


@pytest.mark.parametrize(
    "digest", ["c" * 63, "C" * 64, "g" * 64, "c" * 64 + "c", "$(id)" + "c" * 59]
)
def test_a_pin_takes_only_a_64_hex_lowercase_digest(digest: str) -> None:
    with pytest.raises(ValidationError):
        SifPin(path="/x.sif", sha256=digest)


def test_a_pin_path_may_not_contain_a_line_break() -> None:
    with pytest.raises(ValidationError, match="line break"):
        SifPin(path="/x\n.sif", sha256="c" * 64)


def test_hex_and_path_are_printf_arguments_never_the_format(tmp_path: Path) -> None:
    """A path with a space and a `%` survives: it is a quoted argument, not format bytes."""
    odd = tmp_path / "odd dir %s %n"
    sif = _sif(odd)
    good = SifPin(path=str(sif), sha256=hashlib.sha256(sif.read_bytes()).hexdigest())
    executor = _LocalBash(tmp_path)
    ok = executor.run(f"{sif_guard(good)}echo LAUNCHED")
    assert ok.returncode == 0 and ok.stdout.strip() == "LAUNCHED"
    assert ok.stderr.strip() == f"AERO-SIF-VERIFIED sha256={good.sha256} path={sif}"
    bad = executor.run(f"{sif_guard(good.model_copy(update={'sha256': '0' * 64}))}echo LAUNCHED")
    assert bad.returncode == 86 and "LAUNCHED" not in bad.stdout
    assert bad.stderr.strip() == f"AERO-SIF-REFUSED expected={'0' * 64} path={sif}"


def test_the_guard_never_contains_the_launch_literal() -> None:
    """The `--no-home` splice and any reader of the command find the real launch first."""
    assert "apptainer exec" not in sif_guard(SifPin(path="/opt/x.sif", sha256="c" * 64))


@pytest.mark.parametrize("stream", ["stderr", "stdout"])
def test_a_refusal_is_found_in_either_stream(stream: str) -> None:
    """Synchronous launches return it on stderr; a detached one's output.log merges both."""
    line = "AERO-SIF-REFUSED expected=abc path=/x.sif"
    result = ExecResult(command="c", returncode=86, duration_s=0.0, host="h", **{stream: line})
    with pytest.raises(ProvenanceError, match=line):
        raise_if_container_refused(result)


def test_a_refusal_is_found_in_a_result_handles_solver_log() -> None:
    class _Handle(BaseModel):
        solver_log: str

    with pytest.raises(ProvenanceError):
        raise_if_container_refused(_Handle(solver_log="x\nAERO-SIF-REFUSED expected=a path=b\n"))
    raise_if_container_refused(_Handle(solver_log="AERO-SIF-VERIFIED sha256=a path=b\n"))


# --- the record: no v1 claim without a guarded launch -------------------------------------------


def test_a_v1_record_needs_a_guarded_launch(tmp_path: Path) -> None:
    case = case_dir(_SPEC, tmp_path)
    with pytest.raises(ProvenanceError, match="no launch of this run went through the SIF guard"):
        assert_launches_guarded(case, case.provenance)
    case.pin("/opt/aero/containers/openfoam-esi.sif")
    assert_launches_guarded(case, case.provenance)


def test_the_recorded_tuple_must_be_the_one_the_case_was_pinned_from(tmp_path: Path) -> None:
    case = case_dir(_SPEC, tmp_path)
    case.pin("/opt/aero/containers/openfoam-esi.sif")
    other = run_tuple(config_hash="d" * 64)
    with pytest.raises(ProvenanceError, match="not the one the case was prepared with"):
        assert_launches_guarded(case, other)


class _Case:
    name = "fake_case"

    def case_spec(self) -> CaseSpec:
        return _SPEC

    def evaluate(self, solver: Any, result: Any) -> dict[str, float]:
        return {"cd": 0.01}


class _UnguardedSolver:
    """Prepares and 'solves' without pinning anything: a solver that skips the guard."""

    def prepare(self, case: Any, *, provenance: ProvenanceTupleV2) -> Any:
        return case_dir(case, Path("/tmp/unguarded"), provenance=provenance)

    def mesh(self, case_dir: Any, executor: Any) -> Any:
        return type("M", (), {"ok": True, "n_elements": 1})()

    def run(self, case_dir: Any, executor: Any) -> Any:
        return type("R", (), {"returncode": 0, "solver_log": ""})()


def _runner(solver: Any) -> Any:
    from aero.vv._base import BenchmarkRunner

    return BenchmarkRunner(
        solver=solver,
        executor=None,  # type: ignore[arg-type]
        tracking_uri="unused",
        experiment="unused",
        db_dsn="unused",
        solver_version="fake",
    )


def test_the_runner_refuses_to_record_a_run_whose_launches_were_not_guarded() -> None:
    with pytest.raises(ProvenanceError, match="no launch of this run went through the SIF guard"):
        _runner(_UnguardedSolver())._drive(_Case(), run_tuple())


def test_the_runner_needs_the_typed_tuple_to_pin_from() -> None:
    from aero.provenance.four_fold import ProvenanceTuple

    legacy = ProvenanceTuple(
        git_sha="0" * 40,
        dvc_input_hash="b" * 64,
        container_sif_sha256="c" * 64,
        config_hash="a" * 64,
    )
    with pytest.raises(ProvenanceError, match="pinned from it"):
        _runner(_UnguardedSolver())._drive(_Case(), legacy)


def test_the_runner_reads_a_refusal_before_the_return_code() -> None:
    class _Refused(_UnguardedSolver):
        def run(self, case_dir: Any, executor: Any) -> Any:
            return type("R", (), {"returncode": 86, "solver_log": "AERO-SIF-REFUSED e=a p=b"})()

    with pytest.raises(ProvenanceError, match="AERO-SIF-REFUSED"):
        _runner(_Refused())._drive(_Case(), run_tuple())


# --- SHA256SUMS: the strict parser, and HEAD's copy -------------------------------------------


def test_the_committed_sha256sums_parses_strictly() -> None:
    sums = read_sha256sums(REPO)
    assert len(sums) == 13
    assert sums["openfoam-esi.sif"] == (
        "c9d7f32974c66bfbc924d407193bbf488fa165b2b35b01ee21ed9fdf9606e91c"
    )
    # The two-token comment `# containers/SHA256SUMS` is a comment, not a `#` digest.
    assert "containers/SHA256SUMS" not in sums


def _sums(tmp_path: Path, body: str) -> Path:
    (tmp_path / "containers").mkdir(exist_ok=True)
    (tmp_path / "containers" / "SHA256SUMS").write_text(body, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("body", "match"),
    [
        (f"{'c' * 64}  a.sif\n{'d' * 64}  a.sif\n", "listed twice"),
        (f"{'C' * 64}  a.sif\n", "not a `<sha256> <name>` entry"),
        (f"{'c' * 64}  a.sif  extra\n", "not a `<sha256> <name>` entry"),
        ("deadbeef  a.sif\n", "not a `<sha256> <name>` entry"),
    ],
)
def test_a_malformed_or_ambiguous_sha256sums_is_refused(
    tmp_path: Path, body: str, match: str
) -> None:
    with pytest.raises(ProvenanceError, match=match):
        read_sha256sums(_sums(tmp_path, body))


def test_comments_and_blank_lines_are_skipped(tmp_path: Path) -> None:
    root = _sums(tmp_path, f"# containers/SHA256SUMS\n\n   # x y\n{'c' * 64}  a.sif\n")
    assert read_sha256sums(root) == {"a.sif": "c" * 64}


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def test_sha256sums_must_equal_heads_even_for_a_dirty_run(tmp_path: Path) -> None:
    root = _sums(tmp_path, f"{'c' * 64}  a.sif\n")
    _git(root, "init", "-q")
    with pytest.raises(ProvenanceError, match="not committed at HEAD"):
        sha256sums_at_head(root)
    _git(root, "add", "containers/SHA256SUMS")
    _git(root, "commit", "-q", "-m", "sums")
    sha256sums_at_head(root)
    _sums(root, f"{'d' * 64}  a.sif\n")
    with pytest.raises(ProvenanceError, match="differs from HEAD's"):
        sha256sums_at_head(root)


def test_compute_provenance_checks_sha256sums_before_anything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(repo_root: Path) -> None:
        raise ProvenanceError("differs from HEAD's")

    monkeypatch.setattr(four_fold, "sha256sums_at_head", refuse)
    monkeypatch.setattr(four_fold, "git_sha", lambda *a, **k: pytest.fail("git_sha ran first"))
    with pytest.raises(ProvenanceError, match="differs from HEAD's"):
        four_fold.compute_provenance(
            repo_root=REPO, container_sif="openfoam-esi.sif", resolved_config={}, allow_dirty=True
        )


# --- refused paths (ADR-053, ledgered) ---------------------------------------------------------


def _cli(*args: str) -> Any:
    import aero.cli as aero_cli
    from typer.testing import CliRunner

    return CliRunner().invoke(aero_cli.app, list(args))


@pytest.mark.parametrize(
    "args",
    [
        ("run", "naca0012", "--executor", "runpod"),
        ("vv", "run", "--case", "blasius_flat_plate", "--executor", "runpod"),
        ("surrogate", "train", "--baseline", "mlp_baseline"),
        ("surrogate", "train", "--baseline", "domino", "--executor", "runpod"),
    ],
)
def test_the_paths_that_cannot_guard_a_launch_are_refused(args: tuple[str, ...]) -> None:
    result = _cli(*args)
    assert result.exit_code == 4, result.output
    assert "refused" in result.output and "ADR-053" in result.output


def test_the_in_process_jax_gradient_records_no_container() -> None:
    """`differentiable_run` launches no SIF, so its result may carry no tuple to claim one."""
    from aero.adapters.jax_fluids.schemas import JaxGradientResult

    assert not {"provenance", "container_sif_sha256"} & set(JaxGradientResult.model_fields)


# --- hygiene: every launch in aero/ is guarded ---------------------------------------------------


def _functions(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) == name or getattr(n.func, "attr", None) == name)
    ]


def test_every_build_apptainer_exec_call_is_pinned_and_its_result_checked() -> None:
    unpinned, unchecked = [], []
    for path in sorted((REPO / "aero").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _functions(tree):
            builds = _calls(fn, "build_apptainer_exec")
            for call in builds:
                if "expected" not in {k.arg for k in call.keywords}:
                    unpinned.append(f"{path.relative_to(REPO)}:{call.lineno}")
            runs = [c for c in _calls(fn, "run") if isinstance(c.func, ast.Attribute)]
            if builds and runs and not _calls(fn, "raise_if_container_refused"):
                unchecked.append(f"{path.relative_to(REPO)}:{fn.name}")
    assert unpinned == [], f"build_apptainer_exec without expected=: {unpinned}"
    assert unchecked == [], f"a guarded launch whose result is never checked: {unchecked}"


def test_no_launch_line_is_built_by_hand() -> None:
    """Outside the builder, the only literal launch is the refused DoMINO hand launch."""
    found = []
    for path in sorted((REPO / "aero").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef)
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
        }
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and "apptainer exec" in n.value
                and id(n) not in docs
            ):
                found.append(str(path.relative_to(REPO)))
    assert sorted(found) == ["aero/adapters/_base.py", "aero/cli.py"]


#: Drivers that launch through the adapters and are ported to the guarded path.
PORTED_LAUNCHERS = {"stage11_moving_vv.py", "stage18_turek_hron.py"}
_LAUNCH_SEAMS = (
    "build_apptainer_exec",
    "build_participant_command",
    "mesh_with_ladder",
    "launch_coupled",
    "prepare",
)


def test_every_script_that_launches_is_ported_or_refuses() -> None:
    for path in sorted((REPO / "scripts").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not any(_calls(tree, seam) for seam in _LAUNCH_SEAMS):
            continue
        refused = bool(_calls(tree, "refuse_unported_driver"))
        if path.name in PORTED_LAUNCHERS:
            assert not refused, f"{path.name} is ported and must not refuse"
        else:
            assert refused, f"{path.name} launches a SIF but is neither ported nor refused"
