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
    transport_error: str = Field(
        default="",
        description=(
            "Non-empty when the executor could not reach the compute target at all — the "
            "command never ran. Distinguishing this from an ordinary non-zero exit is the "
            "difference between an infrastructure fault and a physics result."
        ),
    )

    @property
    def ok(self) -> bool:
        """True iff the command exited 0."""
        return self.returncode == 0

    @property
    def transport_failed(self) -> bool:
        """True iff the executor never got the command onto the compute target.

        Stage 20: a `moving-vv` dispatch died because the CI runner cannot resolve
        `aero-dev`. SSH returned 255 with an empty stderr, the adapter logged only
        `returncode` and `stdout`, and the failure surfaced as "blockMesh failed" —
        pointing at the mesher rather than at DNS. A transport fault is never a
        statement about the case, so it carries its own flag.
        """
        return bool(self.transport_error)


def describe_failure(result: ExecResult, *, what: str) -> str:
    """A single-line-plus-detail explanation of why `what` did not succeed.

    Every adapter that turns a non-zero `ExecResult` into an error message should
    build it here, so `rc`, `stderr` and the actual command are never dropped —
    dropping them is what made an unreachable host read as a mesher failure.
    """
    headline = (
        f"{what} could not run: {result.transport_error}"
        if result.transport_failed
        else f"{what} failed (rc={result.returncode}) on {result.host}"
    )
    parts = [headline, f"command: {result.command}"]
    parts.append(f"stderr: {result.stderr.strip()}" if result.stderr.strip() else "stderr: (empty)")
    tail = result.stdout.strip()
    if tail:
        parts.append(f"stdout tail:\n{tail[-2000:]}")
    return "\n".join(parts)


@runtime_checkable
class Executor(Protocol):
    """Runs a shell command on a compute target and returns an `ExecResult`.

    Implementations must not raise on a non-zero exit — they return an
    `ExecResult` carrying the non-zero `returncode` and let the caller decide.
    They *may* raise on infrastructure failure (host unreachable, timeout); if
    they do not raise, they **must** set `ExecResult.transport_error` so the
    caller can tell "the command ran and failed" from "the command never ran"
    (Stage 20). Returning an unmarked non-zero code for an unreachable host is
    how a DNS fault gets reported as a solver fault.
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
