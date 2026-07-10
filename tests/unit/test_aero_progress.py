"""Hermetic tests for ``scripts/aero_progress.py`` (stdlib-only run monitor).

Builds synthetic case dirs under tmp_path — never touches /mnt/aero-nfs. The status-JSON
shape test pins the machine contract consumed by Claude waiters (--once --json --run X).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "aero_progress", Path(__file__).resolve().parents[2] / "scripts" / "aero_progress.py"
)
ap = importlib.util.module_from_spec(_SPEC)
sys.modules["aero_progress"] = ap  # dataclasses resolve types via sys.modules[__module__]
_SPEC.loader.exec_module(ap)

NOW = 1_800_000_000.0


def _controldict(end_time: float = 211.11503, application: str = "overPimpleDyMFoam") -> str:
    return f"""
FoamFile {{ version 2.0; format ascii; class dictionary; object controlDict; }}
application     {application};
startTime       0;
endTime         {end_time};
deltaT          0.010995574;
adjustTimeStep  yes;
purgeWrite      40;
functions
{{
    forces1 {{ type forces; writeControl timeStep; writeInterval 1; }}
    // decoy entries inside functions must NOT win over the top-level ones above
    dummy {{ endTime 999999; }}
}}
"""


def _log_block(sim_t: float, exec_s: float, clock_s: float) -> str:
    return (
        f"Courant Number mean: 0.0046 max: 1.99\n"
        f"deltaT = 0.00278\n"
        f"Time = {sim_t}\n\n"
        f"stuff...\nExecutionTime = {exec_s} s  ClockTime = {clock_s} s\n\n"
    )


def _make_case(
    root: Path,
    name: str = "flap_case",
    end_time: float = 211.11503,
    application: str = "overPimpleDyMFoam",
    log_points: list[tuple[float, float, float]] | None = None,
    log_end: bool = False,
    force_rows: list[float] | None = None,
    time_dirs: list[float] | None = None,
    sentinels: tuple[str, ...] = (),
    pad_log_to: int = 0,
    mtime: float | None = None,
    component_decoy: bool = False,
) -> Path:
    case = root / name
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text(_controldict(end_time, application))
    if component_decoy:
        (case / "component" / "system").mkdir(parents=True)
        (case / "component" / "system" / "controlDict").write_text(_controldict(end_time=1.0))
    if log_points is not None:
        text = "Exec   : overPimpleDyMFoam\n" + "x" * pad_log_to + "\n"
        text += "".join(_log_block(*p) for p in log_points)
        if log_end:
            text += "\nEnd\n"
        (case / "log.solve").write_text(text)
    if force_rows is not None:
        d = case / "postProcessing" / "forces1" / "0"
        d.mkdir(parents=True)
        rows = "# Time forces\n" + "".join(f"{t} 0.1 0.2 0.3\n" for t in force_rows)
        (d / "force.dat").write_text(rows)
    for t in time_dirs or []:
        (case / f"{t:g}").mkdir()
    for s in sentinels:
        (case / s).touch()
    if mtime is not None:
        for p in case.rglob("*"):
            import os

            os.utime(p, (mtime, mtime))
        import os

        os.utime(case, (mtime, mtime))
    return case


# ------------------------------------------------------------------ parsers


def test_controldict_top_level_first_match(tmp_path):
    case = _make_case(tmp_path)
    ctrl = ap.parse_controldict(case / "system" / "controlDict")
    assert float(ctrl["endTime"]) == pytest.approx(211.11503)  # not the functions{} decoy
    assert ctrl["application"] == "overPimpleDyMFoam"


def test_component_decoy_controldict_ignored(tmp_path):
    case = _make_case(tmp_path, component_decoy=True, log_points=[(100.0, 500.0, 510.0)])
    probe = ap.probe_run(case)
    assert probe.end_time == pytest.approx(211.11503)  # top-level, not component/ (endTime 1.0)


def test_log_tail_on_large_log_and_end_marker(tmp_path):
    points = [(150.0 + i, 1000.0 + 60 * i, 1010.0 + 60 * i) for i in range(10)]
    case = _make_case(tmp_path, log_points=points, pad_log_to=100_000, log_end=True)
    probe = ap.probe_run(case)
    assert probe.sim_time == pytest.approx(159.0)
    assert probe.sim_source == "log.solve"
    assert probe.log_end_seen
    assert len(probe.exec_pairs) == 10  # padding pushed nothing relevant out of the 64 KB tail


def test_tail_rate_and_restart_guard(tmp_path):
    case = _make_case(tmp_path, log_points=[(100.0, 1000.0, 1000.0), (109.0, 1900.0, 1900.0)])
    probe = ap.probe_run(case)
    assert ap.tail_rate(probe) == pytest.approx(9.0 / 900.0)
    # mid-tail ExecutionTime reset (solver restart) must be discarded, not produce a bogus rate
    reset = _make_case(
        tmp_path, name="reset", log_points=[(100.0, 9000.0, 9000.0), (109.0, 60.0, 60.0)]
    )
    assert ap.tail_rate(ap.probe_run(reset)) is None


def test_force_dat_variants(tmp_path):
    flat = _make_case(tmp_path, name="flat", force_rows=[1.0, 2.0, 3.5])
    assert ap.probe_run(flat).sim_time == pytest.approx(3.5)
    d = tmp_path / "paren" / "postProcessing" / "forces1" / "0"
    _make_case(tmp_path, name="paren")
    d.mkdir(parents=True)
    (d / "force.dat").write_text("# Time\n0.5 ((0.1 0.2 0.3) (0 0 0))\n0.7 ((0.1 0.2 0.3))\n")
    assert ap.last_data_line(d / "force.dat") == pytest.approx(0.7)
    assert ap.last_data_line(Path(tmp_path / "nope.dat")) is None
    comments = tmp_path / "c.dat"
    comments.write_text("# only\n# comments\n")
    assert ap.last_data_line(comments) is None


def test_executor_run_without_log_uses_force_and_time_dirs(tmp_path):
    case = _make_case(tmp_path, name="naca0012-x", force_rows=[10.0, 20.0], time_dirs=[15.0, 25.0])
    probe = ap.probe_run(case)
    assert probe.sim_time == pytest.approx(25.0)
    assert probe.sim_source == "time-dirs"


# ------------------------------------------------------------------ classify


@pytest.mark.parametrize(
    ("sentinels", "log_end", "age", "expected"),
    [
        ((".failed",), False, 10, "failed"),
        ((".done",), False, 10, "done"),
        ((), True, 10, "done"),  # End marker
        ((), False, 10, "running"),
        ((), False, 5000, "stale"),
    ],
)
def test_classify_matrix(tmp_path, sentinels, log_end, age, expected):
    case = _make_case(
        tmp_path,
        log_points=[(100.0, 500.0, 510.0)],
        log_end=log_end,
        sentinels=sentinels,
        mtime=NOW - age,
    )
    assert ap.classify(ap.probe_run(case), NOW) == expected


def test_classify_done_presumed_at_endtime(tmp_path):
    case = _make_case(tmp_path, log_points=[(211.115, 900.0, 910.0)], mtime=NOW - 5000)
    assert ap.classify(ap.probe_run(case), NOW) == "done"


def test_classify_setup_before_solve_output(tmp_path):
    case = _make_case(tmp_path, mtime=NOW - 60)
    assert ap.classify(ap.probe_run(case), NOW) == "setup"


# ------------------------------------------------------------------ sampler / ETA / store


def test_windowed_rate_and_short_history():
    samples = [[NOW - 1800, 100.0], [NOW - 900, 109.0], [NOW, 118.0]]
    assert ap.windowed_rate(samples, NOW, 2700) == pytest.approx(18.0 / 1800.0)
    assert ap.windowed_rate([[NOW, 100.0]], NOW, 2700) is None
    assert ap.windowed_rate([[NOW - 60, 100.0], [NOW, 101.0]], NOW, 2700) is None  # span < 120 s


def test_state_store_roundtrip_backwards_reset_and_prune(tmp_path):
    store = ap.StateStore(tmp_path / "state.json")
    store.load()
    store.add_sample("r1", NOW - 60, 100.0, 2700)
    store.add_sample("r1", NOW, 110.0, 2700)
    store.save()
    store2 = ap.StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.data["runs"]["r1"]["samples"] == [[NOW - 60, 100.0], [NOW, 110.0]]
    store2.add_sample("r1", NOW + 60, 50.0, 2700)  # sim time went backwards -> reset history
    assert store2.data["runs"]["r1"]["samples"] == [[NOW + 60, 50.0]]
    store2.prune(set())
    assert store2.data["runs"] == {}
    corrupt = ap.StateStore(tmp_path / "state.json")
    (tmp_path / "state.json").write_text("{broken")
    corrupt.load()
    assert corrupt.data == {"runs": {}}


# ------------------------------------------------------------------ status contract


def _status_for(tmp_path, **kwargs):
    case = _make_case(tmp_path, **kwargs)
    store = ap.StateStore(tmp_path / "state.json")
    store.load()
    return ap.build_status([ap.probe_run(case)], store, NOW, 2700, 900)


def test_status_json_shape_pin(tmp_path):
    status = _status_for(
        tmp_path, log_points=[(100.0, 1000.0, 1000.0), (109.0, 1900.0, 1900.0)], mtime=NOW - 10
    )
    assert set(status) == {"generated_at", "runs_root", "runs"}
    (run,) = status["runs"]
    assert set(run) == {
        "run_id",
        "application",
        "state",
        "percent",
        "sim_time",
        "start_time",
        "end_time",
        "sim_source",
        "rate_sim_per_hour",
        "rate_basis",
        "eta_s",
        "eta_iso",
        "eta_human",
        "eta_upper_bound",
        "clock_time_s",
        "last_update_iso",
        "age_s",
        "error",
    }
    assert run["state"] == "running"
    assert run["percent"] == pytest.approx(51.6, abs=0.1)  # 109 / 211.115
    assert run["rate_basis"] == "log-tail"
    assert run["eta_s"] == pytest.approx((211.11503 - 109.0) / 0.01, rel=0.01)
    json.dumps(status)  # must be serialisable as-is


def test_steady_run_eta_marked_upper_bound(tmp_path):
    status = _status_for(
        tmp_path,
        application="simpleFoam",
        end_time=3000,
        log_points=[(500.0, 100.0, 100.0), (1000.0, 200.0, 200.0)],
        mtime=NOW - 10,
    )
    assert status["runs"][0]["eta_upper_bound"] is True


# ------------------------------------------------------------------ discovery


def test_discovery_filters_by_mtime_but_keeps_armed_runs(tmp_path):
    _make_case(tmp_path, name="old_done", sentinels=(".done",), mtime=NOW - 10 * 86400)
    _make_case(tmp_path, name="fresh", mtime=NOW - 3600)
    _make_case(tmp_path, name="old_armed", sentinels=(".assembled",), mtime=NOW - 10 * 86400)
    (tmp_path / "not_a_case").mkdir()
    found = {p.name for p in ap.discover_runs(tmp_path, max_age_days=3, now=NOW)}
    assert found == {"fresh", "old_armed"}
    all_found = {p.name for p in ap.discover_runs(tmp_path, include_all=True)}
    assert all_found == {"old_done", "fresh", "old_armed"}
    named = {p.name for p in ap.discover_runs(tmp_path, names=["old_done"])}
    assert named == {"old_done"}


# ------------------------------------------------------------------ notifier


def test_notifier_transitions_and_dedupe_across_restart(tmp_path):
    sent: list[tuple[str, str]] = []

    def fake_post(url, title, message, priority="default", tags=""):
        assert title.encode("latin-1", errors="strict")  # HTTP headers must stay latin-1-safe
        sent.append((title, priority))
        return True

    store = ap.StateStore(tmp_path / "state.json")
    store.load()
    status = {
        "runs": [
            {"run_id": "r1", "state": "done", "clock_time_s": 7200, "percent": 100.0, "age_s": 10}
        ]
    }
    ap.process_notifications(status, store, "http://x/topic", False, post=fake_post)
    ap.process_notifications(status, store, "http://x/topic", False, post=fake_post)
    assert len(sent) == 1  # dedupe within a process
    store.save()
    store2 = ap.StateStore(tmp_path / "state.json")
    store2.load()
    ap.process_notifications(status, store2, "http://x/topic", False, post=fake_post)
    assert len(sent) == 1  # dedupe survives a daemon restart

    failed = {
        "runs": [
            {"run_id": "r2", "state": "failed", "clock_time_s": 60, "percent": 3.0, "age_s": 10}
        ]
    }
    ap.process_notifications(failed, store2, "http://x/topic", False, post=fake_post)
    assert sent[-1] == ("r2 FAILED", "high")

    # stale alert only fires with the flag, only on running->stale, and re-arms on recovery
    running = {
        "runs": [
            {"run_id": "r3", "state": "running", "clock_time_s": 60, "percent": 10.0, "age_s": 10}
        ]
    }
    stale = {
        "runs": [
            {"run_id": "r3", "state": "stale", "clock_time_s": 60, "percent": 10.0, "age_s": 2000}
        ]
    }
    ap.process_notifications(running, store2, "http://x/topic", True, post=fake_post)
    ap.process_notifications(stale, store2, "http://x/topic", True, post=fake_post)
    assert sent[-1][0] == "r3 stalled"
    n = len(sent)
    ap.process_notifications(running, store2, "http://x/topic", True, post=fake_post)
    ap.process_notifications(stale, store2, "http://x/topic", True, post=fake_post)
    assert len(sent) == n + 1  # re-armed after recovery -> fires again


def test_fresh_state_baseline_records_without_posting(tmp_path):
    """A brand-new daemon must not flood the topic with catch-up pushes (43 runs, once)."""
    store = ap.StateStore(tmp_path / "state.json")
    store.load()
    done = {
        "runs": [{"run_id": "r1", "state": "done", "clock_time_s": 1, "percent": 100.0, "age_s": 1}]
    }
    ap.process_notifications(
        done,
        store,
        "http://x/topic",
        False,
        post=lambda *a, **k: pytest.fail("baseline must not post"),
        record_only=True,
    )
    assert store.data["runs"]["r1"]["notified"] == {"done": True}
    sent = []
    ap.process_notifications(  # subsequent normal cycles stay silent for the same run
        done, store, "http://x/topic", False, post=lambda *a, **k: sent.append(1) or True
    )
    assert sent == []


def test_no_notify_url_is_noop(tmp_path):
    store = ap.StateStore(tmp_path / "state.json")
    store.load()
    status = {
        "runs": [{"run_id": "r1", "state": "done", "clock_time_s": 1, "percent": 100.0, "age_s": 1}]
    }
    ap.process_notifications(status, store, None, False, post=lambda *a, **k: pytest.fail("sent"))
