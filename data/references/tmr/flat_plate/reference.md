# TMR Turbulent Flat Plate — Reference Data

**Case:** `flat_plate_te` — zero-pressure-gradient turbulent flat plate.
**Conditions:** Re_L = 5e6 (Reynolds based on plate length L = 2.0), M = 0.2,
fully turbulent from the leading edge, k-omega SST.
**Geometry source:** NASA Turbulence Modeling Resource —
<https://turbmodels.larc.nasa.gov/flatplate.html>

## `cf.csv` — local skin-friction coefficient vs. x

Columns: `x` (streamwise position, plate runs 0 -> 2.0), `cf` (local Cf).

The reference Cf is the **White turbulent flat-plate correlation**

    Cf(x) = 0.455 / [ ln( 0.06 * Re_x ) ]^2 ,   Re_x = Re_L * x / L

(F. M. White, *Viscous Fluid Flow*, 3rd ed., McGraw-Hill 2006, Eq. 6-78).

This is the canonical analytic verification target for a turbulent flat
plate: the case exists precisely to confirm a turbulence model reproduces the
known flat-plate skin-friction law. NASA TMR's own SA and SST results for this
case agree with this correlation to within ~2-3%; the Stage-05 pointwise
tolerance is 5% (ADR-005).

> **Note (Stage 05):** the build host had no outbound network access, so the
> exact TMR CFD verification files could not be mirrored. The White
> correlation is used as a genuine, citable analytic reference. Replacing it
> with the TMR-published CFL3D/FUN3D Cf distribution is a documented
> open item — see the Stage-05 handoff.

## License

The White correlation is a published textbook formula. The NASA TMR data
itself is a US Government work and in the public domain (no NASA endorsement
implied).
