#!/usr/bin/env python3
"""The ADR-009 certificate watermark: ``non_commercial: true`` requires a ``_nc`` surrogate name.

It checks every certificate in every tracked JSON file, at any depth. The committed certificates
nest under ``/certificate`` or inside loop records, so a top-level-only check, or a glob for a
``certificates/`` directory, finds nothing. The watermark step this replaces scanned zero files.
A certificate is any JSON object that carries both ``surrogate_name`` and ``non_commercial``, the
two fields the watermark relates (``CertificateOfValidity``). FAIL-LOUD: no certificate found at all
is a failure, because a scan that checks nothing must not report green.

    python3 -I scripts/check_cert_watermark.py              # every `git ls-files '*.json'`
    python3 -I scripts/check_cert_watermark.py FILE [...]   # just these
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def certificates(doc: Any, pointer: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(doc, dict):
        if "surrogate_name" in doc and "non_commercial" in doc:
            yield pointer or "/", doc
        for key, value in doc.items():
            yield from certificates(value, f"{pointer}/{key}")
    elif isinstance(doc, list):
        for i, value in enumerate(doc):
            yield from certificates(value, f"{pointer}/{i}")


def violations(path: Path) -> tuple[int, list[str]]:
    """(certificates found, watermark violations) for one JSON file."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    found, bad = 0, []
    for pointer, cert in certificates(doc):
        found += 1
        nc = cert["non_commercial"]
        name = cert["surrogate_name"]
        if not isinstance(nc, bool):
            bad.append(f"{path}#{pointer}: non_commercial is {nc!r}, not a boolean")
        elif nc and not str(name).endswith("_nc"):
            bad.append(
                f"{path}#{pointer}: non_commercial=true but surrogate_name {name!r} lacks '_nc'"
            )
    return found, bad


def main(argv: list[str]) -> int:
    if argv:
        files = [Path(a) for a in argv]
    else:
        out = subprocess.run(
            ["git", "ls-files", "-z", "*.json"], capture_output=True, check=True
        ).stdout.decode()
        files = [Path(p) for p in out.split("\0") if p]
    total, problems, holders = 0, [], 0
    for f in files:
        found, bad = violations(f)
        total += found
        holders += bool(found)
        problems.extend(bad)
    for p in problems:
        print(f"::error::{p} (ADR-009 section 5)")
    if total == 0:
        print(
            "::error::no certificate found: the watermark check would be vacuous", file=sys.stderr
        )
        return 1
    print(
        f"{total} certificate(s) in {holders} of {len(files)} JSON files; {len(problems)} violation(s)"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
