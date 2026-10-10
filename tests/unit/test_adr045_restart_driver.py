"""ADR-045 R1/R2/R5/R7 on the driver side: the relaunch INTO the existing case root.

The adapter patch (containers/calculix-precice-adr045.patch) writes the solid's state at
the converged window boundary and re-enters the step from it; this file pins what the
DRIVER does around that: the hash-exempt exports the Solid participant receives, the
rotation of everything a relaunch would truncate (A8), the fluid's explicit startTime and
preCICE's remaining time (A7/A13), the R5 bounds computed from the reference run, the
record a restarted segment carries (R7), and the read-back gate that refuses a gated
verdict on a restarted solve without a passing R3 (A4).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from aero.adapters.precice.case import CASE_ROOT_DIRNAME, spec_config_digest
from aero.adapters.precice.launcher import (
    CheckpointOptions,
    ObservabilityOptions,
    build_participant_command,
    render_supervisor_script,
)
from aero.adapters.precice.solver import PreciceCoupledSolver
from aero.vv.fsi.hg2007_flexible_foil import hg2007_case_spec
from pydantic import ValidationError

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
DT = 2e-5
N = 50
W = 20


def _driver():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


_KNOBS = {
    "arm": "flexible",
    "rung": "mid",
    "time_window_size": DT,
    "max_time": N * DT,
    "wall_clock_ceiling_s": 3600,
    "numerics_label": "adr040-candidate",
    "mpi_ranks": 4,
    "coupling_scheme": "parallel-implicit",
    "hht_alpha": -0.05,
    "solid_sif": "calculix-precice.sif",
}


# --- the launcher's exports ---------------------------------------------------------------


def _case_dir(spec: Any, host: Path) -> Any:
    from aero.adapters._base import CaseDir

    return CaseDir(run_id="hg2007_flexible_foil-fake", spec=spec, host_path=host, remote_path=host)


def test_inert_checkpoint_options_leave_the_command_bytes_alone() -> None:
    spec = hg2007_case_spec(**_KNOBS)  # type: ignore[arg-type]
    plan = PreciceCoupledSolver().launch_plan(_case_dir(spec, Path("/tmp/x")))
    solid = next(p for p in plan.participants if p.name == "Solid")
    bare = build_participant_command(solid, case_root_remote="/case", sif_path="/s.sif")
    inert = build_participant_command(
        solid, case_root_remote="/case", sif_path="/s.sif", checkpoint=CheckpointOptions()
    )
    assert inert == bare and "AERO_" not in bare


def test_the_solid_and_only_the_solid_gets_the_checkpoint_exports() -> None:
    spec = hg2007_case_spec(**_KNOBS)  # type: ignore[arg-type]
    plan = PreciceCoupledSolver().launch_plan(_case_dir(spec, Path("/tmp/x")))
    plan = plan.model_copy(
        update={"checkpoint": CheckpointOptions(every_windows=2000, at_windows=(400,))}
    )
    script = render_supervisor_script(plan)
    assert script.count("AERO_CKPT_EVERY=2000") == 1
    assert "AERO_CKPT_AT=400 AERO_CKPT_KEEP=2" in script
    fluid = next(p for p in plan.participants if p.name == "Fluid")
    assert "AERO_" not in build_participant_command(
        fluid, case_root_remote="/case", sif_path="/s.sif", checkpoint=plan.checkpoint
    )


def test_a_restart_without_its_r5_bounds_is_refused_at_construction() -> None:
    with pytest.raises(ValidationError, match="R5"):
        CheckpointOptions(restart_file="aero-checkpoint-w4000.bin", restart_window=4000)
    options = CheckpointOptions(
        every_windows=2000,
        restart_file="aero-checkpoint-w4000.bin",
        restart_window=4000,
        max_displacement=1.5e-3,
        energy_min=5e-9,
        energy_max=5e-7,
    )
    exports = options.exports()
    for token in (
        "AERO_RESTART_FILE=aero-checkpoint-w4000.bin",
        "AERO_RESTART_WINDOW=4000",
        "AERO_RESTART_MAX_DISP=0.0015",
        "AERO_RESTART_ENERGY_MIN=5e-09",
        "AERO_RESTART_ENERGY_MAX=5e-07",
        "AERO_CKPT_EVERY=2000",
    ):
        assert token in exports, token


# --- the relaunch --------------------------------------------------------------------------


def _write_run(
    tmp_path: Path, name: str, *, checkpoint: bool = True, windows: int = W + 5
) -> tuple[Path, Path]:
    """A materialised case with a finished first segment: logs, a solid checkpoint at W,
    a fluid dump at W, plus the CalculiX outputs a relaunch must not truncate."""
    driver = _driver()
    spec = hg2007_case_spec(**_KNOBS)  # type: ignore[arg-type]
    host = tmp_path / name
    # The case writer chowns the tree to the participant uid, which a non-root CI runner
    # cannot do (and this test does not care about ownership).
    with mock.patch("aero.adapters.precice.solver._chown_tree"):
        PreciceCoupledSolver()._write_case(spec, host)
    root = host / CASE_ROOT_DIRNAME
    exchange = next(root.glob("hg2007-*-foil"))
    solid = exchange / "solid-calculix"
    fluid = exchange / "fluid-openfoam"
    (root / "Fluid.log").write_text("aeroInterfacePower 0 0 0 0\n", encoding="utf-8")
    lines = []
    for w in range(1, windows + 1):
        lines.append(
            f"---[precice] \x1b[0m it 1 (min: 1, max: 50), time-window {w}, t {w * DT} (max: 0.001), Dt 2e-05, max-dt 2e-05\n"
        )
        lines.append(f" internal energy = {1.0e-9 * w:e}\n kinetic energy = {2.0e-9 * w:e}\n")
    (root / "Solid.log").write_text("".join(lines), encoding="utf-8")
    (root / "coupled-status.json").write_text(
        json.dumps(
            {
                "run_id": name,
                "stopped_by": "participant-died",
                "started_epoch": 1,
                "ended_epoch": 2,
                "wall_clock_s": 1,
                "participants": [
                    {
                        "name": "Fluid",
                        "returncode": 143,
                        "started_epoch": 1,
                        "ended_epoch": 2,
                        "log_path": "x",
                    },
                    {
                        "name": "Solid",
                        "returncode": 143,
                        "started_epoch": 1,
                        "ended_epoch": 2,
                        "log_path": "y",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "run-coupled.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    for log in (
        "precice-Solid-iterations.log",
        "precice-Solid-watchpoint-Trailing-Edge.log",
        "precice-Solid-convergence.log",
    ):
        (solid / log).write_text("header\n", encoding="utf-8")
    (solid / "precice-profiling").mkdir()
    (fluid / "precice-Fluid-iterations.log").write_text("header\n", encoding="utf-8")
    for ext in (".sta", ".cvg", ".dat", ".frd"):
        (solid / f"hg2007-flexible-solid{ext}").write_text("ccx\n", encoding="utf-8")
    if checkpoint:
        (solid / f"aero-checkpoint-w{W}.bin").write_bytes(b"AEROCKPT" + b"\0" * 64)
    t_name = f"{W * DT:.12g}"
    for rank in range(4):
        dump = fluid / f"processor{rank}" / t_name
        (dump / "polyMesh").mkdir(parents=True)
        (dump / "uniform").mkdir()
        for f in driver._FLUID_RESTART_FILES:
            (dump / f).write_text("field\n", encoding="utf-8")
    submission = {
        "schema": driver.SUBMISSION_SCHEMA,
        "run_id": name,
        "session": f"fsi-{name}",
        "host": "aero-dev",
        "arm": "flexible",
        "rung": "mid",
        "gated": False,
        "observability": {"core_dumps": True, "malloc_check": False, "asan": False},
        "spec_knobs": dict(_KNOBS),
        "spec_sha256": spec_config_digest(spec),
        "case_host_path": str(host),
        "case_remote_path": str(host),
    }
    sub = tmp_path / f"{name}-submission.json"
    sub.write_text(json.dumps(submission), encoding="utf-8")
    return sub, root


class _Status:
    def __init__(self, returncode: int, text: str) -> None:
        self.returncode = returncode
        self.stdout = text
        self.stderr = ""


class _Submit:
    transport_failed = False
    returncode = 0
    stderr = ""


class _Executor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def submit_detached(self, command: str, *, session: str) -> _Submit:
        self.calls.append((command, session))
        return _Submit()


def _args(driver: Any, **kw: Any) -> Any:
    base = {
        "restart": None,
        "restart_window": W,
        "restart_reference": None,
        "ckpt_every": 2000,
        "ckpt_at": None,
        "out": None,
        "host": "aero-dev",
        "host_nfs_root": None,
        "remote_nfs_root": None,
    }
    base.update(kw)
    return driver.argparse.Namespace(**base)


def test_a_restart_rotates_patches_the_clocks_and_records_the_segment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    sub, root = _write_run(tmp_path, "hg2007_flexible_foil-treat")
    ref, _ = _write_run(tmp_path, "hg2007_flexible_foil-ref")
    executor = _Executor()
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(1, "session: failed"))
    monkeypatch.setattr(driver, "_executor", lambda *a, **k: executor)

    rc = driver._restart(_args(driver, restart=sub, restart_reference=ref))

    assert rc == 0
    exchange = next(root.glob("hg2007-*-foil"))
    solid, fluid = exchange / "solid-calculix", exchange / "fluid-openfoam"
    # A8: rotated, not truncated
    for name in ("Fluid.seg1.log", "Solid.seg1.log", "coupled-status.seg1.json", "run-coupled.sh"):
        assert (root / name).exists(), name
    assert not (root / "Solid.log").exists() and not (root / "coupled-status.json").exists()
    assert (solid / "precice-Solid-iterations.seg1.log").exists()
    assert (solid / "precice-Solid-watchpoint-Trailing-Edge.seg1.log").exists()
    assert (solid / "precice-profiling.seg1").is_dir()
    assert (fluid / "precice-Fluid-iterations.seg1.log").exists()
    assert (solid / "hg2007-flexible-solid.seg1.sta").exists()
    # A13: an explicit startTime at the dump; endTime untouched
    control = (fluid / "system" / "controlDict").read_text(encoding="utf-8")
    assert f"startTime       {W * DT:.12g};" in control and "startFrom       startTime;" in control
    # A7: preCICE gets the remaining time
    config = (exchange / "precice-config.xml").read_text(encoding="utf-8")
    assert f'max-time value="{float(f"{(N - W) * DT:.13e}")!r}"' in config
    # A18: every exchange gains initialize="true" so the fresh preCICE seeds from the
    # restored state instead of snapping the fluid interface to zero (session-15 finding)
    assert config.count('initialize="true"') == 2
    # the Solid's exports carry the restart and its R5 bounds; the cadence continues
    script = (root / "run-coupled.sh").read_text(encoding="utf-8")
    assert f"AERO_RESTART_FILE=aero-checkpoint-w{W}.bin" in script
    assert f"AERO_RESTART_WINDOW={W}" in script and "AERO_CKPT_EVERY=2000" in script
    (_command, session) = executor.calls[0]
    assert session == "fsi-hg2007_flexible_foil-treat-seg2"
    # R7: the record
    record = json.loads((root.parent / "restart-seg2-submission.json").read_text(encoding="utf-8"))
    assert record["restart_generations"] == 1 and record["restart_windows"] == [W]
    assert (
        record["restart"]["segment"] == 2
        and record["restart"]["fluid_time_dir"] == f"{W * DT:.12g}"
    )
    assert record["restart"]["bounds"]["reference_energy_j"] == pytest.approx(3.0e-9 * W)
    assert record["restart"]["bounds"]["energy_min"] == pytest.approx(3.0e-10 * W)
    assert record["restart"]["bounds"]["max_displacement"] > 0.0
    assert [m["kind"] for m in record["restart"]["mutations"]] == [
        "fluid-startTime",
        "max-time+exchange-initialize",
    ]
    assert record["spec_sha256"] == json.loads(sub.read_text(encoding="utf-8"))["spec_sha256"]
    assert record["session"] == session


def test_a_restart_refuses_a_missing_checkpoint_or_a_purged_fluid_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(1, "session: failed"))
    monkeypatch.setattr(driver, "_executor", lambda *a, **k: _Executor())
    ref, _ = _write_run(tmp_path, "hg2007_flexible_foil-ref")
    sub, _ = _write_run(tmp_path / "a", "hg2007_flexible_foil-nockpt", checkpoint=False)
    with pytest.raises(SystemExit, match="no solid checkpoint"):
        driver._restart(_args(driver, restart=sub, restart_reference=ref))
    sub, root = _write_run(tmp_path / "b", "hg2007_flexible_foil-purged")
    exchange = next(root.glob("hg2007-*-foil"))
    (exchange / "fluid-openfoam" / "processor2" / f"{W * DT:.12g}" / "U").unlink()
    with pytest.raises(SystemExit, match="not a restartable fluid dump"):
        driver._restart(_args(driver, restart=sub, restart_reference=ref))


def test_a_running_job_is_not_relaunched_into(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    sub, _ = _write_run(tmp_path, "hg2007_flexible_foil-live")
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(2, "session: running"))
    with pytest.raises(SystemExit, match="still running"):
        driver._restart(_args(driver, restart=sub, restart_reference=sub))


def test_the_r5_bounds_read_the_reference_at_the_same_window(tmp_path: Path) -> None:
    driver = _driver()
    _, root = _write_run(tmp_path, "hg2007_flexible_foil-ref", windows=30)
    assert driver._energy_at_window(root / "Solid.log", 7) == pytest.approx(3.0e-9 * 7)
    with pytest.raises(SystemExit, match="energy blocks"):
        driver._energy_at_window(root / "Solid.log", 31)
    amp = next(root.glob("hg2007-*-foil")) / "solid-calculix" / "plunge.amp"
    bound = driver._plunge_bound(amp, W)
    rows = [
        line for line in amp.read_text(encoding="utf-8").splitlines() if not line.startswith("*")
    ]
    assert bound == pytest.approx(3.0 * max(abs(float(r.split(",")[1])) for r in rows[: W + 1]))


def test_a_restarted_gated_solve_needs_a_passing_r3_on_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    monkeypatch.setattr(driver, "_REPO_ROOT", tmp_path)
    driver._assert_restart_admissible({"run_id": "x", "restart_generations": 0, "gated": True})
    driver._assert_restart_admissible({"run_id": "x", "restart_generations": 2, "gated": False})
    with pytest.raises(SystemExit, match="no R3 record"):
        driver._assert_restart_admissible({"run_id": "x", "restart_generations": 1, "gated": True})
    record = tmp_path / "data" / "vv" / driver.R3_RECORD_NAME
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"passed": False}), encoding="utf-8")
    with pytest.raises(SystemExit, match="did not pass"):
        driver._assert_restart_admissible({"run_id": "x", "restart_generations": 1, "gated": True})
    record.write_text(json.dumps({"passed": True}), encoding="utf-8")
    driver._assert_restart_admissible({"run_id": "x", "restart_generations": 1, "gated": True})


def test_every_submission_records_its_checkpoint_cadence() -> None:
    """The cadence is a fact about the run, recorded like the observability (R2)."""
    options = CheckpointOptions(every_windows=2000)
    assert json.loads(options.model_dump_json())["every_windows"] == 2000
    assert ObservabilityOptions().any_enabled is False  # unchanged sibling
