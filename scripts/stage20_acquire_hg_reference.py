#!/usr/bin/env python3
"""Acquire the Heathcote & Gursul (2007) reference OF RECORD for the Stage-20 gate.

Mirrors ``scripts/stage19_acquire_fsi_reference.py``'s five steps. Needs NO PDF: it
consumes the two git-tracked tables, so anyone (and CI) can re-run it.

WHAT IT DOES
------------
1. Records the sha256 of both acquired tables (``digitization.csv``, ``text_sourced.csv``)
   as git-tracked sidecars. The source PDF is never committed -- licence -- so its
   reproducible content digest travels inside digitization.csv's header instead.
2. Recomputes the gated quantities from the digitized markers: the flexible-minus-rigid
   increments at the pre-registered operating point, with the correlated/uncorrelated
   uncertainty split applied. HG publish C_T (Fig 5.6) and eta (Fig 5.9) but NOT C_P, so
   C_P = C_T/eta is DERIVED here and reported as a consistency output, not as an
   independent check -- saying otherwise would dress a definition up as evidence.
3. Identifies the row: which figure, which foil, which Re, which St, and by how much each
   arm had to be interpolated onto the common gated Strouhal number.
4. Fail-loud cross-check (R2) against every applicable text-sourced value, with bounds
   fixed BEFORE the numbers were read. STOPS on disagreement rather than preferring
   whichever is closer.
5. Writes ``hg2007_recomputed.csv`` -- the reference of record ADR-039 sizes its bands from.

THE ONE DOCUMENTED DISAGREEMENT (see R2_CROSSOVER below). The thesis prose states the
rigid drag-to-thrust transition occurs "at a Strouhal number St=0.17" and that this holds
"for all Reynolds numbers" (5.3.2, repeated for efficiency in 5.3.3). Its own Figure 5.6
does not: the digitized crossover is 0.191 / 0.161 / 0.167 at Re = 9000 / 18000 / 27000.
Two of three reproduce the prose; Re=9000 is ~13 % high. The digitization is not at fault
-- the calibration is verified three independent ways per panel, and Fig 5.9a independently
shows the rigid efficiency curve beginning at St = 0.205 with nothing plotted below it.
The prose is a rounded generalisation. It is therefore cross-checked where it holds and
RECORDED, with the measured value, where it does not. The consequence is carried into
reference.md: a blanket "for all Re" statement in this thesis is not by itself evidence.

Usage:
    python scripts/stage20_acquire_hg_reference.py
    python scripts/stage20_acquire_hg_reference.py --check   # verify, write nothing
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from itertools import pairwise
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REFERENCE_DIR = _REPO_ROOT / "data" / "references" / "fsi" / "heathcote_gursul_2007"

# --- the pre-registered operating point (ADR-039) -----------------------------
# Fixed from the reference ALONE, before any solve, by the rule recorded in ADR-039:
# maximise the flexible-minus-rigid increment in HG's OWN normalisation, d(C_T/St^2),
# restricted to the band 0.2 < St < 0.4 that the thesis itself identifies as the range
# observed in nature and in which its own propulsive-efficiency optimum (St = 0.29) sits.
# Selecting on raw dC_T instead walks to the right-hand edge of the figure, because C_T
# scales as St^2 -- which is exactly why HG plot C_T/St^2.
REYNOLDS = 9000
ST_GATE = 0.345
BC_FLEXIBLE = "0.85e-3"
BC_RIGID = "4.23e-3"

# Rig constants (thesis 2.1.4, 2.1.6). h = a/c = 17.5/90 = 0.194 -- NOT 0.175, which is
# the NACA-0012 validation model and the SPANWISE wing (100 mm chord, same 17.5 mm shaker
# amplitude). Getting that wrong changes the plunge amplitude by 11 %.
CHORD_M = 0.090
AMPLITUDE_M = 0.0175
SPAN_M = 0.300
RHO = 1000.0
NU = 1.0e-6

# --- pre-registered R2 bounds (fixed before the values were read) -------------
# 15 % on every anchor. Wide enough to absorb the prose quoting pitch amplitudes to one
# significant figure ("6 degrees" means 5.5-6.5) and the abscissa's own reading error;
# far tighter than the 3-5x class of error R2 exists to catch -- this repo's OTHER
# Heathcote reference was wrong by that much for a whole stage.
R2_TOL = 0.15

# The crossover anchor is checked only where the prose and the figure agree; see the
# module docstring. Re=9000 is reported with its measured value and its deviation.
R2_CROSSOVER_GATED_RE = (18000, 27000)


class ReferenceError(RuntimeError):
    """The reference could not be assembled, or disagrees with its own text."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(line for line in fh if not line.startswith("#")))


def _series(
    rows: list[dict[str, str]], fig: str, panel: str, bc: str
) -> list[tuple[float, float, float, float]]:
    """(St, value, u_reading, u_axis) for one series, St-ascending."""
    return sorted(
        (
            float(r["strouhal"]),
            float(r["value"]),
            float(r["u_reading_abs"]),
            float(r["u_axis_abs"]),
        )
        for r in rows
        if r["figure"] == fig and r["panel"] == panel and r["b_over_c"] == bc
    )


def _interp(
    series: list[tuple[float, float, float, float]], st: float
) -> tuple[float, float, float]:
    """Linear interpolation onto `st`; returns (value, u_reading, u_axis). Fail loud."""
    if not series:
        raise ReferenceError("empty series")
    lo, hi = series[0][0], series[-1][0]
    if not lo - 1e-9 <= st <= hi + 1e-9:
        raise ReferenceError(
            f"St={st} is outside the digitized range [{lo:.4f}, {hi:.4f}] -- refusing to "
            "extrapolate a reference value"
        )
    for a, b in pairwise(series):
        if a[0] <= st <= b[0]:
            f = 0.0 if b[0] == a[0] else (st - a[0]) / (b[0] - a[0])
            return (
                a[1] + f * (b[1] - a[1]),
                max(a[2], b[2]),  # reading term: the worse of the two bracketing markers
                max(a[3], b[3]),
            )
    return (series[-1][1], series[-1][2], series[-1][3])


def _crossing(series: list[tuple[float, float, float, float]]) -> float | None:
    for a, b in pairwise(series):
        if a[1] < 0 <= b[1]:
            return a[0] + (b[0] - a[0]) * (-a[1]) / (b[1] - a[1])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Verify only; write nothing.")
    args = ap.parse_args()

    dig_path = _REFERENCE_DIR / "digitization.csv"
    txt_path = _REFERENCE_DIR / "text_sourced.csv"
    for p in (dig_path, txt_path):
        if not p.is_file():
            print(f"{p}: not found")
            return 2

    # --- step 1: digests ------------------------------------------------------
    print("[1/5] acquired-table digests")
    digests = {p.name: _sha256(p) for p in (dig_path, txt_path)}
    for name, digest in digests.items():
        print(f"      {name}: {digest}")
        if not args.check:
            (_REFERENCE_DIR / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")

    dig = _read(dig_path)
    txt = _read(txt_path)

    # --- step 2: recompute ----------------------------------------------------
    print(
        f"[2/5] recomputing at Re={REYNOLDS}, St={ST_GATE}, "
        f"flexible b/c={BC_FLEXIBLE} vs rigid b/c={BC_RIGID}"
    )
    u_inf = REYNOLDS * NU / CHORD_M
    freq = ST_GATE * u_inf / (2.0 * AMPLITUDE_M)
    print(
        f"      U={u_inf:.4f} m/s  f={freq:.4f} Hz  T={1.0 / freq:.4f} s  "
        f"h=a/c={AMPLITUDE_M / CHORD_M:.4f}"
    )

    out: list[dict[str, str]] = []

    def emit(
        quantity: str,
        value: float,
        u_read: float,
        u_axis: float,
        *,
        gated: bool,
        units: str,
        provenance: str,
        note: str,
    ) -> None:
        out.append(
            {
                "quantity": quantity,
                "value": f"{value:.6g}",
                "units": units,
                "u_reading_abs": f"{u_read:.6g}",
                "u_axis_abs": f"{u_axis:.6g}",
                "gated": "yes" if gated else "no",
                "provenance": provenance,
                "note": note,
            }
        )

    pairs = (
        ("thrust_coefficient", "5.6", "a", "-", True),
        ("propulsive_efficiency", "5.9", "a", "-", True),
        ("pitch_amplitude", "5.13", "a", "deg", True),
    )
    recomputed: dict[str, dict[str, tuple[float, float, float]]] = {}
    for quantity, fig, panel, units, gated in pairs:
        recomputed[quantity] = {}
        for arm, bc in (("flexible", BC_FLEXIBLE), ("rigid", BC_RIGID)):
            series = _series(dig, fig, panel, bc)
            if not series:
                if quantity == "pitch_amplitude" and arm == "rigid":
                    # Fig 5.13 omits b/c=4.23e-3: its pitch amplitude is too small to
                    # measure a phase for. The thesis bounds it in prose instead (< 2 deg),
                    # which is what the rigid arm is gated against.
                    continue
                raise ReferenceError(f"no digitized {quantity} for b/c={bc}")
            v, ur, ua = _interp(series, ST_GATE)
            recomputed[quantity][arm] = (v, ur, ua)
            emit(
                f"{quantity}_{arm}",
                v,
                ur,
                ua,
                gated=gated,
                units=units,
                provenance=f"figure-digitized (Fig {fig}{panel}), interpolated to St={ST_GATE}",
                note=f"b/c={bc}",
            )
        if "flexible" in recomputed[quantity] and "rigid" in recomputed[quantity]:
            fv, fur, _ = recomputed[quantity]["flexible"]
            rv, rur, _ = recomputed[quantity]["rigid"]
            # The axis-calibration term is COMMON to both arms -- same panel, same axes,
            # same frame -- so it cancels in the difference. Only the independent
            # per-marker reading terms survive, in quadrature. That cancellation is what
            # licenses a tighter band on the increment than on either absolute value, and
            # it is shown here rather than asserted.
            emit(
                f"{quantity}_increment",
                fv - rv,
                (fur**2 + rur**2) ** 0.5,
                0.0,
                gated=True,
                units=units,
                provenance="derived: flexible - rigid on ONE panel",
                note="axis-calibration term cancels (correlated within the figure); "
                "reading terms RSS (uncorrelated per marker)",
            )

    # C_P is DERIVED, not published: HG give C_T and eta but never C_P.
    for arm in ("flexible", "rigid"):
        ct = recomputed["thrust_coefficient"][arm][0]
        eta = recomputed["propulsive_efficiency"][arm][0]
        emit(
            f"power_coefficient_{arm}",
            ct / eta,
            0.0,
            0.0,
            gated=False,
            units="-",
            provenance="DERIVED as C_T/eta -- HG publish C_T and eta, never C_P",
            note="reported for context; not an independent check of our eta definition",
        )

    # --- step 3: identify the row --------------------------------------------
    print("[3/5] row identification")
    for quantity, fig, panel, _u, _g in pairs:
        for arm, bc in (("flexible", BC_FLEXIBLE), ("rigid", BC_RIGID)):
            series = _series(dig, fig, panel, bc)
            if not series:
                continue
            nearest = min(series, key=lambda s: abs(s[0] - ST_GATE))
            print(
                f"      {quantity:22s} {arm:8s} Fig {fig}{panel} b/c={bc}: "
                f"nearest marker St={nearest[0]:.4f} (gate St={ST_GATE}, "
                f"interpolation span {abs(nearest[0] - ST_GATE):.4f})"
            )

    # --- step 4: R2 fail-loud cross-check ------------------------------------
    print(f"[4/5] R2 cross-check against text_sourced.csv (bound {R2_TOL:.0%})")
    failures: list[str] = []

    def check(label: str, measured: float, stated: float) -> None:
        rel = (measured - stated) / stated
        ok = abs(rel) <= R2_TOL
        print(
            f"      {'PASS' if ok else 'FAIL'} {label}: measured {measured:.4g} "
            f"vs stated {stated:.4g} ({rel:+.1%})"
        )
        if not ok:
            failures.append(f"{label}: {measured:.4g} vs {stated:.4g} ({rel:+.1%})")

    stated_pitch = {
        (r["b_over_c"], float(r["strouhal"] or 0)): float(r["value"])
        for r in txt
        if r["quantity"] == "pitch_amplitude_deg" and r["reynolds"] == "9000" and r["b_over_c"]
    }
    for (bc, st), stated in sorted(stated_pitch.items()):
        series = _series(dig, "5.13", "a", bc)
        if not series or bc == BC_RIGID:
            continue  # 4.23e-3 is absent from Fig 5.13 by construction; prose bounds it
        check(f"pitch amplitude b/c={bc} @ St={st}", _interp(series, st)[0], stated)

    crossover_stated = next(
        float(r["value"]) for r in txt if r["quantity"] == "thrust_crossover_strouhal_rigid"
    )
    for panel, re_ in (("a", 9000), ("b", 18000), ("c", 27000)):
        measured = _crossing(_series(dig, "5.6", panel, BC_RIGID))
        if measured is None:
            failures.append(f"no drag-to-thrust crossover found in Fig 5.6{panel}")
            continue
        if re_ in R2_CROSSOVER_GATED_RE:
            check(f"rigid crossover Re={re_}", measured, crossover_stated)
        else:
            rel = (measured - crossover_stated) / crossover_stated
            print(
                f"      NOTE rigid crossover Re={re_}: measured {measured:.4g} vs the "
                f"prose's blanket {crossover_stated:.4g} ({rel:+.1%}) -- RECORDED, not "
                "gated. The prose generalises; the figure does not. See the docstring."
            )
            emit(
                "thrust_crossover_strouhal_rigid_re9000",
                measured,
                0.0,
                0.0,
                gated=False,
                units="-",
                provenance="figure-digitized (Fig 5.6a)",
                note=f"thesis prose states {crossover_stated} 'for all Reynolds numbers'; "
                f"the figure gives {measured:.4g} here ({rel:+.1%}). Documented "
                "disagreement -- a blanket 'for all Re' claim in this thesis is not "
                "by itself evidence.",
            )

    # Sign of the headline result, from the reference itself. If HG's own data did not
    # show the flexible arm beating the rigid one at the gated point, the D5/D6 sign
    # clauses would be gating something the reference does not support.
    for quantity in ("thrust_coefficient", "propulsive_efficiency"):
        inc = recomputed[quantity]["flexible"][0] - recomputed[quantity]["rigid"][0]
        ok = inc > 0.0
        print(f"      {'PASS' if ok else 'FAIL'} {quantity} increment is positive: {inc:+.4g}")
        if not ok:
            failures.append(f"{quantity} increment is not positive in the reference ({inc:+.4g})")

    if failures:
        print(
            "\nR2 FAILED -- the campaign STOPS. A gate compared against a reference we do "
            "not understand is worse than no gate."
        )
        for f in failures:
            print(f"  - {f}")
        return 1

    # --- step 5: the reference of record -------------------------------------
    dest = _REFERENCE_DIR / "hg2007_recomputed.csv"
    print(f"[5/5] writing the reference of record -> {dest}")
    header = (
        "# Heathcote & Gursul (2007) chordwise-flexible plunging airfoil -- REFERENCE OF\n"
        "# RECORD for the ADR-039 gate bands. Regenerate:\n"
        "#     python scripts/stage20_acquire_hg_reference.py\n"
        "#\n"
        f"# Operating point (pre-registered in ADR-039, fixed from the reference alone):\n"
        f"#   Re = {REYNOLDS}, St = {ST_GATE}, flexible b/c = {BC_FLEXIBLE}, "
        f"rigid b/c = {BC_RIGID}\n"
        f"#   c = {CHORD_M} m, a = {AMPLITUDE_M} m (h = a/c = {AMPLITUDE_M / CHORD_M:.4f}), "
        f"span = {SPAN_M} m\n"
        f"#   U = {u_inf:.6g} m/s, f = {freq:.6g} Hz, T = {1.0 / freq:.6g} s, "
        f"rho = {RHO} kg/m3, nu = {NU} m2/s\n"
        "#\n"
        f"#   sources: digitization.csv sha256 {digests['digitization.csv']}\n"
        f"#            text_sourced.csv sha256 {digests['text_sourced.csv']}\n"
        "#\n"
        "# u_reading_abs is UNCORRELATED per marker and survives the flexible-minus-rigid\n"
        "# difference; u_axis_abs is CORRELATED within a figure and CANCELS in it, which is\n"
        "# why every *_increment row carries u_axis_abs = 0. The instrument systematic\n"
        "# (5 % thrust / 10 % efficiency, thesis 2.2.2) is correlated within the instrument\n"
        "# and is applied by the consumer to the ABSOLUTE rows only, for the same reason.\n"
    )
    if args.check:
        print("      --check: not written")
    else:
        with dest.open("w", encoding="utf-8", newline="") as fh:
            fh.write(header)
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(out)
    for row in out:
        print(
            f"      {row['quantity']:38s} {row['value']:>10s} {row['units']:4s} "
            f"gated={row['gated']}"
        )
    print("\n[R1+R2] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
