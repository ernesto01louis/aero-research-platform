# Periodic-hill LES Re=10595 — Breuer & Rapp/Manhart reference

> Breuer, M., Peller, N., Rapp, Ch. & Manhart, M. (2009). **Flow over
> periodic hills — numerical and experimental study in a wide range of
> Reynolds numbers.** *International Journal of Heat and Fluid Flow*, 30(3),
> 433-446.
> <https://doi.org/10.1016/j.ijheatfluidflow.2009.02.004>

## File: `reattachment.csv` (Stage 12 — full pointwise profiles deferred)

CSV with header `reynolds,x_over_h`:

| Re      | x/h     | source                       |
|---------|---------|------------------------------|
| 700     | 6.62    | Breuer 2009 Table 3 (DNS)    |
| 1400    | 5.21    | Breuer 2009 Table 3 (DNS)    |
| 5600    | 4.36    | Breuer 2009 Table 3 (LES)    |
| 10595   | 4.21    | Breuer 2009 Table 3 (LES)    |

Stage 07 ships only the bulk re-attachment-length scalar comparison (the
headline summary metric every periodic-hill paper reports). The full
pointwise mean-velocity-profile comparison and the wall-shear distribution
land in Stage 12, when the periodic-hill mesh and wall-sampler plumbing
mature.

## DVC

```bash
.venv/bin/dvc add data/references/scale_resolving/periodic_hill/reattachment.csv
git add data/references/scale_resolving/periodic_hill/reattachment.csv.dvc \
        data/references/scale_resolving/periodic_hill/.gitignore
git commit -m "feat(stage-07): mirror Breuer 2009 periodic-hill re-attachment"
.venv/bin/dvc push
```
