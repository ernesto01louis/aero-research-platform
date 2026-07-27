"""Concurrent launch of preCICE participants under a supervising script.

Nothing else in the platform runs two long-lived processes at once: every existing
adapter issues one command and waits. ``LocalSSHExecutor._run_detached`` reflects that —
it submits one tmux job and then *blocks* until it finishes, so it cannot start a second
participant alongside the first.

Widening the ``Executor`` protocol to support non-blocking submission would ripple
through every stage for the benefit of one. Instead we keep the executor contract
exactly as it is and make the *payload* concurrent: one detached job whose command is a
generated supervisor script that backgrounds both participants and waits on them. The
executor still sees a single command with a single exit code, ``run_long.sh``'s sentinel
semantics still hold, and ``ResultHandle.returncode`` still means what it always meant.

The supervisor is the authority on why a run stopped. It always writes
``coupled-status.json`` — per-participant exit code, start/end epochs, and a
``stopped_by`` discriminator — so "we hit the wall-clock ceiling" is a *recorded
outcome* rather than something inferred from a truncated log (ADR-036 gate K2). The
Python-side timeout is deliberately set well beyond the supervisor's own ceiling so the
supervisor, and not the poller, decides when the run is over.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.adapters._base import build_apptainer_exec
from aero.adapters.precice.case import ParticipantSpec
from aero.orchestration._base import Executor

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

StoppedBy = Literal["all-exited", "ceiling", "participant-died"]

#: Extra head-room between the supervisor's own ceiling and the executor's poll timeout.
#: The supervisor needs time to SIGTERM, wait out the grace period, SIGKILL and write its
#: status file; if the poller gave up first we would lose the authoritative outcome.
_POLL_MARGIN_S = 900


class CoupledLaunchError(RuntimeError):
    """A coupled run could not be launched, or produced no usable status."""


class CoupledLaunchPlan(BaseModel):
    """Everything the supervisor script needs, resolved to remote paths."""

    model_config = _STRICT

    case_root_remote: str = Field(..., min_length=1)
    participants: tuple[ParticipantSpec, ...] = Field(..., min_length=1)
    sif_paths: Mapping[str, str] = Field(..., description="SIF basename -> absolute remote path.")
    # No lower bound worth defending here: the plan is a mechanical object. A campaign
    # budget that makes no sense is caught on CoupledCaseSpec (ge=60), which is where the
    # pre-declared ceiling actually lives.
    wall_clock_ceiling_s: int = Field(..., ge=1)
    exchange_dir: str = Field(
        default=".",
        min_length=1,
        description=(
            "preCICE exchange directory, relative to case_root_remote. The bind root is "
            "the tutorial ROOT (so that ../../tools resolves), while preCICE creates "
            "precice-run/ beside the config one level in -- these are not the same "
            "directory and the stale-socket cleanup has to target the latter."
        ),
    )
    poll_interval_s: int = Field(default=30, ge=1)
    peer_grace_s: int = Field(
        default=120,
        ge=0,
        description="How long a survivor may outlive a peer's clean exit before it is stopped.",
    )
    term_grace_s: int = Field(
        default=120, ge=1, description="SIGTERM -> SIGKILL grace, so solvers can close writes."
    )

    @model_validator(mode="after")
    def _sifs_resolved(self) -> CoupledLaunchPlan:
        missing = sorted({p.sif for p in self.participants} - set(self.sif_paths))
        if missing:
            raise ValueError(f"no remote path given for SIF(s): {', '.join(missing)}")
        names = [p.name for p in self.participants]
        if len(set(names)) != len(names):
            raise ValueError(f"participant names must be unique, got {names}")
        return self

    @property
    def executor_timeout_s(self) -> int:
        return self.wall_clock_ceiling_s + _POLL_MARGIN_S


class ParticipantOutcome(BaseModel):
    """How one participant ended."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    returncode: int | None = Field(default=None, description="None if it never exited.")
    state: Literal["exited-ok", "exited-fail", "killed", "running"]
    started_epoch: float
    ended_epoch: float | None = None
    log_path: str = Field(..., min_length=1)
    log_tail: str = ""


class CoupledRunResult(BaseModel):
    """The supervisor's verdict on a coupled run."""

    model_config = _STRICT

    run_id: str = Field(..., min_length=1)
    outcomes: tuple[ParticipantOutcome, ...] = Field(..., min_length=1)
    wall_clock_s: float = Field(..., ge=0.0)
    stopped_by: StoppedBy
    status_json_path: Path
    executor_returncode: int

    @property
    def ok(self) -> bool:
        """True only if every participant exited zero of its own accord."""
        return self.stopped_by == "all-exited" and all(
            o.state == "exited-ok" for o in self.outcomes
        )

    @property
    def hit_ceiling(self) -> bool:
        return self.stopped_by == "ceiling"

    def outcome(self, name: str) -> ParticipantOutcome:
        for candidate in self.outcomes:
            if candidate.name == name:
                return candidate
        raise CoupledLaunchError(f"no outcome recorded for participant {name!r}")


def build_participant_command(
    participant: ParticipantSpec, *, case_root_remote: str, sif_path: str
) -> str:
    """The full ``apptainer exec`` command for one participant. Pure; unit-test-pinned.

    ``--no-home`` is not optional: the OpenFOAM-preCICE adapter library is installed into
    the image's ``$FOAM_LIBBIN``, but apptainer bind-mounts the *host* ``$HOME`` by
    default, and a host ``~/OpenFOAM/...`` tree would shadow it via ``$FOAM_USER_LIBBIN``.
    The failure would appear only at run time, as ``controlDict``'s ``libs (...)`` line
    failing to load the adapter.
    """
    # The environment is `export`ed INSIDE the compound command, not passed to
    # build_apptainer_exec's `env=`. That helper emits `cd <target> && K=V <command>`,
    # and a `K=V` prefix applies only to the single command that follows it — which,
    # for a compound command, is our `cd`, not the participant's. The variable would
    # silently fail to reach the participant, and the only symptom would be at run time
    # (upstream's run.sh trying to build a venv from the network inside the SIF).
    parts = [f"cd {shlex.quote(participant.workdir)}"]
    if participant.env:
        exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in sorted(participant.env.items()))
        parts.append(f"export {exports}")
    parts.append(participant.command)
    command = build_apptainer_exec(
        sif_path=sif_path,
        case_bind_source=case_root_remote,
        command=" && ".join(parts),
        writable_tmpfs=participant.writable_tmpfs,
    )
    return command.replace("apptainer exec ", "apptainer exec --no-home ", 1)


def render_supervisor_script(plan: CoupledLaunchPlan) -> str:
    """Render the bash supervisor. Pure — its exact output is pinned by a unit test."""
    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Generated by aero.adapters.precice.launcher — do not edit in place.",
        "# Supervises concurrent preCICE participants and ALWAYS records why the run ended.",
        "set -u",
        "",
        f"CASE_ROOT={shlex.quote(plan.case_root_remote)}",
        f"EXCHANGE_DIR={shlex.quote(plan.exchange_dir)}",
        f"CEILING={plan.wall_clock_ceiling_s}",
        f"POLL={plan.poll_interval_s}",
        f"PEER_GRACE={plan.peer_grace_s}",
        f"TERM_GRACE={plan.term_grace_s}",
        'STATUS="$CASE_ROOT/coupled-status.json"',
        "",
        "# A stale exchange directory is the single most common preCICE hang: the",
        "# acceptor finds an old socket descriptor and both sides wait forever.",
        'rm -rf "$CASE_ROOT/$EXCHANGE_DIR/precice-run"',
        "",
        "START=$(date +%s)",
        "declare -a NAMES PIDS LOGS RCS ENDED",
        "",
    ]
    for index, participant in enumerate(plan.participants):
        command = build_participant_command(
            participant,
            case_root_remote=plan.case_root_remote,
            sif_path=plan.sif_paths[participant.sif],
        )
        log = f"$CASE_ROOT/{participant.name}.log"
        lines += [
            f"NAMES[{index}]={shlex.quote(participant.name)}",
            f'LOGS[{index}]="{log}"',
            f'RCS[{index}]=""',
            f"ENDED[{index}]=0",
            f'( {command} ) > "{log}" 2>&1 &',
            f"PIDS[{index}]=$!",
            f'echo "[supervisor] started {participant.name} as pid ${{PIDS[{index}]}}"',
            "",
        ]

    n = len(plan.participants)
    lines += [
        f"N={n}",
        "STOPPED_BY=",
        "",
        "stop_all() {",
        "  local sig=$1",
        "  for i in $(seq 0 $((N-1))); do",
        '    if [ "${ENDED[$i]}" -eq 0 ]; then',
        '      kill -"$sig" "${PIDS[$i]}" 2>/dev/null || true',
        "    fi",
        "  done",
        "}",
        "",
        "while :; do",
        "  ALL_DONE=1",
        "  ANY_FAILED=0",
        "  FIRST_CLEAN_EXIT_AT=",
        "  for i in $(seq 0 $((N-1))); do",
        '    if [ "${ENDED[$i]}" -eq 0 ]; then',
        '      if kill -0 "${PIDS[$i]}" 2>/dev/null; then',
        "        ALL_DONE=0",
        "      else",
        '        wait "${PIDS[$i]}"; rc=$?',
        '        RCS[$i]="$rc"',
        "        ENDED[$i]=$(date +%s)",
        '        echo "[supervisor] ${NAMES[$i]} exited rc=$rc"',
        "      fi",
        "    fi",
        '    if [ -n "${RCS[$i]}" ] && [ "${RCS[$i]}" -ne 0 ]; then ANY_FAILED=1; fi',
        "  done",
        "",
        "  # A participant that failed takes the whole coupling down with it: its peer",
        "  # would otherwise block forever on a socket that will never be served.",
        '  if [ "$ANY_FAILED" -eq 1 ]; then',
        '    STOPPED_BY="participant-died"',
        "    stop_all TERM",
        "    break",
        "  fi",
        "",
        '  if [ "$ALL_DONE" -eq 1 ]; then',
        '    STOPPED_BY="all-exited"',
        "    break",
        "  fi",
        "",
        "  # One clean exit while the other keeps running means the coupling desynchronised.",
        "  NOW=$(date +%s)",
        "  for i in $(seq 0 $((N-1))); do",
        '    if [ "${ENDED[$i]}" -ne 0 ] && [ $((NOW - ENDED[i])) -gt "$PEER_GRACE" ]; then',
        '      STOPPED_BY="participant-died"',
        "    fi",
        "  done",
        '  if [ -n "$STOPPED_BY" ]; then',
        '    echo "[supervisor] a participant exited but its peer is still running"',
        "    stop_all TERM",
        "    break",
        "  fi",
        "",
        '  if [ $((NOW - START)) -ge "$CEILING" ]; then',
        '    STOPPED_BY="ceiling"',
        '    echo "[supervisor] wall-clock ceiling ${CEILING}s reached — stopping"',
        "    stop_all TERM",
        "    break",
        "  fi",
        '  sleep "$POLL"',
        "done",
        "",
        "# Give the solvers a chance to close their writes cleanly, then insist.",
        "DEADLINE=$(( $(date +%s) + TERM_GRACE ))",
        "while [ $(date +%s) -lt $DEADLINE ]; do",
        "  REMAINING=0",
        "  for i in $(seq 0 $((N-1))); do",
        '    if [ "${ENDED[$i]}" -eq 0 ] && kill -0 "${PIDS[$i]}" 2>/dev/null; then',
        "      REMAINING=1",
        "    fi",
        "  done",
        '  [ "$REMAINING" -eq 0 ] && break',
        "  sleep 1",
        "done",
        "stop_all KILL",
        "for i in $(seq 0 $((N-1))); do",
        '  if [ "${ENDED[$i]}" -eq 0 ]; then',
        '    wait "${PIDS[$i]}" 2>/dev/null; rc=$?',
        '    RCS[$i]="$rc"',
        "    ENDED[$i]=$(date +%s)",
        "  fi",
        "done",
        "",
        "END=$(date +%s)",
        "{",
        '  printf \'{\\n  "run_id": %s,\\n\' "\\"$AERO_RUN_ID\\""',
        '  printf \'  "stopped_by": "%s",\\n\' "$STOPPED_BY"',
        '  printf \'  "started_epoch": %s,\\n  "ended_epoch": %s,\\n\' "$START" "$END"',
        '  printf \'  "wall_clock_s": %s,\\n\' "$((END - START))"',
        "  printf '  \"participants\": [\\n'",
        "  for i in $(seq 0 $((N-1))); do",
        '    sep=","; [ "$i" -eq $((N-1)) ] && sep=""',
        '    printf \'    {"name": "%s", "returncode": %s, "started_epoch": %s, '
        '"ended_epoch": %s, "log_path": "%s"}%s\\n\' \\',
        '      "${NAMES[$i]}" "${RCS[$i]:-null}" "$START" "${ENDED[$i]}" "${LOGS[$i]}" "$sep"',
        "  done",
        "  printf '  ]\\n}\\n'",
        '} > "$STATUS"',
        'echo "[supervisor] wrote $STATUS (stopped_by=$STOPPED_BY)"',
        "",
        "# Exit code mirrors the outcome so run_long.sh's sentinel is meaningful.",
        'if [ "$STOPPED_BY" = "ceiling" ]; then exit 124; fi',
        "for i in $(seq 0 $((N-1))); do",
        '  if [ "${RCS[$i]:-1}" -ne 0 ]; then exit "${RCS[$i]}"; fi',
        "done",
        "exit 0",
        "",
    ]
    return "\n".join(lines)


def _tail(path: Path, *, lines: int = 40) -> str:
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def read_coupled_status(
    status_json: Path, *, case_root_host: Path, executor_returncode: int
) -> CoupledRunResult:
    """Parse the supervisor's ``coupled-status.json``. A missing file is a loud failure."""
    if not status_json.is_file():
        raise CoupledLaunchError(
            f"{status_json}: the supervisor wrote no status file. The coupled run's outcome "
            "is unknown — treat it as failed and inspect the participant logs."
        )
    try:
        payload = json.loads(status_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CoupledLaunchError(f"{status_json}: unparseable supervisor status — {exc}") from exc

    outcomes: list[ParticipantOutcome] = []
    for entry in payload["participants"]:
        rc = entry["returncode"]
        ended = entry["ended_epoch"]
        # Classify by the exit code itself, not by why the RUN stopped. A shell reports
        # a signal death as 128+signum, so SIGTERM from our own teardown shows as 143.
        # Keeping that distinct from a nonzero exit is what identifies which participant
        # actually died first: in a `participant-died` teardown the culprit carries its
        # own status (e.g. 1) while its peer carries 143.
        if rc is None:
            state: str = "running"
        elif rc == 0:
            state = "exited-ok"
        elif rc >= 128:
            state = "killed"
        else:
            state = "exited-fail"
        log_name = Path(entry["log_path"]).name
        outcomes.append(
            ParticipantOutcome(
                name=entry["name"],
                returncode=rc,
                state=state,  # type: ignore[arg-type]
                started_epoch=float(entry["started_epoch"]),
                ended_epoch=None if not ended else float(ended),
                log_path=entry["log_path"],
                log_tail=_tail(case_root_host / log_name),
            )
        )
    return CoupledRunResult(
        run_id=payload["run_id"],
        outcomes=tuple(outcomes),
        wall_clock_s=float(payload["wall_clock_s"]),
        stopped_by=payload["stopped_by"],
        status_json_path=status_json,
        executor_returncode=executor_returncode,
    )


def launch_coupled(
    plan: CoupledLaunchPlan,
    executor: Executor,
    *,
    run_id: str,
    case_root_host: Path,
) -> CoupledRunResult:
    """Write the supervisor into the case, run it detached, and read back its verdict."""
    script_host = case_root_host / "run-coupled.sh"
    script_host.write_text(render_supervisor_script(plan), encoding="utf-8")
    script_host.chmod(0o755)

    remote_script = f"{plan.case_root_remote}/run-coupled.sh"
    command = f"AERO_RUN_ID={shlex.quote(run_id)} bash {shlex.quote(remote_script)}"
    result = executor.run(
        command,
        long_running=True,
        session=f"fsi-{run_id}",
        timeout_s=plan.executor_timeout_s,
    )
    return read_coupled_status(
        case_root_host / "coupled-status.json",
        case_root_host=case_root_host,
        executor_returncode=result.returncode,
    )
