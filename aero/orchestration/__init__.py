"""Execution backends — see `aero.orchestration._base.Executor`."""

from __future__ import annotations

from aero.orchestration._base import ExecResult, Executor, describe_failure
from aero.orchestration.local_container import LocalContainerExecutor
from aero.orchestration.local_ssh import LocalSSHExecutor

__all__ = [
    "ExecResult",
    "Executor",
    "LocalContainerExecutor",
    "LocalSSHExecutor",
    "describe_failure",
]
