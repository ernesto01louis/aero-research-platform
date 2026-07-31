# Chordwise-flexible plunging airfoil — Heathcote & Gursul (2007) — reference data

**Case:** `hg2007_flexible_foil` — a chordwise-flexible teardrop/flat-plate airfoil in pure
plunge, `h = a_LE/c = 0.175`, `St = 2 f a / U₀`, `Re = 9 000 / 18 000 / 27 000`, water tunnel.
**Tier:** flapping (flagship) — the **flexible** row of
`.claude/rules/flapping-validation-ladder.md`. Stage 20's experiment-anchored gate (Hard Rule 15).

> **This is NOT the same experiment as the platform's existing HG reference.**
> `data/references/unsteady/plunging_airfoil_hg2007/` holds *rigid NACA-0012* thrust read from
> thesis **Fig 2.9**, used by the Stage-11/13 single-solver plunging case. This directory holds
> the **chordwise-flexibility** experiment of thesis **Chapter 5** — a different airfoil (teardrop
> + steel plate, 90 mm chord), different figures, and the source of the AIAA-J 2007 paper.
> Nor is it Heathcote, Wang & Gursul (2008), which is *spanwise* flexibility on a NACA-0012 wing
> of 100 mm chord and 300 mm span. Three experiments, one author, easily conflated.

## Source

Heathcote, S. & Gursul, I. (2007), "Flexible Flapping Airfoil Propulsion at Low Reynolds
Numbers," *AIAA Journal* 45(5):1066–1079. https://doi.org/10.2514/1.25431 — **paywalled**.

Values here come from the open-access origin of that data, **Samuel Heathcote's PhD thesis**
(University of Bath), Chapter 5 "Effect of chordwise flexibility at low Reynolds numbers", and
Chapter 2 "Experimental apparatus and methods".

- Retrieved 2026-07-30 from
  `https://purehost.bath.ac.uk/ws/files/188126105/Samuel_Francis_Heathcote_thesis.pdf`
- **sha256 `fdee2ce497ab39af65aff769f04d858e4a2a3cf10adacc0c1351760f3f74fe10`**, 12 MB, 186 pages
- The PDF is **not committed** (licence); only its digest, retrieval URL and date are recorded.

Every value below is marked **text-sourced** (quoted from the prose, exact) or
**figure-digitized** (read off a rasterised plot, carries digitization uncertainty). The
distinction is load-bearing — see the correction note at the end of this file.

## Benchmark setup (text-sourced, thesis §2.1.6)

| quantity | value |
|---|---|
| span | 300 mm |
| chord `c` | 90 mm |
| leading-edge element | solid **aluminium** teardrop, chordwise + streamwise stiff, 30 mm |
| trailing-edge element | **Carbon-Manganese steel** plate, **length 60 mm**, `E = 2.05 × 10¹¹ N/m²` |
| plate thicknesses tested | 2, 3, 4, 5, 6, 8, 15 thousandths of an inch |
| ⇒ thickness ratios `b/c` | 0.56, 0.85, 1.13, 1.41, 1.69, 2.23, 4.23 (× 10⁻³) |
| plunge amplitude | `h = a_LE/c = 0.175`, pure heave of the **leading edge** |
| Reynolds numbers | 9 000, 18 000, 27 000 |
| medium | water tunnel |

Relative bending stiffness `λ/λ₀` (thesis Table 2-1), `λ₀` being the thinnest plate:

| `b/c` × 10³ | 0.56 | 0.84 | 1.12 | 1.41 | 1.69 | 2.25 | 4.23 |
|---|---|---|---|---|---|---|---|
| `λ/λ₀` | 1 | 3.4 | 8 | 15.6 | 27 | 64 | **422** |

### Airfoil outline (thesis Fig 2.5 — a *scale* diagram, measured)

Fig 2.5 is captioned "Scale diagram of the chord-wise flexible airfoil" and carries **no dimension
labels**, so the outline below is **measured off the rendered figure**, not text-sourced. It is
recorded here because the Stage-20 CalculiX solid mesh needs the real wetted shape — preCICE maps
between the fluid and solid *surfaces*, so an invented outline would be an invented experiment.

| quantity | value | how |
|---|---|---|
| teardrop LE length | **30 mm** (0.333c) | **exact** — 90 mm chord − 60 mm plate, both text-sourced |
| teardrop max thickness | **≈ 9.6 mm** (≈ 0.107c) | measured off Fig 2.5 at 200 dpi |
| teardrop max-thickness location | ≈ 8-9 mm from the nose (≈ 0.1c) | measured |
| plate length | **60 mm** (0.667c) | text-sourced (§2.1.6) |
| plate thickness | `b = (b/c) × 90 mm`, e.g. **0.38 mm** for `b/c = 4.23e-3` | text-sourced |

**The scale reading is self-checking.** Measuring the teardrop's length off the figure gives
≈29.5 mm against the 30 mm the text implies arithmetically — a 1.7 % agreement on a quantity known
two independent ways. That is what makes the *unlabelled* thickness measurement trustworthy at
roughly the same level; carry **≈5 % on the teardrop thickness** and treat the outline as a declared
approximation of a shape the thesis draws but does not tabulate.

The LE is "machined in two halves, and the plate clamped between the two" (Fig 2.5 caption), so the
plate is built in at `x = 30 mm` and the structural root is there — not at the nose.

**The pitching motion is not prescribed — it arises from the flexibility.** The leading edge is
driven in pure heave; the plate's inertial and hydrodynamic loading produces the pitch. That is
why Stage 20 drives the plunge from the *solid* leading edge and lets the coupling produce the
deformation, rather than prescribing a pitch schedule.

**`b/c = 4.23 × 10⁻³` is the rigid control**: the thesis calls it "essentially rigid" and
measures a pitch amplitude **below 2°** even at the highest oscillation frequency (§2.1.6), and
"less than 1 degree" at Re = 9000, St = 0.56 (§5.3.1). It is a *measured* case, not an idealisation
— which is what lets both ends of the flexible-minus-rigid increment carry an experimental anchor.

## Normalization convention (CONFIRMED — thesis Nomenclature, p. VIII)

| symbol | thesis definition | platform equivalent |
|---|---|---|
| `Ct` | thrust coefficient **defined on the freestream velocity** | `C_T = T̄ / (½ ρ U₀² c)` — `propulsive_metrics.thrust_coefficient` |
| `cP` | power-input coefficient | `C_P = P̄ / (½ ρ U₀³ c)` — `propulsive_metrics.power_coefficient` |
| `η` | propulsive efficiency, **`Ct/Cp`** | `propulsive_metrics.propulsive_efficiency` |
| `St` | `2 f a / U₀` | `propulsive_metrics.strouhal` |
| `h` | `a_LE / c` | plunge amplitude / chord |
| `K` | thin-plate bending stiffness `E b³ / 12` | — |

**There is no normalization mismatch**: `η = C_T / C_P` is exactly what
[`aero/postprocess/efficiency.py:100-109`](../../../../aero/postprocess/efficiency.py) computes,
and `C_T` is freestream-normalised in both. Confirmed against the thesis nomenclature table, not
inferred.

> ⚠️ **One real trap, recorded before it bites anyone.** Figures 5.6 and 5.1 plot **`C_T/St²`**,
> not `C_T`, even though the caption of Figure 5.6 reads "Thrust coefficient as a function of
> Strouhal number". Any value read off those figures must be multiplied by `St²`. At St = 0.3 that
> is a factor of **11.1** — the same order as the 3–5× error that the *other* HG reference file in
> this repo had to correct in Stage 12.

## Which figures carry the gated quantities

| quantity | figure | axes | Re |
|---|---|---|---|
| thrust | **Fig 5.6** (a/b/c), thesis pp. 122-123 | `C_T/St²` vs `St`, five `b/c` | 9 000 / 18 000 / 27 000 |
| efficiency | **Fig 5.9** (a/b/c), thesis pp. 126-127 | `η` vs `St`, five `b/c` | 9 000 / 18 000 / 27 000 |
| structural response | **Fig 5.13** (a/b), thesis p. 131 | pitch amplitude [deg] and pitch phase [deg] vs `St`, four `b/c` | 9 000 |
| thrust vs stiffness | Fig 5.1, thesis pp. 117-119 | `C_T/St²` vs `b/c` | all three |

Figures 5.6 and 5.9 plot the five thicknesses `b/c ∈ {0.56, 0.85, 1.13, 1.41, 4.23} × 10⁻³`;
Fig 5.13 omits the rigid `4.23 × 10⁻³` (its pitch amplitude is too small to measure a phase for).

## Text-sourced values (exact — quoted from the prose, no digitization)

`text_sourced.csv` carries these. They are the anchor for the R-family cross-check: any
digitization of Figures 5.6/5.9/5.13 must reproduce them, or the digitization is wrong.

| quantity | value | where |
|---|---|---|
| drag→thrust crossover, rigid `b/c = 4.23e-3` | **St = 0.17**, at *all three* Reynolds numbers | §5.3.2 |
| drag→thrust crossover, flexible foils | earlier than St = 0.17 | §5.3.2 |
| `C_T` of `b/c = 0.56e-3` at Re = 27 000, high St | **0.04** | §5.3.1 |
| pitch amplitude, `b/c = 4.23e-3`, Re = 9000, St = 0.56 | **< 1°** ("essentially rigid") | §5.3.1 |
| pitch amplitude, intermediate foil, Re = 9000, St = 0.56 | **6°** | §5.3.1 |
| pitch amplitude, `b/c = 0.56e-3`, Re = 9000, St = 0.56 | **17°** | §5.3.1 |
| pitch amplitude, `b/c = 4.23e-3`, any Re, highest frequency | **< 2°** | §2.1.6 |
| peak efficiency occurs at | St = 0.29, pitch phase 95-100° | §5.1 |
| thrust peaks at pitch phase | 110-120° | §5.1 |
| `C_d` of the validation NACA-0012, St = 0.19, Re = 20 000 | 0.028 ± 0.005 | §2.2.3 |
| Reynolds sensitivity over 10 000 < Re < 30 000 | **small**; St is the key parameter | §2.2.3 |

## `u95_input` — and why most of it is *measured*, not guessed

The thesis states its own instrument uncertainty (§2.2.2), which is far better evidence than a
digitization estimate:

- **thrust: ≈ 5 %** — "the combined error in the strain gauge readings is approximately 5 %",
  built from bending-moment insensitivity (< 0.5 %), cross-axis coupling (2 %), z-torque (1 %) and
  linearity (1 %); temperature negligible.
- **efficiency: ≈ 10 %** — "since the efficiency calculations depend on the gauge readings in both
  directions, the error in the efficiency data is approximately 10 %."
- PIV momentum flux: < 10 % (not gated here).

Digitization uncertainty adds to that in quadrature for any figure-read value, and is recorded
per-point in `digitization.csv` with the tool and the three independent readings it came from.

**Carry, for reportable composition:**

| gated quantity | `u95_input` (fractional) | basis |
|---|---|---|
| absolute `C_T` | `RSS(0.05, digitization)` | measured (thesis §2.2.2) + digitization |
| absolute `η` | `RSS(0.10, digitization)` | measured (thesis §2.2.2) + digitization |
| **increment** `ΔC_T`, `Δη` | `RSS(reading_flex, reading_rigid)` only | see below |

**The increment's uncertainty is smaller than the absolutes', and that is not a trick.** Both
points of an increment are read off the *same figure with the same axes*, so the
**axis-calibration** term is common to both and cancels in the difference; only the independent
per-marker **reading** term survives. The instrument's systematic component largely cancels too,
since both foils were measured on the same gauge with the same calibration. The correlated /
uncorrelated split is recorded explicitly in `digitization.csv` — it is what justifies a tighter
band on the increment than on the absolute value, and it must be shown, not asserted.

## Tracking

Small scalar tables are git-tracked directly (forward-regime tier convention). The source PDF is
not committed. No DVC artifact yet — if full digitized traces are added later they move to DVC
with `.dvc` + `.sha256` sidecars, per the Stage-18/19 pattern.

## Status of the figure digitization

**Text-sourced values: complete and committed.** Figure digitization of 5.6 / 5.9 / 5.13 is the
remaining acquisition step, and it is deliberately not being rushed: the *other* HG reference in
this repo was wrong by 3–5× for a whole stage because someone digitized the wrong curve (thrust
confused with efficiency, thesis Fig 2.9 vs the efficiency figure). The method is fixed in advance
in `scripts/stage20_acquire_hg_reference.py`:

1. render the figure page at 200 dpi (reproducible from the recorded PDF digest);
2. read each required marker **three times independently**, recording all three;
3. reading term = half-range of the three; axis-calibration term from the tick spacing;
4. **multiply Fig 5.6 values by `St²`** — the axis is `C_T/St²`;
5. cross-check against every applicable text-sourced value above (the R2 gate) and **STOP** on
   disagreement rather than preferring whichever is closer.

## License

Thesis © Samuel Heathcote / University of Bath, open-access via the Bath research portal.
Published scientific values are reproduced here for verification and validation under fair use,
with full citation; the source PDF itself is not redistributed.

## Cross-references

- ADR-016 (why the solid solver is CalculiX, and why this claim is separate from Stage 19's)
- ADR-022 (the 2-D-vs-3-D model-form NO-GO measured on the *rigid NACA-0012* HG anchor)
- ADR-039 (the pre-registered Stage-20 gate block — sizes its bands from this file)
- `data/references/unsteady/plunging_airfoil_hg2007/reference.md` (the *other*, rigid experiment)
- `.claude/rules/flapping-validation-ladder.md` (the flexible flapping row this fills)
