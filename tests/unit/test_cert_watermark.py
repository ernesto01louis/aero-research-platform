"""scripts/check_cert_watermark.py: the ADR-009 `_nc` watermark, at any depth, never vacuous."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_cert_watermark.py"


def _run(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, doc: object) -> Path:
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_a_nested_certificate_is_found_and_checked(tmp_path: Path) -> None:
    ok = _write(
        tmp_path / "ok.json", {"certificate": {"surrogate_name": "x_nc", "non_commercial": True}}
    )
    bad = _write(
        tmp_path / "bad.json",
        {"loop": {"records": [{"certificate": {"surrogate_name": "x", "non_commercial": True}}]}},
    )
    assert _run(str(ok)).returncode == 0
    r = _run(str(bad))
    assert r.returncode == 1 and "/loop/records/0/certificate" in r.stdout


def test_a_non_boolean_flag_fails(tmp_path: Path) -> None:
    f = _write(tmp_path / "c.json", {"surrogate_name": "x", "non_commercial": "yes"})
    assert _run(str(f)).returncode == 1


def test_finding_no_certificate_at_all_fails(tmp_path: Path) -> None:
    f = _write(tmp_path / "plain.json", {"a": 1})
    r = _run(str(f))
    assert r.returncode == 1 and "vacuous" in r.stderr


def test_the_repository_certificates_pass_and_are_actually_scanned() -> None:
    r = _run()
    assert r.returncode == 0, r.stdout + r.stderr
    found = int(r.stdout.split(" certificate", 1)[0])
    assert found >= 3  # stage17 cert, the refused v2 cert, and the in-loop certificates
