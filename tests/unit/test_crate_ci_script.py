"""``scripts/crate_ci.py``, the clean-machine round-trip helper, does what the CI relies on."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "crate_ci.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_reader_requirements_pin_the_locked_closure_with_hashes(tmp_path: Path) -> None:
    out = tmp_path / "req.txt"
    assert (
        _run("reader-requirements", "--lock", str(REPO / "uv.lock"), "--out", str(out)).returncode
        == 0
    )
    lock = {
        p["name"]: p["version"] for p in tomllib.loads((REPO / "uv.lock").read_text())["package"]
    }
    lines = out.read_text().splitlines()
    names = [line.split("==")[0] for line in lines]
    assert names == [
        "annotated-types",
        "numpy",
        "pydantic",
        "pydantic-core",
        "typing-extensions",
        "typing-inspection",
    ]
    for line in lines:
        name, rest = line.split("==", 1)
        assert rest.split(" ")[0] == lock[name]
        assert "--hash=sha256:" in rest


def test_transport_sums_detect_a_changed_or_added_byte(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.json").write_text("{}\n")
    (tmp_path / "y.bin").write_bytes(b"\x00\x01")
    assert _run("transport-sums", str(tmp_path)).returncode == 0
    assert _run("check-transport", str(tmp_path)).returncode == 0
    (tmp_path / "y.bin").write_bytes(b"\x00\x02")
    assert _run("check-transport", str(tmp_path)).returncode == 1
    (tmp_path / "y.bin").write_bytes(b"\x00\x01")
    (tmp_path / "extra").write_text("x")
    assert _run("check-transport", str(tmp_path)).returncode == 1


def test_compare_and_same_bytes(tmp_path: Path) -> None:
    numbers = {"c": {"result": {"/a": ["float", "0x1.0p+0"]}, "gates": {}}}
    (tmp_path / "e.json").write_text(json.dumps({"numbers": numbers}))
    (tmp_path / "g.json").write_text(json.dumps(numbers))
    assert _run("compare", str(tmp_path / "e.json"), str(tmp_path / "g.json")).returncode == 0
    numbers["c"]["result"]["/a"] = ["float", "0x1.0000000000001p+0"]  # one ulp
    (tmp_path / "g.json").write_text(json.dumps(numbers))
    assert _run("compare", str(tmp_path / "e.json"), str(tmp_path / "g.json")).returncode == 1
    (tmp_path / "p").write_bytes(b"x")
    (tmp_path / "q").write_bytes(b"y")
    assert _run("same-bytes", str(tmp_path / "p"), str(tmp_path / "p")).returncode == 0
    assert _run("same-bytes", str(tmp_path / "p"), str(tmp_path / "q")).returncode == 1


def test_assert_absent_names_present_modules() -> None:
    assert _run("assert-absent", "definitely_not_a_module_xyz").returncode == 0
    assert _run("assert-absent", "json").returncode == 1
