"""Stage 04 — hermetic tests for the four-fold provenance contract.

These exercise `aero.provenance.four_fold` without any live service: git runs
in a `tmp_path` repo, `dvc status -c` is mocked. Run in the default CI suite.
"""

from __future__ import annotations

import hashlib
import json
import subprocess

import pytest
from aero.provenance import ProvenanceError, ProvenanceTuple, compute_provenance
from aero.provenance.four_fold import (
    config_hash,
    container_sif_sha256,
    dvc_input_hash,
    git_sha,
)
from pydantic import ValidationError

pytestmark = pytest.mark.stage_04

_SHA = "a" * 64
_GITSHA = "0123456789abcdef0123456789abcdef01234567"


# --- ProvenanceTuple ---------------------------------------------------------


def test_provenance_tuple_valid() -> None:
    pt = ProvenanceTuple(
        git_sha=_GITSHA, dvc_input_hash=_SHA, container_sif_sha256=_SHA, config_hash=_SHA
    )
    assert pt.as_mlflow_tags() == {
        "git_sha": _GITSHA,
        "dvc_input_hash": _SHA,
        "container_sif_sha256": _SHA,
        "config_hash": _SHA,
    }


def test_provenance_tuple_accepts_dirty_git_sha() -> None:
    pt = ProvenanceTuple(
        git_sha=f"{_GITSHA}-dirty",
        dvc_input_hash=_SHA,
        container_sif_sha256=_SHA,
        config_hash=_SHA,
    )
    assert pt.git_sha.endswith("-dirty")


def test_provenance_tuple_rejects_bad_hash() -> None:
    with pytest.raises(ValidationError):
        ProvenanceTuple(
            git_sha=_GITSHA, dvc_input_hash="nothex", container_sif_sha256=_SHA, config_hash=_SHA
        )


def test_provenance_tuple_rejects_extra_key() -> None:
    with pytest.raises(ValidationError):
        ProvenanceTuple(
            git_sha=_GITSHA,
            dvc_input_hash=_SHA,
            container_sif_sha256=_SHA,
            config_hash=_SHA,
            solver="openfoam",  # type: ignore[call-arg]
        )


def test_provenance_tuple_is_frozen() -> None:
    pt = ProvenanceTuple(
        git_sha=_GITSHA, dvc_input_hash=_SHA, container_sif_sha256=_SHA, config_hash=_SHA
    )
    with pytest.raises(ValidationError):
        pt.git_sha = _GITSHA  # type: ignore[misc]


# --- config_hash -------------------------------------------------------------


def test_config_hash_deterministic() -> None:
    cfg = {"case": {"reynolds": 6e6, "aoa_deg": 0.0}, "z": 1}
    assert config_hash(cfg) == config_hash(cfg)


def test_config_hash_invariant_to_key_order() -> None:
    a = {"alpha": 1, "beta": {"x": 1, "y": 2}}
    b = {"beta": {"y": 2, "x": 1}, "alpha": 1}
    assert config_hash(a) == config_hash(b)


def test_config_hash_matches_canonical_json() -> None:
    cfg = {"b": 2, "a": 1}
    expected = hashlib.sha256(
        json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert config_hash(cfg) == expected


def test_config_hash_changes_with_value() -> None:
    assert config_hash({"reynolds": 6e6}) != config_hash({"reynolds": 3e6})


def test_config_hash_rejects_non_serializable() -> None:
    with pytest.raises(ProvenanceError):
        config_hash({"bad": object()})


# --- container_sif_sha256 ----------------------------------------------------


def test_container_sif_sha256_found(tmp_path) -> None:
    (tmp_path / "containers").mkdir()
    (tmp_path / "containers" / "SHA256SUMS").write_text(
        f"{_SHA}  _base.sif\n{'b' * 64}  openfoam-esi.sif\n"
    )
    assert container_sif_sha256(tmp_path, "openfoam-esi.sif") == "b" * 64


def test_container_sif_sha256_basename_only(tmp_path) -> None:
    (tmp_path / "containers").mkdir()
    (tmp_path / "containers" / "SHA256SUMS").write_text(f"{_SHA}  openfoam-esi.sif\n")
    assert container_sif_sha256(tmp_path, "/opt/aero/containers/openfoam-esi.sif") == _SHA


def test_container_sif_sha256_missing_entry(tmp_path) -> None:
    (tmp_path / "containers").mkdir()
    (tmp_path / "containers" / "SHA256SUMS").write_text(f"{_SHA}  _base.sif\n")
    with pytest.raises(ProvenanceError, match="no SHA256 entry"):
        container_sif_sha256(tmp_path, "openfoam-esi.sif")


def test_container_sif_sha256_missing_file(tmp_path) -> None:
    with pytest.raises(ProvenanceError, match="SHA256SUMS not found"):
        container_sif_sha256(tmp_path, "openfoam-esi.sif")


# --- git_sha -----------------------------------------------------------------


def _git(repo, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@aero.local")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "file.txt").write_text("hello\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


def test_git_sha_clean_tree(git_repo) -> None:
    sha = git_sha(git_repo)
    assert len(sha) == 40
    assert not sha.endswith("-dirty")


def test_git_sha_dirty_tree_fails_loud(git_repo) -> None:
    (git_repo / "file.txt").write_text("modified\n")
    with pytest.raises(ProvenanceError, match="dirty"):
        git_sha(git_repo)


def test_git_sha_dirty_tree_allowed(git_repo) -> None:
    (git_repo / "file.txt").write_text("modified\n")
    sha = git_sha(git_repo, allow_dirty=True)
    assert sha.endswith("-dirty")
    assert len(sha) == 40 + len("-dirty")


# --- dvc_input_hash (subprocess mocked) --------------------------------------


def _fake_run(returncode: int, stdout: str = "", stderr: str = ""):
    def _run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    return _run


def test_dvc_input_hash_in_sync(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout="{}"))
    expected = hashlib.sha256(b"{}").hexdigest()
    assert dvc_input_hash(tmp_path) == expected


def test_dvc_input_hash_changes_with_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout="{}"))
    in_sync = dvc_input_hash(tmp_path)
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout='{"data/x.csv": ["modified"]}'))
    assert dvc_input_hash(tmp_path) != in_sync


def test_dvc_input_hash_fails_loud_on_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run(1, stderr="no remote"))
    with pytest.raises(ProvenanceError, match="dvc status"):
        dvc_input_hash(tmp_path)


# --- compute_provenance (integration, dvc mocked) ----------------------------


def test_compute_provenance_end_to_end(git_repo, monkeypatch) -> None:
    (git_repo / "containers").mkdir()
    (git_repo / "containers" / "SHA256SUMS").write_text(f"{'c' * 64}  openfoam-esi.sif\n")
    # git_sha needs a clean tree; the SHA256SUMS write dirtied it — commit.
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-q", "-m", "add sums")
    monkeypatch.setattr(subprocess, "run", _real_run_except_dvc())

    pt = compute_provenance(
        repo_root=git_repo,
        container_sif="openfoam-esi.sif",
        resolved_config={"case": {"reynolds": 6e6}},
    )
    assert pt.container_sif_sha256 == "c" * 64
    assert len(pt.git_sha) == 40
    assert pt.dvc_input_hash == hashlib.sha256(b"{}").hexdigest()


def _real_run_except_dvc():
    """Pass git through to real subprocess, but stub `dvc status -c`."""
    real = subprocess.run

    def _run(cmd, *args, **kwargs):
        if cmd[:1] == ["dvc"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        return real(cmd, *args, **kwargs)

    return _run
