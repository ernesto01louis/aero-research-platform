# SU2 mesh assets (Stage 06, ADR-006)

Native `.su2` meshes the platform consumes but does not generate analytically.
Stage 06 ships exactly one such asset:

* `onera_m6.su2` — the BSD-licensed ONERA M6 wing mesh from the SU2 tutorial
  repository at
  `https://github.com/su2code/Tutorials/blob/master/compressible_flow/Turbulent_ONERAM6/mesh_ONERAM6_turb_hexa_43008.su2`
  (mirrored here, DVC-tracked). Markers in the mesh: `WING` (no-slip wall),
  `SYMMETRY` (root-plane symmetry), `FARFIELD` (characteristic far field).
  The `OneraM6` `SU2MeshFileSpec` references this asset.

Acquire with `dvc pull`; the file is not committed to git directly because
of its size (~3 MB ASCII).
