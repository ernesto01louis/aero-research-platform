"""ADR-045 R6: the sanitizer hunt's reading is derived, and the evidence lands beside the run.

The hunt (`fsi-hg2007_flexible_foil-20260915-113918`) was running when this file was
written, and that is the point: the rule that reads it is fixed BEFORE the report exists,
exactly as ADR-044 Z4 demanded of the run it graded. Three things have to hold:

**The reading is computed, never typed in.** R6's vocabulary is closed -- ADAPTER-LINE /
CALCULIX-LINE / NO-REPORT-COMPLETED / NO-REPORT-DIED / UNCLASSIFIED -- and the mapping from
(the parsed reports, the run's outcome) onto it is code.

**Ownership is decided by PATH, never by basename.** The adapter tree compiled into
``ccx_preCICE`` carries its own ``ccx_2.20.c``; CalculiX ships one too. The one real
report on disk prints ``/src/CalculiX/ccx_2.20/src/keystart.f:71`` and
``/src/calculix-adapter/ccx_2.20.c:195``, so the rule keys on those prefixes.

**The known-benign READ never decides anything.** It fires on every run, including two that
completed 8000 windows, and a read cannot corrupt heap metadata (handoff §6.72). The real
report from the first hunt attempt is the fixture, verbatim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from aero.adapters.precice.asan import (
    AsanReport,
    classify_frame_path,
    find_asan_reports,
    parse_asan_reports,
)
from aero.vv.fsi.hg2007_flexible_foil import asan_hunt_verdict

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _driver():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


# The real report: /mnt/aero-nfs/runs/hg2007_flexible_foil-20260915-113507/tutorial/
# asan-solid.2431025 (the first hunt attempt, 32 s, halt_on_error=1). Verbatim.
REAL_BENIGN_REPORT = """\
=================================================================
==2431025==ERROR: AddressSanitizer: global-buffer-overflow on address 0x5a3277524385 at pc 0x7abbb6ec5eaa bp 0x7fff44b039a0 sp 0x7fff44b03148
READ of size 12 at 0x5a3277524385 thread T0
    #0 0x7abbb6ec5ea9 in MemcmpInterceptorCommon(void*, int (*)(void const*, void const*, unsigned long), void const*, void const*, unsigned long) ../../../../src/libsanitizer/sanitizer_common/sanitizer_common_interceptors.inc:813
    #1 0x7abbb6ec637a in memcmp ../../../../src/libsanitizer/sanitizer_common/sanitizer_common_interceptors.inc:845
    #2 0x7abbb6ec637a in memcmp ../../../../src/libsanitizer/sanitizer_common/sanitizer_common_interceptors.inc:840
    #3 0x7abbb6077f6b in _gfortran_compare_string (/lib/x86_64-linux-gnu/libgfortran.so.5+0x2d1f6b) (BuildId: 43c25b99f1801797aedd2bfedb0d7af6cf4fe7dc)
    #4 0x5a3276de35f2 in keystart_ /src/CalculiX/ccx_2.20/src/keystart.f:71
    #5 0x5a3276ad79dc in readinput /src/CalculiX/ccx_2.20/src/readinput.c:341
    #6 0x5a327665eb57 in main /src/calculix-adapter/ccx_2.20.c:195
    #7 0x7abbb5ad41c9 in __libc_start_call_main ../sysdeps/nptl/libc_start_call_main.h:58
    #8 0x7abbb5ad428a in __libc_start_main_impl ../csu/libc-start.c:360
    #9 0x5a3276692434 in _start (/opt/calculix/bin/ccx_preCICE+0x18b434) (BuildId: e20e8135ce7df346fd8e70161e9356e026c626d2)

0x5a3277524385 is located 0 bytes after global variable '*.LC65' defined in '/src/CalculiX/ccx_2.20/src/readinput.c' (0x5a3277524380) of size 5
  '*.LC65' is ascii string 'NODE'
0x5a3277524385 is located 59 bytes before global variable '*.LC66' defined in '/src/CalculiX/ccx_2.20/src/readinput.c' (0x5a32775243c0) of size 6
  '*.LC66' is ascii string '*NSET'
SUMMARY: AddressSanitizer: global-buffer-overflow ../../../../src/libsanitizer/sanitizer_common/sanitizer_common_interceptors.inc:813 in MemcmpInterceptorCommon(void*, int (*)(void const*, void const*, unsigned long), void const*, void const*, unsigned long)
Shadow bytes around the buggy address:
  0x5a3277524100: 00 03 f9 f9 f9 f9 f9 f9 00 00 03 f9 f9 f9 f9 f9
=>0x5a3277524380:[05]f9 f9 f9 f9 f9 f9 f9 06 f9 f9 f9 f9 f9 f9 f9
Shadow byte legend (one shadow byte represents 8 application bytes):
  Addressable:           00
  Global redzone:        f9
==2431025==ABORTING
"""


def _frames(*locs: str) -> str:
    return "".join(
        f"    #{i} 0x{0x5A3276000000 + i:x} in fn{i} {loc}\n" for i, loc in enumerate(locs)
    )


def _heap_report(
    *,
    pid: int = 777,
    kind: str = "heap-buffer-overflow",
    access: str = "WRITE",
    access_frames: tuple[str, ...],
    allocated_frames: tuple[str, ...] = (),
    freed_frames: tuple[str, ...] = (),
) -> str:
    text = (
        "=================================================================\n"
        f"=={pid}==ERROR: AddressSanitizer: {kind} on address 0x602000000090 at pc "
        "0x5a327665eb57 bp 0x7ffd sp 0x7ffc\n"
        f"{access} of size 8 at 0x602000000090 thread T0\n"
        + _frames(*access_frames)
        + "\n0x602000000090 is located 0 bytes after 80-byte region [0x602000000040,"
        "0x602000000090)\n"
    )
    if freed_frames:
        text += "freed by thread T0 here:\n" + _frames(*freed_frames) + "\n"
    if allocated_frames:
        text += "previously allocated by thread T0 here:\n" + _frames(*allocated_frames) + "\n"
    text += f"SUMMARY: AddressSanitizer: {kind} {access_frames[0]} in fn0\n"
    text += "Shadow bytes around the buggy address:\n  0x0c047fff8000: fa fa 00 00\n"
    text += f"=={pid}==ABORTING\n"
    return text


ASAN_RT = "../../../../src/libsanitizer/asan/asan_interceptors_memintrinsics.cpp:22"
ADAPTER_C = "/src/calculix-adapter/nonlingeo_precice.c:1690"
ADAPTER_IFACE = "/src/calculix-adapter/adapter/PreciceInterface.c:702"
CCX_F = "/src/CalculiX/ccx_2.20/src/results.f:311"
CCX_C = "/src/CalculiX/ccx_2.20/src/u_calloc.c:55"
CCX_MAIN = "/src/CalculiX/ccx_2.20/src/ccx_2.20.c:1041"
LIBC = "../sysdeps/nptl/libc_start_call_main.h:58"


# --- the parser and the ownership rule -------------------------------------------------


def test_the_real_report_parses_and_is_the_known_benign_read() -> None:
    (report,) = parse_asan_reports(REAL_BENIGN_REPORT)
    assert report.pid == 2431025
    assert report.kind == "global-buffer-overflow"
    assert (report.access, report.size, report.address) == ("READ", 12, "0x5a3277524385")
    assert report.summary is not None and report.summary.startswith("global-buffer-overflow")
    (access,) = report.stacks
    assert access.role == "access"
    assert [f.index for f in access.frames] == list(range(10))
    owners = [f.owner for f in access.frames]
    assert owners == ["runtime"] * 4 + ["calculix-upstream"] * 2 + ["adapter"] + ["runtime"] * 3
    assert access.frames[6].path == "/src/calculix-adapter/ccx_2.20.c"
    assert access.frames[6].line == 195
    assert access.frames[3].path is None  # (lib+0x...) frame, BuildId stripped
    assert access.frames[3].function == "_gfortran_compare_string"
    site = access.site
    assert site is not None and site.path is not None
    assert (Path(site.path).name, site.line) == ("keystart.f", 71)
    assert report.known_benign is True
    assert report.heap_relevant is False


def test_ownership_is_decided_by_path_never_by_basename() -> None:
    assert classify_frame_path("/src/calculix-adapter/ccx_2.20.c") == "adapter"
    assert classify_frame_path("/src/CalculiX/ccx_2.20/src/ccx_2.20.c") == "calculix-upstream"
    # a relative path for an unambiguous adapter file (comp_dir not joined) is still ours
    assert classify_frame_path("adapter/PreciceInterface.c") == "adapter"
    assert classify_frame_path("nonlingeo_precice.c") == "adapter"
    # a bare ccx_2.20.c is AMBIGUOUS and must not be claimed either way
    assert classify_frame_path("ccx_2.20.c") == "unknown"
    assert classify_frame_path(None) == "runtime"
    assert classify_frame_path(ASAN_RT) == "runtime"
    assert classify_frame_path(LIBC) == "runtime"
    assert classify_frame_path("/home/someone/elsewhere/thing.c") == "unknown"
    # CalculiX's allocator wrappers sit on top of EVERY allocation stack, ours included;
    # the line that sized the object is the caller above them
    assert classify_frame_path("/src/CalculiX/ccx_2.20/src/u_calloc.c") == "runtime"
    assert classify_frame_path("/src/CalculiX/ccx_2.20/src/u_free.c") == "runtime"


def test_a_heap_report_carries_its_allocation_stack_and_every_site() -> None:
    (report,) = parse_asan_reports(
        _heap_report(access_frames=(ASAN_RT, CCX_F), allocated_frames=(ASAN_RT, CCX_C, ADAPTER_C))
    )
    assert report.kind == "heap-buffer-overflow"
    assert report.access == "WRITE"
    assert [s.role for s in report.stacks] == ["access", "allocated"]
    assert [s.site_text.split(" at ")[1] for s in report.sites] == [
        f"{CCX_F} [calculix-upstream]",
        f"{ADAPTER_C} [adapter]",  # u_calloc.c is the wrapper; the caller sized the object
    ]
    assert report.known_benign is False
    assert report.heap_relevant is True


def test_free_family_headers_parse_to_their_bug_class() -> None:
    double_free = (
        "==5==ERROR: AddressSanitizer: attempting double-free on 0x602000000090 in thread T0:\n"
        + _frames(ASAN_RT, ADAPTER_IFACE)
        + "0x602000000090 is located 0 bytes inside of 80-byte region\n"
        "freed by thread T0 here:\n" + _frames(ASAN_RT, ADAPTER_IFACE) + "\n"
        "previously allocated by thread T0 here:\n" + _frames(ASAN_RT, CCX_C) + "\n"
        "SUMMARY: AddressSanitizer: double-free x in free\n==5==ABORTING\n"
    )
    (report,) = parse_asan_reports(double_free)
    assert report.kind == "double-free"
    assert report.access is None
    assert [s.role for s in report.stacks] == ["access", "freed", "allocated"]
    assert report.heap_relevant is True
    bad_free = (
        "==6==ERROR: AddressSanitizer: attempting free on address which was not malloc()-ed: "
        "0x602000000090 in thread T0\n" + _frames(ASAN_RT, CCX_C) + "==6==ABORTING\n"
    )
    (report,) = parse_asan_reports(bad_free)
    assert report.kind == "bad-free"
    segv = (
        "==7==ERROR: AddressSanitizer: SEGV on unknown address 0x000000000000 (pc 0x1 bp 0x2 "
        "sp 0x3 T0)\n==7==The signal is caused by a WRITE memory access.\n"
        "==7==Hint: address points to the zero page.\n" + _frames(CCX_F) + "==7==ABORTING\n"
    )
    (report,) = parse_asan_reports(segv)
    assert (report.kind, report.access, report.address) == ("SEGV", "WRITE", "0x000000000000")
    # a wild-pointer WRITE is not a heap-family class: it cannot be the chunk-header write
    assert report.heap_relevant is False


def test_a_file_with_several_reports_keeps_them_in_order() -> None:
    text = REAL_BENIGN_REPORT + _heap_report(pid=2431025, access_frames=(ASAN_RT, ADAPTER_C))
    reports = parse_asan_reports(text)
    assert [r.known_benign for r in reports] == [True, False]
    assert reports[1].sites[0].path == "/src/calculix-adapter/nonlingeo_precice.c"


def test_a_truncated_report_still_parses_what_it_has() -> None:
    cut = REAL_BENIGN_REPORT.split("#5 ")[0]
    (report,) = parse_asan_reports(cut)
    assert report.kind == "global-buffer-overflow"
    assert len(report.stacks[0].frames) == 5
    assert report.known_benign is True  # the site frame (#4) survived the cut


# --- the R6 rule ------------------------------------------------------------------------


def _reports(*texts: str) -> tuple[AsanReport, ...]:
    return tuple(r for t in texts for r in parse_asan_reports(t))


def test_a_write_whose_access_site_is_ours_is_an_adapter_line() -> None:
    verdict, why = asan_hunt_verdict(
        _reports(
            _heap_report(access_frames=(ASAN_RT, ADAPTER_C), allocated_frames=(CCX_C, CCX_MAIN))
        ),
        completed=False,
        stopped_by="participant-died",
    )
    assert verdict == "adapter-line"
    assert "faulting access" in why and "nonlingeo_precice.c:1690" in why


def test_a_write_in_upstream_fortran_through_a_buffer_the_adapter_authored_is_ours() -> None:
    """The line we compile may be the allocation, not the store. R6 reads both."""
    verdict, why = asan_hunt_verdict(
        _reports(
            _heap_report(
                access_frames=(ASAN_RT, CCX_F), allocated_frames=(ASAN_RT, CCX_C, ADAPTER_IFACE)
            )
        ),
        completed=False,
        stopped_by="participant-died",
    )
    assert verdict == "adapter-line"
    assert "allocated in code the adapter authored" in why


def test_an_allocation_inside_the_adapters_copy_of_a_calculix_driver_is_a_human_call() -> None:
    """nonlingeo_precice.c is nonlingeo.c with the coupling spliced in; CalculiX NNEWs nearly
    every object of the dynamic step from those lines. An allocation there says the object
    was allocated where CalculiX allocates it -- not that we sized it."""
    verdict, why = asan_hunt_verdict(
        _reports(
            _heap_report(
                access_frames=(ASAN_RT, CCX_F), allocated_frames=(ASAN_RT, CCX_C, ADAPTER_C)
            )
        ),
        completed=False,
        stopped_by="participant-died",
    )
    assert verdict == "unclassified"
    assert "verbatim-derived copy" in why and "human call" in why


def test_a_write_whose_every_site_is_upstream_is_a_calculix_line() -> None:
    verdict, why = asan_hunt_verdict(
        _reports(
            _heap_report(
                access_frames=(ASAN_RT, CCX_F), allocated_frames=(ASAN_RT, CCX_C, CCX_MAIN)
            )
        ),
        completed=False,
        stopped_by="participant-died",
    )
    assert verdict == "calculix-line"
    assert "results.f:311" in why and "ccx_2.20.c:1041" in why


def test_the_benign_read_never_decides_and_is_counted_as_ignored() -> None:
    verdict, why = asan_hunt_verdict(
        _reports(REAL_BENIGN_REPORT), completed=False, stopped_by="participant-died"
    )
    assert verdict == "no-report-died"
    assert "1 known-benign" in why and "NOT exoneration" in why
    verdict, _ = asan_hunt_verdict(
        _reports(REAL_BENIGN_REPORT, _heap_report(access_frames=(ASAN_RT, ADAPTER_C))),
        completed=False,
        stopped_by="participant-died",
    )
    assert verdict == "adapter-line"


def test_silence_on_a_completed_run_is_recorded_as_silence_not_as_clean() -> None:
    verdict, why = asan_hunt_verdict((), completed=True, stopped_by="all-exited")
    assert verdict == "no-report-completed"
    assert "NOT exoneration" in why


def test_a_report_with_only_runtime_frames_goes_to_a_human() -> None:
    verdict, why = asan_hunt_verdict(
        _reports(_heap_report(access_frames=(ASAN_RT, LIBC))),
        completed=False,
        stopped_by="participant-died",
    )
    assert verdict == "unclassified"
    assert "no source-level frame" in why


def test_an_unrecognised_source_path_goes_to_a_human() -> None:
    verdict, why = asan_hunt_verdict(
        _reports(_heap_report(access_frames=(ASAN_RT, "ccx_2.20.c:1121"))),
        completed=False,
        stopped_by="participant-died",
    )
    assert verdict == "unclassified"
    assert "no pinned rule recognises" in why


def test_a_read_elsewhere_cannot_explain_the_corruption_and_is_not_the_verdict() -> None:
    """A non-benign READ is a finding, but not the write the hunt exists for."""
    verdict, why = asan_hunt_verdict(
        _reports(
            _heap_report(
                kind="global-buffer-overflow", access="READ", access_frames=(ASAN_RT, CCX_MAIN)
            )
        ),
        completed=True,
        stopped_by="all-exited",
    )
    assert verdict == "unclassified"
    assert "cannot be the write that poisoned" in why


# --- the driver mode: evidence lands beside the run ---------------------------------------


def _asan_case(
    tmp_path: Path,
    *,
    reports: dict[str, str],
    stopped_by: str,
    solid_rc: int,
    fluid_rc: int,
    windows: int,
    requested: int = 8000,
    asan: bool = True,
) -> Path:
    driver = _driver()
    case_host = tmp_path / "run"
    case_root = case_host / "tutorial"
    case_root.mkdir(parents=True)
    marker = (
        "---[precice] \x1b[0m it 1 (min: 1, max: 50), time-window {w}, "
        "t {t} (max: 0.16), Dt 2e-05, max-dt 2e-05\n"
    )
    lines = []
    for window in range(1, windows + 1):
        lines.append(marker.format(w=window, t=window * 2e-5))
        lines.append(" largest residual force= 0.000100 in node 2030 and dof 2\n")
    lines.append("corrupted double-linked list\n" if solid_rc == 134 else "")
    (case_root / "Solid.log").write_text("".join(lines), encoding="utf-8")
    (case_root / "Fluid.log").write_text("Time = 0.04\n", encoding="utf-8")
    for name, text in reports.items():
        (case_root / name).write_text(text, encoding="utf-8")
    status = {
        "run_id": "hg2007_flexible_foil-fake",
        "stopped_by": stopped_by,
        "started_epoch": 1789472114,
        "ended_epoch": 1789480114,
        "wall_clock_s": 8000,
        "participants": [
            {
                "name": "Fluid",
                "returncode": fluid_rc,
                "started_epoch": 1789472114,
                "ended_epoch": 1789480114,
                "log_path": str(case_root / "Fluid.log"),
            },
            {
                "name": "Solid",
                "returncode": solid_rc,
                "started_epoch": 1789472114,
                "ended_epoch": 1789480110,
                "log_path": str(case_root / "Solid.log"),
            },
        ],
    }
    (case_root / "coupled-status.json").write_text(json.dumps(status), encoding="utf-8")
    submission = {
        "schema": driver.SUBMISSION_SCHEMA,
        "adr": "ADR-040",
        "adr041_rung": None,
        "label": "probe",
        "note": None,
        "observability": {"asan": asan, "core_dumps": True, "malloc_check": False},
        "run_id": "hg2007_flexible_foil-fake",
        "session": "fsi-hg2007_flexible_foil-fake",
        "host": "aero-dev",
        "arm": "flexible",
        "rung": "mid",
        "spec_knobs": {
            "max_time": requested * 2e-5,
            "time_window_size": 2e-05,
            "hht_alpha": 0.0,
            "solid_sif": "calculix-precice-address.sif",
        },
        "case_host_path": str(case_host),
    }
    path = tmp_path / "asan-hunt-submission.json"
    path.write_text(json.dumps(submission), encoding="utf-8")
    return path


class _Status:
    def __init__(self, returncode: int, text: str) -> None:
        self.returncode = returncode
        self.stdout = text
        self.stderr = ""


def _evaluate(driver: Any, submission: Path) -> dict[str, Any]:
    rc = driver._asan_evaluate(driver.argparse.Namespace(asan_evaluate=submission))
    assert rc == 0
    out = submission.parent / "run" / "asan-hunt-verdict.json"
    return dict(json.loads(out.read_text(encoding="utf-8")))


def test_evaluating_a_dead_hunt_writes_the_reports_the_owners_and_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    submission = _asan_case(
        tmp_path,
        reports={
            "asan-solid.4242": _heap_report(
                pid=4242, access_frames=(ASAN_RT, CCX_F), allocated_frames=(ASAN_RT, ADAPTER_IFACE)
            )
        },
        stopped_by="participant-died",
        solid_rc=134,
        fluid_rc=143,
        windows=1900,
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(1, "session: failed"))

    record = _evaluate(driver, submission)

    assert record["verdict"] == "adapter-line"
    assert record["adr"] == "ADR-045" and record["clause"] == "R6"
    assert record["stopped_by"] == "participant-died"
    assert record["windows_reached"] == 1900 and record["windows_requested"] == 8000
    assert record["completed"] is False
    assert [p["returncode"] for p in record["participants"]] == [143, 134]
    assert "corrupted double-linked list" in record["solid_log_tail"]
    (report,) = record["reports"]
    assert report["known_benign"] is False and report["heap_relevant"] is True
    assert report["sites"][1].endswith("PreciceInterface.c:702 [adapter]")
    assert record["solid_error_lines"] == []
    assert record["windows_completed_by_coupling"] is None  # no iterations log in the fixture
    assert report["stacks"][1]["frames"][1]["owner"] == "adapter"
    # the rule that produced the reading rides with it
    assert record["classification"]["adapter_source_prefix"] == "/src/calculix-adapter/"
    assert record["classification"]["known_benign"]["site"] == "keystart.f:71"
    assert record["known_benign_ignored"] == 0
    # ADR-041's detector read the same run, so the record says whether the signature was there
    assert record["divergence"]["verdict"] in {"clean", "inconclusive", "precursor", "no-data"}
    assert record["observability"]["asan"] is True


def test_the_first_attempt_shape_reads_as_no_report_died_with_the_benign_read_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run that produced the fixture: 32 s, rc=134, only the keystart.f:71 READ."""
    driver = _driver()
    submission = _asan_case(
        tmp_path,
        reports={"asan-solid.2431025": REAL_BENIGN_REPORT},
        stopped_by="participant-died",
        solid_rc=134,
        fluid_rc=1,
        windows=0,
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(1, "session: failed"))

    record = _evaluate(driver, submission)

    assert record["verdict"] == "no-report-died"
    assert record["known_benign_ignored"] == 1
    assert record["reports"][0]["known_benign"] is True
    assert "NOT exoneration" in record["why"]


def test_a_completed_silent_hunt_is_no_report_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="all-exited", solid_rc=0, fluid_rc=0, windows=8000
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))

    record = _evaluate(driver, submission)

    assert record["verdict"] == "no-report-completed"
    assert record["completed"] is True
    assert record["report_files"] == []


def test_a_running_hunt_has_no_reading_yet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="all-exited", solid_rc=0, fluid_rc=0, windows=100
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(2, "session: running"))

    with pytest.raises(SystemExit, match="still running"):
        driver._asan_evaluate(driver.argparse.Namespace(asan_evaluate=submission))


def test_a_vanished_hunt_is_refused_rather_than_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="all-exited", solid_rc=0, fluid_rc=0, windows=100
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(4, "session: vanished"))

    with pytest.raises(SystemExit, match="No automatic reading"):
        driver._asan_evaluate(driver.argparse.Namespace(asan_evaluate=submission))


def test_a_run_without_asan_cannot_be_read_as_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    submission = _asan_case(
        tmp_path,
        reports={},
        stopped_by="all-exited",
        solid_rc=0,
        fluid_rc=0,
        windows=8000,
        asan=False,
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))

    with pytest.raises(SystemExit, match="did not run with --asan"):
        driver._asan_evaluate(driver.argparse.Namespace(asan_evaluate=submission))


def test_find_asan_reports_returns_only_report_files_sorted(tmp_path: Path) -> None:
    (tmp_path / "asan-solid.20").write_text("x", encoding="utf-8")
    (tmp_path / "asan-solid.3").write_text("x", encoding="utf-8")
    (tmp_path / "asan-solid.dir").mkdir()
    assert [p.name for p in find_asan_reports(tmp_path)] == ["asan-solid.20", "asan-solid.3"]


# --- review findings, pinned ---------------------------------------------------------------


def test_a_ceiling_stop_is_neither_a_death_nor_completion() -> None:
    verdict, why = asan_hunt_verdict((), completed=False, stopped_by="ceiling")
    assert verdict == "unclassified"
    assert "ceiling" in why and "not a death" in why.lower()
    verdict, why = asan_hunt_verdict((), completed=False, stopped_by="all-exited")
    assert verdict == "unclassified"
    assert "inconsistent" in why


def test_the_campaign_container_cannot_be_read_as_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--asan only exports ASAN_OPTIONS; the sanitizer lives in the -address SIF."""
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="all-exited", solid_rc=0, fluid_rc=0, windows=8000
    )
    data = json.loads(submission.read_text(encoding="utf-8"))
    data["spec_knobs"]["solid_sif"] = driver.SOLID_SIF_OF_RECORD
    submission.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))

    with pytest.raises(SystemExit, match="not built with a sanitizer"):
        driver._asan_evaluate(driver.argparse.Namespace(asan_evaluate=submission))


def test_a_missing_supervisor_record_is_refused_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="participant-died", solid_rc=134, fluid_rc=143, windows=10
    )
    (tmp_path / "run" / "tutorial" / "coupled-status.json").unlink()
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(1, "session: failed"))

    with pytest.raises(SystemExit, match="No automatic reading"):
        driver._asan_evaluate(driver.argparse.Namespace(asan_evaluate=submission))


def test_which_conjuncts_the_run_was_off_is_computed_not_asserted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first attempt ran alpha OF RECORD with only the container moved."""
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="all-exited", solid_rc=0, fluid_rc=0, windows=8000
    )
    data = json.loads(submission.read_text(encoding="utf-8"))
    data["spec_knobs"]["hht_alpha"] = driver.ALPHA_OF_RECORD
    submission.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))

    record = _evaluate(driver, submission)

    assert record["off_campaign_configuration"] == {"hht_alpha": False, "solid_sif": True}
    assert record["note"] == "diagnostic sanitizer hunt; sizes nothing"
    assert record["solid_sif"] == "calculix-precice-address.sif"
    # the rule that produced the reading rides with it, whole
    rules = record["classification"]
    assert "u_calloc.c" in rules["calculix_allocator_wrappers_are_runtime"]
    assert "heap-buffer-overflow" in rules["heap_relevant"]["kinds"]
    assert rules["heap_relevant"]["or_access"] == "WRITE"
    assert len(record["evaluator_git_sha"]) in {40, len("unknown")}


def test_a_second_reading_keeps_the_first_readings_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="all-exited", solid_rc=0, fluid_rc=0, windows=8000
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(0, "session: done"))
    first = _evaluate(driver, submission)
    second = _evaluate(driver, submission)
    assert second["first_evaluated_at"] == first["evaluated_at"]
    assert "prior reading" in capsys.readouterr().out


# --- second review round, pinned ----------------------------------------------------------


def test_a_named_thread_on_a_freed_line_still_starts_its_own_stack() -> None:
    text = (
        "==14==ERROR: AddressSanitizer: heap-use-after-free on address 0x61400000fe44 at pc 0x1 "
        "bp 0x2 sp 0x3\nWRITE of size 4 at 0x61400000fe44 thread T0\n"
        + _frames(ASAN_RT, CCX_F)
        + "0x61400000fe44 is located 4 bytes inside of 80-byte region\n"
        "freed by thread T1 (spooles) here:\n"
        + _frames(ASAN_RT, ADAPTER_IFACE)
        + "\npreviously allocated by thread T0 here:\n"
        + _frames(ASAN_RT, CCX_C, CCX_MAIN)
        + "\nThread T1 (spooles) created by T0 here:\n"
        + _frames(ASAN_RT, ADAPTER_C)
        + "\nSUMMARY: AddressSanitizer: heap-use-after-free x\n==14==ABORTING\n"
    )
    (report,) = parse_asan_reports(text)
    assert [s.role for s in report.stacks] == ["access", "freed", "allocated", "other"]
    assert [s.basename for s in report.sites] == [
        "results.f",
        "PreciceInterface.c",
        "ccx_2.20.c",
    ]
    verdict, why = asan_hunt_verdict((report,), completed=False, stopped_by="participant-died")
    assert verdict == "adapter-line" and "freed in code the adapter authored" in why


def test_the_summary_line_supplies_the_canonical_bug_class() -> None:
    text = (
        "==9==ERROR: AddressSanitizer: calloc parameters overflow: count * size "
        "(1000000000 * 100000000000) cannot be represented in type size_t (thread T0)\n"
        + _frames(ASAN_RT, CCX_C, ADAPTER_IFACE)
        + "SUMMARY: AddressSanitizer: calloc-overflow x in calloc\n==9==ABORTING\n"
    )
    (report,) = parse_asan_reports(text)
    assert report.kind == "calloc-overflow" and report.heap_relevant is True
    verdict, _ = asan_hunt_verdict((report,), completed=False, stopped_by="participant-died")
    assert verdict == "adapter-line"
    # cut before its SUMMARY, the header wording still maps to the class
    (cut,) = parse_asan_reports(text.split("SUMMARY")[0])
    assert cut.kind == "calloc-overflow"
    (overlap,) = parse_asan_reports(
        "==21==ERROR: AddressSanitizer: memmove-param-overlap: memory ranges [0x10,0x20) and "
        "[0x18, 0x28) overlap\n" + _frames(ASAN_RT, ADAPTER_IFACE) + "==21==ABORTING\n"
    )
    assert overlap.kind == "memmove-param-overlap" and overlap.heap_relevant is False


def test_an_allocation_failure_header_without_a_colon_still_parses() -> None:
    (report,) = parse_asan_reports(
        "==12==ERROR: AddressSanitizer failed to allocate 0x400000000 (17179869184) bytes of "
        "SizeClassAllocator64: Operation not permitted\n"
        + _frames(ASAN_RT, CCX_C, ADAPTER_C)
        + "==12==ABORTING\n"
    )
    assert report.kind == "mmap-failure" and report.heap_relevant is False


def test_unknown_module_frames_keep_their_function_text() -> None:
    (report,) = parse_asan_reports(
        "==3==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x1 at pc 0x2 bp 0x3 sp 0x4\n"
        "WRITE of size 8 at 0x1 thread T0\n"
        "    #0 0x7f12 in ?? (<unknown module>)\n"
        "    #1 0x7f13 in Foo::bar(int) const (<unknown module>)\n"
        "    #2 0x5a01 in main (/opt/calculix/bin/ccx_preCICE+0x2a3f10)\n"
        "==3==ABORTING\n"
    )
    frames = report.stacks[0].frames
    assert (frames[0].function, frames[0].location) == ("??", "(<unknown module>)")
    assert (frames[1].function, frames[1].location) == ("Foo::bar(int) const", "(<unknown module>)")
    # our own binary, unsymbolized: unknown, never runtime -- so the reading goes to a human
    assert frames[2].owner == "unknown"
    verdict, why = asan_hunt_verdict((report,), completed=False, stopped_by="participant-died")
    assert verdict == "unclassified" and "unsymbolized" in why


def test_the_address_is_read_from_free_family_headers_too() -> None:
    (report,) = parse_asan_reports(
        "==5==ERROR: AddressSanitizer: attempting double-free on 0x602000000090 in thread T0:\n"
        + _frames(ASAN_RT, ADAPTER_IFACE)
        + "==5==ABORTING\n"
    )
    assert report.address == "0x602000000090"


def test_ambiguous_basenames_and_climbing_paths_stay_unknown() -> None:
    assert classify_frame_path("CalculiX.h") == "unknown"
    assert (
        classify_frame_path("/src/calculix-adapter/../CalculiX/ccx_2.20/src/results.c") == "unknown"
    )


def test_report_files_are_ordered_by_time_not_by_name(tmp_path: Path) -> None:
    import os

    older = tmp_path / "asan-solid.999"
    newer = tmp_path / "asan-solid.10000"
    older.write_text("x", encoding="utf-8")
    newer.write_text("y", encoding="utf-8")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))
    assert [p.name for p in find_asan_reports(tmp_path)] == ["asan-solid.999", "asan-solid.10000"]


def test_more_than_one_report_file_is_a_human_call() -> None:
    verdict, why = asan_hunt_verdict(
        _reports(_heap_report(access_frames=(ASAN_RT, ADAPTER_IFACE))),
        completed=False,
        stopped_by="participant-died",
        n_report_files=2,
    )
    assert verdict == "unclassified" and "2 report files" in why


def test_the_solvers_own_error_line_is_quoted_in_a_no_report_death(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hunt died rc=201 with `*ERROR: solution seems to diverge` -- name it, do not
    send the reader to the tail."""
    driver = _driver()
    submission = _asan_case(
        tmp_path, reports={}, stopped_by="participant-died", solid_rc=201, fluid_rc=1, windows=2369
    )
    solid_log = tmp_path / "run" / "tutorial" / "Solid.log"
    solid_log.write_text(
        solid_log.read_text(encoding="utf-8")
        + " *ERROR: solution seems to diverge; please try \n automatic incrementation; program stops\n",
        encoding="utf-8",
    )
    (tmp_path / "run" / "tutorial" / "run-coupled.sh").write_text(
        "export ASAN_OPTIONS=detect_leaks=0:halt_on_error=0:intercept_memcmp=0:log_path=/case/asan-solid && ccx\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(driver, "_run_long", lambda *a, **k: _Status(1, "session: failed"))

    record = _evaluate(driver, submission)

    assert record["verdict"] == "no-report-died"
    assert record["solid_error_lines"] == ["*ERROR: solution seems to diverge; please try"]
    assert "solution seems to diverge" in record["why"]
    assert record["asan_options"].startswith("detect_leaks=0:halt_on_error=0:intercept_memcmp=0")
    assert record["participants"][1] == {"name": "Solid", "returncode": 201, "state": "exited-fail"}


def test_known_benign_is_pinned_by_kind_access_and_line_and_drift_fails_safe() -> None:
    """Line drift, a WRITE, or a heap class at the same site is NOT the benign report."""
    drift = REAL_BENIGN_REPORT.replace("keystart.f:71", "keystart.f:72")
    (report,) = parse_asan_reports(drift)
    assert report.known_benign is False
    verdict, _ = asan_hunt_verdict((report,), completed=True, stopped_by="all-exited")
    assert verdict == "unclassified"  # a non-heap READ elsewhere: a human reads it
    write = REAL_BENIGN_REPORT.replace("READ of size", "WRITE of size")
    (report,) = parse_asan_reports(write)
    assert report.known_benign is False and report.heap_relevant is False
    heap = REAL_BENIGN_REPORT.replace("global-buffer-overflow", "heap-buffer-overflow")
    (report,) = parse_asan_reports(heap)
    assert report.known_benign is False and report.heap_relevant is True
    verdict, _ = asan_hunt_verdict((report,), completed=False, stopped_by="participant-died")
    assert verdict == "calculix-line"


def test_the_first_heap_family_report_decides_and_a_heap_family_read_is_decisive() -> None:
    first_upstream = _heap_report(
        pid=1, access_frames=(ASAN_RT, CCX_F), allocated_frames=(CCX_C, CCX_MAIN)
    )
    then_adapter = _heap_report(pid=1, access_frames=(ASAN_RT, ADAPTER_IFACE))
    verdict, _ = asan_hunt_verdict(
        _reports(first_upstream + then_adapter), completed=False, stopped_by="participant-died"
    )
    assert verdict == "calculix-line"
    uaf_read = _heap_report(
        kind="heap-use-after-free",
        access="READ",
        access_frames=(ASAN_RT, CCX_F),
        freed_frames=(ASAN_RT, CCX_C, ADAPTER_IFACE),
        allocated_frames=(ASAN_RT, CCX_C, CCX_MAIN),
    )
    (report,) = parse_asan_reports(uaf_read)
    assert report.heap_relevant is True  # a use-after-free READ is a heap bug of record
    verdict, why = asan_hunt_verdict((report,), completed=False, stopped_by="participant-died")
    assert verdict == "adapter-line" and "freed in code the adapter authored" in why
