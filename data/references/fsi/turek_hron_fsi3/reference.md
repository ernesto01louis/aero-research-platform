# Turek-Hron FSI3 cylinder+flag — external geometry, rigid-flag CFD, and FSI reference data

**Cases:** `turek_hron_cfd2`, `turek_hron_cfd3` (`aero/vv/external_geometry/`) — Stage 18
(arbitrary-geometry ingestion; ADR-033/034); `turek_hron_fsi3` (`aero/vv/fsi/`) — Stage 19
(preCICE FSI core; ADR-035/036). **Tier:** FSI machinery of the validation
ladder (`.claude/rules/flapping-validation-ladder.md`).

> **Document layout.** Sections up to "Tracking" are the Stage-18 rigid-flag record.
> The Stage-19 FSI3 additions — the *moving*-flag displacement reference, the pinned
> upstream tutorial, and a **correction** to what Stage 18 believed the upstream
> `reference-results/` tarballs contain — are in "Stage 19" at the end.

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

> **CORRECTION (Stage 19, 2026-07-27).** The sentence above is right that the tarballs
> are not vendored here, but it implies they *contain* the displacement data Stage 19
> gates on. **They do not.** Both were fetched and listed at Stage-19 open: they hold
> only `*.init.vtu` + `*.dt1..dt3.vtu` coupling-mesh exports — one to three coupled
> time windows — i.e. preCICE's own CI regression fixture, with no watchpoint time
> history at all. The FSI3 displacement reference is the featflow benchmark data
> acquired below. (They remain useful as a cheap 1-window plumbing cross-check —
> ADR-036 gate I2, non-gated.) Fetching them needs no `git-lfs`: they are LFS pointer
> files in the git tree, and `https://media.githubusercontent.com/media/<owner>/<repo>/
> <ref>/<path>` serves the real bytes over plain HTTPS.

---

# Stage 19 — FSI3 (moving flag): displacement reference + the pinned tutorial

Everything above concerns the **rigid**-flag CFD tests. This section is the *moving*-flag
FSI3 reference the Stage-19 coupling gate (ADR-036) is stated against.

## Source of the displacement reference

Same citation and same maintained pages as the CFD tests — Turek & Hron (2006), via
`wwwold.mathematik.tu-dortmund.de/~featflow/en/benchmarks/cfdbenchmarking/fsi_benchmark/`
`fsi_tests/fsi_fsi_tests.html` (tabulated) and `.../fsi_reference.html` (time series).
Two artifacts, acquired 2026-07-27 by `scripts/stage19_acquire_fsi_reference.py`:

1. **`fsi3_reference.csv`** (git-tracked) — the full tabulated FSI3 table: 3 mesh levels
   × 3 time steps, each row `mean ± amplitude [frequency]` for ux(A), uy(A), drag, lift.
   `level`/`ndof` are the featflow **FEM** discretisation and are **not** comparable to an
   FVM cell count.
2. **`ref_fsi3.point`** (DVC-tracked, sha256 sidecar git-tracked) — the published FSI3
   **time series**, 5769 rows, t ∈ [5.0000, 6.4420] s, solver Δt = 2.5e-4 s (about 8
   fundamental periods of the established limit cycle). Columns, per the benchmark page
   ("time, drag on beam, lift on beam, drag on cylinder, lift on cylinder, Ux, Uy" in
   columns 1, 5-8, 11-12): `1 t · 2 Δt · 5,6 drag,lift on the beam · 7,8 drag,lift on the
   cylinder · 11 Ux(A) · 12 Uy(A)`. Total drag/lift are the beam + cylinder sums.

## Which row it is (gate R1) — identified, not assumed

The mesh level is discriminated by scoring the recomputed statistics against every
tabulated row on the four well-conditioned quantities (ux mean, ux amplitude, uy
amplitude, frequency):

| candidate (Δt = 2.5e-4) | mean relative disagreement |
|---|---|
| level 2 (ndof 19 488) | 4.05 % |
| level 3 (ndof 76 672) | 2.39 % |
| **level 4 (ndof 304 128)** | **0.77 %** ← identified |

The time step is **not** inferred: at level 4 the three tabulated Δt rows agree to within
the table's printed precision (3 significant figures), so scoring cannot discriminate Δt
and does not pretend to. Δt is read from the series' own column 2 (2.5e-4 s), which also
matches its published download path (`.../fsi3/0p00025/ref_fsi3.point`).

## Reference of record (gate R3) — recomputed, not transcribed

`fsi3_recomputed.csv` is the reference the D-bands are stated against. It is computed
**from `ref_fsi3.point` with the platform's own `aero.postprocess` estimators**, the same
code path a measured solve goes through, so reference and measurement are extracted
like-for-like. This is not ceremony: "mean" is genuinely ambiguous here, and the ambiguity
is worth 34 % on one quantity (below).

| quantity | recomputed | featflow L4 / Δt 2.5e-4 | agreement | gated |
|---|---|---|---|---|
| frequency | 5.539872 Hz | 5.46 | +1.46 % | yes |
| uy amplitude | 3.495533e-2 m | 3.499e-2 | +0.10 % | yes |
| ux amplitude | 2.700146e-3 m | 2.720e-3 | +0.73 % | yes |
| ux mean | −2.856809e-3 m | −2.880e-3 | +0.81 % | yes |
| ux frequency | 11.0742 Hz | 10.93 | +1.32 % | yes |
| uy mean | 9.664360e-4 m | 1.470e-3 | **+34.26 %** | **no — diagnostic** |
| drag mean / amplitude | 459.0011 / 27.69773 N/m | 460.5 / 27.74 | +0.33 % / +0.15 % | no |
| lift mean / amplitude | 5.15 / 155.2639 N/m | 2.50 / 153.91 | — / +0.88 % | no |

Gate **R2** requires this agreement to stay within 3 % (ux mean, uy amplitude) and 5 %
(frequency) or the campaign stops before any physics run — a gate compared against a
reference we do not understand is worse than no gate.

### Two measured extraction traps (why the estimators are constrained the way they are)

- **Segment every signal at ONE period, taken from uy** (ADR-036 S1). ux, drag and lift
  oscillate at the *second* harmonic (measured ratio 1.999). Segmenting them at their own
  dominant frequency makes consecutive per-cycle amplitudes alternate between the two
  half-strokes, which spuriously trips the periodic-steady-state drift check — measured on
  the reference itself: amplitude drift 0.070 (ux) and 0.163 (drag) against a 0.02
  tolerance. Nothing is wrong with those signals; the segmentation was.
- **The uy mean is period-conditioned and is not gateable.** It is ~3 % of its own
  amplitude, and a 1.5 % change in the assumed period moves it by ~50 % (9.66e-4 →
  1.4656e-3), while ux mean moves 0.9 %. The +34 % row above is that sensitivity, not an
  acquisition error. Same disposition as CFD3's near-zero mean lift, but established
  quantitatively rather than by analogy.
- **Frequency estimator floor.** The +1.46 % agreement is dominated by the platform's own
  FFT + parabolic-interpolation bias on an 8-cycle record (bin width 0.693 Hz), not by the
  reference. A frequency band tighter than ~3 % would be gating our estimator, not the
  physics — which is why D2 is 5 %.

## The pinned upstream tutorial

`precice/tutorials` @ **`cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e`** (branch `develop`,
2026-07-24). Stage 18 pinned `98a78fe2` on `master`; the FSI participants
(`solid-nutils`, `fluid-nutils`) and `reference-results/` exist only on `develop`.

- **`precice-tutorials-turek-hron-fsi3.tar.gz`** (DVC-tracked, 75 877 B, sha256 sidecar
  git-tracked) — a deterministic re-tar (sorted paths, fixed mtime, numeric 0/0 owner,
  `gzip -n`) of `turek-hron-fsi3/` (minus the 351 KB of doc `images/`) and `tools/`
  from the codeload archive of that commit; 332 KB unpacked.
- **`tutorials_pin_manifest.csv`** (git-tracked, 94 files) — per-file sha256. **This, not
  the archive checksum, is the integrity contract**: GitHub codeload tarballs are not
  guaranteed byte-stable across time, so `aero.adapters.precice.materialize_tutorial`
  verifies every materialized file against this manifest (ADR-036 C5).

Three provenance cross-checks, all verified 2026-07-27:

1. `turek-hron-fsi3/fluid-openfoam/system/blockMeshDict` at this `develop` pin has sha256
   `9d85bd3e3e6fd8d58eb3d7115c1ae2685abad8ac8918ba08661acd5c81816d7c` — **byte-identical to
   the digest Stage 18 recorded at the `master` pin**. The Stage-18 geometry provenance
   chain is therefore continuous across the branch change.
2. `precice-config.xml`, `solid-nutils/solid.py` and `solid-nutils/solid.geo` are
   **byte-identical** to the commit that generated the upstream reference results
   (`33a2563`) — so the coupling setup and solid model we run are the ones upstream
   exercised.
3. `fluid-openfoam/system/controlDict` differs from `33a2563` by exactly one deleted
   comment line (a commented-out `pimpleDyMFoam` alternative for OpenFOAM ≤ v1712). No
   physics change.

## Benchmark setup (FSI3, moving flag)

Same geometry and channel as the rigid CFD tests. Fluid ρ = 1000 kg/m³, ν = 1e-3 m²/s,
Ū = 2.0 m/s (Re = 200) with a cosine ramp over t < 2 s (`codedFixedValue` inlet — note it
is *coded*, not `exprFixedValue`; the Stage-18 inlet finding does not transfer). Solid:
St. Venant-Kirchhoff, ρ_s = 1000 kg/m³, ν_s = 0.4, E_s = 5.6e6 Pa. Watch-point "Flap-Tip"
at the flag tip's undeformed position (0.6, 0.2) = benchmark point A.

## u95_input (FSI3)

Same posture as the CFD tests: text/series-sourced from the maintained benchmark, so
digitization uncertainty ≈ 0. The reference's own discretisation spread across mesh levels
is **2.1 %** on uy amplitude (L2 3.573e-2 → L4 3.499e-2) and 1.8 % on frequency, and under
0.5 % across the three Δt. Carry **u95_input ≈ 2 %** for reportable composition of an FSI3
displacement amplitude at the `validated` tier.

---

## License

precice/tutorials is LGPL-3.0 (Invariant-5 compliant); the extracted/closed surface
is a derivative of its blockMeshDict and carries the same license + this provenance
note. The vendored pin archive is a verbatim subset of the same LGPL-3.0 repository.
Benchmark values and the featflow `.point` series are published scientific results,
cited under fair use.

## Cross-references

- ADR-033 §7 (acquisition decision + fallback), ADR-034 (the Stage-18 pre-registered gates).
- ADR-016 (FSI structural-solver strategy), ADR-035 (Stage-19 pins + container strategy),
  ADR-036 (the pre-registered FSI3 gate block).
- `aero/vv/external_geometry/turek_hron_cfd.py` (rigid), `aero/vv/fsi/turek_hron_fsi3.py`
  (coupled), `scripts/stage19_acquire_fsi_reference.py` (this section's acquisition).
