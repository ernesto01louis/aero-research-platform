"""The cost attribution — recovery, refusals, and the identity that makes it a bound.

ADR-040's central claim is that two of session 7's three named levers are refuted by an
upper bound rather than by argument. The bound is ``intercept_share``, and it is only a
bound because the shares provably partition unity. Both properties are tested here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.adapters.openfoam.solver_log import read_fluid_cost_history
from aero.vv.fsi.cost_model import CostModelError, attribute_step_cost

pytestmark = pytest.mark.stage_20

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/import-platform-only.yml"
_CAMPAIGN_LOG = Path("/mnt/aero-nfs/runs/hg2007_flexible_foil-20260810-144742/tutorial/Fluid.log")


def _synthetic(
    tmp_path: Path,
    *,
    p_iterations: list[int],
    u_iterations: list[int],
    seconds_per_p: float,
    seconds_per_u: float,
    intercept: float,
) -> Path:
    """A log whose per-step cost obeys a KNOWN linear model, to millisecond precision."""
    log = tmp_path / "Fluid.log"
    text = []
    cpu = 0.0
    for step, (n_p, n_u) in enumerate(zip(p_iterations, u_iterations, strict=True)):
        cpu += seconds_per_p * n_p + seconds_per_u * n_u + intercept
        text.append(f"Time = {(step + 1) * 2e-05:.12g}\n")
        text.append(
            f"GAMG:  Solving for p, Initial residual = 0.04, Final residual = 4e-08, "
            f"No Iterations {n_p}\n"
        )
        text.append(
            f"smoothSolver:  Solving for Ux, Initial residual = 0.0006, "
            f"Final residual = 2e-09, No Iterations {n_u}\n"
        )
        text.append(f"ExecutionTime = {cpu:.9f} s  ClockTime = {cpu:.9f} s\n")
    log.write_text("".join(text), encoding="utf-8")
    return log


def test_a_known_linear_model_is_recovered(tmp_path: Path) -> None:
    """Generate from known coefficients, fit, and get them back."""
    log = _synthetic(
        tmp_path,
        p_iterations=[900, 700, 1100, 850, 960, 1010, 780, 890],
        u_iterations=[4, 3, 5, 4, 4, 6, 3, 4],
        seconds_per_p=0.00287,
        seconds_per_u=0.0255,
        intercept=0.182,
    )
    attribution = attribute_step_cost(
        read_fluid_cost_history(log), groups={"pressure": ("p", "pcorr"), "momentum": ("Ux",)}
    )

    assert attribution.seconds_per_iteration_by_group["pressure"] == pytest.approx(0.00287)
    assert attribution.seconds_per_iteration_by_group["momentum"] == pytest.approx(0.0255)
    assert attribution.intercept_s == pytest.approx(0.182)
    assert attribution.r_squared == pytest.approx(1.0)
    assert attribution.dominant_group() == "pressure"


def test_the_shares_and_the_intercept_partition_unity(tmp_path: Path) -> None:
    """The identity that turns ``intercept_share`` from an estimate into a BOUND.

    A least-squares fit carrying an intercept column forces the residuals to sum to
    zero, so mean(y) == mean(prediction) and the shares add to exactly one. Without
    this, "the overhead levers are capped at 6 %" would be a guess.
    """
    rng = np.random.default_rng(20)
    n = 60
    log = _synthetic(
        tmp_path,
        p_iterations=[int(x) for x in rng.integers(400, 1200, n)],
        u_iterations=[int(x) for x in rng.integers(2, 9, n)],
        seconds_per_p=0.0031,
        seconds_per_u=0.02,
        intercept=0.25,
    )
    attribution = attribute_step_cost(
        read_fluid_cost_history(log), groups={"pressure": ("p",), "momentum": ("Ux",)}
    )

    total = sum(attribution.share_by_group.values()) + attribution.intercept_share
    assert total == pytest.approx(1.0, abs=1e-9)


def test_a_rank_deficient_design_is_refused(tmp_path: Path) -> None:
    """Two regressors that move together have no identifiable split.

    Least squares would return one arbitrary answer out of an infinite family, and it
    would look exactly like a measurement. This is the plausible-wrong-number failure
    class this stage keeps finding, so it raises.
    """
    counts = [900, 700, 1100, 850, 960, 1010, 780, 890]
    log = _synthetic(
        tmp_path,
        p_iterations=counts,
        u_iterations=counts,  # perfectly collinear with p
        seconds_per_p=0.003,
        seconds_per_u=0.001,
        intercept=0.2,
    )
    with pytest.raises(CostModelError, match="rank-deficient"):
        attribute_step_cost(
            read_fluid_cost_history(log), groups={"pressure": ("p",), "momentum": ("Ux",)}
        )


def test_too_few_steps_for_the_parameter_count_is_refused(tmp_path: Path) -> None:
    """A fit with as many observations as parameters interpolates its own noise."""
    log = _synthetic(
        tmp_path,
        p_iterations=[900, 700, 1100],
        u_iterations=[4, 3, 5],
        seconds_per_p=0.003,
        seconds_per_u=0.02,
        intercept=0.2,
    )
    with pytest.raises(CostModelError, match="cannot support"):
        attribute_step_cost(
            read_fluid_cost_history(log), groups={"pressure": ("p",), "momentum": ("Ux",)}
        )


def test_no_groups_is_refused(tmp_path: Path) -> None:
    log = _synthetic(
        tmp_path,
        p_iterations=[900] * 8,
        u_iterations=[4] * 8,
        seconds_per_p=0.003,
        seconds_per_u=0.02,
        intercept=0.2,
    )
    with pytest.raises(CostModelError, match="nothing to attribute"):
        attribute_step_cost(read_fluid_cost_history(log), groups={})


def test_a_negative_coefficient_is_reported_not_clipped(tmp_path: Path) -> None:
    """A negative cost per iteration means the model does not describe the run.

    Clipping it to zero would let a bad fit read as a good one and would break the
    partition-of-unity identity that makes the bound a bound.
    """
    # Cost falls as the iteration count rises: physically impossible, so the fit must
    # say so rather than quietly present a non-negative split.
    log = _synthetic(
        tmp_path,
        p_iterations=[100, 300, 500, 700, 900, 1100, 1300, 1500],
        u_iterations=[4, 4, 4, 4, 4, 4, 4, 4],
        seconds_per_p=-0.001,
        seconds_per_u=0.0,
        intercept=3.0,
    )
    attribution = attribute_step_cost(read_fluid_cost_history(log), groups={"pressure": ("p",)})

    assert attribution.seconds_per_iteration_by_group["pressure"] < 0.0
    assert attribution.share_by_group["pressure"] < 0.0
    total = sum(attribution.share_by_group.values()) + attribution.intercept_share
    assert total == pytest.approx(1.0, abs=1e-9)


def test_the_import_fence_names_this_module() -> None:
    """``aero/`` core is stdlib + numpy + pydantic; a new module must be fenced by name.

    Named rather than left to ride in transitively, so a future ``import scipy`` here is
    a named CI failure instead of a mystery (the fence's own convention).
    """
    assert "aero.vv.fsi.cost_model" in _WORKFLOW.read_text(encoding="utf-8")


def test_the_campaign_record_attributes_to_the_pressure_solve() -> None:
    """The ADR-040 datum: GAMG dominates, and the overhead levers are capped by it.

    ``intercept_share`` bounds every lever that attacks per-step overhead — the
    ``forces1`` field writes, the preCICE exchange, the adapter checkpoint. Fluid
    subcycling reclaims at most that share (only 1 in K of it recurs) plus the run's
    non-CPU wall; neither is within an order of magnitude of the 15.5x being sought.
    """
    if not _CAMPAIGN_LOG.exists():
        pytest.skip("the I4 campaign log is on NFS and this box cannot see it")
    attribution = attribute_step_cost(
        read_fluid_cost_history(_CAMPAIGN_LOG),
        groups={"gamg_pressure": ("p", "pcorr"), "momentum": ("Ux", "Uy")},
    )

    assert attribution.dominant_group() == "gamg_pressure"
    assert attribution.share_by_group["gamg_pressure"] == pytest.approx(0.908, abs=0.01)
    assert attribution.intercept_share == pytest.approx(0.060, abs=0.01)
    assert attribution.seconds_per_iteration_by_group["gamg_pressure"] == pytest.approx(
        0.00287, abs=1e-4
    )
    assert attribution.r_squared > 0.8
    total = sum(attribution.share_by_group.values()) + attribution.intercept_share
    assert total == pytest.approx(1.0, abs=1e-9)
