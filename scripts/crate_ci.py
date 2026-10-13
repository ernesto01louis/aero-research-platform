#!/usr/bin/env python3
"""Helpers for the clean-machine crate round-trip CI (``.github/workflows/crate-roundtrip.yml``).

Stage 21, ADR-047. The READ-side subcommands use only the stdlib, because this file travels in
the CI artifact to runners that have no checkout and nothing installed but the built wheel,
numpy and pydantic:

    check-transport DIR                  verify DIR/ARTIFACT-SHA256SUMS (the move did not alter bytes)
    compare EXPECTED.json GOT.json       the reader's numbers equal the expected numbers, exactly
    assert-absent MOD [MOD ...]          the named modules are NOT importable here (clean machine)
    wheel-hygiene WHEEL                  the wheel holds only aero/ + its dist-info, GPL-3.0-or-later
    same-bytes A B                       A and B are byte-identical (portable `cmp`)

The WRITE-side subcommands need the repository and the dev environment:

    selftest --out DIR                   write the synthetic crates + expected.json (digests, numbers)
    reader-requirements --out FILE       hash-pinned requirements for the reader closure, from uv.lock
    transport-sums DIR                   write DIR/ARTIFACT-SHA256SUMS
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tomllib
import zipfile
from pathlib import Path

READER_PACKAGES = (
    "annotated-types",
    "numpy",
    "pydantic",
    "pydantic-core",
    "typing-extensions",
    "typing-inspection",
)
TRANSPORT_SUMS = "ARTIFACT-SHA256SUMS"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_transport_sums(root: Path) -> int:
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != TRANSPORT_SUMS)
    lines = [f"{_sha256(p)}  {p.relative_to(root).as_posix()}\n" for p in files]
    (root / TRANSPORT_SUMS).write_text("".join(lines), encoding="ascii", newline="\n")
    print(f"{len(files)} files summed")
    return 0


def cmd_check_transport(root: Path) -> int:
    sums = (root / TRANSPORT_SUMS).read_text(encoding="ascii").splitlines()
    listed = set()
    for line in sums:
        digest, rel = line.split("  ", 1)
        listed.add(rel)
        if _sha256(root / rel) != digest:
            print(f"TRANSPORT CORRUPTED: {rel}", file=sys.stderr)
            return 1
    present = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.name != TRANSPORT_SUMS
    }
    if present != listed:
        print(f"TRANSPORT MEMBER SET CHANGED: {sorted(present ^ listed)}", file=sys.stderr)
        return 1
    print(f"transport intact: {len(listed)} files")
    return 0


def cmd_compare(expected: Path, got: Path) -> int:
    want = json.loads(expected.read_text(encoding="utf-8"))["numbers"]
    have = json.loads(got.read_text(encoding="utf-8"))
    if want != have:
        for crate in sorted(set(want) | set(have)):
            if want.get(crate) != have.get(crate):
                print(f"NUMBERS DIFFER for {crate}", file=sys.stderr)
        return 1
    n = sum(len(v["result"]) + len(v["gates"]) for v in want.values())
    print(f"same numbers, bit for bit: {len(want)} crates, {n} values")
    return 0


def cmd_assert_absent(modules: list[str]) -> int:
    present = [m for m in modules if importlib.util.find_spec(m) is not None]
    if present:
        print(f"NOT A CLEAN MACHINE: importable {present}", file=sys.stderr)
        return 1
    print(f"clean machine: none of {modules} is importable")
    return 0


def cmd_wheel_hygiene(wheel: Path) -> int:
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        tops = {n.split("/", 1)[0] for n in names}
        dist = [t for t in tops if t.endswith(".dist-info")]
        if tops - {"aero", *dist} or len(dist) != 1:
            print(f"wheel has unexpected top-level entries: {sorted(tops)}", file=sys.stderr)
            return 1
        meta = zf.read(f"{dist[0]}/METADATA").decode()
    if "License-Expression: GPL-3.0-or-later" not in meta:
        print("wheel METADATA lacks License-Expression: GPL-3.0-or-later", file=sys.stderr)
        return 1
    if not any(n.startswith("aero/crate/") for n in names):
        print("wheel lacks aero/crate/", file=sys.stderr)
        return 1
    print(f"wheel hygiene ok: {wheel.name} ({len(names)} entries)")
    return 0


def cmd_same_bytes(a: Path, b: Path) -> int:
    if a.read_bytes() != b.read_bytes():
        print(f"BYTES DIFFER: {a} vs {b}", file=sys.stderr)
        return 1
    print(f"byte-identical: {a.name} == {b.name}")
    return 0


def cmd_reader_requirements(lock: Path, out: Path) -> int:
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    by_name = {p["name"]: p for p in data["package"]}
    lines = []
    for name in READER_PACKAGES:
        pkg = by_name[name]
        hashes = sorted(
            {w["hash"].split(":", 1)[1] for w in pkg.get("wheels", [])}
            | ({pkg["sdist"]["hash"].split(":", 1)[1]} if "sdist" in pkg else set())
        )
        pins = " ".join(f"--hash=sha256:{h}" for h in hashes)
        lines.append(f"{name}=={pkg['version']} {pins}\n")
    out.write_text("".join(lines), encoding="ascii", newline="\n")
    print("".join(line.split(" --hash")[0] + "\n" for line in lines), end="")
    return 0


def cmd_selftest(out: Path) -> int:
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from aero.crate import verify_members, write_crate
    from tests.unit._crate_fixtures import SHAPES, built

    out.mkdir(parents=True, exist_ok=False)
    expected: dict[str, dict[str, object]] = {"digests": {}, "numbers": {}}
    for shape in sorted(SHAPES):
        members = built(shape)
        verified = verify_members(members)
        crate_id = verified.manifest.crate_id
        write_crate(out / crate_id, members)
        expected["digests"][crate_id] = verified.digest
        expected["numbers"][crate_id] = verified.numbers()
    (out / "expected.json").write_text(json.dumps(expected, indent=1, sort_keys=True) + "\n")
    print(f"wrote {len(SHAPES)} self-test crates to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-transport").add_argument("root", type=Path)
    sub.add_parser("transport-sums").add_argument("root", type=Path)
    c = sub.add_parser("compare")
    c.add_argument("expected", type=Path)
    c.add_argument("got", type=Path)
    sub.add_parser("assert-absent").add_argument("modules", nargs="+")
    sub.add_parser("wheel-hygiene").add_argument("wheel", type=Path)
    s = sub.add_parser("same-bytes")
    s.add_argument("a", type=Path)
    s.add_argument("b", type=Path)
    r = sub.add_parser("reader-requirements")
    r.add_argument("--lock", type=Path, default=Path("uv.lock"))
    r.add_argument("--out", type=Path, required=True)
    sub.add_parser("selftest").add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.cmd == "check-transport":
        return cmd_check_transport(a.root)
    if a.cmd == "transport-sums":
        return cmd_transport_sums(a.root)
    if a.cmd == "compare":
        return cmd_compare(a.expected, a.got)
    if a.cmd == "assert-absent":
        return cmd_assert_absent(a.modules)
    if a.cmd == "wheel-hygiene":
        return cmd_wheel_hygiene(a.wheel)
    if a.cmd == "same-bytes":
        return cmd_same_bytes(a.a, a.b)
    if a.cmd == "reader-requirements":
        return cmd_reader_requirements(a.lock, a.out)
    return cmd_selftest(a.out)


if __name__ == "__main__":
    sys.exit(main())
