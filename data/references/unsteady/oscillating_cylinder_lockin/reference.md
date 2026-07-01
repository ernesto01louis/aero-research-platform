# Oscillating cylinder — wake lock-in — reference data

**Case:** `oscillating_cylinder_lockin` — a circular cylinder at Re = 100 forced to
oscillate transversely (pure heave) at amplitude A/D = 0.5, forcing frequency ratio
F = f_e / f_0 = 1.1 (10 % above the natural shedding frequency).
**Tier:** unsteady machinery (Stage-11 moving-body validation) — the flapping-validation
ladder's first moving-mesh rung.

## `strouhal.csv` — locked wake Strouhal number

Columns: `frequency_ratio` (F = f_e/f_0), `strouhal` (the wake response St = f_response D/U).

The reference is **first-principles, not a digitized experimental datum**: inside the
lock-in (synchronization) band the wake abandons its natural shedding frequency and sheds
at the **forcing frequency**, so the response Strouhal equals the forcing Strouhal:

    St_response = F · St_0 = 1.1 × 0.165 = 0.1815

- Natural shedding at Re = 100: St_0 ≈ 0.164–0.166 (Williamson 1989; the platform's own
  Stage-10 forward-regime cylinder GO uses 0.165).
- That F = 1.1 at A/D = 0.5 lies **inside** the 1:1 lock-in band at Re = 100 is established
  by: Placzek, Sigrist & Hamdouni (2009), *Computers & Fluids* 38:80–100 (forced
  oscillations, F ∈ [0.5, 1.5], A/D ∈ [0.25, 1.25]); Koopmann (1967), *J. Fluid Mech.*
  28:501–512 (experimental lock-in band, which widens with amplitude).

**Why F = 1.1 (not F = 1.0):** forcing off-natural makes the test *discriminating*. An
*unlocked* wake would shed near St_0 = 0.165, which is > 3 % from the forcing St = 0.1815,
so the 3 % tolerance passes only on genuine synchronization — not on a wake that ignored the
forcing and shed at its own frequency.

## Uncertainty

`u95_input = 0`: the reference value 0.1815 is exact by the definition of lock-in (response
= forcing) once synchronization is established — there is no measured/digitized quantity.
`u95_statistical` (the sampling error of the FFT-recovered response frequency over the
converged limit cycle) lands at Stage 12 (batch-means / N_eff over the per-cycle samples the
Stage-11 loader exposes).

## Tracking

Git-tracked (a single first-principles scalar — the forward-regime tier's small-data
convention). No DVC needed; no dataset license applies.

## License

The lock-in relation is classical fluid mechanics (public domain). The cited papers are
referenced, not redistributed.
