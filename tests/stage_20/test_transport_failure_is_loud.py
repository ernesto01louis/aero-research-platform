"""Stage 20 — an unreachable host must not read as a solver failure.

The `moving-vv` workflow's first dispatch died in 18 s because the CI runner
cannot resolve `aero-dev`: ssh returned 255, the adapter logged only
`returncode` and `stdout`, and the failure surfaced as "blockMesh failed" —
pointing at the mesher rather than at DNS. These tests pin the three properties
that make that impossible to repeat:

1. the executor marks an ssh transport fault, even when stderr is empty;
2. `describe_failure` never drops rc, stderr or the command;
3. the V&V runner raises with the adapter's recorded reason, not a hard-coded
   component name.
"""

from __future__ import annotations

import pytest
from aero.orchestration._base import ExecResult, describe_failure
from aero.orchestration.local_ssh import _TRANSPORT_RC, _transport_error

pytestmark = pytest.mark.stage_20


def _result(**kwargs: object) -> ExecResult:
    base: dict[str, object] = {
        "command": "apptainer exec --bind /case:/case openfoam-esi.sif bash -lc 'blockMesh'",
        "returncode": 1,
        "stdout": "",
        "stderr": "",
        "duration_s": 0.5,
        "host": "aero-dev",
    }
    base.update(kwargs)
    return ExecResult(**base)  # type: ignore[arg-type]


class TestTransportDetection:
    def test_rc_255_with_empty_stderr_is_still_flagged(self) -> None:
        """The regression case: no stderr to pattern-match against.

        A stderr-pattern matcher would have missed exactly the failure it was
        written for, so 255 is treated as a transport fault on the code alone.
        """
        message = _transport_error(returncode=255, stderr="", target="root@aero-dev")
        assert message
        assert "255" in message
        assert "root@aero-dev" in message

    def test_rc_255_carries_ssh_stderr_when_there_is_some(self) -> None:
        message = _transport_error(
            returncode=255,
            stderr="ssh: Could not resolve hostname aero-dev: Name or service not known",
            target="root@aero-dev",
        )
        assert "Could not resolve hostname" in message

    @pytest.mark.parametrize("rc", [0, 1, 2, 4, 124, 137])
    def test_other_exit_codes_are_not_transport_faults(self, rc: int) -> None:
        """A solver that fails is a result about the case; do not relabel it."""
        assert _transport_error(returncode=rc, stderr="boom", target="root@aero-dev") == ""

    def test_transport_failed_defaults_false_so_existing_results_are_unchanged(self) -> None:
        assert _result(returncode=1).transport_failed is False
        assert _result(returncode=0).transport_failed is False

    def test_transport_rc_constant_is_sshs_own_code(self) -> None:
        assert _TRANSPORT_RC == 255


class TestDescribeFailure:
    def test_names_the_command_that_actually_ran(self) -> None:
        """The old message hard-coded "blockMesh" even for a four-utility pipeline."""
        pipeline = "surfaceFeatureExtract && blockMesh && snappyHexMesh -overwrite && flattenMesh"
        text = describe_failure(_result(command=pipeline), what=f"meshing ({pipeline})")
        assert "snappyHexMesh" in text
        assert "flattenMesh" in text

    def test_includes_returncode_and_stderr(self) -> None:
        text = describe_failure(
            _result(returncode=139, stderr="Segmentation fault"), what="blockMesh"
        )
        assert "rc=139" in text
        assert "Segmentation fault" in text

    def test_says_empty_rather_than_silently_omitting_stderr(self) -> None:
        assert "stderr: (empty)" in describe_failure(_result(), what="blockMesh")

    def test_transport_fault_leads_with_the_transport_reason(self) -> None:
        text = describe_failure(
            _result(returncode=255, transport_error="ssh exited 255 for root@aero-dev"),
            what="meshing (blockMesh)",
        )
        assert text.splitlines()[0].startswith("meshing (blockMesh) could not run:")
        assert "ssh exited 255" in text

    def test_stdout_tail_is_bounded(self) -> None:
        text = describe_failure(_result(stdout="x" * 10_000), what="blockMesh")
        assert len(text) < 4_000


class _StubSolver:
    """A `SolverLike` whose `mesh` always fails with a recorded reason."""

    def __init__(self, failure: str) -> None:
        self._failure = failure

    def prepare(self, spec: object) -> object:
        return object()

    def mesh(self, case_dir: object, executor: object) -> object:
        return _StubMesh(self._failure)

    def run(self, case_dir: object, executor: object) -> object:
        raise AssertionError("run() must not be reached after a mesh failure")


class _StubMesh:
    def __init__(self, failure: str) -> None:
        self.ok = False
        self.failure = failure


class _StubCase:
    name = "hg2007_flexible_foil"

    def case_spec(self) -> object:
        return object()


class TestBenchmarkRunnerReportsTheRecordedReason:
    def _runner(self, failure: str) -> object:
        from aero.vv._base import BenchmarkRunner

        return BenchmarkRunner(
            solver=_StubSolver(failure),  # type: ignore[arg-type]
            executor=object(),  # type: ignore[arg-type]
            tracking_uri="http://unused",
            experiment="unused",
            db_dsn="unused",
            solver_version="unused",
            stage="20",
        )

    def test_the_adapters_reason_reaches_the_error(self) -> None:
        """The transport detail must survive all the way to the raised message."""
        from aero.vv._base import BenchmarkError

        reason = (
            "meshing (blockMesh) could not run: ssh exited 255 for root@aero-dev\n"
            "command: apptainer exec ...\nstderr: (empty)"
        )
        with pytest.raises(BenchmarkError) as exc:
            self._runner(reason)._drive(_StubCase())  # type: ignore[attr-defined]
        message = str(exc.value)
        assert "ssh exited 255 for root@aero-dev" in message
        assert "blockMesh failed" not in message

    def test_a_reasonless_handle_says_so_instead_of_guessing(self) -> None:
        from aero.vv._base import BenchmarkError

        with pytest.raises(BenchmarkError, match="the adapter recorded no reason"):
            self._runner("")._drive(_StubCase())  # type: ignore[attr-defined]
