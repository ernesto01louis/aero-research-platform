# Taylor-Green vortex Re=1600 — DNS reference (Brachet et al. 1983)

The kinetic-energy dissipation rate trace `epsilon(t) = -d(KE)/dt` from the
original DNS reported in:

> Brachet, M.E., Meiron, D.I., Orszag, S.A., Nickel, B.G., Morf, R.H. and
> Frisch, U. (1983). **Small-scale structure of the Taylor-Green vortex.**
> *Journal of Fluid Mechanics*, 130, 411-452.
> <https://doi.org/10.1017/S0022112083001159>

The canonical comparison curve is figure 7 of the paper, Re=1600.

## File: `dissipation_re1600.csv`

CSV with header `t,diss`:

- `t` — dimensionless time in convective units (V0 = 1, L = 1).
- `diss` — volume-averaged dissipation rate `-d(KE)/dt`.

Expected dissipation peak: magnitude `~ 1.30 × 10^-2` near `t ~ 9`.

## Digitisation

The CSV must be digitised from figure 7 of the JFM 1983 paper, OR pulled from
one of several public mirrors (Wang et al. HiOCFD3 workshop dataset; the
PyFR / NekRS verification repositories). The digitised dataset is then
DVC-tracked alongside the SU2 ONERA M6 mesh (Stage 06 operator-followups §0c
pattern):

```bash
.venv/bin/dvc add data/references/scale_resolving/taylor_green/dissipation_re1600.csv
git add data/references/scale_resolving/taylor_green/dissipation_re1600.csv.dvc \
        data/references/scale_resolving/taylor_green/.gitignore
git commit -m "feat(stage-07): mirror Brachet 1983 TG dissipation Re=1600"
.venv/bin/dvc push
```

Stage-07 ships the registry stub + reference loader; the operator pulls or
digitises this CSV during the Stage-07 cluster validation sweep. Until it
lands, the `taylor_green_p3_32.evaluate()` call still produces the measured
`TimeHistory` and scalar `peak_dissipation` (so `aero run --solver pyfr` runs
end-to-end and logs the four-fold provenance), but `aero vv run --case
taylor_green_p3_32` raises a `BenchmarkError` at the reference-load step.
