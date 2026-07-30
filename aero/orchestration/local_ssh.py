"""`LocalSSHExecutor` — runs commands on an aero LXC over SSH.

The single concrete `Executor` for Stage 03. Short commands run synchronously
(`ssh <target> <cmd>`); long-running commands (a `simpleFoam` solve) are
submitted through `scripts/run_long.sh`, the platform's detached-tmux long-job
pattern, then polled to completion — no SSH connection is held open for the
duration (CLAUDE.md long-job convention).
"""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from aero.orchestration._base import ExecResult

# SSH options applied to every invocation: never prompt, fail fast on a dead
# host rather than hang.
_SSH_OPTS: tuple[str, ...] = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=15")
_TIMEOUT_RC = 124  # conventional exit code for a timed-out command
_VANISHED_RC = 4  # run_long.sh `vanished`: job died without a sentinel (Stage 19)
_TRANSPORT_RC = 255  # ssh's own "an error occurred" code — the connection, not the command


def _transport_error(*, returncode: int, stderr: str, target: str) -> str:
    """Explain an SSH transport failure, or return "" if this looks like a real exit.

    `ssh` reserves 255 for its own errors (name resolution, refused connection,
    key rejection) and passes any other code through from the remote command.
    We therefore treat 255 as a transport fault by default rather than only when
    stderr matches a known phrase: the failure that motivated this — the CI
    runner being unable to resolve `aero-dev` — arrived as **rc 255 with an empty
    stderr**, so a pattern match would have missed exactly the case it was for.
    A remote command that genuinely exits 255 is vanishingly rare, and the
    message says so rather than asserting a verdict.
    """
    if returncode != _TRANSPORT_RC:
        return ""
    detail = stderr.strip() or (
        "ssh printed nothing on stderr, which is itself a tell: the aero-* aliases live in "
        "~/.ssh/config.d/aero on the Proxmox host and do NOT exist inside the LXCs, so a CI "
        "runner resolving them fails silently. Only aero-build (192.168.2.232) is in the "
        "runner's /etc/hosts."
    )
    return (
        f"ssh exited {_TRANSPORT_RC} for {target} — its own transport-failure code, meaning the "
        f"command never reached the host (bad hostname, refused connection, rejected key). "
        f"{detail} If the remote command genuinely exited {_TRANSPORT_RC}, this is a hint, not "
        f"a verdict."
    )


class LocalSSHExecutor(BaseModel):
    """Runs commands on a named SSH host (an aero LXC)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )

    host: str = Field(default="aero-build", min_length=1, description="SSH host alias.")
    ssh_user: str = Field(default="root", min_length=1, description="SSH login user.")
    repo_root: Path = Field(..., description="Repo root; locates scripts/run_long.sh.")
    long_timeout_s: int = Field(default=1800, gt=0, description="Long-job poll ceiling, s.")
    short_timeout_s: int = Field(default=300, gt=0, description="Default short-cmd timeout, s.")

    @property
    def ssh_target(self) -> str:
        """The `user@host` SSH destination."""
        return f"{self.ssh_user}@{self.host}"

    @property
    def _run_long_script(self) -> Path:
        return self.repo_root / "scripts" / "run_long.sh"

    def run(
        self,
        command: str,
        *,
        timeout_s: int | None = None,
        long_running: bool = False,
        session: str | None = None,
    ) -> ExecResult:
        """Run `command` on the SSH target — see `Executor.run`."""
        if long_running:
            return self._run_detached(command, timeout_s or self.long_timeout_s, session)
        return self._run_sync(command, timeout_s or self.short_timeout_s)

    def _run_sync(self, command: str, timeout_s: int) -> ExecResult:
        """Run a short command synchronously over a single SSH connection."""
        argv = ["ssh", *_SSH_OPTS, self.ssh_target, command]
        logger.debug("ssh-exec on {}: {}", self.ssh_target, command)
        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout_s, check=False
            )
        except subprocess.TimeoutExpired as exc:
            return ExecResult(
                command=command,
                returncode=_TIMEOUT_RC,
                stdout=_as_text(exc.stdout),
                stderr=f"ssh command timed out after {timeout_s}s",
                duration_s=time.monotonic() - started,
                host=self.host,
            )
        return ExecResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_s=time.monotonic() - started,
            host=self.host,
            transport_error=_transport_error(
                returncode=proc.returncode, stderr=proc.stderr, target=self.ssh_target
            ),
        )

    def _run_detached(self, command: str, timeout_s: int, session: str | None) -> ExecResult:
        """Submit a long job via run_long.sh, poll it to completion."""
        session = session or f"aero-{int(time.time())}"
        run_long = str(self._run_long_script)
        started = time.monotonic()

        submit = subprocess.run(
            [run_long, self.ssh_target, session, command],
            capture_output=True,
            text=True,
            check=False,
        )
        if submit.returncode != 0:
            # run_long.sh's own submit guard dies with "cannot reach <alias> …
            # refusing to submit" when the duplicate-session probe cannot open a
            # connection. That is a transport fault, not a solver one, and it must
            # not reach the caller wearing an ordinary non-zero exit code.
            unreachable = "cannot reach" in submit.stderr
            return ExecResult(
                command=command,
                returncode=submit.returncode or 1,
                stdout=submit.stdout,
                stderr=f"run_long.sh submit failed: {submit.stderr}",
                duration_s=time.monotonic() - started,
                host=self.host,
                transport_error=(
                    f"run_long.sh could not reach {self.ssh_target} and refused to submit "
                    f"'{session}' — the job never started. {submit.stderr.strip()}"
                    if unreachable
                    else ""
                ),
            )
        logger.info("submitted long job '{}' on {}", session, self.ssh_target)

        # run_long.sh wait polls sentinel files (no held connection): exit 0
        # done, 1 failed, 2 timeout, 4 vanished. Guard with a slightly larger
        # Python-side timeout in case run_long.sh itself wedges.
        try:
            waited = subprocess.run(
                [run_long, "wait", self.ssh_target, session, str(timeout_s)],
                capture_output=True,
                text=True,
                timeout=timeout_s + 120,
                check=False,
            )
            wait_rc = waited.returncode
        except subprocess.TimeoutExpired:
            wait_rc = 2

        logs = subprocess.run(
            [run_long, "logs", self.ssh_target, session],
            capture_output=True,
            text=True,
            check=False,
        )
        duration = time.monotonic() - started

        if wait_rc == 2:
            return ExecResult(
                command=command,
                returncode=_TIMEOUT_RC,
                stdout=logs.stdout,
                stderr=f"long job '{session}' timed out after {timeout_s}s",
                duration_s=duration,
                host=self.host,
            )
        if wait_rc == _VANISHED_RC:
            # The remote job died without writing a sentinel — killed, or its
            # tmux server went away. Distinguishing this from a normal non-zero
            # exit matters: there is no `rc` file to read, so falling through to
            # `_remote_rc` would report a bare 1 with an empty stderr and a
            # truncated log, which reads exactly like an ordinary solver failure.
            return ExecResult(
                command=command,
                returncode=_VANISHED_RC,
                stdout=logs.stdout,
                stderr=(
                    f"long job '{session}' vanished on {self.ssh_target}: the tmux session "
                    "is gone and no .done/.failed sentinel or rc was written. The job did "
                    "NOT complete — its output log, if any, is partial."
                ),
                duration_s=duration,
                host=self.host,
            )
        return ExecResult(
            command=command,
            returncode=self._remote_rc(session),
            stdout=logs.stdout,
            stderr="",
            duration_s=duration,
            host=self.host,
        )

    def _remote_rc(self, session: str) -> int:
        """Read the true exit code run_long.sh recorded for a finished job."""
        proc = subprocess.run(
            ["ssh", *_SSH_OPTS, self.ssh_target, f"cat .aero-jobs/{shlex.quote(session)}/rc"],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return int(proc.stdout.strip())
        except ValueError:
            return proc.returncode or 1


def _as_text(value: str | bytes | None) -> str:
    """Coerce captured subprocess output (which may be bytes) to str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
