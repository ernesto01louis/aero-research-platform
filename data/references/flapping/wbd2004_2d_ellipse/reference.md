# Rigid 2-D flapping wing in hover — Wang, Birch & Dickinson (2004) — reference data

**Case:** `flapping_wing_wbd2004` — a thin elliptic wing in prescribed 2-D flapping hover
(sinusoidal translation + sinusoidal pitch), validated against the robotic-wing (Robofly)
experiment. **Tier:** flapping flagship (Stage 14; `.claude/rules/flapping-validation-ladder.md`).

## Source

Wang, Z. Jane; Birch, James M.; Dickinson, Michael H. (2004), "Unsteady forces and flows in
low Reynolds number hovering flight: two-dimensional computations vs robotic wing experiments,"
*Journal of Experimental Biology* 207(3):449–460. https://doi.org/10.1242/jeb.00739

**Full text (open access):** the corresponding author hosts the PDF openly at
`https://dragonfly.tam.cornell.edu/publications/2004_JEB_Wang_Birch_Dickinson.pdf`. All values
below are **text-sourced** from the paper's Results (pp. 454–455) and equations — **not**
figure-digitized. The time-resolved traces (Figs 2–4) are figure-locked and treated as a
diagnostic overlay, not the gated anchor.

Secondary/context: Dickinson, Lehmann & Sane (1999), *Science* 284:1954–1960 (the
advanced > symmetrical > delayed rotation-timing lift-enhancement result; Re ≈ 136). Its
per-timing mean-lift numbers are paywalled/figure-locked and are **not** used as an anchor;
WBD 2004's own 3-D experimental column supersedes them for this case.

## Kinematics (WBD Eqs 10–11, fully specified)

- Stroke (translation):   `x(t) = (A0/2) cos(2 pi f t)` — sinusoidal; A0 = peak-to-peak stroke.
- Pitch (rotation):        `alpha(t) = alpha0 + beta sin(2 pi f t + phi)`.
- Fixed: `alpha0 = 90 deg`, `beta = 45 deg`. Baseline stroke `A0/c = 2.8` (= 60 deg robot stroke).
- Rotation timing `phi`: **advanced +45 deg**, **symmetrical 0**, **delayed −45 deg**
  (reversal geometric AoA 45 / 90 / 135 deg respectively).
- Reynolds number: `Re = U_max c / nu = pi f A0 c / nu`, `U_max = pi f A0` the max wing speed.
  Baseline `A0/c = 2.8 -> Re = 75`.
- 2-D section: a **thin ellipse** (the paper leaves the thickness ratio free — their
  normalisation removes wing-thickness dependence; we use `thickness_ratio = 0.125`).

The platform's implementation (`aero/adapters/openfoam/motion.py::FlappingMotionSpec`,
`aero/postprocess/flapping_kinematics.py`) reproduces these equations exactly, with a C1
startup ramp over the first cycles (the post-ramp limit cycle is ramp-independent).

## Normalization convention (CONFIRMED — reproduced exactly)

WBD normalise the instantaneous force by the **peak quasi-steady force** over the cycle (their
Eqs 14–15, a 2-D fit), NOT by a conventional `0.5 rho U^2 S`:

    C_L,qs(alpha) = 1.2 sin(2 alpha)            C_D,qs(alpha) = 1.4 - cos(2 alpha)
    N_L = max_t[ 0.5 rho c u(t)^2 C_L,qs(alpha(t)) ]     (N_D analogous)
    C_L(t) = F_lift(t) / N_L                             C_D(t) = F_drag(t) / N_D

with `u(t)` the instantaneous wing speed. This is implemented verbatim in
`aero/postprocess/flapping_forces.py`, so the platform's coefficients compare 1:1 with the
paper. (It is a fixed constant rescale of the conventional coefficient built on `U_max`, which
the loader also reports as a diagnostic.) Lift = the vertical force (perpendicular to the
horizontal stroke); drag = the force opposing the instantaneous wing motion.

## `mean_coefficients.csv` — stroke-averaged coefficients (baseline A0/c = 2.8)

Columns: `rotation_timing`, `pitch_phase_deg`, `mean_cl_experiment`, `mean_cl_computation_2d`,
`mean_cd_experiment`, `mean_cd_computation_2d`. Values from WBD Results (pp. 454–455):

| Timing | phi (deg) | C_L exp (3-D) | C_L comp (2-D) | C_D exp | C_D comp |
|--------|-----------|---------------|----------------|---------|----------|
| delayed     | −45 | 0.38 | 0.19 | 1.10 | 1.21 |
| symmetrical |   0 | 0.86 | 0.82 | 1.34 | 1.44 |
| advanced    | +45 | 0.93 | 1.10 | 1.28 | 1.36 |

**The anchor is the experiment column** (`mean_cl_experiment`; VALIDATE-AGAINST-EXPERIMENT,
Hard Rule 15). The 2-D computation column is corroboration context (WBD's own 2-D result), not
the anchor.

## Which quantity is gated (and why)

- **GATED:** the **symmetrical**-rotation stroke-averaged mean C_L vs the experiment (0.86).
  2-D reproduces this well (WBD's own 2-D: 0.82, −5 %); it is the honest, robust anchor.
- **NOT gated (diagnostic):** the **delayed** timing — WBD's own 2-D under-predicts the delayed
  mean lift ~2× with a phase shift (a documented 2-D-vs-3-D limitation, p. 454–458), so gating it
  would invite dishonest tolerance relaxation. The **advanced** timing, the advanced > symmetrical
  > delayed **ordering**, mean drag, and the phase-resolved lift/drag traces are all reported as
  corroborating evidence, not pass/fail gates.

## `u95_input` (digitization + model-form uncertainty)

The mean coefficients are **text-sourced** (running text, not digitized), so digitization
uncertainty is ~0. The residual input uncertainty is the reference's own experimental scatter
and the reporting precision (2 significant figures). Carry **`u95_input ≈ 5 %`** (fractional) on
the gated symmetrical mean C_L — the WBD-reported precision plus robotic-wing measurement
scatter. (This is distinct from the *model-form* 2-D-vs-3-D gap, which is captured by the
pre-registered acceptance band, not by `u95_input`.)

## Cross-references

- Dickinson, Lehmann & Sane (1999), *Science* 284:1954 — the rotation-timing lift result
  (context only; not an anchor here).
- Wang (2000), *J Fluid Mech* 410 — the 2-D quasi-steady coefficient fits (Eqs 14–15 origin).

## Tracking

Git-tracked scalar table (~0.3 KB; forward-regime tier convention). A future digitized
force-trace CSV (Figs 2–4) would be a small git-tracked table too; a full PIV/force-history
dataset would move to DVC under `-r aero-nas`.

## License

Experimental + computational data published in Wang, Birch & Dickinson (2004), cited under fair
use. Text-sourced numeric values carry no additional dataset license.
