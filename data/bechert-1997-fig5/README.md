# Bechert 1997 Fig 5 — blade-riblet calibration data

## Source

Bechert, D. W., Bruse, M., Hage, W., van der Hoeven, J. G. T., Hoppe, G.
(1997). *Experiments on drag-reducing surfaces and their optimization
with an adjustable geometry.* Journal of Fluid Mechanics, 338, 59–87.
[DOI: 10.1017/S0022112096004673](https://doi.org/10.1017/S0022112096004673)

The blade-riblet curve at `h/s = 0.5`, `t/s = 0.02` is the calibration
target for Stage 5 of `aero-research-platform`.

## Calibration column

**Use the Bechert experimental column, not Heidarian's CFD column.**

Heidarian, A., Ghassemi, H., Saryazdi, M. G. (2018). *Numerical analysis
of the effects of riblets on drag reduction of a flat plate.* Journal of
Applied Fluid Mechanics, 11(3), 679–688. Table 1 of that paper
cross-references multiple riblet studies; the "Oil Blade Riblet" row
cites Bechert's blade-riblet experimental peak DR ≈ 9.9 %. Heidarian's
own RANS CFD column reports ≈ 11 % for sawtooth/scalloped types — not the
calibration target here.

If our Stage-5 RANS gives ≈ 11 %, the proper read is *"RANS reproduces
Heidarian's CFD shape but overshoots the Bechert experimental peak"* —
escalate to wall-resolved LES per the Stage-5 brief, do **not** re-target
the hypothesis bound (peak 9.9 ± 2 pp at s+ ≈ 17, crossover 27 ± 3).

## File: `digitized.csv`

Two-column CSV: `s_plus`, `dr_percent`.

### Provenance — read this before trusting the values

**These rows are PROVISIONAL anchor points consistent with the published
peak DR and crossover s+ that Bechert reports, NOT a high-resolution
WebPlotDigitizer extraction of the figure.** Specifically:

* The peak DR (9.9 %) and its location (s+ ≈ 17) are pinned to the
  Heidarian 2018 Table 1 secondary-source value attributed to Bechert.
* The crossover (DR = 0) at s+ ≈ 27 is consistent with the standard
  García-Mayoral & Jiménez 2011 ARFM review (Fig 5 of that paper
  redraws Bechert's curve).
* Intermediate points are smooth interpolations matching the canonical
  shape of the blade-riblet DR-vs-s+ curve (rising approximately
  linearly to peak, falling more steeply past it, asymptotic decline
  past crossover).

**Before the Stage-5 PASS/FAIL verdict is signed**, the operator should:

1. Pull the Bechert 1997 Fig 5 PDF.
2. Extract the blade-riblet curve points using
   [WebPlotDigitizer](https://apps.automeris.io/wpd/) 4.x or later.
3. Replace the rows in `digitized.csv` with the extracted (s+, DR%) pairs.
4. Note in `STAGE-5-OUTPUTS.md` which version of the digitization was
   used for the final PASS/FAIL bound.

The provisional values are good enough for the pilot smoke + notebook
plumbing during Stage-5 foundation work; they're not good enough to ship
as the final calibration reference.

## File: `digitized.csv` schema

```
s_plus       float >= 0   wall-unit riblet pitch
dr_percent   float        drag reduction (+ = reduction, - = increase)
```

Lines starting with `#` are comments (numpy.loadtxt / pandas.read_csv
both handle this with `comment='#'`).
