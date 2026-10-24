#!/usr/bin/env python3
"""Read one run's provenance back and recompute its terms from git alone (Stage 23, E2E-1).

    python -I scripts/provenance_readback.py --run-id <mlflow run id> [--mirror]
    python -I scripts/provenance_readback.py --tags-json tags.json [--config-json spec.json]
    python -I scripts/provenance_readback.py --record record.json --mirror   # a hosted run's record

READ-ONLY. It reads the run's tags from the MLflow REST API (or a JSON file of them), and with
`--mirror` the run's row of the Postgres mirror, through `AERO_PROVENANCE_DSN` (never printed).
It never imports `aero`: the point is a second, independent computation of what the platform
recorded, from the repository at the run's own `git_sha`:

1. both scheme tags are v1 (`declared-dvc-pointers-md5/v1`, `sif-sha256-verified-at-launch/v1`)
   and `git_sha` is a clean 40-hex commit of this checkout;
2. `dvc_input_hash` is sha256(`aero.dvc-inputs/v1\\n` + the `dvc_inputs` tag), the tag is the
   canonical JSON of its own content, and each input's md5 and size are what its pointer
   `<path>.dvc` says at `git_sha` (ADR-052);
3. `container_sif_sha256` is the entry for `container_sif_name` in `containers/SHA256SUMS` at
   `git_sha`, as is every member of `container_sif_set` (ADR-053);
4. no term equals a value recorded before Stage 23;
5. with `--config-json`, `config_hash` is sha256 of that config's canonical JSON;
6. with `--mirror`, the mirror row equals the tags byte for byte.

Exit 0 when every check passes, 1 otherwise. Each check prints one line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
TRACKING_URI = "http://192.168.2.234:5000"  # conf/mlflow/default.yaml

PREFIX = b"aero.dvc-inputs/v1\n"
SCHEMES = {
    "dvc_input_hash_scheme": "declared-dvc-pointers-md5/v1",
    "container_sif_sha256_scheme": "sif-sha256-verified-at-launch/v1",
}
#: Every DVC value recorded before Stage 23 that a new value must never equal.
LEGACY_DVC = {
    "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",  # sha256("{}")
    "618b8fedbd8d84a3d551056ba3bdf4300a3c994a1a94d1d18802a2978d255162",  # CI since 2026-07-30
    "7ec8590f5fb8607da8f64b854ef5a04322408ad76b72f14eea29f3adca66f092",  # data/vv, the crates
}
MIRROR_COLUMNS = (
    "git_sha",
    "dvc_input_hash",
    "container_sif_sha256",
    "config_hash",
    "container_sif_set",
    "dvc_input_hash_scheme",
    "container_sif_sha256_scheme",
    "dvc_inputs",
)
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, ok: bool, what: str, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {what}{f'  ({detail})' if detail else ''}")
        self.failed += 0 if ok else 1


def run_tags(run_id: str, tracking_uri: str) -> dict[str, str]:
    query = urllib.parse.urlencode({"run_id": run_id})
    with urllib.request.urlopen(f"{tracking_uri}/api/2.0/mlflow/runs/get?{query}", timeout=30) as r:
        payload = json.load(r)
    return {t["key"]: t["value"] for t in payload["run"]["data"].get("tags", [])}


def git_show(sha: str, path: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{sha}:{path}"], capture_output=True, check=False
    )
    return proc.stdout if proc.returncode == 0 else None


def pointer_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.strip().removeprefix("- ").partition(": ")
        if sep:
            fields[key] = value
    return fields


def sums_at(sha: str) -> dict[str, str]:
    raw = git_show(sha, "containers/SHA256SUMS")
    sums: dict[str, str] = {}
    for line in (raw or b"").decode("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and not line.lstrip().startswith("#") and _HEX64.match(parts[0]):
            sums[parts[1]] = parts[0]
    return sums


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def check_tags(tags: dict[str, str], report: Report) -> None:
    for key, want in SCHEMES.items():
        report.check(tags.get(key) == want, f"{key} = {want}", tags.get(key, "absent"))
    sha = tags.get("git_sha", "")
    report.check(bool(_HEX40.match(sha)), "git_sha is a clean commit", sha)
    known = bool(_HEX40.match(sha)) and git_show(sha, "pyproject.toml") is not None
    report.check(known, "git_sha resolves in this checkout")

    # 2. the DVC term, from the pointers at git_sha
    raw = tags.get("dvc_inputs")
    report.check(raw is not None, "dvc_inputs tag present")
    if raw is not None:
        value = hashlib.sha256(PREFIX + raw.encode("ascii")).hexdigest()
        report.check(value == tags.get("dvc_input_hash"), "dvc_input_hash = sha256(prefix + tag)")
        inputs = json.loads(raw)["inputs"]
        report.check(canonical({"inputs": inputs}) == raw.encode(), "dvc_inputs is canonical")
        paths = [i["path"] for i in inputs]
        report.check(paths == sorted(paths), "dvc_inputs sorted by path", str(paths))
        for item in inputs:
            pointer = git_show(sha, f"{item['path']}.dvc") if known else None
            fields = pointer_fields(pointer.decode("utf-8")) if pointer else {}
            ok = (
                fields.get("md5") == item["md5"]
                and fields.get("size") == str(item["size"])
                and fields.get("hash") == item["hash"] == "md5"
            )
            report.check(ok, f"{item['path']}: md5 and size match its pointer at git_sha")

    # 3. the container term, from SHA256SUMS at git_sha
    sums = sums_at(sha) if known else {}
    name = tags.get("container_sif_name", "")
    report.check(
        sums.get(name) == tags.get("container_sif_sha256"),
        f"container_sif_sha256 = SHA256SUMS[{name}] at git_sha",
    )
    for member in filter(None, tags.get("container_sif_set", "").split(",")):
        sif, _, digest = member.partition("=")
        report.check(sums.get(sif) == digest, f"roster {sif} = SHA256SUMS[{sif}] at git_sha")

    # 4. never a pre-Stage-23 value
    report.check(
        tags.get("dvc_input_hash") not in LEGACY_DVC, "dvc_input_hash is not a legacy value"
    )


def check_config(tags: dict[str, str], config_json: Path, report: Report) -> None:
    config = json.loads(config_json.read_text(encoding="utf-8"))
    value = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    report.check(value == tags.get("config_hash"), "config_hash = sha256(canonical config)")


def check_mirror(run_id: str, tags: dict[str, str], report: Report) -> None:
    import psycopg2

    dsn = os.environ.get("AERO_PROVENANCE_DSN")
    if not dsn:
        report.check(False, "mirror read", "AERO_PROVENANCE_DSN is not set")
        return
    conn = psycopg2.connect(dsn)
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(MIRROR_COLUMNS)} FROM mlflow_artifact_provenance "
                "WHERE run_id = %s",
                (run_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    report.check(len(rows) == 1, "exactly one mirror row", str(len(rows)))
    if len(rows) == 1:
        expected = tuple(tags.get(c) for c in MIRROR_COLUMNS)
        report.check(rows[0] == expected, "the mirror row equals the tags byte for byte")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-id", help="MLflow run id (read over the REST API)")
    source.add_argument("--tags-json", type=Path, help="a JSON object of the run's tags")
    source.add_argument(
        "--record",
        type=Path,
        help="a hosted_repro.py run record: its run id and tags (a run-local MLflow has no API)",
    )
    ap.add_argument("--tracking-uri", default=TRACKING_URI)
    ap.add_argument("--config-json", type=Path, help="the resolved config the run hashed")
    ap.add_argument("--mirror", action="store_true", help="also read the Postgres mirror row")
    args = ap.parse_args(argv)
    if args.mirror and not (args.run_id or args.record):
        ap.error("--mirror needs --run-id or --record")

    run_id = args.run_id
    if args.run_id:
        tags = run_tags(args.run_id, args.tracking_uri)
    elif args.record:
        record = json.loads(args.record.read_text(encoding="utf-8"))
        tags, run_id = record["tags"], record["mlflow_run_id"]
    else:
        tags = json.loads(args.tags_json.read_text(encoding="utf-8"))
    report = Report()
    check_tags(tags, report)
    if args.config_json:
        check_config(tags, args.config_json, report)
    if args.mirror:
        check_mirror(run_id, tags, report)
    print(f"{'ALL CHECKS PASS' if not report.failed else f'{report.failed} CHECK(S) FAILED'}")
    return 0 if not report.failed else 1


if __name__ == "__main__":
    sys.exit(main())
