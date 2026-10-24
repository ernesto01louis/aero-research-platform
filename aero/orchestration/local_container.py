"""`LocalContainerExecutor` — run a solver command on THIS host, with no SSH (ADR-050 D2).

The hosted reproducibility check (ADR-050) runs the cluster's own `openfoam-esi.sif` on a
GitHub-hosted runner, so the command the adapter builds — the ADR-053 launch guard followed by
`apptainer exec` — runs in a local `bash` instead of over SSH to an aero LXC. Everything else is
the `Executor` contract unchanged: a non-zero exit is returned, never raised; a command that never
started carries `transport_error`; a timeout is rc 124.

A `long_running` job runs to completion in the same call, with stderr merged into stdout, which
is what a detached `run_long.sh` job returns (`output.log` holds both streams), so an adapter reads
the same `ExecResult` either way. There is no detached state to reattach to on a hosted runner.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time

from pydantic import BaseModel, ConfigDict, Field

from aero.orchestration._base import ExecResult

__all__ = ["LocalContainerExecutor"]

_TIMEOUT_RC = 124  # as `LocalSSHExecutor`: the conventional exit code of a timed-out command
_NOT_STARTED_RC = 127  # the shell's "command not found"


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class LocalContainerExecutor(BaseModel):
    """Runs each command in a local `bash -c` — see `aero.orchestration._base.Executor`."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )

    shell: str = Field(default="bash", min_length=1, description="The shell that runs commands.")
    long_timeout_s: int = Field(default=2700, gt=0, description="Long-job ceiling, s.")
    short_timeout_s: int = Field(default=900, gt=0, description="Default short-cmd timeout, s.")

    @property
    def host(self) -> str:
        """The compute target an `ExecResult` names: this machine."""
        return f"local:{socket.gethostname() or 'localhost'}"

    def run(
        self,
        command: str,
        *,
        timeout_s: int | None = None,
        long_running: bool = False,
        session: str | None = None,
    ) -> ExecResult:
        """Run `command` here, to completion — see `Executor.run`.

        `session` names a detached job on the cluster; here it only labels the log line.
        """
        timeout = timeout_s or (self.long_timeout_s if long_running else self.short_timeout_s)
        from loguru import logger  # lazy: keeps loguru off the core import path (H-12)

        logger.debug("local exec ({}): {}", session or "sync", command)
        started = time.monotonic()
        try:
            # Its own session, so a timeout stops the whole tree (apptainer and the solver under
            # the shell), not just the shell.
            proc = subprocess.Popen(
                [self.shell, "-c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT if long_running else subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            return ExecResult(
                command=command,
                returncode=_NOT_STARTED_RC,
                duration_s=time.monotonic() - started,
                host=self.host,
                transport_error=f"the shell {self.shell!r} could not be started: {exc}",
            )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, _ = proc.communicate()
            return ExecResult(
                command=command,
                returncode=_TIMEOUT_RC,
                stdout=_as_text(stdout),
                stderr=f"local command timed out after {timeout}s",
                duration_s=time.monotonic() - started,
                host=self.host,
            )
        return ExecResult(
            command=command,
            returncode=proc.returncode,
            stdout=_as_text(stdout),
            stderr="" if long_running else _as_text(stderr),
            duration_s=time.monotonic() - started,
            host=self.host,
        )
