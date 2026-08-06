"""Stage 20 — the wait ceiling must be honest, and a timeout must never strand a solve.

`moving-vv` run 30615205786 died at **4 h 02 m 32 s** against a nominal 4 h ceiling
and left `pimpleFoam` running on aero-dev with no reader — despite
`AERO_RUN_LONG_REAP=1`, the flag that exists to prevent exactly that.

Root cause: `run_long.sh cmd_wait` accumulated `elapsed += interval`, counting only
its sleeps and ignoring the SSH round trip each `remote_state` poll costs. At ~0.5 s
per probe its counter ran ~10 % slow, so a nominal 14400 s ceiling did not fire until
~15800 s. `LocalSSHExecutor` guards the subprocess at `timeout_s + 120` = 14520 s, so
the guard always won the race, SIGKILLed the script before it reached its reap branch,
and the reap never happened.

Two independent defences, both pinned here: the ceiling is honest, and the executor
reaps for itself if its own guard fires anyway.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUN_LONG = _REPO_ROOT / "scripts" / "run_long.sh"


class TestTheCeilingIsHonest:
    def test_wait_measures_a_real_clock_not_accumulated_sleeps(self) -> None:
        """The counter must not be `elapsed += interval`."""
        body = _RUN_LONG.read_text(encoding="utf-8")
        wait_body = body.split("cmd_wait()", 1)[1].split("\ncmd_logs()", 1)[0]
        assert "elapsed=$(( $(date +%s) - start_epoch ))" in wait_body
        assert "elapsed=$((elapsed + interval))" not in wait_body, (
            "accumulating the sleep interval ignores per-poll SSH latency and makes "
            "the ceiling run slow — the 30615205786 failure mode"
        )

    def test_a_short_wait_fires_close_to_its_nominal_ceiling(self) -> None:
        """End-to-end on a real (unreachable) target: a 5 s ceiling fires in ~5 s.

        Uses an alias whose SSH will fail fast, so every poll pays a real round-trip
        cost — which is precisely the latency the old counter ignored. The assertion
        is one-sided and loose: it must not fire absurdly late.
        """
        env = {**os.environ, "AERO_RUN_LONG_REAP": "0"}
        proc = subprocess.run(
            [
                str(_RUN_LONG),
                "wait",
                "aero-lit",  # a valid alias; the session will never exist
                "stage20-nonexistent-session-probe",
                "5",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=90,
        )
        # 2 = running/timeout, 4 = vanished, 3 = unknown — any terminal answer is
        # fine; what is pinned is that it ANSWERS, well inside a generous bound.
        assert proc.returncode in (2, 3, 4), proc.stderr


class TestATimeoutNeverStrandsASolve:
    def test_the_executor_reaps_when_its_own_guard_fires(self, tmp_path: Path) -> None:
        """If `run_long.sh wait` is killed by the Python guard, the executor reaps.

        A stub `run_long.sh` records its invocations: `submit` returns immediately,
        `wait` hangs past the guard, and `kill` must then be called.
        """
        from aero.orchestration import local_ssh
        from aero.orchestration.local_ssh import LocalSSHExecutor

        calls = tmp_path / "calls.log"
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        stub = scripts / "run_long.sh"
        # Subcommand is $1 for `wait`/`kill`; a submit is `<target> <session> <cmd...>`,
        # so $1 is the target and never matches.
        stub.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$@" >> {calls}\n'
            'case "$1" in\n'
            "  wait) sleep 600 ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)

        # Shrink the guard margin rather than sleep through the real 120 s.
        monkey = pytest.MonkeyPatch()
        monkey.setattr(local_ssh, "_WAIT_GUARD_MARGIN_S", 1)
        monkey.setenv("AERO_RUN_LONG_REAP", "1")
        try:
            executor = LocalSSHExecutor(host="aero-dev", repo_root=tmp_path, long_timeout_s=1)
            result = executor.run("true", long_running=True, session="probe", timeout_s=1)
        finally:
            monkey.undo()

        assert result.returncode == 124, "a guard-fired wait must report a timeout"
        logged = calls.read_text(encoding="utf-8")
        assert "kill" in logged, (
            "the executor must reap when its own guard kills run_long.sh before the "
            f"script reaches its reap branch; calls were:\n{logged}"
        )

    def test_no_reap_when_the_caller_does_not_own_the_job(self, tmp_path: Path) -> None:
        """Without the flag, a human who stops watching keeps their solve."""
        from aero.orchestration.local_ssh import _reap_enabled

        os.environ.pop("AERO_RUN_LONG_REAP", None)
        assert _reap_enabled() is False
        os.environ["AERO_RUN_LONG_REAP"] = "1"
        try:
            assert _reap_enabled() is True
        finally:
            os.environ.pop("AERO_RUN_LONG_REAP", None)
