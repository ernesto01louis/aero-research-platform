"""`run_long.sh` must distinguish a DEAD detached job from a slow one (Stage 19).

Before the `vanished` state existed, `remote_state` fell through to `unknown` when a
job's tmux session was gone without a sentinel, and `cmd_wait` only returned early on
`done`/`failed` — so a job killed at minute 5 of a 6-hour wait blocked the caller for the
full six hours and was then reported as *"still running"*. That is the same class of
silent-wrong-answer the platform refuses everywhere else: a dead solve must be loud.

These tests drive the real script through a fake `ssh` that executes the remote command
locally against a temporary HOME, so they need no cluster and run in the unit suite.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.stage_19]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUN_LONG = _REPO_ROOT / "scripts" / "run_long.sh"

# run_long.sh exit codes for `status` / `wait`.
_DONE, _FAILED, _RUNNING, _UNKNOWN, _VANISHED = 0, 1, 2, 3, 4

_ALIAS = "aero-dev"  # must be a member of AERO_ALIASES
_SESSION = "unit-probe"


@pytest.fixture
def fake_remote(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A fake `ssh` that runs the remote command locally against `tmp_path`.

    run_long.sh always invokes `ssh <target> "<script>"`, so dropping a shim named `ssh`
    at the front of PATH exercises the script's REAL remote logic — quoting, ordering and
    all — without a host.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "ssh"
    # `shift` drops the target; the rest is the remote script. `cd` into the fake home so
    # the script's home-relative .aero-jobs paths resolve there.
    shim.write_text(f"#!/usr/bin/env bash\nshift\nexec bash -c \"cd '{tmp_path}' && $*\"\n")
    shim.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    return tmp_path, env


def _status(env: dict[str, str], session: str = _SESSION) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_RUN_LONG), "status", _ALIAS, session],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _jobdir(home: Path, session: str = _SESSION) -> Path:
    d = home / ".aero-jobs" / session
    d.mkdir(parents=True, exist_ok=True)
    return d


def _age_cmd_sh(jobdir: Path, *, minutes: int) -> None:
    """Write cmd.sh with an mtime `minutes` in the past (the grace window is 1 minute)."""
    cmd = jobdir / "cmd.sh"
    cmd.write_text("echo hello\n")
    old = time.time() - minutes * 60
    os.utime(cmd, (old, old))


def test_killed_job_reports_vanished_not_unknown(fake_remote) -> None:
    """No sentinel + no session + an aged job dir is a DEATH, and says so."""
    home, env = fake_remote
    _age_cmd_sh(_jobdir(home), minutes=5)

    proc = _status(env)

    assert proc.returncode == _VANISHED, proc.stderr
    assert "vanished" in proc.stdout


def test_a_just_submitted_job_is_running_not_vanished(fake_remote) -> None:
    """The submit -> tmux-registration race must never be misread as a death.

    Between `mkdir` and the tmux session appearing there is a window in which a live job
    looks exactly like a dead one. The grace period is what keeps a healthy submission
    from being declared dead, so it is worth a test of its own.
    """
    home, env = fake_remote
    _age_cmd_sh(_jobdir(home), minutes=0)

    proc = _status(env)

    assert proc.returncode == _RUNNING, proc.stderr
    assert "running" in proc.stdout


def test_sentinels_still_win_over_the_vanished_check(fake_remote) -> None:
    """A finished job is terminal regardless of its session or job-dir age."""
    home, env = fake_remote
    jobdir = _jobdir(home)
    _age_cmd_sh(jobdir, minutes=5)

    (jobdir / ".done").touch()
    assert _status(env).returncode == _DONE

    (jobdir / ".done").unlink()
    (jobdir / ".failed").touch()
    assert _status(env).returncode == _FAILED


def test_never_submitted_session_is_unknown_not_vanished(fake_remote) -> None:
    """`unknown` (never existed) and `vanished` (existed, then died) are different facts."""
    _home, env = fake_remote

    proc = _status(env, session="never-submitted")

    assert proc.returncode == _UNKNOWN, proc.stderr
    assert "unknown" in proc.stdout


def test_wait_fails_fast_on_a_vanished_job(fake_remote) -> None:
    """`wait` must return at once, not burn its whole timeout on a corpse.

    This is the regression that matters for Stage 20: an FSI solve killed early would
    otherwise hold the harness for its full multi-hour ceiling and then be misreported.
    """
    home, env = fake_remote
    _age_cmd_sh(_jobdir(home), minutes=5)

    started = time.monotonic()
    proc = subprocess.run(
        [str(_RUN_LONG), "wait", _ALIAS, _SESSION, "120"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    elapsed = time.monotonic() - started

    assert proc.returncode == _VANISHED, proc.stderr
    assert elapsed < 30, f"wait burned {elapsed:.0f}s of its 120s budget on a dead job"
    assert "VANISHED" in proc.stderr


def test_kill_records_a_killed_job_as_failed(fake_remote) -> None:
    """`kill` leaves an honest record: .failed + rc=143, never a silent disappearance."""
    home, env = fake_remote
    jobdir = _jobdir(home)
    _age_cmd_sh(jobdir, minutes=5)

    proc = subprocess.run(
        [str(_RUN_LONG), "kill", _ALIAS, _SESSION],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert (jobdir / ".failed").exists()
    assert (jobdir / "rc").read_text().strip() == "143"
    # And the state it now reports is `failed`, not `vanished`.
    assert _status(env).returncode == _FAILED


def test_kill_never_overwrites_a_real_sentinel(fake_remote) -> None:
    """Reaping an already-finished job must not rewrite its verdict."""
    home, env = fake_remote
    jobdir = _jobdir(home)
    _age_cmd_sh(jobdir, minutes=5)
    (jobdir / ".done").touch()
    (jobdir / "rc").write_text("0\n")

    subprocess.run(
        [str(_RUN_LONG), "kill", _ALIAS, _SESSION],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert (jobdir / "rc").read_text().strip() == "0"
    assert not (jobdir / ".failed").exists()
    assert _status(env).returncode == _DONE
