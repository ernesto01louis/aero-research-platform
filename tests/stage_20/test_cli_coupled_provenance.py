"""What the CLI must say about a two-container run — and what it used to say instead.

Two of these were live faults rather than missing features. Both ride into MLflow tags, so
they are provenance-bearing fields written with values nobody computed:

* `_SOLVER_VERSIONS["precice"]` names **Nutils**, and the stage was derived from the SOLVER
  name (`precice -> "19"`). One adapter drives materially different physics — a Nutils solid
  for Turek-Hron, a CalculiX solid for Heathcote-Gursul across two containers — so a Stage-20
  bundle would have claimed a Nutils solid and Stage-19 provenance.
* `assert_provenance_describes` had **zero call sites**. It is ADR-038's real obligation, the
  one that replaced Stage 19's blanket refusal of gated multi-container runs, and without it
  a two-SIF run logs `container_sif_sha256` for the fluid alone and an empty roster: the
  record silently omits CalculiX.

The third is a design point rather than a fault: the FSI3 expectation was hard-wired into
`_build_solver`, which cannot be right for a second coupled case, because an authored case's
expectation is DERIVED from its own spec.
"""

from __future__ import annotations

import pytest
from aero.adapters.precice.case import CoupledCaseError, assert_provenance_describes
from aero.cli import _CASE_PROVENANCE, _SOLVER_SIF, _coupled_spec_or_none, _precice_expectation
from aero.provenance.four_fold import ContainerRef, ProvenanceTuple

from tests.stage_20._hg2007 import authored_spec

pytestmark = pytest.mark.stage_20


def _provenance(*containers: tuple[str, str]) -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40,
        dvc_input_hash="b" * 64,
        container_sif_sha256="c" * 64,
        config_hash="d" * 64,
        containers=tuple(ContainerRef(name=n, sha256=s) for n, s in containers),
    )


# --------------------------------------------------------------------------------------
# The two provenance faults
# --------------------------------------------------------------------------------------


def test_a_stage_20_run_does_not_inherit_stage_19s_stack_description() -> None:
    """The `precice` adapter's default names Nutils; Stage 20 runs CalculiX."""
    for case in ("hg2007_flexible_foil", "hg2007_rigid_foil"):
        stage, solver_version = _CASE_PROVENANCE[case]
        assert stage == "20"
        assert "CalculiX" in solver_version
        assert "Nutils" not in solver_version


def test_turek_hron_keeps_the_solver_derived_defaults() -> None:
    """The override is per-case, so Stage 19's record is untouched."""
    assert "turek_hron_fsi3" not in _CASE_PROVENANCE


def test_a_two_container_run_must_name_both_sifs() -> None:
    spec = authored_spec()
    assert spec.multi_container
    assert spec.container_of_record == "precice-fsi.sif"
    assert spec.extra_container_sifs == ("calculix-precice.sif",)

    # What the CLI computes for a coupled case: the roster from the spec, not the table.
    assert_provenance_describes(
        spec, _provenance(("calculix-precice.sif", "e" * 64), ("precice-fsi.sif", "c" * 64))
    )


def test_a_roster_that_omits_calculix_is_refused() -> None:
    """Exactly what the CLI produced before this commit: the fluid SIF and an empty roster."""
    spec = authored_spec()
    with pytest.raises(CoupledCaseError, match=r"calculix-precice\.sif"):
        assert_provenance_describes(spec, _provenance())


def test_the_solver_sif_table_cannot_express_a_two_container_run() -> None:
    """Why the SIFs are derived from the SPEC rather than by widening `_SOLVER_SIF`.

    The table is `dict[str, str]` feeding a single-SIF `compute_provenance`; there is no
    value it could hold that names both containers.
    """
    assert isinstance(_SOLVER_SIF["precice"], str)
    assert _SOLVER_SIF["precice"] == "precice-fsi.sif"
    assert all(isinstance(v, str) for v in _SOLVER_SIF.values())


def test_the_cli_recognises_a_coupled_spec_and_leaves_others_alone() -> None:
    assert _coupled_spec_or_none(authored_spec()) is not None
    assert _coupled_spec_or_none(object()) is None


# --------------------------------------------------------------------------------------
# The expectation registry
# --------------------------------------------------------------------------------------


def test_the_fsi3_expectation_is_no_longer_hard_wired_for_every_coupled_case() -> None:
    from aero.vv.fsi import TUREK_HRON_FSI3_EXPECTATION

    assert _precice_expectation("turek_hron_fsi3") is TUREK_HRON_FSI3_EXPECTATION
    assert _precice_expectation(None) is TUREK_HRON_FSI3_EXPECTATION


def test_an_authored_case_does_not_inherit_the_fsi3_expectation() -> None:
    """Inheriting it would assert FSI3's numerics — `Stress`, 1e-4, max-iterations 100 —
    against a configuration that legitimately carries `Force`, 5e-3 and 50, and the run
    would be refused before it started. The authored materializer asserts its own,
    derived from the spec, inside `write_precice_config`."""
    for case in ("hg2007_flexible_foil", "hg2007_rigid_foil"):
        assert _precice_expectation(case) is None
