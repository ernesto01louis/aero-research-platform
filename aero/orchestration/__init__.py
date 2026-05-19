"""Execution backends — see `aero.orchestration._base.Executor`."""

from __future__ import annotations

from aero.orchestration._base import ExecResult, Executor
from aero.orchestration.local_ssh import LocalSSHExecutor

__all__ = ["ExecResult", "Executor", "LocalSSHExecutor"]
