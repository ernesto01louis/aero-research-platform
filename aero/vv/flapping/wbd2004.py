"""Rigid 2-D flapping wing in hover — stroke-averaged lift vs Wang-Birch-Dickinson (2004).

The Stage-14 flagship validation rung (VALIDATE-AGAINST-EXPERIMENT). A thin elliptic wing
performs the WBD idealised flapping stroke (sinusoidal translation + sinusoidal pitch,
alpha0 = 90 deg, beta = 45 deg, stroke A0/c = 2.8, Re = 75) in a quiescent domain. Three
rotation timings — advanced / symmetrical / delayed (pitch phase phi = +45 / 0 / -45 deg) —
are the Dickinson (1999) lift-enhancement signature.

**Gated quantity: the symmetrical-rotation stroke-averaged mean lift coefficient**, anchored
to the WBD *experiment* (their 3-D robotic-wing measurement, mean C_L = 0.86). This is the
robust anchor: WBD's own 2-D computation reproduced it to within ~5 % (0.82), and 2-D matches
3-D well for advanced/symmetrical lift and all drag. The **delayed** timing is a documented 2-D
failure (their own 2-D under-predicts the delayed mean lift ~2x with a phase shift), so it is
carried as a DIAGNOSTIC, never gated. The advanced > symmetrical > delayed ordering and the
phase-resolved lift/drag traces are additional (non-gated) evidence.

Coefficients use the WBD normalisation (peak quasi-steady force; :mod:`aero.postprocess.
flapping_forces`), reproducing the paper's reported numbers 1:1. Reference values and their
digitization/model-form uncertainty are in
``data/references/flapping/wbd2004_2d_ellipse/reference.md``; the acceptance band is
pre-registered in ``docs/vv/stage14-preregistration.md`` (fixed before any campaign run).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from aero.adapters.openfoam.flapping_wing import FlappingWingSpec
from aero.adapters.openfoam.motion import FlappingMotionSpec
from aero.vv._base import (
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
    scaled_count,
)

RotationTiming = Literal["symmetrical", "advanced", "delayed"]

# WBD 2004 idealised kinematics (their Eqs 10-11, baseline stroke A0/c = 2.8).
_PITCH_MEAN_DEG = 90.0  # alpha0
_PITCH_AMP_DEG = 45.0  # beta
_STROKE_RATIO = 2.8  # A0 / c
_REYNOLDS = 75.0  # Re = pi f A0 c / nu at A0/c = 2.8
_U_REF = 1.0  # nondimensional: choose f so U_max = omega * (A0/2) = 1
# Rotation-timing phase phi (deg): advanced leads reversal, delayed lags (Dickinson 1999).
_TIMING_PHASE: dict[str, float] = {"symmetrical": 0.0, "advanced": 45.0, "delayed": -45.0}

# Pre-registered acceptance band for the gated symmetrical mean C_L (docs/vv/
# stage14-preregistration.md). A relative tolerance vs the WBD experiment; NEVER relaxed to
# pass (a miss is investigated / documented as a NO-GO).
_MEAN_CL_TOLERANCE = 0.25


def _frequency_for_reference() -> float:
    """f such that U_max = omega * (A0/2) = _U_REF, with A0 = _STROKE_RATIO * chord (chord=1)."""
    # U_max = 2*pi*f * (A0/2) = pi f A0  => f = U_ref / (pi * A0)
    import math

    return _U_REF / (math.pi * _STROKE_RATIO)


def _variant_name(timing: str) -> str:
    """Registry key. The symmetrical (gated) case keeps the base name."""
    return "flapping_wing_wbd2004" if timing == "symmetrical" else f"flapping_wing_wbd2004_{timing}"


class FlappingWingWBD2004:
    """Rigid 2-D flapping wing (WBD 2004, A0/c=2.8, Re=75) — stroke-averaged lift vs experiment."""

    name = "flapping_wing_wbd2004"
    description = (
        "Rigid 2-D elliptic flapping wing in hover (WBD 2004, A0/c=2.8, Re=75, symmetrical "
        "rotation) — stroke-averaged mean lift coefficient vs the robotic-wing experiment."
    )
    sweep_metric = "mean_lift_coefficient"

    def __init__(
        self,
        spec: FlappingWingSpec | None = None,
        *,
        rotation_timing: RotationTiming = "symmetrical",
        mesh_motion: Literal["overset", "morph"] = "overset",
    ) -> None:
        self._timing = rotation_timing if spec is None else _timing_of(spec)
        self.name = _variant_name(self._timing)
        self.description = (
            "Rigid 2-D elliptic flapping wing in hover (WBD 2004, A0/c=2.8, Re=75, "
            f"{self._timing} rotation) — stroke-averaged mean lift coefficient vs experiment."
        )
        if spec is None:
            f = _frequency_for_reference()
            motion = FlappingMotionSpec(
                stroke_amplitude=0.5 * _STROKE_RATIO,  # A0/2, chord = 1
                frequency=f,
                pitch_amplitude_deg=_PITCH_AMP_DEG,
                pitch_phase_deg=_TIMING_PHASE[rotation_timing],
                pitch_mean_deg=_PITCH_MEAN_DEG,
                ramp_cycles=2.0,  # gentle start; discarded before the converged tail
            )
            spec = FlappingWingSpec(
                name=self.name,
                reynolds=_REYNOLDS,
                motion=motion,
                mesh_motion=mesh_motion,
                # ~24 flapping periods: settle + ramp (~6-8) then a converged tail >= 16 cycles,
                # so the batch-means statistical U95 can reach `reliable` (N_eff >= 8).
                end_time_cycles=24.0,
                write_phases_per_cycle=16,
            )
        self._spec = spec

    def case_spec(self) -> FlappingWingSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        # Anchor = the WBD *experiment* (3-D robotic wing), keyed on the rotation-timing phase.
        cl = load_scalar_csv(
            repo_root
            / "data"
            / "references"
            / "flapping"
            / "wbd2004_2d_ellipse"
            / "mean_coefficients.csv",
            key_col="pitch_phase_deg",
            key=_TIMING_PHASE[self._timing],
            value_col="mean_cl_experiment",
        )
        return ReferenceData(
            case_name=self.name,
            source="Wang, Birch & Dickinson 2004 (J Exp Biol 207:449-460), robotic-wing "
            "stroke-averaged mean lift (WBD normalisation)",
            scalars={"mean_lift_coefficient": cl},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # ONLY the stroke-averaged mean lift is gated (the robust, text-sourced anchor). The
        # delayed timing is a known 2-D failure and is reported, not gated; drag + the
        # phase-resolved traces are diagnostics produced by the reportable/LEV scripts.
        return (
            MetricSpec(
                name="mean_lift_coefficient",
                kind="scalar",
                tolerance=_MEAN_CL_TOLERANCE,
                comparison="relative",
            ),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        # solver.load() raises unless the hover limit cycle converged; mean_lift_coefficient is
        # the WBD-normalised stroke-average over the converged cycles.
        solve = solver.load(result)
        mean_cl = solve.scalars.get("mean_lift_coefficient")
        if mean_cl is None:
            raise ValueError(
                f"{self.name}: SolveResult.scalars['mean_lift_coefficient'] missing — the "
                "flapping loader did not run (is this a FlappingWingSpec?)."
            )
        out: dict[str, float | Series] = {"mean_lift_coefficient": mean_cl}
        # mean drag: a diagnostic (mean_lift is the gated + Richardson target).
        mean_cd = solve.scalars.get("mean_drag_coefficient")
        if mean_cd is not None:
            out["mean_drag_coefficient"] = mean_cd
        return out

    def refined(self, ratio: float) -> FlappingWingWBD2004:
        s = self._spec
        return FlappingWingWBD2004(
            s.model_copy(
                update={
                    "n_radial": scaled_count(s.n_radial, ratio),
                    "n_azimuthal": scaled_count(s.n_azimuthal, ratio),
                }
            )
        )

    def refined_dt(self, ratio: float) -> FlappingWingWBD2004:
        """A copy with a COARSER timestep (``max_courant`` scaled by ``ratio``), fixed mesh.

        The temporal arm of a space+time GCI (Stage-13 pattern): the moving-mesh timestep is
        Courant-driven, so ``refined`` (mesh counts) cannot touch it. ``ratio == 1`` is the
        finest dt; ``ratio > 1`` coarsens.
        """
        if ratio <= 0.0:
            raise ValueError(f"refined_dt ratio must be > 0, got {ratio}")
        s = self._spec
        return FlappingWingWBD2004(s.model_copy(update={"max_courant": s.max_courant * ratio}))


def _timing_of(spec: FlappingWingSpec) -> RotationTiming:
    """Recover the rotation timing from a spec's pitch phase (for round-tripping copies)."""
    phi = spec.motion.pitch_phase_deg
    for timing, phase in _TIMING_PHASE.items():
        if abs(phi - phase) < 1.0e-6:
            return timing  # type: ignore[return-value]
    raise ValueError(f"unrecognised rotation-timing phase {phi} deg (expected -45/0/+45)")
