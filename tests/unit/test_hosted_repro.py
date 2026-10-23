"""ADR-050 — the hosted reproducibility check's executor, driver and band (Stage 23, PR 8a).

The hosted run itself happens only in `hosted-repro.yml`, after its cluster reference is committed.
Here: `LocalContainerExecutor` keeps the `Executor` contract, the ADR-053 guard holds through it,
the runner logs `cf_mid` in the same run, and the band and the reference are pure functions of the
records, pinned on their edges.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from aero.adapters._base import SifPin, build_apptainer_exec, raise_if_container_refused
from aero.orchestration import Executor, LocalContainerExecutor
from aero.provenance.four_fold import EMPTY_DVC_INPUTS_DIGEST, ProvenanceError, config_hash

from tests.unit._launch_fixtures import REPO, SUMS

pytestmark = pytest.mark.stage_23

sys.path.insert(0, str(REPO / "scripts"))
import hosted_repro  # noqa: E402

# --- LocalContainerExecutor ---------------------------------------------------------------------


def test_it_is_an_executor_and_names_this_host() -> None:
    executor = LocalContainerExecutor()
    assert isinstance(executor, Executor)
    assert executor.host.startswith("local:")


def test_a_nonzero_exit_is_returned_with_both_streams() -> None:
    result = LocalContainerExecutor().run("echo out; echo err >&2; exit 3")
    assert (result.returncode, result.stdout, result.stderr) == (3, "out", "err")
    assert not result.transport_failed


def test_a_long_job_merges_its_streams_as_a_detached_job_does() -> None:
    """run_long.sh's output.log holds both streams, so a detached refusal is found in stdout."""
    result = LocalContainerExecutor().run("echo out; echo err >&2", long_running=True)
    assert result.stdout.splitlines() == ["out", "err"]
    assert result.stderr == ""


def test_a_timeout_is_rc_124_and_stops_the_whole_tree(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    started = time.monotonic()
    result = LocalContainerExecutor().run(f"sleep 60 & echo $! > {pid_file}; wait", timeout_s=2)
    assert result.returncode == 124 and "timed out after 2s" in result.stderr
    assert time.monotonic() - started < 30
    child = int(pid_file.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)  # the grandchild died with its process group


def test_a_shell_that_cannot_start_is_a_transport_error() -> None:
    result = LocalContainerExecutor(shell="/nonexistent/bash").run("true")
    assert result.returncode == 127 and result.transport_failed


def test_the_launch_guard_holds_through_it(tmp_path: Path) -> None:
    """The adapter's command runs unchanged: a match launches, a same-name swap exits 86."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "apptainer"
    shim.write_text('#!/usr/bin/env bash\necho LAUNCHED "$@"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    sif = tmp_path / "openfoam-esi.sif"
    sif.write_bytes(b"image\n")
    pin = SifPin(path=str(sif), sha256=hashlib.sha256(b"image\n").hexdigest())
    command = build_apptainer_exec(expected=pin, case_bind_source=str(tmp_path), command="true")
    path = os.environ["PATH"]
    os.environ["PATH"] = f"{bin_dir}:{path}"
    try:
        ok = LocalContainerExecutor().run(command, long_running=True)
        sif.write_bytes(b"other!\n")
        refused = LocalContainerExecutor().run(command, long_running=True)
    finally:
        os.environ["PATH"] = path
    assert ok.returncode == 0 and "LAUNCHED exec" in ok.stdout
    raise_if_container_refused(ok)
    assert refused.returncode == 86 and "LAUNCHED" not in refused.stdout
    with pytest.raises(ProvenanceError, match="AERO-SIF-REFUSED"):
        raise_if_container_refused(refused)


# --- the case and its terms (ADR-050 D1/D3) -----------------------------------------------------


def test_the_hosted_case_has_the_adrs_terms() -> None:
    from aero.vv.forward_regime.blasius_flat_plate import BlasiusFlatPlate

    case = BlasiusFlatPlate()
    assert case.sweep_metric == "cf_mid" and case.dvc_inputs == ()
    assert config_hash(case.case_spec().model_dump(mode="json")) == (
        "d1d264c56c893e2120178e076f1064b39dabb51ea37726bca958fdd05e459442"
    )
    assert SUMS[hosted_repro.SIF_NAME].startswith("c9d7f329")
    assert EMPTY_DVC_INPUTS_DIGEST.startswith("1ef5b7d9")


# --- the runner logs the named scalar in the same run --------------------------------------------


class _Case:
    name = "blasius_flat_plate"
    dvc_inputs: tuple[str, ...] = ()

    def __init__(self, measured: dict[str, Any]) -> None:
        self._measured = measured

    def case_spec(self) -> Any:
        from aero.vv.forward_regime.blasius_flat_plate import BlasiusFlatPlate

        return BlasiusFlatPlate().case_spec()

    def metrics(self) -> tuple[Any, ...]:
        from aero.vv._base import MetricSpec

        return (MetricSpec(name="cd", kind="scalar", tolerance=0.05, comparison="relative"),)

    def reference(self, repo_root: Path) -> Any:
        from aero.vv._base import ReferenceData

        return ReferenceData(case_name=self.name, source="test", scalars={"cd": 0.01})


def _runner(monkeypatch: pytest.MonkeyPatch, measured: dict[str, Any]) -> tuple[Any, list[Any]]:
    from aero.vv._base import BenchmarkRunner

    runner = BenchmarkRunner(
        solver=None,  # type: ignore[arg-type]
        executor=None,  # type: ignore[arg-type]
        tracking_uri="sqlite:///unused",
        experiment="unused",
        db_dsn="unused",
        solver_version="test",
    )
    monkeypatch.setattr(runner, "_drive", lambda case, prov: (measured, None, None))
    logged: list[Any] = []
    monkeypatch.setattr(runner, "_log", lambda *a: logged.append(a) or "run-1")
    monkeypatch.setattr("aero.vv._base._check_tuple_describes", lambda *a: None)
    return runner, logged


def test_the_runner_logs_a_named_scalar_in_the_same_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.unit._launch_fixtures import run_tuple

    runner, logged = _runner(monkeypatch, {"cd": 0.0101, "cf_mid": 0.002345})
    result = runner.run(_Case({}), provenance=run_tuple(), repo_root=REPO, log_scalars=("cf_mid",))
    assert result.mlflow_run_id == "run-1"
    (args,) = logged
    assert args[-1] == {"cf_mid": 0.002345}


@pytest.mark.parametrize("measured", [{"cd": 0.01}, {"cd": 0.01, "cf_mid": True}])
def test_a_scalar_the_solve_did_not_produce_is_refused_before_logging(
    monkeypatch: pytest.MonkeyPatch, measured: dict[str, Any]
) -> None:
    from aero.vv._base import BenchmarkError

    from tests.unit._launch_fixtures import run_tuple

    runner, logged = _runner(monkeypatch, measured)
    with pytest.raises(BenchmarkError, match="no scalar 'cf_mid'"):
        runner.run(_Case({}), provenance=run_tuple(), repo_root=REPO, log_scalars=("cf_mid",))
    assert logged == []


# --- the band (ADR-050 D5) ----------------------------------------------------------------------

_TAGS = {
    "git_sha": "a" * 40,
    "config_hash": "d1d264c56c893e2120178e076f1064b39dabb51ea37726bca958fdd05e459442",
    "dvc_input_hash": EMPTY_DVC_INPUTS_DIGEST,
    "container_sif_sha256": SUMS["openfoam-esi.sif"],
    "container_sif_name": "openfoam-esi.sif",
    "dvc_input_hash_scheme": "declared-dvc-pointers-md5/v1",
    "container_sif_sha256_scheme": "sif-sha256-verified-at-launch/v1",
    "dvc_inputs": '{"inputs":[]}',
}


def _record(cf: float, **tags: str) -> dict[str, Any]:
    return {"tags": {**_TAGS, **tags}, "cf_mid": cf, "cf_mid_hex": cf.hex()}


def _verdict(record: dict[str, Any], reference: dict[str, Any]) -> tuple[bool, list[str]]:
    checks = hosted_repro.band_checks(record, reference)
    return all(ok for ok, _ in checks), [line for ok, line in checks if not ok]


def test_the_same_number_on_other_hardware_passes() -> None:
    cluster = 0.0023456789
    ok, failed = _verdict(_record(cluster * (1 + 3e-4), git_sha="b" * 40), _record(cluster))
    assert ok, failed


@pytest.mark.parametrize("factor", [1.0101, 0.9899])
def test_a_miss_beyond_one_percent_fails(factor: float) -> None:
    ok, failed = _verdict(_record(0.002 * factor), _record(0.002))
    assert not ok and len(failed) == 1 and failed[0].startswith("|cf_mid_h - cf_mid_c|")


@pytest.mark.parametrize(
    ("term", "value"),
    [
        ("config_hash", "e" * 64),
        ("dvc_input_hash", "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
        ("container_sif_sha256", "e" * 64),
        ("dvc_input_hash_scheme", "repo-sync-state/v0"),
        ("container_sif_sha256_scheme", "sha256sums-lookup/v0"),
    ],
)
def test_the_same_number_under_different_terms_fails(term: str, value: str) -> None:
    ok, failed = _verdict(_record(0.002, **{term: value}), _record(0.002))
    assert not ok and any(term in line for line in failed)


def test_a_dirty_tree_on_either_side_fails() -> None:
    ok, failed = _verdict(_record(0.002, git_sha="a" * 40 + "-dirty"), _record(0.002))
    assert not ok and failed == ["the record's git_sha is a clean commit"]


def test_the_band_reads_the_exact_bits_not_a_rounded_float() -> None:
    record = _record(0.002)
    record["cf_mid"] = 999.0  # the decimal field is for humans; the hex is the number
    assert _verdict(record, _record(0.002))[0]


# --- the reference ------------------------------------------------------------------------------


def test_the_reference_comes_only_from_a_clean_cluster_run() -> None:
    cluster = {
        **_record(0.002),
        "format": hosted_repro.RECORD_FORMAT,
        "case": "blasius_flat_plate",
        "executor": "local-ssh",
        "mlflow_run_id": "r",
        "experiment": "aero-provenance",
        "host": "aero-build",
    }
    reference = hosted_repro.reference_from(cluster)
    assert reference["format"] == hosted_repro.REFERENCE_FORMAT
    assert reference["cf_mid_hex"] == (0.002).hex() and reference["band"] == 0.01
    with pytest.raises(SystemExit, match="cluster run"):
        hosted_repro.reference_from({**cluster, "executor": "local-container"})
    dirty = {**cluster, "tags": {**cluster["tags"], "git_sha": "a" * 40 + "-dirty"}}
    with pytest.raises(SystemExit, match="clean tree"):
        hosted_repro.reference_from(dirty)


# --- the driver's own refusals and the negative step --------------------------------------------


def test_a_hosted_run_may_not_log_to_the_platforms_tracking_server(tmp_path: Path) -> None:
    sif = tmp_path / "openfoam-esi.sif"
    sif.write_bytes(b"x")
    with pytest.raises(SystemExit, match="run-local store"):
        hosted_repro.main(
            [
                "run",
                "--executor",
                "local-container",
                "--sif",
                str(sif),
                "--tracking-uri",
                "http://192.168.2.234:5000",
                "--record",
                str(tmp_path / "r.json"),
            ]
        )


def test_the_hosted_run_needs_the_sif_under_its_recorded_name(tmp_path: Path) -> None:
    other = tmp_path / "renamed.sif"
    other.write_bytes(b"x")
    with pytest.raises(SystemExit, match=r"openfoam-esi\.sif"):
        hosted_repro.main(
            ["run", "--executor", "local-container", "--sif", str(other), "--record", "r.json"]
        )


def test_the_negative_step_passes_on_any_copy_that_is_not_the_recorded_bytes(
    tmp_path: Path,
) -> None:
    sif = tmp_path / "openfoam-esi.sif"
    sif.write_bytes(b"stand-in image " * 100)
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "hosted_repro.py"), "negative", "--sif", str(sif)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.count("PASS") == 3 and "apptainer never started" in proc.stdout
