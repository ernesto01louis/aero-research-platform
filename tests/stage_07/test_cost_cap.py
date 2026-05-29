"""Unit tests for aero.orchestration.cost_cap — Stage 07 budget enforcement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from aero.orchestration.cost_cap import (
    CAP_ENV_VAR,
    DEFAULT_CAP_USD,
    CostCap,
    CostCapExceeded,
    CostCapOrphanedEntry,
    Ledger,
    LedgerEntry,
)

pytestmark = pytest.mark.stage_07


def _new_cap(tmp_path: Path, *, cap_usd: float | None = None) -> CostCap:
    """Helper: a CostCap whose ledger lives in tmp_path."""
    return CostCap(ledger_path=tmp_path / "runpod-ledger.json", cap_usd=cap_usd)


def test_default_cap_is_50_usd_when_no_env_or_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CAP_ENV_VAR, raising=False)
    cap = CostCap(ledger_path=Path("/tmp/unused"))
    assert cap.cap_usd == DEFAULT_CAP_USD


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CAP_ENV_VAR, "125.5")
    cap = CostCap(ledger_path=Path("/tmp/unused"))
    assert cap.cap_usd == 125.5


def test_ctor_arg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CAP_ENV_VAR, "10")
    cap = CostCap(ledger_path=Path("/tmp/unused"), cap_usd=200.0)
    assert cap.cap_usd == 200.0


def test_negative_cap_rejected() -> None:
    with pytest.raises(ValueError, match="cap_usd must be > 0"):
        CostCap(ledger_path=Path("/tmp/unused"), cap_usd=-1.0)


def test_ensure_ledger_creates_empty_when_missing(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=50.0)
    assert not (tmp_path / "runpod-ledger.json").exists()
    ledger = cap.ensure_ledger()
    assert (tmp_path / "runpod-ledger.json").exists()
    assert ledger.cap_usd == 50.0
    assert ledger.entries == []


def test_check_budget_passes_with_empty_ledger(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=50.0)
    ledger = cap.check_budget(0.50)
    assert ledger.month_to_date_usd() == 0.0


def test_check_budget_refuses_when_projected_exceeds_cap(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=10.0)
    with pytest.raises(CostCapExceeded, match="projected"):
        cap.check_budget(11.0)


def test_check_budget_refuses_zero_or_negative_estimate(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=50.0)
    with pytest.raises(ValueError, match="estimated_usd must be > 0"):
        cap.check_budget(0)


def test_record_launch_then_check_sees_projected_cost(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=50.0)
    cap.record_launch(
        run_id="test-1",
        pod_type="NVIDIA H100 PCIe",
        projected_hours=0.25,
        hourly_rate_usd=2.49,
    )
    # 0.25 * 2.49 = 0.6225 USD recorded; 49.5 more would exceed cap.
    with pytest.raises(CostCapExceeded):
        cap.check_budget(50.0)
    # 49 more is fine.
    cap.check_budget(49.0)


def test_record_termination_amends_entry_and_tags_ok(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=50.0)
    cap.record_launch(
        run_id="test-2",
        pod_type="NVIDIA H100 PCIe",
        projected_hours=0.5,
        hourly_rate_usd=2.49,
    )
    updated = cap.record_termination(run_id="test-2", actual_hours=0.4)
    assert updated.tag == "ok"
    assert updated.actual_hours == 0.4
    assert updated.actual_cost_usd == pytest.approx(0.4 * 2.49)
    assert updated.terminated_at is not None
    # MTD now uses actual, not projected.
    ledger = cap.ensure_ledger()
    assert ledger.month_to_date_usd() == pytest.approx(0.4 * 2.49)


def test_orphaned_entry_refuses_subsequent_launches(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=50.0)
    cap.record_launch(
        run_id="test-3",
        pod_type="NVIDIA H100 PCIe",
        projected_hours=0.1,
        hourly_rate_usd=2.49,
    )
    cap.record_termination(run_id="test-3", actual_hours=0.1, tag="orphaned")
    with pytest.raises(CostCapOrphanedEntry, match="orphaned"):
        cap.check_budget(0.1)


def test_record_termination_without_matching_running_raises(tmp_path: Path) -> None:
    cap = _new_cap(tmp_path, cap_usd=50.0)
    with pytest.raises(Exception, match="no 'running' entry"):
        cap.record_termination(run_id="ghost", actual_hours=0.1)


def test_month_to_date_only_counts_this_calendar_month(tmp_path: Path) -> None:
    """Entries from prior months do not count against the current cap."""
    cap = _new_cap(tmp_path, cap_usd=10.0)
    # Inject a prior-month entry into the ledger directly.
    last_month = datetime.now(UTC).replace(day=1) - timedelta(days=15)
    ledger = cap.ensure_ledger()
    ledger.entries.append(
        LedgerEntry(
            run_id="prior",
            pod_type="NVIDIA H100 PCIe",
            started_at=last_month,
            projected_hours=4.0,
            hourly_rate_usd=2.49,
            projected_cost_usd=4.0 * 2.49,
            terminated_at=last_month + timedelta(hours=4),
            actual_hours=4.0,
            actual_cost_usd=4.0 * 2.49,
            tag="ok",
        )
    )
    cap._write_ledger(ledger)
    # Prior-month $9.96 does NOT count; cap of $10 allows a fresh $9.99 launch.
    ledger2 = cap.check_budget(9.99)
    assert ledger2.month_to_date_usd() == 0.0


def test_ledger_persists_across_costcap_instances(tmp_path: Path) -> None:
    """Two CostCap instances pointing at the same path share state."""
    cap1 = _new_cap(tmp_path, cap_usd=50.0)
    cap1.record_launch(
        run_id="persisted",
        pod_type="NVIDIA H100 PCIe",
        projected_hours=0.5,
        hourly_rate_usd=2.49,
    )
    cap2 = _new_cap(tmp_path, cap_usd=50.0)
    ledger = cap2.ensure_ledger()
    assert len(ledger.entries) == 1
    assert ledger.entries[0].run_id == "persisted"


def test_ledger_entry_billed_cost_falls_back_to_projected() -> None:
    e = LedgerEntry(
        run_id="rt",
        pod_type="NVIDIA H100 PCIe",
        started_at=datetime.now(UTC),
        projected_hours=1.0,
        hourly_rate_usd=2.49,
        projected_cost_usd=2.49,
        tag="running",
    )
    assert e.billed_cost_usd == 2.49
    terminated = e.model_copy(
        update={
            "terminated_at": datetime.now(UTC),
            "actual_hours": 0.5,
            "actual_cost_usd": 1.245,
            "tag": "ok",
        }
    )
    assert terminated.billed_cost_usd == 1.245


def test_ledger_roundtrip_json(tmp_path: Path) -> None:
    """A persisted ledger reloads identically (Pydantic round-trip safety)."""
    cap = _new_cap(tmp_path, cap_usd=42.0)
    cap.record_launch(
        run_id="rt",
        pod_type="NVIDIA H100 PCIe",
        projected_hours=0.1,
        hourly_rate_usd=2.49,
    )
    raw = (tmp_path / "runpod-ledger.json").read_text(encoding="utf-8")
    ledger = Ledger.model_validate_json(raw)
    assert ledger.cap_usd == 42.0
    assert len(ledger.entries) == 1
    assert ledger.entries[0].run_id == "rt"
    assert ledger.entries[0].tag == "running"
