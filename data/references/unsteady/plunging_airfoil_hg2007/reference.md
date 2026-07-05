# Plunging airfoil — Heathcote & Gursul (2007) rigid-foil thrust — reference data

**Case:** `plunging_airfoil_hg2007` — a rigid NACA-0012 in pure plunge (heave), amplitude
h0/c = 0.175, Strouhal St = 2 f h0 / U, Re ≈ 1e4 (laminar 2-D solve).
**Tier:** unsteady machinery (Stage-11 moving-body validation → **Stage-13** transition +
unsteady-airfoil validation is its proper ladder home).

## Source

Heathcote, S. & Gursul, I. (2007), "Flexible Flapping Airfoil Propulsion at Low Reynolds
Numbers," *AIAA Journal* 45(5):1066–1079. https://doi.org/10.2514/1.25431

**Primary figure verified (Stage-12):** the rigid-foil C_T-vs-St values below are read from
**Samuel Heathcote's PhD thesis (University of Bath, open access)** — the origin of the HG2007
AIAA-Journal data — **Fig 2.9** (rigid NACA-0012, h/c = 0.175, Re = 20 000, with the Young &
Lai Navier–Stokes curve overplotted). Thesis file:
`https://purehost.bath.ac.uk/ws/files/188126105/Samuel_Francis_Heathcote_thesis.pdf`.

## Normalization convention (CONFIRMED)

Thesis Eqn 2.1: **C_T = T̄ / (½ ρ U∞² c)** — freestream velocity and chord (exactly the
convention this case assumed). St = 2 f h0 / U∞ (h0 the amplitude). **There is no
normalization mismatch.** Thrust is ~Re-independent over 10 000 ≤ Re ≤ 30 000 (thesis).

## `thrust.csv` — mean thrust coefficient vs Strouhal

Columns: `strouhal` (St = 2 f h0 / U), `thrust_coefficient` (C_T = −C_D, freestream-normalized).

| St  | C_T  | provenance |
|-----|------|-----------|
| 0.2 | 0.20 | Heathcote thesis Fig 2.9, experimental (rigid NACA-0012, Re-indep.) |
| 0.3 | 0.22 | Heathcote thesis Fig 2.9 experimental trend (measured ≈0.22 at St≈0.27; monotone) |
| 0.4 | 0.30 | **beyond the measured range** (figure stops at St≈0.33); CFD-reproduction estimate |

The drag→thrust crossover for the stiff ("essentially rigid") foil is at **St ≈ 0.17** (stated
in the thesis prose). The experimental curve rises monotonically and only reaches St ≈ 0.33
(C_T ≈ 0.22–0.23); **St = 0.4 lies outside the measured range**, so its value here is a
CFD-reproduction estimate, not a measured datum — carry a large `u95_input` (see below).

## ⚠️ CORRECTION (Stage-12) — the previous digitized points were WRONG

The Stage-11 file digitized **St 0.2→0.04, 0.3→0.11, 0.4→0.21**. Primary-source verification
(Stage-12) shows these were **low by ~3–5×**: the rigid-foil experimental C_T is **≈0.16–0.22
over St 0.17–0.33**, not O(0.04–0.21). The most likely origin of the spurious low values is a
confusion with the **propulsive efficiency** η (which peaks ≈0.23 near St≈0.15). Corrected here.

### Consequence for the Stage-11 CONCERN — the solver, not the reference, over-predicts

Stage 11 concluded "the reference is implausibly low, the solver (C_T≈0.96) is right" — but
that rested on **inviscid Garrick ∝St² theory**, which the thesis explicitly shows over-predicts
because **viscous drag offsets thrust at low Re**. With the corrected reference the ordering is:

> experiment (~0.2–0.3) < 2-D RANS CFD (Camacho et al. 2020, ~0.56–0.67 at St=0.4) < our 2-D
> laminar solve (~0.96)

— a monotonic **over-prediction as fidelity drops**. So the plunging foil is a genuine
**over-prediction CONCERN** (our 2-D laminar C_T is ~2–4× the experiment), **not** a
reference error. Per Stage-10/12 discipline the tolerance is **not relaxed**; the case is
reported `validated` (not `thesis-grade`, failing anchor) and the root-cause (2-D-vs-3-D /
laminar-vs-transitional over-prediction; re-anchor at a pre-bifurcation St 0.2–0.3) is a
**Stage-13** item (`docs/handoff-bundle/STAGE-13-transition-and-unsteady-airfoil.md`).

## `u95_input` (digitization + model-form uncertainty)

The dominant term is the **model-form gap** (2-D laminar Re=1e4 vs 3-D transitional water-tunnel
experiment on a teardrop, not NACA-0012) plus the beyond-measured-range extrapolation at St=0.4.
Carry **u95_input ≈ 40 %** (fractional) on the St=0.4 reference — treat C_T(St=0.4) ≈ 0.30 ± 0.30
(spanning the experiment-to-RANS band), pending a proper Stage-13 re-anchor.

## Cross-references (CFD reproductions, same regime + normalization)

- Camacho, Neves, Silva & Barata (2020), *Energies* 13(8):1861 (open access) — rigid plunging
  NACA-0012, explicit C_T = −mean(C_D) normalization; fitted Ct(St) gives ≈0.56–0.67 at St=0.4.
  https://doi.org/10.3390/en13081861
- Young & Lai (2004), *AIAA J* 42(10):2042 — the NS curve overplotted in Heathcote Fig 2.9.

## Tracking

Git-tracked scalar table (~100 bytes; forward-regime tier convention). A future *large* raw HG
dataset (full force histories / PIV) would move to DVC under `-r aero-nfs`.

## License

Experimental data published in Heathcote & Gursul (2007) / Heathcote PhD thesis; cited under
fair use. Digitized/estimated points carry no additional dataset license.
