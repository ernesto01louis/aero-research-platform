#!/usr/bin/env python3
"""An independent oracle for the committed result crates (Stage 21, ADR-047; crate-roundtrip CI).

It never imports ``aero``. It reads the committed source records with the stdlib ``json`` module,
and from them states what each crate must carry:

- every leaf of the source record (the result must be a lossless superset of it);
- each quantity's ``u95_total``, recomputed here as an IEEE-exact RSS;
- the crate's config hashes, as recorded;
- every gate's observed value, read from the record that holds it;
- the crate digest, pinned.

``compare`` then checks a reader's ``python -m aero.crate numbers`` output against that. It runs
on fresh runners with no checkout, so it is stdlib-only and the oracle JSON travels with it.

    python3 -I scripts/crate_oracle.py build --out oracle.json     # in the repository
    python3 -I crate_oracle.py compare oracle.json got.json        # anywhere
    python3 -I crate_oracle.py digests oracle.json [--merge expected.json] --out digests.json

Re-exporting a committed crate changes its digest, so it must update ``DIGESTS`` here as well. That
is deliberate: published crates are immutable (ADR-047 D8).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

DIGESTS = {
    "stage12-oscillating-cylinder-lockin": "a0ca217d655a243a777574dd3f68b1f6f82542e6e9126bd9e4edfdd43d497773",
    "stage14-rigid-flapping-wbd2004": "438517c449c6d9aa743a2c45d770ccd384b6ab59b817356cf6458a21d27dc989",
    "stage15-airfoil-optimization": "bc42503f99e28f3dcbdcd0af4c05e10928f7902db7cb36b3053ce3fa30c8675f",
    "stage16-airfoil-grid-certification": "0bf8ecae5943929317dd6567efac5e4a94c4555dc9f195e9ef8be3aba70e86b0",
    "stage17-surrogate-accelerated-optimization": "b41399231a7e298802aaf9c2a0d8bb1e2b3e36988c321d0f93cc55dccd187383",
}

VV = "data/vv"
S17_CORPUS = "crates/stage17-surrogate-accelerated-optimization/evidence/corpus.json"


def _typed(value: Any) -> list[Any]:
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, float):
        return ["float", value.hex()]
    if isinstance(value, int):
        return ["int", value]
    if value is None:
        return ["null", None]
    return ["str", value]


def _leaves(obj: Any, path: str = "") -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            out.update(_leaves(v, f"{path}/{k}"))
    elif isinstance(obj, list) and obj:
        for i, v in enumerate(obj):
            out.update(_leaves(v, f"{path}/{i}"))
    elif isinstance(obj, dict | list):
        out[path] = ["empty", "{}" if isinstance(obj, dict) else "[]"]
    else:
        out[path] = _typed(obj)
    return out


def _at(doc: Any, pointer: str) -> Any:
    for part in pointer.strip("/").split("/"):
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc


def _rss(*terms: float) -> float:
    total = 0.0
    for t in terms:
        total += t * t
    return math.sqrt(total)


def _crate(
    repo: Path, record: str | None, configs: list[str], gates: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, list[Any]] = {}
    if record is not None:
        doc = json.loads((repo / VV / record).read_text(encoding="utf-8"))
        result = _leaves(doc)
        for i, q in enumerate(doc["quantities"]):
            # Independent of the platform's arithmetic: x*x, summed left to right.
            u95 = _rss(q["u95_numerical"], q.get("u95_statistical", 0.0), q.get("u95_input", 0.0))
            result[f"/quantities/{i}/u95_total"] = _typed(u95)
    return {
        "result": result,
        "configs": sorted(set(configs)),
        "gates": {k: _typed(v) for k, v in gates.items()},
    }


def build(repo: Path) -> dict[str, Any]:
    def rec(name: str) -> Any:
        return json.loads((repo / VV / name).read_text(encoding="utf-8"))

    s12 = rec("stage12_reportable_oscillating_cylinder_lockin.json")
    s14 = rec("stage14_flapping_nogo.json")
    per = {p["timing"]: p for p in s14["per_timing"]}
    s15, g15 = rec("stage15_optimization.json"), rec("stage15_grid_convergence.json")
    s16, g16 = rec("stage16_relaxed_optimization.json"), rec("stage16_relaxed_convergence.json")
    s17, sp = rec("stage17_optimization.json"), rec("stage17_speedup.json")
    cert = rec("stage17_surrogate_cert.json")
    proposer = rec("stage17_arm_surrogate_explore.json")["accelerated"]["records"][1]["certificate"]
    corpus = json.loads((repo / S17_CORPUS).read_text(encoding="utf-8"))
    corpus_best = max(r["ld"] for r in corpus["rows"] if not r["failed"])

    crates = {
        "stage12-oscillating-cylinder-lockin": _crate(
            repo,
            "stage12_reportable_oscillating_cylinder_lockin.json",
            [s12["provenance"]["config_hash"]],
            {"thesis-grade-gate/lock-in-anchor": s12["anchors"][0]["observed_error"]},
        ),
        "stage14-rigid-flapping-wbd2004": _crate(
            repo,
            None,
            [],
            {
                "forward-validation/symmetrical-mean-lift-within-band": s14["gated_rel_err"],
                "forward-validation/rotation-timing-ordering": s14["ordering_correct"],
                "forward-validation/advanced-mean-lift-rel-err": per["advanced"]["rel_err_vs_exp"],
                "forward-validation/delayed-mean-lift-rel-err": per["delayed"]["rel_err_vs_exp"],
            },
        ),
        "stage15-airfoil-optimization": _crate(
            repo,
            "stage15_optimization.json",
            [s15["provenance"]["config_hash"]]
            + [r["provenance"]["config_hash"] for r in g15["solves"]],
            {
                "optimization-claim/delta-exceeds-k-u95": g15["delta_fine"],
                "optimization-claim/delta-exceeds-own-u95": g15["delta_fine"],
                "optimization-claim/observed-order-in-asymptotic-range": g15[
                    "observed_order_delta"
                ],
                "optimization-claim/all-solves-converged": g15["all_converged"],
            },
        ),
        "stage16-airfoil-grid-certification": _crate(
            repo,
            "stage16_relaxed_optimization.json",
            [s16["provenance"]["config_hash"]]
            + [r["provenance"]["config_hash"] for r in g16["solves"]],
            {
                "grid-certification/significant": g16["delta_fine"],
                "grid-certification/all-converged": g16["gates"]["all_converged"],
                "grid-certification/delta-monotone": g16["gates"]["delta_monotone"],
                "grid-certification/order-in-asymptotic-range": g16["observed_order_delta"],
            },
        ),
        "stage17-surrogate-accelerated-optimization": _crate(
            repo,
            "stage17_optimization.json",
            [s17["provenance"]["config_hash"]],
            {
                "optimization-claim/delta-exceeds-k-u95": s17["optimization"]["improvement"][
                    "delta"
                ],
                "optimization-claim/margin-over-corpus-best-exceeds-u95": s17["quantities"][0][
                    "value"
                ]
                - corpus_best,
                "optimization-claim/held-out-is-same-grid-re-solve": sp["verification"][
                    "V1_held_out_ld"
                ]
                == sp["reported_optimum"]["loop_best_ld"],
                "optimization-claim/proposer-certificate-p95-within-bar": float(
                    proposer["held_out_metrics"]["ld_mae"]["p95"]
                ),
                "optimization-claim/proposer-certificate-coverage-in-band": float(
                    proposer["uncertainty_calibration"]["empirical_coverage"]
                ),
                "surrogate-certificate/c1-coverage-in-band": float(
                    cert["gates"]["C1_empirical_coverage"]
                ),
                "surrogate-certificate/c2-p95-within-bar": float(cert["gates"]["C2_p95"]),
                "speed-up/genuine-wins-in-2-of-3-seeds": float(sp["speedup"]["genuine_wins"]),
                "speed-up/literal-marginal-wins": float(sp["speedup"]["literal_marginal_wins"]),
            },
        ),
    }
    for crate_id, entry in crates.items():
        entry["digest"] = DIGESTS[crate_id]
    return crates


def compare(oracle: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """Every problem found; empty means the reader's numbers agree with the oracle exactly."""
    problems: list[str] = []
    if set(oracle) != set(got):
        problems.append(f"crate set {sorted(got)} != oracle {sorted(oracle)}")
    for crate_id in sorted(set(oracle) & set(got)):
        want, have = oracle[crate_id], got[crate_id]
        if want["digest"] != have["digest"]:
            problems.append(f"{crate_id}: digest {have['digest']} != pinned {want['digest']}")
        if want["configs"] != have["configs"]:
            problems.append(f"{crate_id}: configs {have['configs']} != recorded {want['configs']}")
        for pointer, value in want["result"].items():
            if have["result"].get(pointer) != value:
                problems.append(
                    f"{crate_id}: result{pointer} = {have['result'].get(pointer)} != {value}"
                )
        if set(want["gates"]) != set(have["gates"]):
            problems.append(f"{crate_id}: gates {sorted(have['gates'])} != {sorted(want['gates'])}")
        for name, value in want["gates"].items():
            if name in have["gates"] and have["gates"][name]["observed"] != value:
                problems.append(
                    f"{crate_id}: gate {name} observed {have['gates'][name]['observed']} != {value}"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    b.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("oracle", type=Path)
    c.add_argument("got", type=Path)
    d = sub.add_parser("digests")
    d.add_argument("oracle", type=Path)
    d.add_argument("--merge", type=Path, help="a selftest expected.json whose digests to include")
    d.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.cmd == "build":
        oracle = build(a.repo)
        a.out.write_text(json.dumps(oracle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        n = sum(len(v["result"]) + len(v["gates"]) for v in oracle.values())
        print(f"oracle: {len(oracle)} crates, {n} values")
        return 0
    if a.cmd == "digests":
        digests = {
            k: v["digest"] for k, v in json.loads(a.oracle.read_text(encoding="utf-8")).items()
        }
        if a.merge is not None:
            digests.update(json.loads(a.merge.read_text(encoding="utf-8"))["digests"])
        a.out.write_text(json.dumps(digests, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    problems = compare(
        json.loads(a.oracle.read_text(encoding="utf-8")),
        json.loads(a.got.read_text(encoding="utf-8")),
    )
    for line in problems:
        print(f"ORACLE MISMATCH: {line}", file=sys.stderr)
    if problems:
        return 1
    print("the committed crates carry exactly the recorded numbers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
