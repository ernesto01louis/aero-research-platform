"""Smoke tests — keep CI green; prove the consumer contract holds.

These two tests are the strongest local check we can run without an
orchestrator. ``test_campaign_yamls_parse`` is the load-bearing one:
it round-trips every YAML in ``campaigns/0*.yaml`` through the SDK's
``CampaignCreate.model_validate`` and will fail loudly if a future
edit drifts a YAML off the public contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ai_orchestrator_client import CampaignCreate

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_package_imports() -> None:
    """The namespace package imports cleanly."""
    import aero_research_platform

    assert aero_research_platform.__version__ == "0.0.0"


@pytest.mark.parametrize(
    "yaml_path",
    sorted((REPO_ROOT / "campaigns").glob("0*.yaml")),
    ids=lambda p: p.name,
)
def test_campaign_yaml_round_trips_through_sdk(yaml_path: Path) -> None:
    """Each campaign YAML deserializes into the SDK's CampaignCreate.

    This is the contract test: if the orchestrator's CampaignCreate
    schema drifts in a breaking way, this test fails and we know to
    bump the SDK pin in pyproject.toml. If a YAML drifts off the
    contract, we know which one.
    """
    data = yaml.safe_load(yaml_path.read_text())
    # Extra top-level fields like `budget_total_usd` are silently
    # ignored by the SDK's `extra="ignore"` config — that's intentional
    # and documented in RUNBOOK.md § "budget_total_usd current behavior".
    CampaignCreate(**data)
