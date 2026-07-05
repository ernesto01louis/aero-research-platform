"""Forced transversely-oscillating cylinder — wake lock-in (synchronization).

A circular cylinder at Re = 100 sheds a von Kármán street at its natural Strouhal
St_0 ~= 0.165. When the cylinder is *forced* to oscillate transversely at a frequency
inside the **lock-in (synchronization) band**, the wake abandons its natural frequency and
sheds at the forcing frequency. Forcing 10 % above natural (F = f_e/f_0 = 1.1) at
amplitude A/D = 0.5 sits safely inside the 1:1 lock-in band at Re = 100 (Placzek, Sigrist &
Hamdouni 2009 studied F in [0.5, 1.5], A/D in [0.25, 1.25]; Koopmann 1967).

The falsifiable claim: **the wake response frequency equals the forcing frequency** (the
solver reproduces synchronization). Forcing off-natural (F = 1.1) makes the test
discriminating — an *unlocked* wake would shed near St_0 = 0.165, which is > 3 % away from
the forcing St = 0.1815, so the tolerance only passes on genuine lock-in. This is the
Stage-11 primary GO: cheap (Re = 100 laminar), first-principles (the reference is the
forcing frequency, not a digitized datum), and in the transient regime already validated
at Stage 10.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.openfoam.cylinder import CylinderSpec
from aero.adapters.openfoam.motion import MotionSpec
from aero.vv._base import (
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
    scaled_count,
)

_ST_NATURAL = 0.165  # Williamson St-Re at Re=100 (the platform's own baseline)
_FREQ_RATIO = 1.1  # F = f_e / f_0 (forcing 10% above natural — inside the lock-in band)
_AMP_RATIO = 0.5  # A / D


class OscillatingCylinderLockin:
    """Forced oscillating cylinder (Re=100, A/D=0.5, F=1.1) — wake lock-in to the forcing."""

    name = "oscillating_cylinder_lockin"
    description = (
        "Forced transversely-oscillating cylinder (Re=100, A/D=0.5, F=f_e/f_0=1.1) — the "
        "wake shedding frequency locks to the forcing (Placzek 2009; Koopmann 1967)."
    )
    sweep_metric = "strouhal"

    def __init__(self, spec: CylinderSpec | None = None) -> None:
        if spec is None:
            f_forced = _FREQ_RATIO * _ST_NATURAL  # forcing St (D = U = 1 => f = St)
            spec = CylinderSpec(
                name=self.name,
                reynolds=100.0,
                inflow_angle_deg=0.0,  # the motion breaks symmetry; no tilt seed needed
                motion=MotionSpec(amplitude=_AMP_RATIO, frequency=f_forced),
                # ~36 forcing periods: under forcing the wake locks within ~5-10 periods
                # (faster than free shedding), leaving a long converged tail for the FFT +
                # cycle-convergence + the Stage-12 batch-means samples.
                end_time_convective=200.0,
                write_interval_convective=0.1,  # ~55 samples/period (FFT + cycle resolution)
            )
        self._spec = spec

    def case_spec(self) -> CylinderSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        st = load_scalar_csv(
            repo_root
            / "data"
            / "references"
            / "unsteady"
            / "oscillating_cylinder_lockin"
            / "strouhal.csv",
            key_col="frequency_ratio",
            key=_FREQ_RATIO,
            value_col="strouhal",
        )
        return ReferenceData(
            case_name=self.name,
            source="Wake lock-in: response frequency = forcing frequency (Placzek 2009; Koopmann 1967)",
            scalars={"strouhal": st},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # 3% is tight-but-defensible: in true lock-in the wake frequency IS the forcing
        # frequency (exact by construction), so the only error is FFT resolution.
        return (MetricSpec(name="strouhal", kind="scalar", tolerance=0.03, comparison="relative"),)

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        # solver.load() raises if the limit cycle has not converged (the loader's NO-GO
        # discipline), so a reported Strouhal here always comes from a converged cycle.
        solve = solver.load(result)
        st = solve.scalars.get("strouhal")
        if st is None:
            raise ValueError(
                f"{self.name}: SolveResult.scalars['strouhal'] missing — the moving loader "
                "did not recover a response frequency (did the wake lock in?)."
            )
        return {"strouhal": st}

    def refined(self, ratio: float) -> OscillatingCylinderLockin:
        s = self._spec
        return OscillatingCylinderLockin(
            s.model_copy(
                update={
                    "n_radial": scaled_count(s.n_radial, ratio),
                    "n_azimuthal": scaled_count(s.n_azimuthal, ratio),
                }
            )
        )

    def refined_dt(self, ratio: float) -> OscillatingCylinderLockin:
        """Return a copy with a COARSER timestep (``max_courant`` scaled by ``ratio``), fixed mesh.

        The temporal analogue of :meth:`refined` for a combined space+time GCI (Stage 12): the
        moving-cylinder timestep is Courant-driven (``max_courant``), which :meth:`refined` cannot
        touch, so the temporal arm sweeps ``max_courant`` at fixed mesh. ``ratio == 1.0`` is the
        base (finest) timestep; ``ratio > 1`` is coarser (a larger Courant cap -> larger dt). The
        representative timestep scales ~linearly with ``max_courant``.
        """
        if ratio <= 0.0:
            raise ValueError(f"refined_dt ratio must be > 0, got {ratio}")
        s = self._spec
        return OscillatingCylinderLockin(
            s.model_copy(update={"max_courant": s.max_courant * ratio})
        )
