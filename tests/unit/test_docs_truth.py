"""Docs match reality (CLAUDE.md Hard Rule 9; ADR-049 H-05, H-25, H-26, H-30).

Each test pins one claim that drifted before Stage 21, so the drift cannot quietly return.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
# The name `aero` on PyPI is an unrelated project; `pip install aero` installs the wrong thing.
BARE_PIP = re.compile(r"pip install aero(?![-\w])")
INSTALL_DOCS = ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CITATION.cff")
REQUIRED_AT_STAGE_21_OPEN = (
    "ruff",
    "mypy (strict on aero/)",
    "pytest unit (py3.12)",
    "README STATUS block consistency",
    "enforce Conventional Commits on PR title and every commit",
    "import aero with no extras",
    "vv-required — stage-gated V&V",
    "fence",
    "small-signal-gate — Invariant 10",
    "data-origin-fence — Invariant 11",
)


def _text(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "rel", [*INSTALL_DOCS, *(str(p.relative_to(REPO)) for p in (REPO / "aero").rglob("*.py"))]
)
def test_no_bare_pip_install_aero(rel: str) -> None:
    hits = [n for n, line in enumerate(_text(rel).splitlines(), 1) if BARE_PIP.search(line)]
    assert hits == [], f"{rel}:{hits}: install from a clone (uv sync) or the Release wheel"


def test_contributing_lists_every_required_context() -> None:
    registry = REPO / ".github" / "required-checks.json"
    if registry.is_file():
        contexts = [
            e["context"] for e in json.loads(registry.read_text(encoding="utf-8"))["contexts"]
        ]
    else:
        contexts = list(REQUIRED_AT_STAGE_21_OPEN)
    text = _text("CONTRIBUTING.md")
    missing = [c for c in contexts if f"`{c}`" not in text]
    assert missing == []


@pytest.mark.parametrize(
    ("rel", "stale"),
    [
        ("CONTRIBUTING.md", "1 approving review"),
        ("CONTRIBUTING.md", "host TBD in Stage 02"),
        ("CONTRIBUTING.md", "auto_cite"),
        ("CONTRIBUTING.md", "production-budget"),
        ("SECURITY.md", "post-Stage 14"),
        ("SECURITY.md", "Stage 13 wires a self-hosted runner"),
        ("SECURITY.md", "CODEOWNERS-restricted PRs only"),
        ("SECURITY.md", "cost cap policies (Stage 13)"),
        ("README.md", "20-stage build map"),
        ("README.md", "will be reserved in"),
        ("CLAUDE.md", "Promoting to CONSTITUTION Invariant 10"),
        ("CLAUDE.md", "Promoting to CONSTITUTION"),
        (".github/PULL_REQUEST_TEMPLATE.md", "`production-budget` CI check"),
        ("aero/__init__.py", "aero[agentic]"),
    ],
)
def test_stale_claims_stay_gone(rel: str, stale: str) -> None:
    assert stale not in _text(rel)


def test_changelog_has_unreleased_and_a_link_for_every_version() -> None:
    text = _text("CHANGELOG.md")
    assert re.search(r"^## \[Unreleased\]", text, re.M)
    versions = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.M)
    links = set(re.findall(r"^\[(\d+\.\d+\.\d+|Unreleased)\]: https://", text, re.M))
    assert "Unreleased" in links
    assert [v for v in versions if v not in links] == []


def test_the_bug_report_requires_an_exact_identity() -> None:
    form = yaml.safe_load(_text(".github/ISSUE_TEMPLATE/bug_report.yml"))
    fields = {b.get("id"): b for b in form["body"] if b.get("id")}
    for required in ("version", "identity", "what"):
        assert fields[required]["validations"]["required"] is True
    assert "four-tuple" in fields["identity"]["attributes"]["label"].lower()
    assert (
        yaml.safe_load(_text(".github/ISSUE_TEMPLATE/config.yml"))["blank_issues_enabled"] is False
    )


def test_the_community_files_exist() -> None:
    for rel in ("CODE_OF_CONDUCT.md", "SECURITY.md", ".github/ISSUE_TEMPLATE/feature_request.yml"):
        assert (REPO / rel).is_file(), rel
    assert "## Support and governance" in _text("README.md")
