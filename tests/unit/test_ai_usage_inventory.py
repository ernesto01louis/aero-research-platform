"""scripts/ai_usage_inventory.py: the paper's AI disclosure is checked against the commit it names.

The block records the commit it was generated at. A commit cannot contain its own hash, so the PR
that writes the block always lands one commit after the one it names. ``--check`` therefore
regenerates at the named commit and requires it to be a recent ancestor of ``--ref`` (Stage 21).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]
PAPER = "# AI usage disclosure\n\n<!-- AI-INVENTORY:START -->\n<!-- AI-INVENTORY:END -->\n"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "ai_usage_inventory", REPO / "scripts" / "ai_usage_inventory.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_usage_inventory"] = module
    spec.loader.exec_module(module)
    return module


inv = _load()


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args]
    return subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, check=True).stdout


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "paper.md").write_text(PAPER, encoding="utf-8")
    handoffs = tmp_path / "docs" / "handoffs"
    handoffs.mkdir(parents=True)
    for stage, model in ((1, "claude-a"), (2, "claude-a"), (3, "claude-b")):
        (handoffs / f"STAGE-0{stage}-x-DONE-2026-01-0{stage}.md").write_text(
            f"---\nstage: {stage}\nmodel: {model}\n---\n", encoding="utf-8"
        )
    _commit(tmp_path, "one\n\nCo-Authored-By: Claude X <noreply@anthropic.com>")
    _commit(tmp_path, "two")
    return tmp_path


def _run(repo: Path, *args: str) -> int:
    return int(inv.main([*args, "--repo", str(repo)]))


def test_the_block_is_generated_from_the_named_commit(repo: Path) -> None:
    assert _run(repo, "--write", "--ref", "main") == 0
    text = (repo / "paper" / "paper.md").read_text(encoding="utf-8")
    assert "trailers at `main` (" in text
    assert "Of the 2 commits on `main`, 1 carry" in text
    assert "`claude-a` (Stages 1\u20132); `claude-b` (Stage 3)" in text


def test_the_pr_that_writes_the_block_passes_the_check(repo: Path) -> None:
    assert _run(repo, "--write", "--ref", "main") == 0
    _commit(repo, "docs: regenerate the disclosure")  # the merge that lands it: one commit later
    assert _run(repo, "--check") == 0


def test_a_block_more_commits_behind_than_allowed_is_stale(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(repo, "--write", "--ref", "main") == 0
    _commit(repo, "docs: regenerate the disclosure")
    _commit(repo, "feat: later work")
    assert _run(repo, "--check") == 1
    assert "2 commits behind" in capsys.readouterr().err
    assert _run(repo, "--check", "--max-behind", "2") == 0


def test_an_edited_block_is_stale(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(repo, "--write", "--ref", "main") == 0
    paper = repo / "paper" / "paper.md"
    paper.write_text(paper.read_text(encoding="utf-8").replace("1 carry", "2 carry"), "utf-8")
    _commit(repo, "docs: hand-edit")
    assert _run(repo, "--check") == 1
    assert "differs from the record" in capsys.readouterr().err


def test_a_block_naming_a_commit_off_the_branch_is_stale(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "switch", "-q", "-c", "side")
    _commit(repo, "side work")
    assert _run(repo, "--write", "--ref", "side") == 0
    text = (repo / "paper" / "paper.md").read_text(encoding="utf-8")
    _git(repo, "switch", "-q", "main")
    (repo / "paper" / "paper.md").write_text(text, encoding="utf-8")
    _commit(repo, "docs: a block from another branch")
    assert _run(repo, "--check") == 1
    assert "not an ancestor" in capsys.readouterr().err


def test_a_handoff_added_after_the_named_commit_does_not_change_the_block(repo: Path) -> None:
    assert _run(repo, "--write", "--ref", "main") == 0
    (repo / "docs" / "handoffs" / "STAGE-04-x-DONE-2026-01-04.md").write_text(
        "---\nstage: 4\nmodel: claude-c\n---\n", encoding="utf-8"
    )
    _commit(repo, "docs: the disclosure and a new handoff")
    assert _run(repo, "--check") == 0
