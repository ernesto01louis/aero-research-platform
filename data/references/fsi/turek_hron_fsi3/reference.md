# Turek-Hron FSI3 cylinder+flag — external geometry + rigid-flag CFD reference data

**Case:** `turek_hron_cfd2`, `turek_hron_cfd3` (`aero/vv/external_geometry/`) — Stage 18
(arbitrary-geometry ingestion; ADR-033/034). **Tier:** FSI machinery of the validation
ladder (`.claude/rules/flapping-validation-ladder.md`); the geometry + tabulated data
acquired here also anchor Stage 19 (preCICE FSI core, the FSI3 displacement gates).

## Source

S. Turek, J. Hron, "Proposal for numerical benchmarking of fluid-structure interaction
between an elastic object and laminar incompressible flow", in *Fluid-Structure
Interaction*, LNCSE 53, Springer, 2006. DOI 10.1007/3-540-34596-5_15.

Tabulated CFD-test values retrieved from the maintained featflow benchmark pages
(2026-07-26): `wwwold.mathematik.tu-dortmund.de/~featflow/en/benchmarks/`
`cfdbenchmarking/fsi_benchmark/fsi_tests/fsi_cfd_tests.html` — finest-resolution rows
(CFD1/CFD2: mesh level 6+0; CFD3: Δt = 0.005). These are *numerical-benchmark*
reference solutions (mesh-converged consensus, like NASA TMR), which is what the
ladder's FSI tier names as the reference for machinery validation.

## Geometry acquisition (the EXTERNAL surface — full provenance)

The platform did NOT analytically generate this shape. Acquisition chain, executed
2026-07-26 (`scripts/stage18_acquire_geometry.py`):

1. **Upstream source:** `github.com/precice/tutorials` @ commit
   `98a78fe2dc2f6c5d84b2b30d35d00352782236f8` (LGPL-3.0 — posture-compliant),
   file `turek-hron-fsi3/fluid-openfoam/system/blockMeshDict`
   (sha256 `9d85bd3e3e6fd8d58eb3d7115c1ae2685abad8ac8918ba08661acd5c81816d7c`) —
   the third-party-authored body-fitted mesh of the benchmark fluid domain.
   **Branch note (corrected post-tag):** that commit is the head of the repo's
   `master` branch (2024-04-16); the repo's DEFAULT and actively maintained branch is
   **`develop`** (head `cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e` at 2026-07-26). The
   `blockMeshDict` is **byte-identical on both branches** (same sha256, verified by
   direct diff), so the acquired geometry is unaffected by the branch choice; but
   anything else read from this tutorial — notably `reference-results/`, `fluid-nutils`
   and `solid-nutils` — exists **only on `develop`**, not at the pinned `master` commit.
2. **Mesh + extract** (OpenFOAM-ESI v2412 SIF on aero-dev): the *upstream*
   blockMeshDict was run verbatim (`blockMesh`), then the body wall surface was
   extracted with `surfaceMeshExtract -patches '("cylinder" "flap")' band.stl` —
   an open prismatic band (668 triangles, z ∈ [-0.1, 0.1]), whose x-y profile is
   100 % upstream-authored.
3. **Declared shape-preserving closure** (the only platform-applied transform;
   ledger verbatim from the acquisition run):
   - `fill_hole (x334)`: filled a 334-edge boundary loop with a planar ear-clip patch
   - `fill_hole (x334)`: filled a 334-edge boundary loop with a planar ear-clip patch
   (the two planar caps at z = ±0.1; the x-y profile is untouched).
4. **Verification:** the shipped STL passes the strict default ingestion gate
   (ADR-034 Q1-Q4) with **zero repairs**: 1332 faces, watertight, edge-manifold,
   orientation-consistent, 0 self-intersections.

`cylinder_flag.stl` sha256:
`155b66892fb8564f100730eba3477aea0161e0ad38b3b79d0d453ee6f4990cf2`
(also in the git-tracked sidecar `cylinder_flag.stl.sha256`, which the V&V cases
verify against the pulled bytes).

**V1 metrology (ingested extents vs the published spec, tol 0.001 m):**
x ∈ [0.150012, 0.600000] (expected [0.15, 0.60]); y ∈ [0.150004, 0.249996]
(expected [0.15, 0.25]). The ~1e-5 offsets are the upstream mesh's polygonal
faceting of the cylinder arc — a property of the acquired tessellation, recorded,
not repaired. z ∈ [-0.1, 0.1] (the upstream span; the quasi-2D slab sits inside it).

## Benchmark setup (fluid, rigid flag)

Channel 2.5 × 0.41 m; cylinder r = 0.05 m centred (0.2, 0.2) (deliberately 0.005
below mid-channel — seeds the asymmetry); flag 0.35 × 0.02 m ending at x = 0.6.
ρ = 1000 kg/m³, ν = 1e-3 m²/s. Parabolic inlet U(y) = 1.5 Ū y(H−y)/(H/2)²
(paper eq. 10); no-slip walls; zero-gradient outlet pressure.

## Normalization convention (CONFIRMED)

The paper reports dimensional forces per unit span on the cylinder+flag union. The
platform's `forceCoeffs` output is compared coefficient-normalized:
`Cd = F_drag / (0.5 ρ Ū² D)`, `Cl = F_lift / (0.5 ρ Ū² D)` with D = 0.1 m (the case
writer sets `Aref = D × slab_thickness`, cancelling the quasi-2D span). Relative
tolerances are normalization-invariant, so this compares exactly the published
quantities. Frequency is dimensional [Hz] (solver time is seconds).

## cfd_reference.csv

| test_id | Ū | drag [N/m] | lift [N/m] | cd | cl | cl_amplitude | frequency [Hz] | provenance |
|---|---|---|---|---|---|---|---|---|
| 1 (CFD1, Re=20, steady) | 0.2 | 14.2929 | 1.11905 | 7.146450 | 0.559525 | — | — | text-sourced |
| 2 (CFD2, Re=100, steady) | 1.0 | 136.700 | 10.5343 | 2.734000 | 0.210686 | — | — | text-sourced |
| 3 (CFD3, Re=200, periodic) | 2.0 | 439.45 ± 5.6183 | −11.893 ± 437.81 | 2.197250 | −0.059465 | 2.189050 | 4.3956 | text-sourced |

Amplitudes are the paper's `± amplitude` halved-peak-to-peak convention; the CSV's
`cd_amplitude`/`cl_amplitude` are the coefficient-normalized amplitudes.

## Which quantity is gated (and why) — ADR-034 V-gates

- **GATED (CFD2, V3):** cd (5 %), cl (10 %).
- **GATED (CFD3, V5 — stretch):** mean cd (5 %), lift oscillation frequency (5 %),
  lift amplitude (15 %).
- **NOT gated (diagnostics):** CFD3 mean lift (−0.0595 — ~2.7 % of its own
  oscillation amplitude; a relative tolerance on a near-zero mean invites dishonest
  tolerance inflation), CFD3 drag amplitude, CFD1 (not run in Stage 18 — the steady
  machinery is already covered by CFD2 at a more demanding Re).

## u95_input

Text-sourced numeric values from the maintained benchmark tables — digitization
uncertainty ≈ 0. The reference itself carries discretization uncertainty (it is a
numerical benchmark, not an experiment); the featflow convergence tables show the
finest-level values stable to ~0.1 % (CFD2 drag) and ~1 % (CFD3 amplitudes). Carry
**u95_input ≈ 1 %** for reportable composition at the `validated` tier.

## Tracking

`cfd_reference.csv` is git-tracked (small scalar table — forward-regime tier
convention). `cylinder_flag.stl` (65 KB binary) is DVC-tracked
(`cylinder_flag.stl.dvc`, default remote `aero-minio`) with the git-tracked sha256
sidecar. The upstream `reference-results/` FSI3 tarballs
(`fluid-openfoam_solid-dealii.tar.gz`, `fluid-nutils_solid-nutils.tar.gz`) are NOT
vendored here — Stage 19 acquires the displacement data it gates on, and must fetch
them from the **`develop`** branch (they do NOT exist at the `master` pin above).

## License

precice/tutorials is LGPL-3.0 (Invariant-5 compliant); the extracted/closed surface
is a derivative of its blockMeshDict and carries the same license + this provenance
note. Benchmark values are published scientific results, cited under fair use.

## Cross-references

- ADR-033 §7 (acquisition decision + fallback), ADR-034 (the pre-registered gates).
- ADR-016 / Stage 19: the same upstream case is the supported preCICE FSI3 tutorial
  the coupling verification will run against.
