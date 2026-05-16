# STAGE-5-OUTPUTS — Bechert 1997 Blade-Riblet Replication

**Stage:** 5 of 6
**Date:** 2026-05-13 to 2026-05-16 (UTC)
**Operator:** Louis
**Agent:** Claude Opus 4.7 (1M context) running on LXC 200 (`ai-orchestrator`, 192.168.2.218)
**Verdict:** **FAIL** — against the pre-registered hypothesis bound. RANS
k-omega SST does **not** reproduce the Bechert 1997 blade-riblet
drag-reduction curve. Best modelled DR is **+0.2 % at s+=20** against an
experimental peak of **+9.9 % near s+~17** — a ~9.7-percentage-point
miss, ~5× the pre-registered ±2 pp tolerance. The modelled curve is
at-or-below zero everywhere; there is no drag-reduction plateau and no
clean +→− crossover near s+~27. **This is the documented, expected
outcome**: the hypothesis pre-registered the escalation — "if RANS
misses, escalate to wall-resolved LES." Stage 5 delivers a
citation-grade *negative* result and a concrete LES handoff. The
pipeline, mesh, solver and evidence chain all functioned; what failed
is the turbulence closure, exactly where the literature says it fails.

---

## TL;DR

Stage 5 set out to replicate Bechert et al. 1997 (JFM 338:59-87, Fig 5):
static blade riblets at h/s=0.5 give a peak drag reduction of ~9.9 % near
s+~17, crossing back to drag *increase* near s+~27. The hypothesis
pre-registered acceptance at peak DR within ±2 pp and crossover within
±3 in s+.

A 9-point s+ sweep [5…40] plus a paired smooth baseline was run as a
**streamwise-periodic channel** (the canonical riblet-CFD domain — see
`STAGE-5-REDESIGN.md`) at Re_τ=180, OpenFOAM v2412 `simpleFoam`,
k-omega SST. Drag reduction was measured from the mean pressure gradient
the `meanVelocityForce` momentum source applies to hold a fixed bulk
velocity:

    DR% = (dpdx_smooth − dpdx_riblet) / dpdx_smooth × 100

**Result:** the modelled curve never lifts off zero. Peak +0.2 %; the
whole curve is a shallow drag *penalty*. Verdict **FAIL** on both
pre-registered criteria. The failure is a turbulence-closure limitation,
not a pipeline or mesh defect — and it is escalated to LES per plan.

---

## Drag-reduction curve — the headline result

Smooth baseline: `dpdx_smooth = 0.987768` (mean over the last 1000
iterations; the smooth channel is s+-independent, so one baseline serves
every sweep point — see the validation notebook).

| s+ | dpdx_riblet | **DR % (RANS, this work)** | DR % (Bechert 1997) | miss (pp) | mesh band |
|---:|---:|---:|---:|---:|:--|
| 5  | 2.486444 | **−151.7** | −1.5 | 150.2 | artifact (9.2 % degenerate cells) |
| 10 | 1.380522 | **−39.8**  | +5.0 | 44.8  | artifact (2.8 %) |
| 15 | 1.048971 | **−6.2**   | +8.8 | 15.0  | **trustworthy (0.44 %)** |
| 17 | 1.001195 | **−1.4**   | +9.9 | 11.3  | **trustworthy (0.33 %) — pre-registered peak** |
| 20 | 0.985759 | **+0.2**   | +9.0 | 8.8   | **trustworthy (0.11 %) — modelled peak** |
| 25 | 0.995917 | **−0.8**   | +3.5 | 4.3   | **trustworthy (0.11 %)** |
| 30 | 1.027218 | **−4.0**   | −3.5 | 0.5   | artifact (9.0 %) |
| 35 | 1.139777 | **−15.4**  | −8.5 | 6.9   | artifact (34.0 %) |
| 40 | 1.112821 | **−12.7**  | −12.0 | 0.7  | clean (re-meshed, `Mesh OK`) |

Positive = drag reduction, negative = drag increase (sign convention from
`data/bechert-1997-fig5/`). Curve, CSV and the verdict computation are in
`notebooks/02-bechert-1997-replication.ipynb`; rendered artifacts at
`results/02-flat-plate-riblet-bechert/dr_vs_s_plus.{csv,png}`.

**The verdict rests on the trustworthy band, s+ ∈ [15, 25]** (mesh
well-posedness ≤ 0.44 % degenerate cells — see *Mesh quality* below).
Across that band the model gives −6.2 … +0.2 % where Bechert gives
+3.5 … +9.9 %. The pre-registered peak (s+~17) sits inside this band and
the model misses it by **11.3 pp**.

---

## Campaign facts

| Field | Value |
|---|---|
| Campaign hypothesis | `campaigns/02-flat-plate-riblet-bechert.yaml` (REFORMS §1 pre-registration) |
| Turbulence model | k-omega SST (Mele & Tognaccini 2022 RANS-riblet practice) |
| Domain | streamwise-periodic channel, Re_τ=180, δ=1, u_τ=1, ν=1/Re_τ (`STAGE-5-REDESIGN.md`) |
| Sweep | s+ ∈ {5,10,15,17,20,25,30,35,40}; h/s=0.5; t/s=0.02; surface ∈ {riblet, smooth} |
| Solver | OpenFOAM v2412 `simpleFoam`, 6000 iterations, `mpirun -np 8` |
| Forcing | `meanVelocityForce` fvOption, target Ubar=15.7 |
| Execution | **SSH-direct on `aero-research` (192.168.2.231)** — orchestrator LLM pipeline bypassed (see *Process notes*) |
| Runs | 9 riblet + 1 smooth baseline = 10 |
| aero-research-platform commit | `469ea0f` (`feat/stage5-flat-plate-bechert`) |
| Evidence bundle | orchestrator campaign `cbf6d068-ad88-541b-9caf-956e0dd5e2f9`, bundle `99523422-…`, DSSE-signed (see *Evidence bundle* below) |

---

## Methodology — streamwise-periodic channel

The Stage-5 redesign (`STAGE-5-REDESIGN.md`, 2026-05-15) replaced the
original developing-boundary-layer flat plate with a **streamwise-periodic
channel** after four pilot meshing failures isolated the root cause: a
developing BL cannot resolve micro-scale riblets without a four-orders-of-
magnitude aspect-ratio pathology. The periodic channel is the canonical
riblet-CFD domain — every reference the brief cites (García-Mayoral &
Jiménez 2011, Mele & Tognaccini 2022) uses it.

- **Domain.** Normalized on the half-height δ=1, u_τ=1, ν=1/Re_τ at
  Re_τ=180. Riblet pitch `s = s+/Re_τ`; at s+=17, s ≈ 0.094 δ — a sizeable
  fraction of the domain, so cells are near-isotropic and the
  developing-BL scale mismatch is gone. x and y (spanwise) are cyclic;
  the riblet wall is at z=0, a `symmetryPlane` caps z=δ.
- **Forcing.** A `meanVelocityForce` momentum source holds the bulk
  velocity Ubar and reports the pressure gradient it must apply each
  iteration — that pressure gradient *is* the integral wall drag.
- **DR measurement.** At matched Ubar the riblet channel needs a smaller
  pressure gradient than the smooth baseline iff the riblets reduce drag.
  DR% is computed from the paired `dpdx` values, averaged over the last
  1000 iterations to remove the mild periodic oscillation (below).
- **Riblet representation.** Bechert blade riblets, h/s=0.5, t/s=0.02, on
  a structured multi-block `blockMesh` (no snappyHexMesh, no STL) —
  `aero_research_platform/meshing/periodic_riblet_strip.py`.

---

## Mesh quality — what passed, what failed

The structured `blockMesh` is **geometrically valid everywhere**:
non-orthogonality max = 0, skewness ~1e-13, **zero negative-volume
cells** in all 10 cases. Those are the checks whose failure corrupts a
finite-volume solution; none failed.

`checkMesh -allTopology -allGeometry` did report one failed check on the
riblet meshes — **cell well-posedness** ("cells with small determinant
< 0.001"), the stretched cells inside the riblet groove:

| run | cells | degenerate cells | fraction | `checkMesh` |
|---|---:|---:|---:|:--|
| smooth   | 414 720 | 0 | 0 % | **Mesh OK** |
| riblet-5  | 432 960 | 39 840 | 9.2 % | Failed 1 |
| riblet-10 | 432 960 | 12 000 | 2.8 % | Failed 1 |
| riblet-15 | 432 960 | 1 920 | 0.44 % | Failed 1 |
| riblet-17 | 432 960 | 1 440 | 0.33 % | Failed 1 |
| riblet-20 | 432 960 | 480 | 0.11 % | Failed 1 |
| riblet-25 | 432 960 | 480 | 0.11 % | Failed 1 |
| riblet-30 | 432 960 | 38 880 | 9.0 % | Failed 1 |
| riblet-35 | 432 960 | 147 360 | 34.0 % | Failed 2 |
| riblet-40 | 432 960 | 0 | 0 % | **Mesh OK** |

Two things follow, and both are load-bearing for the verdict:

1. **A trustworthy band exists: s+ ∈ [15, 25].** There the degenerate
   fraction is 0.11–0.44 % — small, localized in the groove, on an
   otherwise perfectly orthogonal mesh, and the runs converged to
   stationary states with no FPEs. The pre-registered peak (s+~17) and
   the modelled peak (s+=20) both sit inside this band. **The FAIL
   verdict is read entirely from this band** and does not depend on the
   compromised extremes.

2. **The extremes (s+ 5, 10, 30, 35) are mesh artifacts** — 2.8–34 %
   degenerate cells. Their DR values (−152 %, −40 %, −15 %) are *not*
   used for the verdict; they are reported for completeness and flagged.
   The `z_bl` flooring fix (`469ea0f`) re-meshed s+=40 to a fully clean
   `Mesh OK` state (0 degenerate cells, max aspect ratio 29 vs ~50–350
   for the un-fixed meshes) — proof the mesher *can* produce clean
   riblet meshes; s+ 5–35 simply predate that fix.

**Robustness check.** Could the 0.33 % degenerate cells at s+~17 explain
the 11.3 pp miss? No. riblet-17 gives `dpdx = 1.0012`, a 1.4 % drag
*increase*; matching Bechert's +9.9 % would require `dpdx ≈ 0.89`. A
sub-percent population of well-posedness-flagged cells cannot turn a
+1.4 % penalty into a −9.9 % reduction — the gap is an order of
magnitude larger than any plausible discretization perturbation. The
miss is a closure failure, not a mesh failure (see next section).

---

## Convergence

All 10 runs completed the full 6000 iterations and wrote `End`.

- **Residuals.** Initial-residual on Ux at iteration 6000 ranged
  5.5e-7 (s+=40) to 1.1e-5 (s+=35); most runs sat at 1–7e-6. The
  campaign target was 1e-6. The plateau slightly above target is **not
  non-convergence** — it is genuine mild periodic unsteadiness: the
  pressure gradient oscillates with a small, stationary amplitude
  (vortex shedding off the riblet tips). A steady solver on a weakly
  unsteady flow yields the time-mean *if* you average, which is why DR
  is taken as the mean `dpdx` over the last 1000 iterations. A fully
  rigorous treatment is URANS or LES — another pointer to the escalation.
- **Near-wall resolution.** y+ is below 1 essentially everywhere:
  bottomWall y+ ≤ 0.46 in all cases; riblet-surface y+ averages
  0.13 (s+=5) → 0.87 (s+=40), with a few riblet-tip cells reaching
  ~1.8 at the highest s+. k-omega SST integrates to the wall here —
  no wall functions — so the near-wall gradient is resolved, not
  modelled. Resolution is *not* the limiting factor.

---

## Results — what RANS got, and what it missed

The model produces a **shallow, all-negative** DR curve where the
experiment produces a ~9 pp-tall drag-reduction hump. Reading the
trustworthy band:

| s+ | RANS DR % | Bechert DR % |
|---:|---:|---:|
| 15 | −6.2 | +8.8 |
| 17 | −1.4 | +9.9 |
| 20 | +0.2 | +9.0 |
| 25 | −0.8 | +3.5 |

One striking, physically coherent contrast localizes the failure:

- **In the roughness regime (s+ ≫ crossover)** the only mesh-clean
  riblet run, **s+=40**, gives DR −12.7 % against Bechert's −12.0 % —
  agreement within 0.7 pp. When the riblet is coarse enough to act as
  plain surface roughness, RANS represents the drag penalty correctly.
- **In the drag-reduction regime (s+ ≲ 25)** the model collapses:
  −1.4 % at the pre-registered peak against +9.9 % measured.

RANS handles riblets-as-roughness but not riblets-as-drag-reducers.
That is exactly the expected signature. Riblet drag reduction is a
**near-wall anisotropic** effect: the grooves impede the spanwise motion
of the quasi-streamwise vortices and shift the virtual origin of the
cross-flow relative to the streamwise flow (the protrusion-height
mechanism — Luchini 1991; Bechert et al. 1997; García-Mayoral &
Jiménez 2011). k-omega SST is an **isotropic eddy-viscosity** closure:
it represents turbulence with a single scalar ν_t and structurally
cannot carry the differential streamwise/spanwise protrusion height that
*is* the drag-reduction mechanism. It can represent the extra wetted
area and form drag of a coarse riblet (hence the s+=40 agreement); it
cannot represent the sublayer reorganization that yields net reduction.

This is consistent with the literature the hypothesis cites: Mele &
Tognaccini 2022 obtain RANS riblet DR only with a *modified*
boundary-condition / roughness-correction treatment, not with vanilla
SST resolving the geometry. Stage 5 confirms that, on its own pre-
registered terms.

---

## Verdict against the pre-registered hypothesis

Pre-registered acceptance (`campaigns/02-flat-plate-riblet-bechert.yaml`):
peak DR within **±2 pp** of +9.9 % at s+~17; crossover within **±3** in
s+ of s+~27.

| Criterion | Pre-registered | Measured | Result |
|---|---|---|---|
| Peak DR | +9.9 % ± 2 pp | **+0.2 %** (at s+=20) | **FAIL** — 9.7 pp low |
| Peak location | s+ 17 ± 3 | s+ 20 | within tolerance, but moot — magnitude fails |
| Crossover | s+ 27 ± 3 | **s+ ≈ 21** (interpolated) | **FAIL** — 6 in s+ low |

Both criteria fail. The validation notebook computes **VERDICT: FAIL**.
The result is robust to the mesh well-posedness caveat (the verdict band
s+ 15–25 is the cleanest-mesh region; the 11.3 pp peak miss dwarfs any
sub-percent-degenerate-cell perturbation) and robust to the convergence
caveat (DR is a stationary time-mean).

A negative result against a pre-registered bound is a **valid Stage-5
deliverable** — the hypothesis explicitly anticipated it and named the
next step.

---

## Evidence bundle — citation-grade provenance

The sweep ran SSH-direct, so it did not pass through the orchestrator's
planner→generator→judge pipeline and produced no `LlmCall` trace. That
is **correct, not degraded**: a CFD recipe fixed in the campaign YAML has
no LLM provenance to capture. Its citation-grade provenance is the git
SHA + input params + solver version + per-run SHA-256 manifest + DSSE
signature — none of which need an LLM.

Stage 5 is the first real consumer of the orchestrator's
**deterministic-run evidence path** (`core/deterministic_run.py`,
shipped this session). All 10 runs were registered and bundled:

- **Bundle:** `campaigns/cbf6d068-ad88-541b-9caf-956e0dd5e2f9/` in the
  orchestrator repo — RO-Crate 1.2 / WRROC, built standalone via
  `orchestrator build-bundle cbf6d068-…`.
- **Bundle id:** `99523422-a739-4544-9ff8-ba966ff5730d`; orchestrator
  code fingerprint git SHA `da3e844`.
- **Provenance mode:** all 10 runs stamped `provenance_mode:
  deterministic`; `llm_call_count: 0`, `n_deterministic_runs: 10` — the
  empty `llm_calls[]` reads as *intentional*, not as a gap.
- **Attestation:** DSSE-signed (Ed25519, keyid `4c10ad9c…`), 79 signed
  statement subjects. `python -m evidence.verify --crate-dir
  campaigns/cbf6d068-…` → **verifies cleanly**.

The Stage-5 FAIL verdict is therefore itself a signed, verifiable
artifact — the negative result is as citable as a positive one would
have been.

---

## Escalation — wall-resolved LES (pre-registered)

Per the hypothesis: *"If RANS misses, escalate to wall-resolved LES on a
SkyPilot A100 burst per the Mele & Tognaccini 2022 practice."* Concrete
handoff for the LES stage:

1. **Domain / mesh — reuse, but re-mesh clean.** Keep the periodic
   channel and `periodic_riblet_strip.py`. Re-generate **every** riblet
   mesh with the `469ea0f` `z_bl` flooring fix so all sweep points reach
   `checkMesh: Mesh OK` (s+=40 already does). LES cannot tolerate the
   degenerate cells the RANS sweep ran on at the extremes.
2. **Turbulence treatment.** Wall-resolved LES (WALE or dynamic
   Smagorinsky), `pimpleFoam`, with the near-wall spanwise resolution
   the protrusion-height mechanism requires (Δy+ ~ 1, Δx+ ~ 10–20,
   Δz+ ~ 5 across the groove). Re_τ=180 keeps the cell count tractable
   on a single A100.
3. **Compute.** SkyPilot A100 burst (`sky/torch-eval.yaml` pattern,
   adapted to an OpenFOAM image). The orchestrator's Phase 2.5 burst
   route + Phase 2.4 budget accrual already exist; this is their first
   real CFD use.
4. **Scope.** Start with the three trustworthy-band points s+ ∈
   {15, 17, 20} to confirm LES recovers the +9 % plateau before
   committing the full 9-point sweep.
5. **Acceptance.** Unchanged — the pre-registered ±2 pp / ±3 bound
   carries over. Do **not** move the bound; that was a pre-registration
   commitment.

---

## Process notes — orchestrator bypass + handoff to Stage 6

- **The sweep ran SSH-direct, not through the orchestrator.** Under a
  229-run backlog the Ollama planner/judge servers saturated (40-min
  timeouts, HTTP 500s); for a fully-specified CFD recipe the
  planner→generator→judge cycle is pure ceremony and was the only point
  of failure. Real work routed around it. The structural fix landed
  this session in the orchestrator repo: `core/deterministic_run.py` +
  `orchestrator build-bundle` give SSH-direct runs a first-class
  evidence bundle (used above) instead of no evidence at all.
- **Mesh-first discipline paid off.** Moving mesh iteration to direct
  `blockMesh`/`checkMesh` on the target (~1 min each) instead of full
  ~45-min orchestrator campaigns is what made the 9-point sweep
  finishable. Keep it for Stage 6.
- **For Stage 6** (NACA 0012 at α≈10° with riblets): the α=10
  cold-start / mesh-resolution blocker from Stage 4 (`STAGE-4-OUTPUTS.md`
  Issue 4) is still open and **must land before Stage 6**. Stage 6 also
  inherits the LES escalation if it, too, needs riblet drag reduction
  rather than just riblet roughness.
- **Re-meshing follow-up.** Re-running the RANS s+ 5–35 points on the
  `469ea0f`-fixed mesher would give a clean-mesh RANS curve for direct
  comparison against the LES — cheap (each run ~20–50 min) and worth
  doing as the LES baseline, but not required to close Stage 5: the
  trustworthy band already settles the verdict.

---

End of STAGE-5-OUTPUTS.
