"""`scripts/provenance_readback.py` — the independent read-back of a run's tuple (Stage 23, E2E-1).

The script recomputes the DVC and container terms from git at the run's `git_sha`, without
importing `aero`. Here the tags of a real `ProvenanceTupleV2` at HEAD pass, and every kind of
tampering is named and fails.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from aero.provenance.dvc_inputs import resolve_declared
from aero.provenance.four_fold import ContainerRef, ProvenanceTupleV2, dvc_inputs_digest

from tests.unit._launch_fixtures import REPO, SUMS, V1

pytestmark = pytest.mark.stage_23

SCRIPT = REPO / "scripts" / "provenance_readback.py"
CFD = "data/references/fsi/turek_hron_fsi3/cylinder_flag.stl.dvc"


def _head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _tags(**overrides: str) -> dict[str, str]:
    inputs = resolve_declared(REPO, (CFD,))
    prov = ProvenanceTupleV2(
        git_sha=_head(),
        dvc_input_hash=dvc_inputs_digest(inputs),
        container_sif_sha256=SUMS["precice-fsi.sif"],
        config_hash="a" * 64,
        container_sif_name="precice-fsi.sif",
        containers=tuple(
            ContainerRef(name=n, sha256=SUMS[n])
            for n in ("calculix-precice.sif", "precice-fsi.sif")
        ),
        dvc_inputs=inputs,
        schemes=V1,
    )
    return {**prov.as_mlflow_tags(), **overrides}


def _run(tmp_path: Path, tags: dict[str, Any], *extra: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "tags.json"
    path.write_text(json.dumps(tags), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--tags-json", str(path), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_real_tuple_reads_back_whole(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"b": 1, "a": [2, 3]}', encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(b'{"a":[2,3],"b":1}').hexdigest()
    proc = _run(tmp_path, _tags(config_hash=digest), "--config-json", str(config))
    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.rstrip().endswith("ALL CHECKS PASS")
    assert "FAIL" not in proc.stdout


@pytest.mark.parametrize(
    ("overrides", "names"),
    [
        ({"dvc_input_hash": "e" * 64}, "dvc_input_hash = sha256(prefix + tag)"),
        ({"container_sif_sha256": "e" * 64}, "container_sif_sha256 = SHA256SUMS"),
        ({"dvc_input_hash_scheme": "repo-sync-state/v0"}, "dvc_input_hash_scheme"),
        ({"container_sif_sha256_scheme": "sha256sums-lookup/v0"}, "container_sif_sha256_scheme"),
        ({"git_sha": "0" * 40}, "git_sha resolves"),
        ({"container_sif_set": "precice-fsi.sif=" + "e" * 64}, "roster precice-fsi.sif"),
        ({"config_hash": "e" * 64}, "config_hash"),
    ],
)
def test_tampering_is_named_and_fails(
    tmp_path: Path, overrides: dict[str, str], names: str
) -> None:
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    proc = _run(tmp_path, _tags(**overrides), "--config-json", str(config))
    assert proc.returncode == 1, proc.stdout
    assert any(line.startswith("FAIL") and names in line for line in proc.stdout.splitlines())


def test_a_dirty_sha_and_a_rewritten_input_fail(tmp_path: Path) -> None:
    tags = _tags()
    tags["git_sha"] += "-dirty"
    assert _run(tmp_path, tags).returncode == 1
    entry = json.loads(_tags()["dvc_inputs"])
    entry["inputs"][0]["size"] += 1
    raw = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    import hashlib

    forged = _tags(
        dvc_inputs=raw,
        dvc_input_hash=hashlib.sha256(b"aero.dvc-inputs/v1\n" + raw.encode()).hexdigest(),
    )
    proc = _run(tmp_path, forged)
    assert proc.returncode == 1
    assert (
        "FAIL  data/references/fsi/turek_hron_fsi3/cylinder_flag.stl: md5 and size" in proc.stdout
    )


def test_the_read_back_never_imports_aero() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "aero" not in imported
