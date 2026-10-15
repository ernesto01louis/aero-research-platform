"""scripts/release_readiness.py: "all required CI green" is verified, never assumed (ADR-049 R2)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "release_readiness", REPO / "scripts" / "release_readiness.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_readiness"] = module
    spec.loader.exec_module(module)
    return module


rr = _load()
GH = "o/r"
HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
).stdout.strip()


class FakeApi:
    """A GitHub API double: check-runs per sha (paginated), statuses, PRs per commit."""

    def __init__(
        self, runs: dict[str, list[dict[str, Any]]], pulls: list[dict[str, Any]] | None = None
    ) -> None:
        self.runs, self.pulls, self.calls = runs, pulls or [], []

    def __call__(self, path: str) -> Any:
        self.calls.append(path)
        if "/check-runs" in path:
            sha = path.split("/commits/", 1)[1].split("/", 1)[0]
            page = int(path.rsplit("page=", 1)[1])
            items = self.runs.get(sha, [])
            return {"check_runs": items[(page - 1) * 100 : page * 100]}
        if path.endswith("/status"):
            return {"statuses": []}
        if path.endswith("/pulls"):
            return self.pulls
        raise AssertionError(path)


def _registry() -> dict[str, Any]:
    return json.loads((REPO / ".github" / "required-checks.json").read_text(encoding="utf-8"))


def _all(conclusion: str = "success", pr_only: bool = False) -> list[dict[str, Any]]:
    return [
        {"name": e["context"], "conclusion": conclusion, "completed_at": "2026-10-20T10:00:00Z"}
        for e in _registry()["contexts"]
        if e["pr_only"] == pr_only
    ]


def _ctx(api: FakeApi) -> Any:
    return rr.Ctx(
        repo=REPO, tag=None, ci=False, online=True, api=api, today=dt.date(2026, 10, 20), gh_repo=GH
    )


def _pull(head_sha: str) -> list[dict[str, Any]]:
    return [{"number": 1, "merged_at": "2026-10-20T09:00:00Z", "head": {"sha": head_sha}}]


def test_every_context_green_passes() -> None:
    # The PR head is HEAD itself here, so the tree trivially matches.
    api = FakeApi({HEAD: _all() + _all(pr_only=True)}, _pull(HEAD))
    assert rr.check_required_contexts(_ctx(api)) == []


@pytest.mark.parametrize("bad", ["skipped", "neutral", "cancelled", "failure", "timed_out"])
def test_anything_but_success_is_not_green(bad: str) -> None:
    runs = _all()
    runs[0]["conclusion"] = bad
    api = FakeApi({HEAD: runs + _all(pr_only=True)}, _pull(HEAD))
    problems = rr.check_required_contexts(_ctx(api))
    assert any(repr(bad) in p for p in problems)


def test_a_missing_context_is_not_green() -> None:
    api = FakeApi({HEAD: _all()[1:] + _all(pr_only=True)}, _pull(HEAD))
    assert any("'missing'" in p for p in rr.check_required_contexts(_ctx(api)))


def test_the_latest_run_of_a_context_decides() -> None:
    first = _all()[0]
    older = {**first, "conclusion": "success", "completed_at": "2026-10-19T00:00:00Z"}
    newer = {**first, "conclusion": "failure", "completed_at": "2026-10-20T11:00:00Z"}
    api = FakeApi({HEAD: [older, newer, *_all()[1:], *_all(pr_only=True)]}, _pull(HEAD))
    assert any(first["name"] in p for p in rr.check_required_contexts(_ctx(api)))


def test_check_runs_are_read_across_pages() -> None:
    filler = [
        {"name": f"other-{i}", "conclusion": "success", "completed_at": "x"} for i in range(150)
    ]
    api = FakeApi({HEAD: filler + _all() + _all(pr_only=True)}, _pull(HEAD))
    assert rr.check_required_contexts(_ctx(api)) == []
    assert sum("check-runs" in c for c in api.calls) >= 2


def test_pr_only_contexts_need_exactly_one_merged_pr_whose_head_is_fetched() -> None:
    api = FakeApi({HEAD: _all() + _all(pr_only=True)}, [])
    assert any("0 merged PRs" in p for p in rr.check_required_contexts(_ctx(api)))
    absent = "f" * 40  # a PR head this clone does not have: its tree cannot be compared
    api = FakeApi({HEAD: _all(), absent: _all(pr_only=True)}, _pull(absent))
    assert any("is not fetched" in p for p in rr.check_required_contexts(_ctx(api)))


def test_offline_is_never_reported_green() -> None:
    c = rr.Ctx(
        repo=REPO,
        tag=None,
        ci=False,
        online=False,
        api=None,
        today=dt.date(2026, 10, 20),
        gh_repo=GH,
    )
    assert rr.check_required_contexts(c) != []


def test_the_body_excludes_acknowledgements_references_and_footnotes() -> None:
    md = "# Summary\n\nreal text\n[^1]: footnote " + rr.L1 + "\n\n# Acknowledgements\n\n" + rr.L1
    assert rr.L1 not in rr._body(md)
    assert rr.L1 in rr._body("# Summary\n\n" + rr.L1 + "\n\n# References\n")


@pytest.mark.parametrize(
    ("line", "bad"),
    [
        ("pip install aero", True),
        ("pip install aero[provenance]", True),
        ("`pip install aero`", True),
        ("pip install aero-research-platform", False),
        ("pip install aero_research", False),
        ("python -m pip install --no-deps aero-0.1.0-py3-none-any.whl", False),
    ],
)
def test_bare_pip_install_is_recognised(line: str, bad: bool) -> None:
    assert bool(rr.BARE_PIP.search(line)) is bad
    assert rr._bare_pip(line) is bad


@pytest.mark.parametrize(
    ("line", "bad"),
    [
        # CONSTITUTION Invariant 1 (ratified in #57) warns against it; a warning is not an instruction.
        (
            "  module. It installs from the checkout, never `pip install aero`: that PyPI name",
            False,
        ),
        ("Do not pip install aero.", False),
        ("There is no `pip install aero`.", False),
        ("Never mind; pip install aero", True),
        ("never `pip install aero`, but then: pip install aero[cad]", True),
    ],
)
def test_a_warning_against_bare_pip_is_not_an_instruction(line: str, bad: bool) -> None:
    assert rr._bare_pip(line) is bad


def test_a_required_phrase_is_found_when_wrapped_and_set_in_bold() -> None:
    # The release notes and the paper wrap L1 across source lines; the notes also set it in bold.
    words = rr.L1.split(" ")
    wrapped = " ".join(words[:12]) + "\n" + " ".join(words[12:])
    assert rr.L1 not in wrapped
    assert rr.L1 in rr._flat(rr._body("# Summary\n\n**" + wrapped + "**\n"))
    assert "certified optimum" in rr._flat("a certified\noptimum")


def _here() -> Any:
    return rr.Ctx(
        repo=REPO,
        tag=None,
        ci=False,
        online=False,
        api=None,
        today=dt.date(2026, 10, 20),
        gh_repo=GH,
    )


def test_the_limitation_and_install_checks_hold_in_this_checkout() -> None:
    assert rr.check_limitation_in_body(_here()) == []
    assert rr.check_install_text(_here()) == []


def test_the_hard_donts_hold_in_this_checkout() -> None:
    c = rr.Ctx(
        repo=REPO,
        tag=None,
        ci=False,
        online=False,
        api=None,
        today=dt.date(2026, 10, 20),
        gh_repo=GH,
    )
    problems = rr.check_hard_donts(c)
    # The evidence tag may not be fetched in a shallow CI clone; everything else must hold.
    assert [p for p in problems if "stage-20-evidence" not in p] == []


def test_a_crashing_check_fails_rather_than_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: Any) -> list[str]:
        raise RuntimeError("nope")

    monkeypatch.setattr(rr, "RELEASE_CHECKS", [("boom", boom)])
    c = rr.Ctx(
        repo=REPO,
        tag=None,
        ci=True,
        online=False,
        api=None,
        today=dt.date(2026, 10, 20),
        gh_repo=GH,
    )
    [result] = rr.run("release", c)
    assert result.problems and "crashed" in result.problems[0]
