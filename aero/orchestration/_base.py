"""Execution backends for the aero platform.

`Executor` is the one abstraction every solve goes through: it runs a shell
command on some compute target and returns a typed `ExecResult`. Stage 03
ships a single concrete implementation, `LocalSSHExecutor` (commands over SSH
to an aero LXC). Cloud executors (RunPod, Lambda Labs, Vast.ai) arrive in
Stage 13 against this same Protocol — deliberately *not* designed here, since
one implementation cannot reveal the right shape of many (anti-premature-
abstraction; see ADR-003).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ExecResult(BaseModel):
    """The typed outcome of one `Executor.run` call."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        validate_default=True,
    )

    command: str = Field(..., min_length=1, description="The command that was run.")
    returncode: int = Field(..., description="Process exit code; 0 is success.")
    stdout: str = Field(default="", description="Captured standard output.")
    stderr: str = Field(default="", description="Captured standard error.")
    duration_s: float = Field(..., ge=0.0, description="Wall-clock duration, seconds.")
    host: str = Field(..., min_length=1, description="Compute target it ran on.")

    @property
    def ok(self) -> bool:
        """True iff the command exited 0."""
        return self.returncode == 0


@runtime_checkable
class Executor(Protocol):
    """Runs a shell command on a compute target and returns an `ExecResult`.

    Implementations must not raise on a non-zero exit — they return an
    `ExecResult` carrying the non-zero `returncode` and let the caller decide.
    They *may* raise on infrastructure failure (host unreachable, timeout).
    """

    def run(
        self,
        command: str,
        *,
        timeout_s: int | None = None,
        long_running: bool = False,
        session: str | None = None,
    ) -> ExecResult:
        """Execute `command`.

        `long_running=True` selects the detached submit-and-poll path for jobs
        that outlast a single connection (a CFD solve); `session` names that
        job. Short commands run synchronously, bounded by `timeout_s`.
        """
        ...
