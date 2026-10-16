"""`scripts/regenerate_status.sh` renders the README STATUS block truthfully (Stage 22 ride-along).

The script had no unit test (ledger, Stage 21); it was exercised only by the required docs-sync
job. Each case builds a throwaway git repository with a README and handoff frontmatter, then runs
the real script inside it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.stage_22]

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "regenerate_status.sh"
README = "# x\n\n<!-- STATUS:START -->\nstale\n<!-- STATUS:END -->\n\ntail\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path, handoffs: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "handoffs").mkdir(parents=True)
    (repo / "README.md").write_text(README)
    for name, front in handoffs.items():
        (repo / "docs" / "handoffs" / name).write_text(f"---\n{front}---\n\n# body\n")
    _git(repo, "init", "-q")
    return repo


def _front(
    *,
    stage: str = "22",
    status: str = "complete",
    tag: str = "v0.1.1",
    nxt: str = "23",
    nxt_name: str = '"Stage 23 — Foundation II: Provenance You Can Trust"',
) -> str:
    return (
        f"stage: {stage}\n"
        f'stage_name: "Stage {stage} — Foundation I: An Honest V&V Report"\n'
        f"status: {status}\n"
        "date_completed: 2026-10-16\n"
        f"stage_tag: {tag}\n"
        f"next_stage: {nxt}\n"
        f"next_stage_name: {nxt_name}\n"
    )


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=repo, capture_output=True, text=True)


def test_complete_but_untagged_names_the_tag_without_claiming_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"STAGE-22-x-DONE-2026-10-16.md": _front()})
    out = _run(repo, "--print").stdout
    assert "**Latest tag:** v0.1.1 (not yet tagged)  ·  **Status:** complete" in out
    assert "**Next:** Stage 23 — Foundation II: Provenance You Can Trust." in out


def test_complete_and_tagged_drops_the_caveat(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"STAGE-22-x-DONE-2026-10-16.md": _front()})
    _git(repo, "commit", "-q", "--allow-empty", "-m", "c")
    _git(repo, "tag", "v0.1.1")
    out = _run(repo, "--print").stdout
    assert "**Latest tag:** v0.1.1  ·" in out and "not yet tagged" not in out


@pytest.mark.parametrize("status", ["partial", "blocked"])
def test_an_unfinished_stage_points_at_finishing_it(tmp_path: Path, status: str) -> None:
    repo = _repo(tmp_path, {"STAGE-22-x-DONE-2026-10-16.md": _front(status=status)})
    out = _run(repo, "--print").stdout
    assert (
        f"**Next:** resume Stage 22 — Foundation I: An Honest V&V Report — {status}, not finished."
        in out
    )
    assert "Stage 23" not in out


def test_an_empty_next_stage_renders_placeholders(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"STAGE-22-x-DONE-2026-10-16.md": _front(nxt="", nxt_name='""')})
    assert "**Next:** Stage ? — TBD." in _run(repo, "--print").stdout


def test_the_lexicographically_last_handoff_wins(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "STAGE-21-a-DONE-2026-10-12.md": _front(stage="21", tag="v0.1.0"),
            "STAGE-22-x-DONE-2026-10-16.md": _front(status="partial"),
        },
    )
    out = _run(repo, "--print").stdout
    assert "v0.1.1" in out and "Stage 22" in out and "v0.1.0" not in out


def test_rewrite_then_check_passes_and_drift_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"STAGE-22-x-DONE-2026-10-16.md": _front()})
    assert _run(repo, "--check").returncode == 1  # README holds "stale"
    assert _run(repo).returncode == 0
    text = (repo / "README.md").read_text()
    assert "stale" not in text and text.endswith("tail\n") and text.startswith("# x\n")
    assert _run(repo, "--check").returncode == 0
    (repo / "README.md").write_text(text.replace("complete", "partial", 1))
    drift = _run(repo, "--check")
    assert drift.returncode == 1 and "out of sync" in drift.stderr


def test_no_handoff_is_the_bootstrap_message(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {})
    assert "Stage 01 in progress" in _run(repo, "--print").stdout


def test_a_bad_argument_is_a_usage_error(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, {}), "--bogus").returncode == 64
