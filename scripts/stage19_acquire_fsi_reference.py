"""Stage-19 acquisition: identify and recompute the Turek-Hron FSI3 displacement reference.

WHY THIS SCRIPT EXISTS
----------------------
The Stage-18 handoff and the STAGE-19 prompt both point at the upstream
`precice/tutorials` `turek-hron-fsi3/reference-results/` tarballs as the FSI3
displacement reference. **They are not.** Both tarballs were fetched and listed at
Stage-19 open: they contain only `*.init.vtu` + `*.dt1..dt3.vtu` coupling-mesh
exports — one to three coupled time windows — i.e. preCICE's own CI regression
fixture, not a watchpoint time history. The gated reference is therefore the
featflow-maintained benchmark data (the same source Stage 18 used for CFD1/2/3).

WHAT IT DOES
------------
1. Records the sha256 of the acquired `ref_fsi3.point` time series (git-tracked
   sidecar; the file itself is DVC-tracked).
2. Recomputes the gated statistics **with the platform's own estimators**
   (`aero.postprocess`), so the reference and the measurement are extracted
   like-for-like — this removes the definitional ambiguity in "mean +/- amplitude"
   (see the SEGMENTATION note below, which is not hypothetical: it moves the uy
   mean by 52 %).
3. Identifies which featflow (level, dt) row the series is, by scoring the
   recomputed values against every row of the git-tracked `fsi3_reference.csv`
   (gate R1).
4. Cross-checks the recomputed values against that identified row within the
   pre-registered R2 bounds and FAILS LOUD otherwise (gate R2) — a gate compared
   against a reference we do not understand is worse than no gate.
5. Writes `fsi3_recomputed.csv`, the reference of record for the ADR-036 D-bands.

SEGMENTATION (the trap this script exists to close)
---------------------------------------------------
ux, drag and lift oscillate at the SECOND harmonic of the flag's transverse motion.
Segmenting them at their own dominant frequency makes consecutive per-cycle
amplitudes alternate between the two half-strokes, which spuriously trips the
periodic-steady-state drift check (measured on the reference itself: amplitude
drift 0.070 for ux and 0.163 for drag, against a 0.02 tolerance). Every signal is
therefore segmented at the SINGLE fundamental period taken from uy — ADR-036 S1.

Usage:
  python scripts/stage19_acquire_fsi_reference.py \
      --point data/references/fsi/turek_hron_fsi3/ref_fsi3.point
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
from aero.postprocess import (
    Signal,
    detect_cycle_convergence,
    dominant_frequency,
    segment_cycles,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REFERENCE_DIR = _REPO_ROOT / "data" / "references" / "fsi" / "turek_hron_fsi3"

# featflow `.point` column map (1-based, as documented on the benchmark page:
# "time, drag on beam, lift on beam, drag on cylinder, lift on cylinder, Ux, Uy"
# in columns 1, 5-8, 11-12). Verified against the tabulated rows by this script.
_COL_TIME = 0
_COL_DT = 1
_COL_DRAG_BEAM = 4
_COL_LIFT_BEAM = 5
_COL_DRAG_CYL = 6
_COL_LIFT_CYL = 7
_COL_UX = 10
_COL_UY = 11
_N_COLS = 12

# ADR-036 R2 bounds. A disagreement wider than these means we do not understand the
# reference; the campaign STOPS rather than gating against it.
_R2_TOL_VALUE = 0.03  # ux mean, uy amplitude
_R2_TOL_FREQUENCY = 0.05


class Recomputed(NamedTuple):
    """The gated statistics, recomputed with the platform's own estimators."""

    f0: float
    n_cycles: int
    n_converged_cycles: int
    ux_mean: float
    ux_amplitude: float
    ux_frequency: float
    uy_mean: float
    uy_amplitude: float
    drag_mean: float
    drag_amplitude: float
    lift_mean: float
    lift_amplitude: float


def _read_point(path: Path) -> dict[str, np.ndarray]:
    """Parse a featflow `.point` table into named arrays. Fail loud on shape drift."""
    rows: list[list[float]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != _N_COLS:
                raise ValueError(
                    f"{path}:{lineno}: expected {_N_COLS} columns, got {len(parts)} — "
                    "the featflow .point layout changed; re-derive the column map before "
                    "trusting any number from this file"
                )
            rows.append([float(p) for p in parts])
    if not rows:
        raise ValueError(f"{path}: no data rows")
    table = np.asarray(rows, dtype=np.float64)
    t = table[:, _COL_TIME]
    if not np.all(np.diff(t) > 0.0):
        raise ValueError(f"{path}: time column is not strictly increasing")
    dt = table[:, _COL_DT]
    if not np.allclose(dt, dt[0], rtol=0.0, atol=0.0):
        raise ValueError(f"{path}: the solver time-step column is not constant")
    return {
        "t": t,
        "solver_dt": dt,
        "ux": table[:, _COL_UX],
        "uy": table[:, _COL_UY],
        "drag": table[:, _COL_DRAG_BEAM] + table[:, _COL_DRAG_CYL],
        "lift": table[:, _COL_LIFT_BEAM] + table[:, _COL_LIFT_CYL],
    }


def recompute(cols: dict[str, np.ndarray]) -> Recomputed:
    """Recompute the FSI3 statistics exactly as `aero/vv/fsi` will for a solve.

    ADR-036 S1: every signal is segmented at the single fundamental period taken
    from uy. See the SEGMENTATION note in the module docstring.
    """
    t = cols["t"]
    uy_signal = Signal.from_arrays(t, cols["uy"], name="flap_tip_uy")
    f0 = dominant_frequency(uy_signal).frequency
    period = 1.0 / f0

    def stats(name: str) -> tuple[float, float, int]:
        samples = segment_cycles(Signal.from_arrays(t, cols[name], name=name), period=period)
        mean = float(np.mean(samples.per_cycle_mean))
        amplitude = float(np.mean(samples.per_cycle_amplitude))
        return mean, amplitude, samples.n_cycles

    uy_mean, uy_amplitude, n_cycles = stats("uy")
    ux_mean, ux_amplitude, _ = stats("ux")
    drag_mean, drag_amplitude, _ = stats("drag")
    lift_mean, lift_amplitude, _ = stats("lift")

    uy_samples = segment_cycles(uy_signal, period=period)
    convergence = detect_cycle_convergence(uy_samples)

    # ux is the second harmonic; measured independently as a structural check (D5).
    ux_frequency = dominant_frequency(
        Signal.from_arrays(t, cols["ux"], name="flap_tip_ux")
    ).frequency

    return Recomputed(
        f0=f0,
        n_cycles=n_cycles,
        n_converged_cycles=convergence.n_converged_cycles,
        ux_mean=ux_mean,
        ux_amplitude=ux_amplitude,
        ux_frequency=ux_frequency,
        uy_mean=uy_mean,
        uy_amplitude=uy_amplitude,
        drag_mean=drag_mean,
        drag_amplitude=drag_amplitude,
        lift_mean=lift_mean,
        lift_amplitude=lift_amplitude,
    )


def _read_table(path: Path) -> list[dict[str, str]]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    return list(csv.DictReader(lines))


def _relative(measured: float, reference: float) -> float:
    if reference == 0.0:
        raise ValueError("zero reference — a relative comparison is undefined")
    return abs(measured - reference) / abs(reference)


def score_row(got: Recomputed, row: dict[str, str]) -> float:
    """Mean relative disagreement between the recomputed values and a tabulated row.

    Scored on the four quantities that are well conditioned under BOTH the
    time-average and midrange readings of "mean" — scoring on the ill-conditioned
    uy mean would let a mis-identification hide behind a 30 % term.
    """
    return (
        _relative(got.ux_mean, float(row["ux_mean"]))
        + _relative(got.ux_amplitude, float(row["ux_amplitude"]))
        + _relative(got.uy_amplitude, float(row["uy_amplitude"]))
        + _relative(got.f0, float(row["uy_frequency"]))
    ) / 4.0


def identify_row(
    got: Recomputed, table: list[dict[str, str]], *, solver_dt: float
) -> tuple[dict[str, str], float]:
    """Identify the tabulated row this series is (gate R1).

    The time step is taken from the file's OWN dt column, not inferred: at level 4
    the three tabulated dt rows agree to within the table's printed precision
    (3 significant figures), so scoring cannot discriminate dt and must not pretend
    to. The mesh level IS discriminated by scoring — the levels differ by 2-5 %,
    well above the recomputation's own ~0.1 % agreement.
    """
    candidates = [row for row in table if float(row["dt"]) == solver_dt]
    if not candidates:
        raise ValueError(
            f"the series declares solver dt={solver_dt:g}, which is not a row in the "
            "tabulated reference — refusing to guess which row it is"
        )
    best: tuple[dict[str, str], float] | None = None
    for row in candidates:
        score = score_row(got, row)
        if best is None or score < best[1]:
            best = (row, score)
    assert best is not None
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--point", type=Path, default=_REFERENCE_DIR / "ref_fsi3.point")
    parser.add_argument("--table", type=Path, default=_REFERENCE_DIR / "fsi3_reference.csv")
    parser.add_argument("--out", type=Path, default=_REFERENCE_DIR / "fsi3_recomputed.csv")
    args = parser.parse_args()

    sha = hashlib.sha256(args.point.read_bytes()).hexdigest()
    args.point.with_suffix(args.point.suffix + ".sha256").write_text(sha + "\n", encoding="utf-8")
    print(f"[acquire] {args.point.name} sha256={sha}")

    cols = _read_point(args.point)
    t = cols["t"]
    solver_dt = float(cols["solver_dt"][0])
    print(
        f"[acquire] {t.size} rows, t in [{t[0]:.4f}, {t[-1]:.4f}] s, "
        f"span {t[-1] - t[0]:.4f} s, sample dt {np.median(np.diff(t)):.3e} s, "
        f"solver dt (self-declared, column 2) {solver_dt:.3e} s"
    )

    got = recompute(cols)
    print(
        f"[recompute] f0={got.f0:.4f} Hz -> {got.n_cycles} full cycles "
        f"({got.n_converged_cycles} settled); ux f={got.ux_frequency:.4f} Hz "
        f"(ratio {got.ux_frequency / got.f0:.3f}, expect ~2)"
    )

    table = _read_table(args.table)
    row, score = identify_row(got, table, solver_dt=solver_dt)
    print(
        f"[R1] identified as level {row['level']} (ndof {row['ndof']}), "
        f"dt {row['dt']} — mean relative score {score:.4%}. "
        "dt is taken from the series' own column 2; the level is discriminated by score."
    )
    for candidate in table:
        marker = " <== identified" if candidate is row else ""
        excluded = "" if float(candidate["dt"]) == solver_dt else "  (other dt)"
        print(
            f"       level {candidate['level']:>1} dt {candidate['dt']:<8} "
            f"score {score_row(got, candidate):.4%}{marker}{excluded}"
        )

    # Gate R2 — pre-registered in ADR-036. Fail loud; never "prefer whichever is closer".
    checks = (
        ("ux_mean", got.ux_mean, float(row["ux_mean"]), _R2_TOL_VALUE),
        ("uy_amplitude", got.uy_amplitude, float(row["uy_amplitude"]), _R2_TOL_VALUE),
        ("frequency", got.f0, float(row["uy_frequency"]), _R2_TOL_FREQUENCY),
    )
    failures: list[str] = []
    print("[R2] recomputed vs tabulated (pre-registered bounds):")
    for name, measured, reference, tol in checks:
        error = _relative(measured, reference)
        status = "PASS" if error <= tol else "FAIL"
        print(
            f"       {name:<13} {measured:+.6e} vs {reference:+.6e}  "
            f"err {error:+.2%}  tol {tol:.0%}  {status}"
        )
        if error > tol:
            failures.append(f"{name}: {error:.2%} > {tol:.0%}")
    # Diagnostics — reported, never gated (the uy mean is period-conditioned: a 1.5 %
    # change in the assumed period moves it by ~50 %).
    for name, measured, reference in (
        ("uy_mean (diag)", got.uy_mean, float(row["uy_mean"])),
        ("ux_amplitude (diag)", got.ux_amplitude, float(row["ux_amplitude"])),
        ("drag_mean (diag)", got.drag_mean, float(row["drag_mean"])),
        ("drag_amp (diag)", got.drag_amplitude, float(row["drag_amplitude"])),
        ("lift_amp (diag)", got.lift_amplitude, float(row["lift_amplitude"])),
    ):
        print(
            f"       {name:<20} {measured:+.6e} vs {reference:+.6e}  "
            f"err {_relative(measured, reference):+.2%}"
        )
    if failures:
        print(
            "[R2] REFERENCE-INTEGRITY NO-GO — the recomputed statistics disagree with the "
            f"published table beyond the pre-registered bounds: {'; '.join(failures)}. "
            "Do NOT gate against a reference we do not understand; investigate the column "
            "map, the file identity, and the units before any campaign run.",
            file=sys.stderr,
        )
        return 1

    args.out.write_text(
        "# Turek-Hron FSI3 reference of record (ADR-036 R3) — RECOMPUTED from the\n"
        f"# DVC-tracked ref_fsi3.point (sha256 {sha}) with the platform's own\n"
        "# aero.postprocess estimators, so the reference and every measured solve are\n"
        "# extracted like-for-like. Identified as featflow level "
        f"{row['level']} (ndof {row['ndof']}), dt {row['dt']} — see reference.md.\n"
        "# All signals segmented at the SINGLE fundamental period from uy (ADR-036 S1).\n"
        "# Means/amplitudes are the mean over full cycles of the per-cycle statistic;\n"
        "# amplitude is half peak-to-peak (the paper's +/- convention).\n"
        "quantity,value,units,gated\n"
        f"frequency,{got.f0:.6e},Hz,yes\n"
        f"uy_amplitude,{got.uy_amplitude:.6e},m,yes\n"
        f"ux_amplitude,{got.ux_amplitude:.6e},m,yes\n"
        f"ux_mean,{got.ux_mean:.6e},m,yes\n"
        f"ux_frequency,{got.ux_frequency:.6e},Hz,yes\n"
        f"uy_mean,{got.uy_mean:.6e},m,no\n"
        f"drag_mean,{got.drag_mean:.6e},N/m,no\n"
        f"drag_amplitude,{got.drag_amplitude:.6e},N/m,no\n"
        f"lift_mean,{got.lift_mean:.6e},N/m,no\n"
        f"lift_amplitude,{got.lift_amplitude:.6e},N/m,no\n",
        encoding="utf-8",
    )
    print(f"[out] wrote {args.out}")
    print("[R1+R2] PASSED — the reference of record is established.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
