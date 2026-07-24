#!/usr/bin/env python3
"""Live progress + ETA for long OpenFOAM runs, read straight off the NFS run dirs.

Long solves (Stage-14 flapping WBD overset is >1 day) only expose ``.done``/``.failed``
sentinels to the ``scripts/run_long.sh`` waiter — no percent, no ETA. This tool derives both
from what a run already writes to ``/mnt/aero-nfs/runs/<run>/``:

* ``log.solve`` tail        -> ``Time = ...`` + ``ExecutionTime/ClockTime`` pairs (live rate)
* ``system/controlDict``    -> ``startTime``/``endTime`` (top-level only: GCI overset cases
                               contain a decoy ``component/system/controlDict``)
* ``postProcessing/*/.../{force,coefficient}.dat`` -> first column is sim time (executor-path
                               runs have NO log.solve or sentinels on NFS, only these)
* numeric time directories  -> max name is a sim-time floor (``purgeWrite`` deletes old ones,
                               so the *count* is meaningless)

Stdlib-only on purpose: the systemd daemon runs on the Proxmox host's ``/usr/bin/python3``
and must survive repo-venv rebuilds. Format knowledge is re-specified here (not imported)
— see ``aero/adapters/openfoam/solver.py`` (regexes ~73, force readers ~617-689) and
``aero/adapters/_base.py`` (~45: DEFAULT_HOST_NFS_ROOT, RUNS_SUBDIR) for the source of truth.

Modes:
    --once (default)   render a table (watch-friendly, no ANSI) or --json; state is read-only
    --daemon           poll every --interval, persist rate samples, push ntfy on done/failed

Waiter integration: with ``--run NAME [NAME...]`` the exit code mirrors run_long.sh cmd_wait
(0 all done, 1 any failed, 2 still running/stale) so one ``--once --json --run X`` call gives
a Claude waiter progress *and* a poll predicate.

    watch -n 30 python3 scripts/aero_progress.py
    python3 scripts/aero_progress.py --once --json --run flap_base_symmetric
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

RUNS_ROOT_DEFAULT = Path("/mnt/aero-nfs/runs")  # DEFAULT_HOST_NFS_ROOT / RUNS_SUBDIR
LOG_TAIL_BYTES = 65536
DAT_TAIL_BYTES = 4096

# "Time = 159.84089348" (some OpenFOAM builds append a bare 's'); anchored so it can never
# match "ExecutionTime = ..." on the same tail.
_TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*s?\s*$", re.M)
# "ExecutionTime = 69217.71 s  ClockTime = 69416 s"
_EXEC_RE = re.compile(r"^ExecutionTime = ([0-9.eE+-]+) s\s+ClockTime = ([0-9.eE+-]+) s", re.M)
_END_MARKERS = ("\nEnd\n", "SIMPLE solution converged", "PIMPLE: converged")
# controlDict "key   value;" — first match wins (top-level entries precede functions{}).
_CTRL_KEYS = ("application", "startTime", "endTime", "deltaT", "adjustTimeStep", "stopAt")

STATE_ORDER = {"running": 0, "stale": 1, "setup": 2, "done": 3, "failed": 4, "unknown": 5}


# --------------------------------------------------------------------------- cheap readers


def tail_text(path: Path, n: int = LOG_TAIL_BYTES) -> str | None:
    """Read at most the last *n* bytes of *path* (never the whole 100+ MB log)."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - n))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def last_data_line(path: Path) -> float | None:
    """First column of the last non-comment row of a force/coefficient .dat file.

    Handles the flat 10-column ESI layout and the parenthesised vector layout;
    ``adjustableRunTime`` duplicate timestamps are harmless (we only read the last row).
    """
    text = tail_text(path, DAT_TAIL_BYTES)
    if not text:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split("(", 1)[0].split()
        if not token:
            continue
        try:
            return float(token[0])
        except ValueError:
            continue
    return None


_ctrl_cache: dict[Path, tuple[float, dict[str, str]]] = {}


def parse_controldict(path: Path) -> dict[str, str]:
    """Top-level ``key value;`` scalars from a controlDict, mtime-cached.

    Deliberately naive (no ``#include``/macros) — fine for platform-generated dicts;
    anything unparseable surfaces as state "unknown", never silently.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    cached = _ctrl_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for key in _CTRL_KEYS:
        m = re.search(rf"^\s*{key}\s+([^;]+);", text, re.M)
        if m:
            out[key] = m.group(1).strip().strip('"')
    _ctrl_cache[path] = (mtime, out)
    return out


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- probe


@dataclass
class RunProbe:
    """Everything observable about one run dir in a single cheap pass."""

    run_id: str
    case_dir: Path
    application: str | None = None
    start_time: float = 0.0
    end_time: float | None = None
    sim_time: float | None = None
    sim_source: str | None = None
    exec_pairs: list[tuple[float, float]] = field(default_factory=list)  # (sim_t, clock_s)
    clock_time_s: float | None = None
    log_end_seen: bool = False
    assembled: bool = False
    done: bool = False
    failed: bool = False
    last_activity: float | None = None  # unix mtime
    probe_error: str | None = None


def _newest_dat(case_dir: Path) -> Path | None:
    """Newest force/coefficient .dat under postProcessing (restarts write under non-0 dirs)."""
    best: tuple[float, Path] | None = None
    pp = case_dir / "postProcessing"
    try:
        for fo_dir in pp.iterdir():
            if not fo_dir.is_dir():
                continue
            for start_dir in fo_dir.iterdir():
                for name in ("force.dat", "coefficient.dat", "forceCoeffs.dat", "moment.dat"):
                    dat = start_dir / name
                    try:
                        mt = dat.stat().st_mtime
                    except OSError:
                        continue
                    if best is None or mt > best[0]:
                        best = (mt, dat)
    except OSError:
        return None
    return best[1] if best else None


def _max_time_dir(case_dir: Path) -> float | None:
    best: float | None = None
    try:
        for entry in case_dir.iterdir():
            if not entry.is_dir():
                continue
            try:
                val = float(entry.name)
            except ValueError:
                continue
            if best is None or val > best:
                best = val
    except OSError:
        return None
    return best


def probe_run(case_dir: Path) -> RunProbe:
    probe = RunProbe(run_id=case_dir.name, case_dir=case_dir)
    try:
        probe.done = (case_dir / ".done").exists()
        probe.failed = (case_dir / ".failed").exists()
        probe.assembled = (case_dir / ".assembled").exists()

        ctrl = parse_controldict(case_dir / "system" / "controlDict")  # top-level ONLY
        probe.application = ctrl.get("application")
        probe.start_time = _to_float(ctrl.get("startTime")) or 0.0
        probe.end_time = _to_float(ctrl.get("endTime"))

        candidates: list[tuple[float, str]] = []
        mtimes: list[float] = []

        log = case_dir / "log.solve"
        tail = tail_text(log)
        if tail is not None:
            with contextlib.suppress(OSError):
                mtimes.append(log.stat().st_mtime)
            times = [_to_float(m) for m in _TIME_RE.findall(tail)]
            times = [t for t in times if t is not None]
            if times:
                candidates.append((times[-1], "log.solve"))
            cur_t: float | None = None
            pos_time = [(m.start(), float(m.group(1))) for m in _TIME_RE.finditer(tail)]
            ti = 0
            for m in _EXEC_RE.finditer(tail):
                while ti < len(pos_time) and pos_time[ti][0] < m.start():
                    cur_t = pos_time[ti][1]
                    ti += 1
                clock = _to_float(m.group(2))
                if cur_t is not None and clock is not None:
                    probe.exec_pairs.append((cur_t, clock))
            if probe.exec_pairs:
                probe.clock_time_s = probe.exec_pairs[-1][1]
            probe.log_end_seen = any(mark in tail for mark in _END_MARKERS)

        dat = _newest_dat(case_dir)
        if dat is not None:
            val = last_data_line(dat)
            if val is not None:
                candidates.append((val, f"postProcessing/{dat.parent.parent.name}"))
            with contextlib.suppress(OSError):
                mtimes.append(dat.stat().st_mtime)

        tdir = _max_time_dir(case_dir)
        if tdir is not None and tdir > probe.start_time:
            candidates.append((tdir, "time-dirs"))

        if candidates:
            probe.sim_time, probe.sim_source = max(candidates, key=lambda c: c[0])
        if mtimes:
            probe.last_activity = max(mtimes)
        else:
            with contextlib.suppress(OSError):
                probe.last_activity = case_dir.stat().st_mtime
    except OSError as exc:  # NFS hiccup — degrade to a visible error, never crash the poller
        probe.probe_error = str(exc)
    return probe


# --------------------------------------------------------------------------- discovery


def discover_runs(
    root: Path,
    max_age_days: float = 3.0,
    include_all: bool = False,
    names: list[str] | None = None,
    now: float | None = None,
) -> list[Path]:
    """Run dirs worth probing (~2000 dirs exist; mtime-filter to the active tail)."""
    out: list[Path] = []
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if names is not None:
            if entry.name in names:
                out.append(entry)
            continue
        if not entry.is_dir() or not (entry / "system" / "controlDict").is_file():
            continue
        if include_all:
            out.append(entry)
            continue
        try:
            fresh = entry.stat().st_mtime >= cutoff
        except OSError:
            continue
        armed_no_verdict = (entry / ".assembled").exists() and not (
            (entry / ".done").exists() or (entry / ".failed").exists()
        )
        if fresh or armed_no_verdict:
            out.append(entry)
    return out


# --------------------------------------------------------------------------- classify + ETA


def classify(probe: RunProbe, now: float, stale_after: float = 900.0) -> str:
    if probe.probe_error:
        return "unknown"
    if probe.failed:
        return "failed"
    if probe.done or probe.log_end_seen:
        return "done"
    if (
        probe.end_time is not None
        and probe.sim_time is not None
        and probe.sim_time >= probe.end_time * 0.999
    ):
        return "done"  # presumed: reached endTime but sentinel/log marker not (yet) visible
    age = None if probe.last_activity is None else now - probe.last_activity
    if probe.sim_time is None:
        # controlDict exists but no solve output yet: meshing/setup — stale if it stopped moving
        if age is not None and age < stale_after:
            return "setup"
        return "stale" if probe.assembled else "setup"
    if age is not None and age < stale_after:
        return "running"
    return "stale"


def tail_rate(probe: RunProbe) -> float | None:
    """Stateless sim-per-wall-second rate from Time/ClockTime pairs inside one log tail.

    Survives poller restarts; a mid-tail ExecutionTime reset (solver restart) is discarded
    by requiring both time and clock to be increasing across the span.
    """
    pairs = probe.exec_pairs
    if len(pairs) < 2:
        return None
    (t0, c0), (t1, c1) = pairs[0], pairs[-1]
    if c1 <= c0 or t1 <= t0:
        return None
    return (t1 - t0) / (c1 - c0)


def windowed_rate(samples: list[list[float]], now: float, window_s: float) -> float | None:
    """Rate from the daemon's own (wall, sim) samples within the trailing window."""
    recent = [s for s in samples if now - s[0] <= window_s]
    if len(recent) < 2:
        return None
    (w0, t0), (w1, t1) = recent[0], recent[-1]
    if w1 - w0 < 120 or t1 <= t0:
        return None
    return (t1 - t0) / (w1 - w0)


# --------------------------------------------------------------------------- state store


class StateStore:
    """Atomic JSON persistence for rate samples + notification dedupe."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {"runs": {}}

    def load(self) -> None:
        try:
            self.data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {"runs": {}}
        self.data.setdefault("runs", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data))
        os.replace(tmp, self.path)

    def run_entry(self, run_id: str) -> dict:
        return self.data["runs"].setdefault(run_id, {"samples": [], "notified": {}})

    def add_sample(self, run_id: str, wall: float, sim_time: float, window_s: float) -> None:
        entry = self.run_entry(run_id)
        samples: list[list[float]] = entry["samples"]
        if samples and sim_time < samples[-1][1]:
            samples.clear()  # solver restarted from an earlier time — history is invalid
        if not samples or sim_time > samples[-1][1]:
            samples.append([wall, sim_time])
        entry["samples"] = [s for s in samples if wall - s[0] <= 2 * window_s][-240:]

    def prune(self, live_ids: set[str]) -> None:
        self.data["runs"] = {k: v for k, v in self.data["runs"].items() if k in live_ids}


def default_state_path() -> Path:
    sd = os.environ.get("STATE_DIRECTORY")  # set by systemd StateDirectory=
    if sd:
        return Path(sd.split(":")[0]) / "state.json"
    return Path.home() / ".local" / "state" / "aero-progress" / "state.json"


# --------------------------------------------------------------------------- status snapshot


def human_duration(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 172800:
        h = seconds / 3600
        return f"{h:.1f}h"
    return f"{seconds / 86400:.1f}d"


def build_status(
    probes: list[RunProbe],
    store: StateStore,
    now: float,
    window_s: float,
    stale_after: float,
) -> dict:
    runs = []
    for p in probes:
        state = classify(p, now, stale_after)
        percent = None
        if p.sim_time is not None and p.end_time is not None and p.end_time > p.start_time:
            percent = max(0.0, min(1.0, (p.sim_time - p.start_time) / (p.end_time - p.start_time)))
        if state == "done":
            percent = 1.0 if p.end_time is not None else percent

        rate = rate_basis = None
        samples = store.data["runs"].get(p.run_id, {}).get("samples", [])
        w = windowed_rate(samples, now, window_s)
        if w is not None:
            rate, rate_basis = w, "windowed"
        else:
            t = tail_rate(p)
            if t is not None:
                rate, rate_basis = t, "log-tail"

        eta_s = eta_iso = None
        if (
            state == "running"
            and rate
            and rate > 0
            and p.sim_time is not None
            and p.end_time is not None
        ):
            eta_s = (p.end_time - p.sim_time) / rate
            eta_iso = (datetime.now(UTC) + timedelta(seconds=eta_s)).isoformat(timespec="seconds")

        runs.append(
            {
                "run_id": p.run_id,
                "application": p.application,
                "state": state,
                "percent": None if percent is None else round(percent * 100, 1),
                "sim_time": p.sim_time,
                "start_time": p.start_time,
                "end_time": p.end_time,
                "sim_source": p.sim_source,
                "rate_sim_per_hour": None if rate is None else round(rate * 3600, 6),
                "rate_basis": rate_basis,
                "eta_s": None if eta_s is None else round(eta_s),
                "eta_iso": eta_iso,
                "eta_human": human_duration(eta_s),
                "eta_upper_bound": p.application == "simpleFoam",  # steady may converge early
                "clock_time_s": p.clock_time_s,
                "last_update_iso": None
                if p.last_activity is None
                else datetime.fromtimestamp(p.last_activity, UTC).isoformat(timespec="seconds"),
                "age_s": None if p.last_activity is None else round(now - p.last_activity),
                "error": p.probe_error,
            }
        )
    runs.sort(key=lambda r: (STATE_ORDER.get(r["state"], 9), r["run_id"]))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "runs_root": None,
        "runs": runs,
    }


BAR_WIDTH = 20


def render_table(status: dict) -> str:
    lines = [
        f"aero runs — {status['generated_at']}  "
        f"({sum(1 for r in status['runs'] if r['state'] == 'running')} running)",
        "",
        f"{'RUN':<28} {'STATE':<8} {'PROGRESS':<{BAR_WIDTH + 8}} {'SIM t/END':<20} "
        f"{'RATE/h':<9} {'ETA':<14} AGE",
    ]
    for r in status["runs"]:
        pct = r["percent"]
        if pct is None:
            bar = "·" * BAR_WIDTH
            pct_s = "   ?"
        else:
            filled = round(pct / 100 * BAR_WIDTH)
            bar = "█" * filled + "░" * (BAR_WIDTH - filled)
            pct_s = f"{pct:5.1f}%"
        sim = "—"
        if r["sim_time"] is not None:
            end = f"{r['end_time']:g}" if r["end_time"] is not None else "?"
            sim = f"{r['sim_time']:.4g}/{end}"
        rate = "—" if r["rate_sim_per_hour"] is None else f"{r['rate_sim_per_hour']:.3g}"
        eta = r["eta_human"]
        if r["eta_iso"]:
            local = datetime.fromisoformat(r["eta_iso"]).astimezone()
            eta = f"{r['eta_human']} ({local:%a %H:%M})"
        if r.get("eta_upper_bound") and r["eta_s"] is not None:
            eta = f"≤{eta}"
        state = r["state"].upper() if r["state"] in ("failed", "stale") else r["state"]
        age = human_duration(r["age_s"])
        lines.append(
            f"{r['run_id']:<28.28} {state:<8} {bar} {pct_s} {sim:<20} {rate:<9} {eta:<14} {age}"
        )
    if not status["runs"]:
        lines.append("(no active runs found)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- notifier


def notify(url: str, title: str, message: str, priority: str = "default", tags: str = "") -> bool:
    """POST to an ntfy topic URL; failure is logged, never fatal.

    HTTP headers are latin-1 — no emoji in Title. Use the ntfy ``Tags`` header instead
    (e.g. ``white_check_mark``); clients render tags as emoji.
    """
    headers = {
        "Title": title.encode("latin-1", errors="replace").decode("latin-1"),
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = tags
    req = urllib.request.Request(url, data=message.encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except (urllib.error.URLError, OSError) as exc:
        print(f"[aero-progress] notify failed: {exc}", file=sys.stderr)
        return False


def process_notifications(
    status: dict,
    store: StateStore,
    notify_url: str | None,
    notify_stale: bool,
    post=notify,
    record_only: bool = False,
) -> None:
    """Push on state transitions. ``record_only`` marks current terminal states as already
    notified WITHOUT posting — the fresh-state baseline pass, so a brand-new daemon doesn't
    flood the topic with catch-up pushes for runs that finished before it existed."""
    if not notify_url:
        return
    for r in status["runs"]:
        entry = store.run_entry(r["run_id"])
        notified: dict = entry["notified"]
        state = r["state"]
        if record_only:
            if state in ("done", "failed"):
                notified[state] = True
            entry["last_state"] = state
            continue
        if state in ("done", "failed") and not notified.get(state):
            elapsed = human_duration(r["clock_time_s"])
            if state == "done":
                ok = post(
                    notify_url,
                    f"{r['run_id']} done",
                    f"solve finished ({elapsed})",
                    tags="white_check_mark",
                )
            else:
                ok = post(
                    notify_url,
                    f"{r['run_id']} FAILED",
                    f"check log.solve (elapsed {elapsed})",
                    priority="high",
                    tags="rotating_light",
                )
            if ok:
                notified[state] = True
        elif notify_stale and state == "stale" and entry.get("last_state") == "running":
            if post(
                notify_url,
                f"{r['run_id']} stalled",
                f"no new output for {human_duration(r['age_s'])} at {r['percent']}%",
                priority="high",
                tags="warning",
            ):
                notified["stale"] = True
        if state == "running":
            notified.pop("stale", None)  # re-arm the stale alert after recovery
        entry["last_state"] = state


# --------------------------------------------------------------------------- modes


def scan(args, store: StateStore, now: float) -> dict:
    dirs = discover_runs(
        Path(args.runs_root),
        max_age_days=args.max_age_days,
        include_all=args.all,
        names=args.run or None,
    )
    probes = [probe_run(d) for d in dirs]
    status = build_status(probes, store, now, args.window, args.stale_after)
    status["runs_root"] = str(args.runs_root)
    return status


def run_once(args) -> int:
    store = StateStore(Path(args.state_file))
    store.load()  # read-only: --once never writes, so it can't corrupt the daemon's state
    status = scan(args, store, time.time())
    print(json.dumps(status, indent=2) if args.json else render_table(status))
    if args.run:
        states = {r["state"] for r in status["runs"]}
        missing = set(args.run) - {r["run_id"] for r in status["runs"]}
        if "failed" in states or missing:
            return 1
        if states <= {"done"}:
            return 0
        return 2
    return 0


def run_daemon(args) -> int:
    store = StateStore(Path(args.state_file))
    fresh_state = not store.path.exists()
    store.load()
    stop = False

    def _term(_sig, _frm):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    print(
        f"[aero-progress] daemon: root={args.runs_root} interval={args.interval}s "
        f"notify={'on' if args.notify_url else 'off'} state={args.state_file}"
    )
    while not stop:
        now = time.time()
        status = scan(args, store, now)
        for r in status["runs"]:
            if r["sim_time"] is not None:
                store.add_sample(r["run_id"], now, r["sim_time"], args.window)
        process_notifications(
            status, store, args.notify_url, args.notify_stale, record_only=fresh_state
        )
        fresh_state = False  # only the very first cycle of a brand-new state file baselines
        store.prune({r["run_id"] for r in status["runs"]})
        try:
            store.save()
        except OSError as exc:
            print(f"[aero-progress] state save failed: {exc}", file=sys.stderr)
        deadline = time.time() + args.interval
        while not stop and time.time() < deadline:
            time.sleep(1)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="single scan (default)")
    mode.add_argument("--daemon", action="store_true", help="poll loop + samples + ntfy")
    ap.add_argument("--json", action="store_true", help="machine-readable output (--once)")
    ap.add_argument("--runs-root", default=str(RUNS_ROOT_DEFAULT))
    ap.add_argument("--run", nargs="*", help="only these run names; sets waiter exit codes")
    ap.add_argument("--all", action="store_true", help="ignore the mtime filter")
    ap.add_argument("--max-age-days", type=float, default=3.0)
    ap.add_argument("--interval", type=float, default=30.0, help="daemon poll seconds")
    ap.add_argument("--window", type=float, default=2700.0, help="rate window seconds")
    ap.add_argument("--stale-after", type=float, default=900.0)
    ap.add_argument("--state-file", default=str(default_state_path()))
    ap.add_argument("--notify-url", help="ntfy topic URL, e.g. http://192.168.2.203:8090/aero-runs")
    ap.add_argument("--notify-stale", action="store_true", help="also alert running->stale")
    args = ap.parse_args()
    return run_daemon(args) if args.daemon else run_once(args)


if __name__ == "__main__":
    sys.exit(main())
