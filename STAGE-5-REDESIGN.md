# STAGE-5 REDESIGN — Developing-BL Plate → Streamwise-Periodic Channel

**Date:** 2026-05-15
**Status:** Decision record. Supersedes the domain choice in
`STAGE-5-bechert-replication.md` (the original brief).
**Author:** Claude Opus 4.7, with operator authorization to "choose
what's best for the future of the project even if it takes longer."

## Summary

Stage 5 pivots from a **developing-boundary-layer flat plate** to a
**streamwise-periodic channel**. The riblet representation, the Bechert
1997 calibration target, and the s+ sweep are all unchanged. Only the
flow domain changes — and it changes to what the riblet-CFD literature
the brief itself cites actually uses.

## Why — four pilot failures, one root cause

| Pilot | Date | Failure |
|---|---|---|
| v1 | 2026-05-14 | snappy + STL + addLayers — 28k negative-volume cells |
| v2 | 2026-05-15 | same, after addLayers retargeted to bottomWall |
| v3 | 2026-05-15 | same, after grading + refinement-level tuning |
| v4 | 2026-05-15 | structured multi-block blockMesh — checkMesh fails ALL 2.86M cells on small determinant; max aspect ratio 4720; simpleFoam FPEs at setup, 0 iterations |

Pilots v1–v3 were snappyHexMesh problems. v4 switched to a structured
multi-block blockMesh and **still** failed — which isolated the true
root cause:

**A developing-BL flat plate cannot resolve micro-scale riblets.**

The riblet pitch at s+=17 is `s = 3.2e-4` chord. A developing BL needs
a streamwise plate length of O(chords). Resolving a 3.2e-4-pitch riblet
requires spanwise cells ~2e-5 chord. Matching that resolution
streamwise over a 4-chord plate is billions of cells — infeasible — so
streamwise cells are necessarily ~0.01 chord, a **500–4700:1 aspect
ratio**. checkMesh flags every cell; the SIMPLE solver's FPE-trap fires
during cell-geometry setup. No block topology, grading, or
refinement-level tuning can fix a scale mismatch of four orders of
magnitude between the riblet pitch and the plate length.

## The fix — streamwise-periodic channel

This is the canonical riblet-drag-reduction CFD setup. Every reference
in the original brief uses it:

* **García-Mayoral & Jiménez 2011** ARFM 43:115–141 — the canonical
  review; riblet DNS in a periodic channel.
* **Mele & Tognaccini 2022** MDPI Fluids 7(7):249 — the RANS-riblet
  practice paper the brief cites for the SST approach; periodic domain.
* Bechert's own analysis frames riblet performance in wall units
  (s+, the protrusion-height concept) — inherently a near-wall,
  periodic-domain picture, not a developing-BL one.

### Domain

Normalize on the channel half-height δ = 1, friction velocity
u_τ = 1, kinematic viscosity ν = 1/Re_τ.

```
x ∈ [0, Lx]   streamwise   — cyclic (periodic)
y ∈ [0, Ly]   spanwise     — cyclic (periodic), Ly = n_pitches · s
z ∈ [0, δ]    wall-normal  — riblet wall at z=0, symmetryPlane at z=δ
```

Because the domain is normalized on δ, the riblet pitch is

```
s = s+ / Re_τ          (s+ = s · u_τ / ν = s · Re_τ)
```

At Re_τ = 180, s+=17 → **s ≈ 0.094 δ** — a *sizeable* fraction of the
domain, not a microscopic 3e-4. Cell sizes become comparable in all
three directions: **isotropic hexes, no aspect-ratio pathology,
~1M cells total.** The scale mismatch is gone because there is no
macroscopic plate length.

### Forcing

A constant mean pressure gradient drives the flow — OpenFOAM
`fvOptions` `meanVelocityForce` maintaining a target bulk velocity
(the `channel395` tutorial pattern). The applied pressure gradient is
the integral wall drag.

### Drag-reduction measurement

At matched bulk velocity U_b, the riblet case requires a smaller mean
pressure gradient than the smooth baseline:

```
DR% = (dpdx_smooth − dpdx_riblet) / dpdx_smooth × 100
```

`meanVelocityForce` reports `dpdx` each iteration. The paired
riblet/smooth sub-runs at each s+ give a self-consistent DR fraction —
same as the original plan, just measured from the pressure gradient
instead of a wall-shear surface integral.

### Re_τ choice

Re_τ = 180 is the canonical low-Reynolds channel (Kim, Moin & Moser
1987; the OpenFOAM channel tutorial). Bechert blade-riblet experiments
sit at higher Re but the riblet DR curve collapses in wall units (s+),
so Re_τ = 180 is an accepted screening value. If the DR curve shape is
right but the magnitude is off, Re_τ is the first knob — but per the
brief, do **not** move the hypothesis bound; document and escalate.

## What carries over unchanged

* `geometry/riblet.py` — blade profile + s+/s mapping. The
  `s_from_s_plus` helper now takes `u_tau = 1`, `nu = 1/Re_τ`.
* The Bechert 1997 Fig 5 calibration CSV (`data/bechert-1997-fig5/`).
* k-omega SST turbulence model (Mele & Tognaccini practice).
* The 8-block-per-period / 3-z-band structured topology — reused
  almost verbatim; only the x faces change from inlet/outlet patches
  to cyclic, and the z=δ top becomes a symmetryPlane.
* The paired riblet + smooth sweep (9 s+ × 2 = 18 sub-runs).
* The orchestrator → SSH → OpenFOAM pipeline (proven; not in question).

## What changes

* `meshing/periodic_riblet_strip.py` — `FlatPlateRibletMeshSpec` gains
  `re_tau`; pitch is derived from `s+/Re_τ`; x faces cyclic; z=δ top
  symmetryPlane; Lx is a fixed multiple of δ (≈3), independent of pitch.
* `cfd/templates/flat-plate-riblet-simpleFoam/` — `0/*` BCs: cyclic x,
  symmetryPlane top; new `constant/fvOptions` with `meanVelocityForce`;
  `potentialFoam` init dropped (the momentum source drives the flow —
  no Kutta condition, no cold-start trap).
* The campaign YAMLs — recipe drops `potentialFoam`; mesh recipe is
  `blockMesh → checkMesh → decomposePar → simpleFoam`.

## Process change

Mesh development moves to **direct SSH iteration** (`blockMesh` +
`checkMesh`, ~1 min each) instead of full orchestrator campaigns
(~45 min each). The orchestrator pilot runs only once the mesh is
verified clean. Four 45-minute campaign cycles were spent discovering
mesh failures that a 1-minute `checkMesh` would have caught.

## Honest risk

Even with a correct isotropic mesh, **RANS k-omega SST resolving
riblets may not reproduce the Bechert DR magnitude.** Riblet DR is
partly a turbulence-modification effect that RANS models capture
imperfectly. Mele & Tognaccini 2022 argue SST gets the curve *shape*;
the *magnitude* is less certain. The brief pre-registered the
escalation: "if RANS misses peak by >2 pp, escalate to wall-resolved
LES on a SkyPilot A100 burst." A RANS miss is therefore a documented,
expected outcome — not a Stage-5 failure.
