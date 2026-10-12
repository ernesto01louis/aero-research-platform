"""``python -I -B -m aero.crate``: exit codes, output, determinism, and the sandbox (ADR-047)."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from aero.crate import verify_members, write_crate

from tests.unit._crate_fixtures import built

pytestmark = pytest.mark.stage_21


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-B", "-m", "aero.crate", *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture
def crates(tmp_path: Path) -> dict[str, Path]:
    out = {}
    for shape in ("steady_optimization", "evidence_only"):
        dest = tmp_path / shape
        write_crate(dest, built(shape))
        out[shape] = dest
    return out


def test_verify_ok(crates: dict[str, Path]) -> None:
    proc = _cli("verify", *map(str, crates.values()))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("OK  ") == 2


def test_a_refused_crate_exits_6(crates: dict[str, Path]) -> None:
    target = crates["steady_optimization"] / "result.json"
    target.write_bytes(target.read_bytes().replace(b"46.37", b"46.38"))
    proc = _cli("verify", str(crates["steady_optimization"]))
    assert proc.returncode == 6
    assert "REFUSED (CrateIntegrityError)" in proc.stderr


def test_an_unexpected_digest_exits_7(crates: dict[str, Path], tmp_path: Path) -> None:
    expect = tmp_path / "expect.json"
    expect.write_text(json.dumps({"stage21-synthetic-evidence-only": "0" * 64}))
    proc = _cli("verify", "--expect-digests", str(expect), str(crates["evidence_only"]))
    assert proc.returncode == 7
    good = verify_members(built("evidence_only")).digest
    expect.write_text(json.dumps({"stage21-synthetic-evidence-only": good}))
    assert (
        _cli("verify", "--expect-digests", str(expect), str(crates["evidence_only"])).returncode
        == 0
    )


def test_show_puts_the_claim_first(crates: dict[str, Path]) -> None:
    proc = _cli("show", str(crates["evidence_only"]))
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[1].startswith("CLAIM     NO CLAIM")
    assert any("diagnostic" in ln and "rotation-timing-ordering" in ln for ln in lines)
    assert any("gate        FAIL  mean-lift-within-band" in ln for ln in lines)
    steady = _cli("show", str(crates["steady_optimization"])).stdout
    assert "No flapping optimization claim is made in v0.1.0." in steady


def test_numbers_is_the_reader_numbers(crates: dict[str, Path]) -> None:
    proc = _cli("numbers", str(crates["steady_optimization"]))
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert (
        report["stage21-synthetic-steady-opt"]
        == verify_members(built("steady_optimization")).numbers()
    )


def test_pack_is_deterministic_and_verifies(crates: dict[str, Path], tmp_path: Path) -> None:
    a, b = tmp_path / "a.crate.zip", tmp_path / "b.crate.zip"
    assert _cli("pack", str(crates["steady_optimization"]), str(a)).returncode == 0
    assert _cli("pack", str(crates["steady_optimization"]), str(b)).returncode == 0
    assert a.read_bytes() == b.read_bytes()
    assert _cli("verify", str(a)).returncode == 0
    assert (
        _cli("pack", str(crates["steady_optimization"]), str(a)).returncode != 0
    )  # never overwrites


def test_the_sandbox_denies_network_subprocess_writes_and_foreign_imports(tmp_path: Path) -> None:
    probe = textwrap.dedent(
        f"""
        import sys
        from aero.crate import sandbox
        sandbox.install()
        results = []
        for label, attempt in [
            ("socket", lambda: __import__("socket").socket()),
            ("subprocess", lambda: __import__("subprocess").run(["true"])),
            ("write", lambda: open({str(tmp_path / "x.txt")!r}, "w")),
            ("import", lambda: __import__("yaml")),
        ]:
            try:
                attempt()
                results.append(label + ":ALLOWED")
            except (PermissionError, ImportError) as exc:
                results.append(label + ":denied")
        print(",".join(results))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "socket:denied,subprocess:denied,write:denied,import:denied"
    assert not (tmp_path / "x.txt").exists()
