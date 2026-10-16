"""The dashboard's status is typed and its banner is per solver stack (Stage 22, ADR-051 D2)."""

from __future__ import annotations

import pytest
from aero.vv.dashboard import _STATUS_COLOR, DashboardEntry, render_dashboard
from aero.vv.status import VV_STATUSES
from pydantic import ValidationError

pytestmark = [pytest.mark.stage_22]


def _entry(name: str, status: str, stack: str = "openfoam", disposition: str = "active"):  # type: ignore[no-untyped-def]
    return DashboardEntry(case_name=name, status=status, stack=stack, disposition=disposition)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["PASS", "green", "skipped", "ok", ""])
def test_an_unknown_status_string_fails_loudly(bad: str) -> None:
    with pytest.raises(ValidationError):
        _entry("x", bad)


def test_an_unknown_stack_fails_loudly() -> None:
    with pytest.raises(ValidationError):
        _entry("x", "pass", stack="nekrs")


def test_every_status_has_a_colour_and_renders(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert set(_STATUS_COLOR) == set(VV_STATUSES)
    out = tmp_path / "d.html"
    render_dashboard([_entry(f"case_{s}", s) for s in VV_STATUSES], out)
    html = out.read_text()
    for status in VV_STATUSES:
        assert status.upper() in html


def test_frozen_and_deferred_are_never_rendered_as_a_pass(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert _STATUS_COLOR["frozen"] != _STATUS_COLOR["pass"]
    assert _STATUS_COLOR["deferred"] != _STATUS_COLOR["pass"]
    out = tmp_path / "d.html"
    render_dashboard(
        [
            _entry("a", "pass"),
            _entry("d", "deferred", disposition="deferred"),
            _entry("m6", "frozen", stack="su2", disposition="frozen"),
        ],
        out,
    )
    html = out.read_text()
    assert "openfoam: ALL GREEN" in html  # the deferred case does not gate the stack
    assert "su2: FROZEN" in html
    assert "ADR-051 D2" in html
