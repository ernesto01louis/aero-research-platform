"""The tag gate: scripts/check_release_tag.sh (ADR-049 R1) and the Stop hook it wraps.

scripts/check_handoff_exists.sh is the Claude Code Stop hook and is never edited. The first tests
pin its behaviour (characterization), including the inline-comment failure mode that broke
docs/handoffs/_template.md. The release gate is exercised in throwaway git repositories.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, env=ENV, capture_output=True, text=True, check=True
    ).stdout.strip()


def _handoff(stage: str = "21", status: str = "complete", sha: str = "0" * 40, **extra: str) -> str:
    fields = {
        "stage": stage,
        "stage_name": '"Stage 21 — Release"',
        "status": status,
        "date_started": "2026-10-11",
        "date_completed": "2026-10-20",
        "git_sha_end": sha,
        "stage_tag": "v0.1.0",
        "next_stage": "22",
        "next_stage_name": '"Stage 22 — Rigid-Flapping Optimization"',
        **extra,
    }
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "---\n\n# Handoff\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A release-ready miniature: code commit, then a docs-only commit with the handoff."""
    r = tmp_path / "r"
    (r / "scripts").mkdir(parents=True)
    for s in ("check_release_tag.sh", "check_handoff_exists.sh"):
        shutil.copy(REPO / "scripts" / s, r / "scripts" / s)
    (r / "aero").mkdir()
    (r / "aero" / "__init__.py").write_text("x = 1\n")
    (r / "pyproject.toml").write_text('[project]\nname = "aero"\nversion = "0.1.0"\n')
    (r / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: 0.1.0\ndate-released: "2026-10-20"\n'
    )
    (r / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-10-20\n")
    (r / ".aero-stage").write_text("21\n")
    _git(r, "init", "-q", "-b", "main")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "build: v0.1.0")
    code = _git(r, "rev-parse", "HEAD")
    (r / "docs" / "handoffs").mkdir(parents=True)
    (r / "docs" / "handoff-bundle").mkdir(parents=True)
    (r / "docs" / "handoffs" / "STAGE-21-release-DONE-2026-10-20.md").write_text(_handoff(sha=code))
    (r / "docs" / "handoff-bundle" / "STAGE-22-rigid-flapping-optimization.md").write_text("# 22\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "docs: handoff complete")
    return r


def _gate(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/check_release_tag.sh", *args],
        cwd=repo,
        env=ENV,
        capture_output=True,
        text=True,
        check=False,
    )


def _stop_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/check_handoff_exists.sh"],
        cwd=repo,
        env=ENV,
        capture_output=True,
        text=True,
        check=False,
    )


# --- characterization of the Stop hook (unchanged) ------------------------------------------------


def test_the_stop_hook_accepts_a_valid_partial_handoff(repo: Path) -> None:
    handoff = repo / "docs/handoffs/STAGE-21-release-DONE-2026-10-20.md"
    handoff.write_text(_handoff(status="partial", sha="a" * 40))
    assert _stop_hook(repo).returncode == 0  # partial is allowed in-session


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"sha": "<<git rev-parse HEAD>>"}, "git_sha_end"),
        ({"status": "done"}, "status"),
        ({"stage": "20"}, "expected '21'"),
    ],
)
def test_the_stop_hook_blocks_bad_frontmatter(
    repo: Path, change: dict[str, str], message: str
) -> None:
    (repo / "docs/handoffs/STAGE-21-release-DONE-2026-10-20.md").write_text(_handoff(**change))
    r = _stop_hook(repo)
    assert r.returncode == 2 and message in r.stderr


def test_the_stop_hook_misreads_an_inline_comment(repo: Path) -> None:
    # Why PR-01 moved the template's comments onto their own lines: the awk parser keeps them.
    text = _handoff().replace("status: complete", "status: complete  # complete | partial")
    (repo / "docs/handoffs/STAGE-21-release-DONE-2026-10-20.md").write_text(text)
    assert _stop_hook(repo).returncode == 2


def test_the_stop_hook_blocks_when_no_handoff_exists(repo: Path) -> None:
    (repo / "docs/handoffs/STAGE-21-release-DONE-2026-10-20.md").unlink()
    assert _stop_hook(repo).returncode == 2


# --- the release gate ------------------------------------------------------------------------------


def test_a_ready_release_passes_pre_tag_and_ci(repo: Path) -> None:
    r = _gate(repo, "v0.1.0", "--pre-tag")
    assert r.returncode == 0, r.stderr
    _git(repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
    assert _gate(repo, "v0.1.0", "--pre-tag").returncode == 1  # it exists now
    assert _gate(repo, "v0.1.0", "--ci").returncode == 0


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: _rewrite_handoff(r, status="partial"), "needs 'complete'"),
        (lambda r: _rewrite_handoff(r, next_stage='""'), "next_stage"),
        (
            lambda r: (r / "docs/handoff-bundle/STAGE-22-rigid-flapping-optimization.md").unlink(),
            "no prompt file",
        ),
        (
            lambda r: (r / "pyproject.toml").write_text('[project]\nversion = "0.0.9"\n'),
            "pyproject version",
        ),
        (lambda r: (r / "CITATION.cff").write_text("version: 0.0.4\n"), "CITATION.cff version"),
        (lambda r: (r / "CHANGELOG.md").write_text("# Changelog\n"), "CHANGELOG.md has no"),
        (lambda r: (r / "aero" / "__init__.py").write_text("x = 2\n"), "code tree"),
        (lambda r: _rewrite_handoff(r, git_sha_end="f" * 40), "does not resolve"),
        (
            lambda r: (r / "docs/handoffs/STAGE-20-other-DONE-2026-09-01.md").write_text(
                _handoff(stage="20")
            ),
            "2 handoffs carry",
        ),
    ],
)
def test_the_release_gate_refuses(repo: Path, mutate, message: str) -> None:  # type: ignore[no-untyped-def]
    mutate(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "change")
    r = _gate(repo, "v0.1.0", "--pre-tag")
    assert r.returncode == 1 and message in r.stderr, r.stderr


def _rewrite_handoff(r: Path, **fields: str) -> None:
    p = r / "docs/handoffs/STAGE-21-release-DONE-2026-10-20.md"
    sha = next(
        line.split(": ", 1)[1]
        for line in p.read_text().splitlines()
        if line.startswith("git_sha_end:")
    )
    status = fields.pop("status", "complete")
    p.write_text(_handoff(status=status, sha=fields.pop("git_sha_end", sha), **fields))


def test_ci_requires_the_tag_at_head(repo: Path) -> None:
    _git(repo, "tag", "-a", "v0.1.0", "HEAD~1", "-m", "v0.1.0")
    r = _gate(repo, "v0.1.0", "--ci")
    assert r.returncode == 1 and "does not point at HEAD" in r.stderr


def test_the_legacy_stage_tag_path_is_unchanged(repo: Path) -> None:
    (repo / ".aero-stage").write_text("19\n")
    # --ci writes the tagged stage into .aero-stage, as the pre-Stage-21 workflow did.
    r = _gate(repo, "v0.0.21", "--ci")
    assert r.returncode == 0, r.stderr
    assert (repo / ".aero-stage").read_text().strip() == "21"
    # Locally, the stage is asserted, never rewritten.
    (repo / ".aero-stage").write_text("19\n")
    assert _gate(repo, "v0.0.21").returncode == 1
    assert (repo / ".aero-stage").read_text().strip() == "19"


def test_usage_errors(repo: Path) -> None:
    assert _gate(repo).returncode == 2
    assert _gate(repo, "v0.1.0", "--bogus").returncode == 2
    assert _gate(repo, "release-1").returncode == 2
    assert _gate(repo, "stage-20-evidence-2026-09-20").returncode == 2
