#!/usr/bin/env python3
"""Digitize Heathcote & Gursul (2007) Figures 5.6 / 5.9 / 5.13 into ``digitization.csv``.

WHY THIS SCRIPT EXISTS
----------------------
The thesis is open-access but NOT redistributable, so the PDF is never committed. This
script is the reproducible bridge between that PDF and the git-tracked reference: point it
at a locally fetched copy and it regenerates ``digitization.csv`` byte-for-byte.

**The source digest is NOT the file digest.** Bath's Pure repository re-wraps the PDF on
every download with OpenPDF 1.4.2, so two fetches of the same URL differ in exactly the
``/CreationDate`` and ``/ID`` trailer fields (60 bytes of 12,175,275, measured). A raw
sha256 is therefore a per-fetch artifact and can never be reproduced. Two invariants that
CAN be, both verified across independent fetches:

* ``pdf_content_sha256`` -- sha256 after normalizing ``/ID`` and the date strings;
* ``page_raster_sha256`` -- sha256 of the 200 dpi page raster under a pinned PyMuPDF.

The raster digest is the stronger of the two, because it pins exactly the pixels that were
read. Both are written into the CSV header.

METHOD (fixed in reference.md BEFORE any value was read; this script implements it)
----------------------------------------------------------------------------------
1. render the figure page at 200 dpi;
2. read each required marker THREE times independently -- here, three independent
   binarizations (grey thresholds 120/140/160) of a normalized-cross-correlation match
   against the figure's OWN legend glyph. Three passes of the same deterministic estimator
   over three different binarizations measure the extraction's real sensitivity; three
   human passes over one image would not be independent in any useful sense. The deviation
   from "three human readings" is deliberate, is recorded in the CSV, and is strictly more
   auditable -- anyone can re-run it.
3. reading term = HALF-RANGE of the three readings (uncorrelated per marker);
   axis-calibration term = +/-1 px on each axis endpoint (correlated within a figure);
4. **Figures 5.6 and 5.1 plot C_T/St^2, NOT C_T** -- despite Fig 5.6's caption reading
   "Thrust coefficient as a function of Strouhal number". Values read off them are
   multiplied by St^2 here, and both the raw and the corrected number are recorded. At
   St = 0.3 that factor is 11.1. Getting this wrong is what made the repo's OTHER
   Heathcote reference wrong by 3-5x for an entire stage.
5. the R2 cross-check against ``text_sourced.csv`` lives in
   ``scripts/stage20_acquire_hg_reference.py``, which needs no PDF.

AXIS RANGES ARE NOT ASSUMED. Each panel's frame is located by longest-contiguous-dark-run,
and the data range each frame spans was read off the rendered axis labels and is asserted
here. Fig 5.6c spans St = 0..0.35, NOT 0..0.5 like 5.6b -- the thesis holds the oscillation
FREQUENCIES fixed across panels, so the St range scales as 1/U (p127). Assuming 0..0.5
there makes the Re=27000 crossover read 0.241 instead of 0.169.

Usage:
    python scripts/stage20_digitize_hg_figures.py --pdf /path/to/heathcote_thesis.pdf
    uv run --no-project --with pymupdf==1.26.3 --with pillow --with numpy --with scipy \
        python scripts/stage20_digitize_hg_figures.py --pdf ...
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REFERENCE_DIR = _REPO_ROOT / "data" / "references" / "fsi" / "heathcote_gursul_2007"
_OUT = _REFERENCE_DIR / "digitization.csv"

DPI = 200
PYMUPDF_PIN = "1.26.3"
THRESHOLDS = (120, 140, 160)

# The reproducible content digest (see module docstring). Verified identical across two
# independent fetches whose raw sha256 differed.
PDF_CONTENT_SHA256 = "276cec6ea449dd130fe6c804afd1e07239d02da022c4a8b12b1303a69371085b"

_ID_RE = re.compile(rb"/ID\s*\[\s*<[0-9A-Fa-f]*>\s*<[0-9A-Fa-f]*>\s*\]")
_DATE_RE = re.compile(rb"/(CreationDate|ModDate)\s*\(D:[^)]*\)")


def pdf_content_sha256(path: Path) -> str:
    """sha256 of the PDF with the per-download ``/ID`` and date stamps normalized."""
    raw = path.read_bytes()
    return hashlib.sha256(
        _DATE_RE.sub(rb"/\1(D:NORMALIZED)", _ID_RE.sub(b"/ID[<0><0>]", raw))
    ).hexdigest()


# --- panel geometry -----------------------------------------------------------
# Every (page, panel) with the data range its frame spans. The ranges were read off the
# rendered axis labels; `assert_frame` re-derives the frame in pixels from the raster.
@dataclass(frozen=True)
class Panel:
    figure: str
    panel: str
    page: int  # 1-based PDF page
    row_band: tuple[int, int]  # search band for the frame, in raster rows
    st_max: float
    y_lo: float
    y_hi: float
    quantity: str
    units: str
    reynolds: int
    legend_box: tuple[int, int, int, int]  # y0, y1, x0, x1 -- excluded from matching
    series: tuple[str, ...]


# b/c keys, x1e-3
S5 = ("0.56e-3", "0.85e-3", "1.13e-3", "1.41e-3", "4.23e-3")
S4 = ("0.56e-3", "0.85e-3", "1.13e-3", "1.41e-3")

PANELS: tuple[Panel, ...] = (
    Panel(
        "5.6",
        "a",
        143,
        (300, 1000),
        1.00,
        -10.0,
        20.0,
        "thrust_coefficient_over_st2",
        "-",
        9000,
        (770, 900, 735, 1010),
        S5,
    ),
    Panel(
        "5.6",
        "b",
        143,
        (1150, 1850),
        0.50,
        -10.0,
        20.0,
        "thrust_coefficient_over_st2",
        "-",
        18000,
        (1610, 1750, 735, 1010),
        S5,
    ),
    Panel(
        "5.6",
        "c",
        144,
        (300, 1100),
        0.35,
        -10.0,
        20.0,
        "thrust_coefficient_over_st2",
        "-",
        27000,
        (880, 1020, 735, 1010),
        S5,
    ),
    Panel(
        "5.9",
        "a",
        147,
        (300, 1000),
        1.00,
        0.0,
        0.30,
        "propulsive_efficiency",
        "-",
        9000,
        (345, 470, 470, 800),
        S5,
    ),
    Panel(
        "5.13",
        "a",
        152,
        (300, 1000),
        1.00,
        0.0,
        25.0,
        "pitch_amplitude",
        "deg",
        9000,
        (340, 450, 730, 1010),
        S4,
    ),
)

# Legend glyph boxes on page 143, panel (a) -- one clean instance of each marker. The
# glyphs are rendered identically in every panel, so one template set serves all.
GLYPHS: dict[str, tuple[int, int, int, int]] = {
    "0.56e-3": (785, 798, 755, 768),  # open triangle
    "0.85e-3": (808, 822, 754, 767),  # open diamond
    "1.13e-3": (833, 846, 756, 768),  # filled circle
    "1.41e-3": (856, 868, 756, 768),  # plus
    "4.23e-3": (878, 891, 756, 768),  # open square
}
GLYPH_PAGE = 143

# Per-series match threshold. The plus is a thin glyph with far less ink than the closed
# outlines, so the correlation floor that cleanly isolates a square drops real plus markers.
# Lowering the floor alone is NOT enough and was measured to be actively wrong: at 0.52 the
# plus template also matched the horizontal C_T/St^2 = 0 gridline (55 spurious "markers"
# strung along it at value ~ 0) and the open triangles of the 0.56e-3 series. The floor is
# therefore lowered AND paired with `_looks_like_a_plus`, a shape test the two false
# positives both fail: a gridline has no central vertical stroke, and an open triangle has
# no ink at its centre at all.
_MATCH_THRESHOLD: dict[str, float] = {"1.41e-3": 0.55}
_DEFAULT_THRESHOLD = 0.62
_PLUS_SERIES = "1.41e-3"


def _looks_like_a_plus(dark, cy: int, cx: int) -> bool:
    """True iff there is a central vertical stroke with light diagonal corners.

    The plus glyph is ~11 px across. A connecting polyline through the marker supplies the
    horizontal arm, so the horizontal arm carries no information; the VERTICAL arm is the
    discriminator.
    """
    h, w = dark.shape
    if not (5 <= cy < h - 5 and 5 <= cx < w - 5):
        return False
    column = dark[cy - 5 : cy + 6, cx - 1 : cx + 2]
    if int(column.any(axis=1).sum()) < 9:  # >= 9 of 11 rows carry ink
        return False
    corners = [dark[cy + dy, cx + dx] for dy in (-4, 4) for dx in (-4, 4)]
    return sum(1 for c in corners if not c) >= 3  # >= 3 of 4 diagonal corners are light


# No panel carries a real datum below this Strouhal number (the lowest measured point in
# any panel is St ~ 0.09). Below it, the only things the matcher can find are the y-axis
# tick marks, which look like a plus.
_ST_FLOOR = 0.05


def _longest_run(mask) -> tuple[int, int, int]:
    import numpy as np

    xs = np.where(mask)[0]
    if len(xs) == 0:
        return (0, 0, 0)
    best = (0, 0, 0)
    s = p = int(xs[0])
    for v in [int(v) for v in xs[1:]] + [10**9]:
        if v - p > 1:
            if p - s + 1 > best[0]:
                best = (p - s + 1, s, p)
            s = v
        p = v
    return best


def frame_of(dark, row_band: tuple[int, int]) -> tuple[int, int, int, int]:
    """(x_left, x_right, y_top, y_bottom) of the plot frame, in raster pixels."""
    r0, r1 = row_band
    ybot = max(range(r0, r1), key=lambda y: _longest_run(dark[y])[0])
    xax = max(range(300, 1100), key=lambda x: _longest_run(dark[:, x][r0:r1])[0])
    _, xs, xe = _longest_run(dark[ybot])
    _, ys, ye = _longest_run(dark[:, xax][r0:r1])
    return xs, xe, ys + r0, ye + r0


def match_peaks(dark, tmpl, region, thresh: float = 0.62, nms: int = 7):
    import numpy as np
    from scipy import ndimage

    y0, y1, x0, x1 = region
    t = tmpl.astype(float)
    t = t - t.mean()
    tn = float(np.sqrt((t * t).sum()))
    sub = dark[y0:y1, x0:x1].astype(float)
    ones = np.ones_like(t)
    n = t.size
    s1 = ndimage.correlate(sub, ones, mode="constant")
    s2 = ndimage.correlate(sub * sub, ones, mode="constant")
    num = ndimage.correlate(sub, t, mode="constant")
    var = s2 - s1 * s1 / n
    var[var < 1e-9] = 1e-9
    score = num / (np.sqrt(var) * tn)
    out: list[tuple[int, int, float]] = []
    o = score.copy()
    while True:
        i = int(np.argmax(o))
        v = float(o.flat[i])
        if v < thresh:
            break
        yy, xx = np.unravel_index(i, o.shape)
        out.append((int(yy) + y0, int(xx) + x0, v))
        o[max(0, yy - nms) : yy + nms + 1, max(0, xx - nms) : min(o.shape[1], xx + nms + 1)] = -1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, type=Path, help="Locally fetched thesis PDF.")
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()

    try:
        import fitz  # PyMuPDF
        import numpy as np
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment guard
        print(
            f"missing dependency: {exc}. Run under `uv run --no-project --with "
            f"pymupdf=={PYMUPDF_PIN} --with pillow --with numpy --with scipy`.",
            file=sys.stderr,
        )
        return 2

    if not args.pdf.is_file():
        print(f"{args.pdf}: not found", file=sys.stderr)
        return 2
    got = pdf_content_sha256(args.pdf)
    if got != PDF_CONTENT_SHA256:
        print(
            f"{args.pdf}: content digest {got}\n  expected {PDF_CONTENT_SHA256}\n"
            "  REFUSING -- this is not the thesis the reference was read from.",
            file=sys.stderr,
        )
        return 1
    print(f"[1/4] source content digest verified: {got[:16]}...")

    doc = fitz.open(args.pdf)
    if doc.page_count != 186:
        print(f"{args.pdf}: {doc.page_count} pages, expected 186", file=sys.stderr)
        return 1

    rasters: dict[int, np.ndarray] = {}
    raster_sha: dict[int, str] = {}
    for page in sorted({p.page for p in PANELS} | {GLYPH_PAGE}):
        png = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
        raster_sha[page] = hashlib.sha256(png).hexdigest()
        import io

        rasters[page] = np.array(Image.open(io.BytesIO(png)).convert("L"))
        print(
            f"[2/4] page {page}: raster sha256 {raster_sha[page][:16]}... "
            f"{rasters[page].shape[1]}x{rasters[page].shape[0]}"
        )

    glyph_src = rasters[GLYPH_PAGE] < 140
    templates = {k: glyph_src[y0:y1, x0:x1] for k, (y0, y1, x0, x1) in GLYPHS.items()}

    rows: list[dict[str, object]] = []
    for panel in PANELS:
        im = rasters[panel.page]
        x0, x1, ytop, ybot = frame_of(im < 128, panel.row_band)
        span_px = ybot - ytop
        full = panel.y_hi - panel.y_lo
        # +/-1 px on each endpoint, in data units. Correlated within a figure.
        u_axis_abs = full * 2.0 / span_px
        print(
            f"[3/4] Fig {panel.figure}{panel.panel} (Re={panel.reynolds}): frame "
            f"x {x0}..{x1}, y {ytop}..{ybot}; St 0..{panel.st_max}; "
            f"{panel.quantity} {panel.y_lo}..{panel.y_hi}; u_axis={u_axis_abs:.4g}"
        )

        # Resolve ALL series jointly, per threshold: one marker belongs to exactly one
        # series. Matching each template independently let the plus template claim open
        # triangles (measured: two spurious "1.41e-3" points in Fig 5.13a carrying the
        # 0.56e-3 triangle's values). Highest correlation wins the pixel.
        by_series: dict[str, list[list[tuple[float, float]]]] = {k: [] for k in panel.series}
        ly0, ly1, lx0, lx1 = panel.legend_box
        for thr in THRESHOLDS:
            dark = im < thr
            cands: list[tuple[float, str, int, int]] = []
            for key in panel.series:
                for py, px, score in match_peaks(
                    dark,
                    templates[key],
                    (ytop - 6, ybot + 6, x0 - 4, x1 + 9),
                    thresh=_MATCH_THRESHOLD.get(key, _DEFAULT_THRESHOLD),
                ):
                    if ly0 <= py <= ly1 and lx0 <= px <= lx1:
                        continue  # legend glyph
                    if py >= ybot - 12:
                        continue  # x-axis tick marks masquerading as a marker
                    if (px - x0) / (x1 - x0) * panel.st_max < _ST_FLOOR:
                        continue  # y-axis tick marks (see _ST_FLOOR)
                    if key == _PLUS_SERIES and not _looks_like_a_plus(dark, py, px):
                        continue  # gridline / open-triangle false positive
                    cands.append((score, key, py, px))
            taken: list[tuple[int, int]] = []
            claimed: dict[str, list[tuple[float, float]]] = {k: [] for k in panel.series}
            for _score, key, py, px in sorted(cands, key=lambda c: -c[0]):
                if any(abs(py - ty) <= 6 and abs(px - tx) <= 6 for ty, tx in taken):
                    continue  # this marker already belongs to a better-scoring series
                taken.append((py, px))
                claimed[key].append(
                    (
                        (px - x0) / (x1 - x0) * panel.st_max,
                        panel.y_hi - (py - ytop) * full / span_px,
                    )
                )
            for key in panel.series:
                by_series[key].append(sorted(claimed[key]))

        for key in panel.series:
            per_thr = by_series[key]

            # pair readings across thresholds by nearest St (markers are >= 20 px apart).
            # Collapse near-coincident entries in the base list first: two peaks within the
            # pairing tolerance are the same marker, and iterating over both would emit the
            # same row twice.
            base: list[tuple[float, float]] = []
            for st_b, v_b in max(per_thr, key=len):
                if base and abs(st_b - base[-1][0]) < 0.012:
                    continue
                base.append((st_b, v_b))
            for st_b, _ in base:
                readings: list[float] = []
                sts: list[float] = []
                for lst in per_thr:
                    near = [(abs(s - st_b), s, v) for s, v in lst if abs(s - st_b) < 0.012]
                    if near:
                        _, s, v = min(near)
                        readings.append(v)
                        sts.append(s)
                if len(readings) < 2:
                    continue
                st = sorted(sts)[len(sts) // 2]
                raw_median = sorted(readings)[len(readings) // 2]
                half_range = (max(readings) - min(readings)) / 2.0
                st2 = st * st if panel.figure in ("5.6", "5.1") else 1.0
                value = raw_median * st2
                rows.append(
                    {
                        "figure": panel.figure,
                        "panel": panel.panel,
                        "quantity": ("thrust_coefficient" if st2 != 1.0 else panel.quantity),
                        "units": panel.units,
                        "b_over_c": key,
                        "reynolds": panel.reynolds,
                        "strouhal": f"{st:.4f}",
                        "reading_1": f"{readings[0]:.4f}",
                        "reading_2": f"{readings[1]:.4f}" if len(readings) > 1 else "",
                        "reading_3": f"{readings[2]:.4f}" if len(readings) > 2 else "",
                        "n_readings": len(readings),
                        "raw_median": f"{raw_median:.4f}",
                        "reading_half_range": f"{half_range:.4f}",
                        "st_squared_factor": f"{st2:.6f}",
                        "value": f"{value:.5f}",
                        "u_reading_abs": f"{half_range * st2:.5f}",
                        "u_axis_abs": f"{u_axis_abs * st2:.5f}",
                        "pdf_page": panel.page,
                        "page_raster_sha256": raster_sha[panel.page],
                        "dpi": DPI,
                        "tool": "stage20_digitize_hg_figures.py/zncc-legend-template",
                        "tool_version": f"pymupdf=={PYMUPDF_PIN};thresholds={'/'.join(map(str, THRESHOLDS))}",
                    }
                )

    rows.sort(key=lambda r: (r["figure"], r["panel"], r["b_over_c"], float(r["strouhal"])))
    header = list(rows[0].keys())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        fh.write(_CSV_HEADER_COMMENT)
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"[4/4] wrote {len(rows)} digitized markers -> {args.out}")
    return 0


_CSV_HEADER_COMMENT = """\
# Heathcote & Gursul (2007) chordwise-flexible plunging airfoil -- FIGURE-DIGITIZED values.
#
# Regenerate with:  python scripts/stage20_digitize_hg_figures.py --pdf <thesis.pdf>
# Source: Samuel Heathcote PhD thesis (University of Bath), 186 pages.
#   pdf_content_sha256 = 276cec6ea449dd130fe6c804afd1e07239d02da022c4a8b12b1303a69371085b
#   (NOT the raw file sha256 -- Bath's Pure repository re-wraps the PDF on every download,
#    so /CreationDate and /ID differ per fetch. See the script docstring.)
# Every row also carries the 200 dpi page_raster_sha256 it was read from, which is the
# strongest reproducibility anchor: it pins the exact pixels.
#
# EVERY VALUE HERE CARRIES DIGITIZATION UNCERTAINTY. Text-sourced (exact) values live in
# text_sourced.csv and are the R2 cross-check anchor for this file.
#
# Figures 5.6 and 5.1 plot C_T/St^2, NOT C_T. `raw_median` is as read off the axis;
# `value` = raw_median * st_squared_factor is the thrust coefficient. For Figs 5.9/5.13
# st_squared_factor is 1 and value == raw_median.
#
# THE CORRELATED / UNCORRELATED SPLIT (this is what licenses a tighter band on the
# flexible-minus-rigid increment than on either absolute value):
#   u_reading_abs -- UNCORRELATED per marker. Half-range of the independent readings.
#                    Survives the difference; RSS the two arms' terms.
#   u_axis_abs    -- CORRELATED within a figure (same axes, same frame, same calibration).
#                    CANCELS in a difference taken between two series on ONE panel.
#   Instrument systematic (5% thrust / 10% efficiency, thesis 2.2.2, in reference.md) is
#   CORRELATED within the instrument -- same gauge, same calibration for both foils -- and
#   largely cancels in the increment too. It is NOT repeated per row here.
#
# Columns:
#   figure,panel            - thesis figure and panel
#   quantity,units          - what `value` is
#   b_over_c                - plate thickness ratio (the series)
#   reynolds,strouhal       - the condition; strouhal is itself digitized (abscissa)
#   reading_1..3,n_readings - the independent readings, in axis units, BEFORE the St^2 fix
#   raw_median              - median of those readings, in axis units
#   reading_half_range      - half-range of those readings, in axis units
#   st_squared_factor       - St^2 for Fig 5.6 (the axis is C_T/St^2), else 1
#   value                   - raw_median * st_squared_factor
#   u_reading_abs,u_axis_abs- the two uncertainty terms, in the units of `value`
#   pdf_page,page_raster_sha256,dpi,tool,tool_version - provenance of the reading
"""


if __name__ == "__main__":
    raise SystemExit(main())
