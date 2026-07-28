"""A registered V&V case with no run must render RED, not vanish (Stage 19).

`aero vv report` used to build its rows purely from what MLflow returned. A case that
went red and then stopped being re-run therefore dropped off the dashboard entirely, and
any "all green" judgement was taken over the survivors — so the production gate of
ADR-005 could be satisfied by attrition rather than by anyone fixing the physics. The
`missing` status is the fix, and it is styled as loudly as `fail` on purpose.
"""

from __future__ import annotations

import pytest
from aero.vv.dashboard import DashboardEntry, render_dashboard

pytestmark = [pytest.mark.stage_19]

_FAIL_RED = "#cf222e"


def test_missing_is_rendered_as_red_not_as_a_neutral_blank(tmp_path) -> None:
    """`missing` must be visually indistinguishable from `fail` — it is not "no news"."""
    out = tmp_path / "dash.html"

    render_dashboard(
        [
            DashboardEntry(case_name="turek_hron_fsi3", status="pass"),
            DashboardEntry(case_name="plunging_airfoil_hg2007", status="missing"),
        ],
        out,
    )
    html = out.read_text()

    assert "plunging_airfoil_hg2007" in html
    # The unevaluated case is coloured with the failure red, not the neutral grey that
    # `unknown` and unrecognised statuses fall back to.
    assert html.count(_FAIL_RED) >= 1
    assert "MISSING" in html
    # The property that actually guards the production gate: one unevaluated case is
    # enough to deny the ALL GREEN banner, even though every case that DID run passed.
    assert "ALL GREEN" not in html
    assert "ATTENTION NEEDED" in html


def test_all_green_still_reachable_when_every_case_passes(tmp_path) -> None:
    """The guard must not be a one-way ratchet — a genuinely clean suite still reads green."""
    out = tmp_path / "dash.html"

    render_dashboard(
        [
            DashboardEntry(case_name="turek_hron_fsi3", status="pass"),
            DashboardEntry(case_name="naca0012", status="pass"),
        ],
        out,
    )
    html = out.read_text()

    assert "ALL GREEN" in html
    assert "ATTENTION NEEDED" not in html


def test_an_unevaluated_case_is_not_silently_dropped(tmp_path) -> None:
    """Every entry handed in appears in the output — the dashboard never filters."""
    out = tmp_path / "dash.html"
    names = ["flat_plate_te", "bump_2d", "naca0012", "oscillating_cylinder_lockin"]

    render_dashboard(
        [DashboardEntry(case_name=n, status="missing") for n in names],
        out,
    )
    html = out.read_text()

    for name in names:
        assert name in html, f"{name} was dropped from the dashboard"
