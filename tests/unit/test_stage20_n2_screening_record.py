"""The screening record ranks candidates and must never be mistaken for a sizing.

ADR-039 I4's "no rate from a transient" rule exists because Stage 19 was off by 3.5-9.6x
extrapolating one. This screen is weaker still: fluid-only, static mesh, uniform initial
fields, 20 steps. Its control runs at 1.013 s/step against the campaign's measured 3.041,
because the deforming mesh makes the pressure system about three times harder. So the
record has to say what it may be used for, in the record, and that has to be enforced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECORD = _REPO_ROOT / "data/vv/stage20_n2_screening.json"


def _record() -> dict:
    return json.loads(_RECORD.read_text(encoding="utf-8"))


def _driver_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import stage20_hg2007_flexible_foil  # type: ignore[import-not-found]

    return stage20_hg2007_flexible_foil


def test_the_record_says_it_cannot_size_anything() -> None:
    """The admissibility statement lives IN the record, not only in the ADR beside it."""
    admissibility = _record()["admissibility"]
    assert "RANKS ONLY" in admissibility
    assert "may NOT size" in admissibility
    assert "COUPLED" in admissibility
    assert _record()["gated"] is False


def test_the_control_is_the_adr039_stack() -> None:
    """A sweep whose control is not the incumbent measures nothing about the incumbent."""
    control = _record()["candidates"]["s0_control"]
    assert control["stack"]["p_smoother"] == "GaussSeidel"
    assert control["stack"]["n_outer_correctors"] == 2
    assert control["speedup_vs_control"] == pytest.approx(1.0)


def test_the_smoother_alone_is_the_largest_single_lever() -> None:
    """The finding ADR-040 rests on, and the one that was not in anybody's hypothesis list.

    GAMG's coarse-grid correction was not working under a plain Gauss-Seidel smoother on
    a C-grid of aspect ratio ~310: 302 iterations per step became 51 for one token.
    """
    candidates = _record()["candidates"]
    smoother_only = candidates["s1_dicgaussseidel"]

    assert smoother_only["speedup_vs_control"] > 2.0
    assert (
        smoother_only["gamg_iterations_per_step"]
        < 0.25 * (candidates["s0_control"]["gamg_iterations_per_step"])
    )
    # And the hypothesis the repo's own docstring records for extreme aspect ratios is not it.
    assert candidates["s4_pcg_dic"]["speedup_vs_control"] < 1.2


def test_parallelism_is_recorded_as_the_weaker_lever_with_its_turnover() -> None:
    """8 ranks is slower than 6. A record that stopped at 6 would imply a curve that rises."""
    ranks = _record()["strong_scaling"]["ranks"]
    assert ranks["6"]["parallel_efficiency"] < 0.5
    assert ranks["8"]["seconds_per_step"] > ranks["6"]["seconds_per_step"]
    assert "contention" in _record()["strong_scaling"]["note"].lower()


def test_the_l_ladder_records_why_mpirun_must_sit_inside_the_uid_drop() -> None:
    """Measured, not reasoned: as root OpenMPI refuses outright.

    This is what makes `build_apptainer_exec(mpi_n=...)` the WRONG seam for the coupled
    launcher — it would hoist mpirun outside `setpriv` and run the wrapper's `mkdir` as
    root on every rank.
    """
    ladder = _record()["l_ladder"]
    assert ladder["L1_mpirun_in_sif"]["passed"] is True
    assert "REFUSED" in ladder["L1_mpirun_in_sif"]["as_root"]
    assert "build_participant_command" in ladder["L1_mpirun_in_sif"]["consequence"]
    # L2: the readout globs the case root only, so this decides whether it still works.
    assert ladder["L2_postprocessing_location"]["passed"] is True
    assert "CASE ROOT" in ladder["L2_postprocessing_location"]["measured"]


def test_the_verdict_states_the_ceiling_consequence() -> None:
    """A speed-up that still misses the ceiling is a budget finding, and must read as one."""
    verdict = _record()["verdict"]
    assert "14-day ceiling" in verdict
    assert "out of reach" in verdict
    assert "UNCONTENDED" in verdict


def test_the_embedded_block_is_adr039s() -> None:
    assert _record()["preregistered_gate_block"] == _driver_module().PREREGISTERED_GATE_BLOCK
