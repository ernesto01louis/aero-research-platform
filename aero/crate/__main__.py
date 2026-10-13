"""``python -I -B -m aero.crate {verify,show,numbers,pack}``: the clean-machine entry point.

The CLI uses only the stdlib's argparse, so it runs where only stdlib + numpy + pydantic are
installed. The ``aero`` console script would need typer. Every command except ``--no-sandbox``
runs under :mod:`aero.crate.sandbox`.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | OK |
| 2 | usage |
| 6 | a crate was refused (the CrateError class and message are printed) |
| 7 | a crate verified, but its digest is not the expected one |
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from aero.crate import sandbox
from aero.crate.errors import CrateError, CrateExpectationError
from aero.crate.members import read_members
from aero.crate.reader import VerifiedCrate, verify_crate
from aero.crate.writer import pack_crate

EXIT_OK, EXIT_USAGE, EXIT_REFUSED, EXIT_EXPECTATION = 0, 2, 6, 7


def _expectations(path: str | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise SystemExit("--expect-digests takes a JSON object {crate_id: digest}")
    return {str(k): v for k, v in data.items()}


def _verify_all(paths: list[str], expect: dict[str, str]) -> list[VerifiedCrate]:
    out = []
    for p in paths:
        verified = verify_crate(p)
        want = expect.get(verified.manifest.crate_id)
        if expect and want is None:
            raise CrateExpectationError(
                f"{p}: no expected digest for {verified.manifest.crate_id!r}"
            )
        if want is not None and want != verified.digest:
            raise CrateExpectationError(
                f"{p}: crate digest {verified.digest} != expected {want} ({verified.manifest.crate_id})"
            )
        out.append(verified)
    return out


def _show(v: VerifiedCrate) -> str:
    m, ctx = v.manifest, v.manifest.validity
    lines = [f"crate     {m.crate_id}  (aero-result-crate format {m.format_version})"]
    if ctx.claim_tier == "none":
        lines.append("CLAIM     NO CLAIM -- evidence only; provenance or U95 is unavailable")
    else:
        lines.append(f"CLAIM     tier = {ctx.claim_tier}  (scope: {ctx.claim_scope})")
    lines.append(f"digest    {v.digest}")
    lines.append(f"title     {m.title}")
    for verdict in ctx.verdicts:
        q = f" ({verdict.qualifier})" if verdict.qualifier else ""
        lines.append(f"VERDICT   {verdict.scope}: {verdict.overall}{q}")
        for g in verdict.gates:
            if g.gated:
                lines.append(
                    f"  gate        {'PASS' if g.passed else 'FAIL'}  {g.name}: {g.criterion}"
                )
        for g in verdict.gates:
            if not g.gated:
                lines.append(
                    f"  diagnostic  {'pass' if g.passed else 'fail'}  {g.name}: {g.criterion}"
                )
    lines.append("LIMITATIONS")
    for lim in ctx.limitations:
        lines.append(f"  [{lim.id}] {lim.text}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aero.crate", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--no-sandbox", action="store_true", help="do not install the audit-hook sandbox"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_verify = sub.add_parser("verify", help="verify crates (directories or .crate.zip)")
    p_verify.add_argument("paths", nargs="+")
    p_verify.add_argument("--expect-digests", help="JSON {crate_id: digest} every crate must match")
    p_show = sub.add_parser(
        "show", help="verify one crate and print what it does and does not claim"
    )
    p_show.add_argument("path")
    p_numbers = sub.add_parser(
        "numbers", help="verify crates and print every number they carry (JSON)"
    )
    p_numbers.add_argument("paths", nargs="+")
    p_pack = sub.add_parser(
        "pack", help="verify a crate directory and write its deterministic .crate.zip"
    )
    p_pack.add_argument("directory")
    p_pack.add_argument("output")
    args = parser.parse_args(argv)

    expect = _expectations(getattr(args, "expect_digests", None))
    if not args.no_sandbox:
        sandbox.install(allow_write=Path(args.output) if args.command == "pack" else None)
    try:
        if args.command == "verify":
            for v in _verify_all(args.paths, expect):
                print(f"OK  {v.manifest.crate_id}  {v.digest}  {v.origin}")
        elif args.command == "show":
            (v,) = _verify_all([args.path], {})
            print(_show(v))
        elif args.command == "numbers":
            report: dict[str, Any] = {}
            for v in _verify_all(args.paths, expect):
                if v.manifest.crate_id in report:
                    raise CrateError(f"{v.origin}: crate {v.manifest.crate_id!r} given twice")
                report[v.manifest.crate_id] = v.numbers()
            print(json.dumps(report, indent=1, sort_keys=True))
        elif args.command == "pack":
            data = pack_crate(read_members(Path(args.directory)))
            with open(args.output, "xb") as fh:
                fh.write(data)
            print(f"packed {args.directory} -> {args.output}")
    except CrateExpectationError as exc:
        print(f"EXPECTATION MISMATCH ({type(exc).__name__}): {exc}", file=sys.stderr)
        return EXIT_EXPECTATION
    except CrateError as exc:
        print(f"REFUSED ({type(exc).__name__}): {exc}", file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
