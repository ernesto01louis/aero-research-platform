# Runbook — aero-progress (live run progress + ETA + ntfy)

`scripts/aero_progress.py` derives percent-complete and ETA for long OpenFOAM runs by
reading the NFS case dirs (`/mnt/aero-nfs/runs/`) directly on the Proxmox host — no SSH,
no MLflow/Prefect dependency, stdlib-only (`/usr/bin/python3`). It replaces "ask Claude
how far along the run is" with a terminal pane and phone pushes.

## Watch it while working (VS Code)

Open a terminal split (`` Ctrl+` `` → split) and run:

```bash
watch -n 30 /usr/bin/python3 /root/projects/aero-research-platform/scripts/aero_progress.py
```

Columns: state (`running`/`STALE`/`setup`/`done`/`FAILED`), `█░` bar + percent,
`sim-time/endTime`, sim-rate per wall-hour, ETA (duration + local wall-clock finish), and
age of the last output. ETAs for `simpleFoam` runs are prefixed `≤` (steady runs may
converge before `endTime` — the percent is an upper bound, by design).

One-off / filtered / machine-readable:

```bash
python3 scripts/aero_progress.py --once                      # table once
python3 scripts/aero_progress.py --once --run flap_delayed   # exit 0 done / 1 failed / 2 running
python3 scripts/aero_progress.py --once --json               # full status JSON
python3 scripts/aero_progress.py --all                       # ignore the 3-day mtime filter
```

## Daemon (windowed ETAs + ntfy pushes)

The daemon samples each run's sim-time every 30 s; `--once` then uses those samples for a
windowed rate (better than the stateless log-tail fallback for adaptive-deltaT flapping
runs), and it pushes ntfy on **done / failed** (deduped across restarts).

Install on the Proxmox host (operator step — host change):

```bash
cp scripts/systemd/aero-progress.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now aero-progress
systemctl status aero-progress
```

Subscribe to pushes: ntfy app / browser → server `http://192.168.2.203:8090`, topic
**`aero-runs`** (gotify on `:80` is untouched). Test:
`curl -d ping http://192.168.2.203:8090/aero-runs`.

State (samples + notification dedupe) lives in `/var/lib/aero-progress/state.json`
(`StateDirectory=`). `--once` never writes state, so ad-hoc calls can't corrupt it.
Optional flags: `--notify-stale` (alert when a running solve stops producing output —
the "driver timeout but tmux still alive" zombie), `--notify-milestones` is deliberately
NOT implemented (user chose done/failed only).

## For Claude sessions (waiters)

Instead of re-deriving progress or tailing logs into context:

```bash
python3 scripts/aero_progress.py --once --json --run <run_id>
```

gives `{state, percent, eta_s, eta_iso, rate_basis, sim_source, ...}` and exits
0 done / 1 failed-or-missing / 2 still-running — the same contract as
`run_long.sh wait`, but with progress. The JSON shape is pinned by
`tests/unit/test_aero_progress.py::test_status_json_shape_pin`.

## How it reads a run (and the limits)

| Signal | Used for |
|---|---|
| `log.solve` tail (last 64 KB) | sim time, wall-clock rate, `End` marker |
| `system/controlDict` (top-level only) | `startTime`/`endTime`; the GCI overset cases have a decoy `component/system/controlDict` that is ignored |
| `postProcessing/*/…/{force,coefficient}.dat` last row | sim time for executor-path runs (they have **no** log/sentinels on NFS) |
| max numeric time-dir | sim-time floor (`purgeWrite` deletes old dirs — counts are meaningless) |
| `.assembled` / `.done` / `.failed` | phase + terminal state |

Known limits (v1, accepted): executor-path steady runs that converge early and stop look
`STALE` (no sentinel reaches NFS to distinguish "converged" from "died") — check
`~/.aero-jobs/<session>/` on `aero-dev` for those; flapping ETAs wobble with the stroke
cycle (45-min rate window smooths this; tune `--window`); the controlDict parser does not
follow `#include`.
