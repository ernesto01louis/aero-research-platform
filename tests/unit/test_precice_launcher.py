"""Unit tests for the coupled-participant launcher and its supervisor script.

The supervisor is generated bash that decides whether a multi-hour coupled run
succeeded, so the tests actually *execute* it against stub participants through a fake
`apptainer` on PATH. Rendering it correctly is not the same as it behaving correctly, and
only one of those is what the campaign depends on.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from aero.adapters.precice.case import ParticipantSpec
from aero.adapters.precice.launcher import (
    CoupledLaunchPlan,
    build_participant_command,
    read_coupled_status,
    render_supervisor_script,
)

pytestmark = pytest.mark.stage_19

_APPTAINER_SHIM = """#!/usr/bin/env bash
# Stands in for `apptainer exec [flags] --bind SRC:TGT SIF bash -lc 'CMD'`.
shift
while [[ "${1:-}" == --* ]]; do
  if [[ "$1" == "--bind" ]]; then shift 2; else shift; fi
done
shift
shift 2
cmd="${1/cd \\/case/cd $AERO_TEST_CASE_ROOT}"
exec bash -c "$cmd"
"""


@pytest.fixture
def shim_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "apptainer"
    shim.write_text(_APPTAINER_SHIM, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _plan(root: Path, fluid_cmd: str, solid_cmd: str, *, ceiling: int = 600) -> CoupledLaunchPlan:
    for name in ("fluid-openfoam", "solid-nutils"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return CoupledLaunchPlan(
        case_root_remote=str(root),
        participants=(
            ParticipantSpec(
                name="Fluid", workdir="fluid-openfoam", command=fluid_cmd, sif="precice-fsi.sif"
            ),
            ParticipantSpec(
                name="Solid", workdir="solid-nutils", command=solid_cmd, sif="precice-fsi.sif"
            ),
        ),
        sif_paths={"precice-fsi.sif": "/opt/aero/containers/precice-fsi.sif"},
        wall_clock_ceiling_s=ceiling,
        poll_interval_s=1,
        peer_grace_s=2,
        term_grace_s=2,
    )


def _run(plan: CoupledLaunchPlan, root: Path, shim_bin: Path, label: str):  # type: ignore[no-untyped-def]
    script = root / "run-coupled.sh"
    script.write_text(render_supervisor_script(plan), encoding="utf-8")
    env = dict(
        os.environ,
        PATH=f"{shim_bin}:{os.environ['PATH']}",
        AERO_TEST_CASE_ROOT=str(root),
        AERO_RUN_ID=label,
    )
    completed = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, env=env, timeout=300, check=False
    )
    return completed, read_coupled_status(
        root / "coupled-status.json",
        case_root_host=root,
        executor_returncode=completed.returncode,
    )


# --- pure rendering ----------------------------------------------------------------


def test_participant_command_is_exact() -> None:
    participant = ParticipantSpec(
        name="Fluid",
        workdir="fluid-openfoam",
        command="../../tools/run-openfoam.sh",
        sif="precice-fsi.sif",
    )
    assert build_participant_command(
        participant,
        case_root_remote="/mnt/aero/runs/x/tutorial/turek-hron-fsi3",
        sif_path="/opt/aero/containers/precice-fsi.sif",
    ) == (
        "apptainer exec --no-home --bind "
        "/mnt/aero/runs/x/tutorial/turek-hron-fsi3:/case "
        "/opt/aero/containers/precice-fsi.sif "
        "bash -lc 'cd /case && cd fluid-openfoam && ../../tools/run-openfoam.sh'"
    )


def test_no_home_is_always_passed() -> None:
    """Without --no-home the host $HOME shadows $FOAM_USER_LIBBIN and the adapter
    library silently fails to load at run time."""
    participant = ParticipantSpec(
        name="Fluid", workdir="f", command="blockMesh", sif="precice-fsi.sif"
    )
    command = build_participant_command(
        participant, case_root_remote="/case/root", sif_path="/x.sif"
    )
    assert command.startswith("apptainer exec --no-home ")


def test_env_is_exported_not_prefixed(shim_bin: Path, tmp_path: Path) -> None:
    """Regression: a `K=V` prefix binds only to the next command.

    The launcher used to hand the participant environment to
    `build_apptainer_exec(env=...)`, which emits `cd <target> && K=V <command>` — so the
    variable applied to the adapter's own `cd` and never reached the participant. The
    only symptom would have been at run time, with upstream's run.sh trying to build a
    venv from the network inside the SIF.
    """
    participant = ParticipantSpec(
        name="Solid",
        workdir="solid-nutils",
        command="./run.sh",
        sif="precice-fsi.sif",
        env={"PRECICE_TUTORIALS_NO_VENV": "1"},
    )
    command = build_participant_command(
        participant, case_root_remote="/case/root", sif_path="/x.sif"
    )
    assert "export PRECICE_TUTORIALS_NO_VENV=1 && ./run.sh" in command
    assert "PRECICE_TUTORIALS_NO_VENV=1 cd " not in command

    # Behavioural: the variable must be visible to the participant process itself.
    root = tmp_path / "case"
    (root / "solid-nutils").mkdir(parents=True)
    probe = root / "solid-nutils" / "run.sh"
    probe.write_text(
        '#!/usr/bin/env bash\necho "SEEN=${PRECICE_TUTORIALS_NO_VENV:-UNSET}"\n', encoding="utf-8"
    )
    probe.chmod(probe.stat().st_mode | stat.S_IEXEC)
    plan = CoupledLaunchPlan(
        case_root_remote=str(root),
        participants=(participant,),
        sif_paths={"precice-fsi.sif": "/x.sif"},
        wall_clock_ceiling_s=120,
        poll_interval_s=1,
        term_grace_s=2,
    )
    _, result = _run(plan, root, shim_bin, "envtest")
    assert result.ok
    assert "SEEN=1" in (root / "Solid.log").read_text(encoding="utf-8")


def test_supervisor_removes_a_stale_exchange_directory() -> None:
    """A stale precice-run/ is the single most common preCICE hang.

    It must be removed from the EXCHANGE directory, which is not the bind root: the bind
    root is the tutorial root (so upstream's ../../tools paths resolve) while preCICE
    creates precice-run/ beside the config, one level in.
    """
    script = render_supervisor_script(_plan(Path("/tmp/x"), "true", "true"))
    assert 'rm -rf "$CASE_ROOT/$EXCHANGE_DIR/precice-run"' in script
    assert "EXCHANGE_DIR=." in script

    nested = _plan(Path("/tmp/x"), "true", "true").model_copy(
        update={"exchange_dir": "turek-hron-fsi3"}
    )
    assert "EXCHANGE_DIR=turek-hron-fsi3" in render_supervisor_script(nested)


def test_executor_timeout_exceeds_the_supervisor_ceiling() -> None:
    """The supervisor, not the poller, must be the authority on when a run is over."""
    plan = _plan(Path("/tmp/x"), "true", "true", ceiling=172800)
    assert plan.executor_timeout_s > plan.wall_clock_ceiling_s


def test_plan_requires_a_path_for_every_sif() -> None:
    with pytest.raises(ValueError, match="no remote path"):
        CoupledLaunchPlan(
            case_root_remote="/case",
            participants=(
                ParticipantSpec(name="A", workdir="a", command="true", sif="a.sif"),
                ParticipantSpec(name="B", workdir="b", command="true", sif="b.sif"),
            ),
            sif_paths={"a.sif": "/opt/a.sif"},
            wall_clock_ceiling_s=120,
        )


# --- behaviour: the three stop paths ------------------------------------------------


def test_all_participants_exit_cleanly(shim_bin: Path, tmp_path: Path) -> None:
    root = tmp_path / "case"
    completed, result = _run(
        _plan(root, "sleep 1; exit 0", "sleep 1; exit 0"), root, shim_bin, "ok"
    )
    assert completed.returncode == 0
    assert result.stopped_by == "all-exited"
    assert result.ok
    assert all(o.state == "exited-ok" for o in result.outcomes)


def test_a_dead_participant_takes_the_coupling_down(shim_bin: Path, tmp_path: Path) -> None:
    """And the one that actually died is identifiable from its exit code."""
    root = tmp_path / "case"
    completed, result = _run(_plan(root, "sleep 120", "sleep 1; exit 3"), root, shim_bin, "died")
    assert result.stopped_by == "participant-died"
    assert not result.ok
    assert completed.returncode != 0
    assert result.outcome("Solid").state == "exited-fail"
    assert result.outcome("Solid").returncode == 3
    # Its peer was stopped by us, and says so rather than masquerading as a failure.
    assert result.outcome("Fluid").state == "killed"
    assert result.outcome("Fluid").returncode == 143


def test_the_wall_clock_ceiling_is_a_recorded_outcome(shim_bin: Path, tmp_path: Path) -> None:
    root = tmp_path / "case"
    completed, result = _run(
        _plan(root, "sleep 300", "sleep 300", ceiling=3), root, shim_bin, "ceiling"
    )
    assert completed.returncode == 124
    assert result.stopped_by == "ceiling"
    assert result.hit_ceiling
    assert not result.ok
    assert all(o.state == "killed" for o in result.outcomes)
    assert 3 <= result.wall_clock_s <= 30


def test_status_json_is_always_written(shim_bin: Path, tmp_path: Path) -> None:
    root = tmp_path / "case"
    _run(_plan(root, "exit 7", "exit 0"), root, shim_bin, "always")
    payload = json.loads((root / "coupled-status.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "always"
    assert {p["name"] for p in payload["participants"]} == {"Fluid", "Solid"}


def test_missing_status_is_loud(tmp_path: Path) -> None:
    from aero.adapters.precice.launcher import CoupledLaunchError

    with pytest.raises(CoupledLaunchError, match="no status file"):
        read_coupled_status(
            tmp_path / "coupled-status.json", case_root_host=tmp_path, executor_returncode=0
        )
