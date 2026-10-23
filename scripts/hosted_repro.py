#!/usr/bin/env python3
"""The hosted reproducibility check's driver: one Blasius number, with its four-tuple (ADR-050).

    # on a GitHub-hosted runner (hosted-repro.yml): the published cluster SIF, logged locally
    python scripts/hosted_repro.py run --executor local-container \\
        --sif "$RUNNER_TEMP/sif/openfoam-esi.sif" --workdir "$RUNNER_TEMP/work" --record record.json

    # on the cluster, the band's reference: the same driver and case, over SSH to aero-build
    python scripts/hosted_repro.py run --executor local-ssh --record cluster.json
    python scripts/hosted_repro.py reference --record cluster.json --out ci/hosted-repro/reference.json

    python scripts/hosted_repro.py band --record record.json --reference ci/hosted-repro/reference.json
    python scripts/hosted_repro.py negative --sif "$RUNNER_TEMP/sif/openfoam-esi.sif"

`run` solves `blasius_flat_plate` once through the platform's own `BenchmarkRunner` and
`start_provenance_run`, on a clean tree (`compute_provenance` refuses a dirty one), and logs
`cf_mid` (ADR-050 D1) beside the case's usual result. The Blasius comparison is a diagnostic, never
the gate. The number and the tags in the record are read back from the MLflow run that was logged,
not taken from memory. A `local-container` run may only log to a run-local store (sqlite or
file); it must never become the V&V gate's newest Blasius evidence (ADR-050 D4).

`band` is the gated, pre-registered comparison: the hosted run's `cf_mid` within 1 % of the
committed cluster reference, at the same config_hash, dvc_input_hash, container digest and scheme
tags. It is never bitwise, and the band is never widened.

`negative` proves the ADR-053 guard on the runner: a one-byte-flipped copy of the SIF under the
same name must exit 86 with `AERO-SIF-REFUSED`, and apptainer must never start.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RECORD_FORMAT = "aero.hosted-repro.record/v1"
REFERENCE_FORMAT = "aero.hosted-repro.reference/v1"
SIF_NAME = "openfoam-esi.sif"
SOLVER_VERSION = "OpenFOAM-ESI v2412"
CLUSTER_TRACKING_URI = "http://192.168.2.234:5000"  # conf/mlflow/default.yaml
#: ADR-050 D5: the gated band, pre-registered. Never widened after the fact.
BAND = 0.01
#: The terms that must be identical between the hosted run and its reference (git_sha may not).
SAME_TERMS = (
    "config_hash",
    "dvc_input_hash",
    "container_sif_sha256",
    "container_sif_name",
    "dvc_input_hash_scheme",
    "container_sif_sha256_scheme",
    "dvc_inputs",
)
PROVENANCE_TAGS = ("git_sha", *SAME_TERMS, "container_sif_set")


def _run(args: argparse.Namespace) -> int:
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.provenance.four_fold import canonical_config_bytes, compute_provenance
    from aero.vv import BenchmarkRunner
    from aero.vv.forward_regime.blasius_flat_plate import BlasiusFlatPlate

    case = BlasiusFlatPlate()
    spec = case.case_spec()
    if args.executor == "local-container":
        from aero.orchestration import LocalContainerExecutor

        sif = Path(args.sif).resolve()
        if sif.name != SIF_NAME or not sif.is_file():
            raise SystemExit(f"--sif must be an existing {SIF_NAME}, got {sif}")
        workdir = Path(args.workdir or tempfile.mkdtemp(prefix="aero-hosted-")).resolve()
        tracking_uri = args.tracking_uri or f"sqlite:///{workdir / 'mlflow.db'}"
        if not tracking_uri.startswith(("sqlite:", "file:")):
            raise SystemExit(
                f"a local-container run logs only to a run-local store, not {tracking_uri!r}: "
                "it must never become the V&V gate's newest Blasius evidence (ADR-050 D4)"
            )
        experiment = args.experiment or "aero-hosted-repro"
        solver = OpenFOAMSolver(sif_path=str(sif), host_nfs_root=workdir, remote_nfs_root=workdir)
        executor: Any = LocalContainerExecutor()
    else:
        from aero.orchestration import LocalSSHExecutor

        nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
        tracking_uri = args.tracking_uri or CLUSTER_TRACKING_URI
        experiment = args.experiment or "aero-provenance"
        solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
        executor = LocalSSHExecutor(
            host=args.host, ssh_user="root", repo_root=REPO, long_timeout_s=2700
        )

    from aero.provenance.db import resolve_dsn

    provenance = compute_provenance(
        repo_root=REPO,
        container_sif=SIF_NAME,
        resolved_config=spec.model_dump(mode="json"),
        dvc_inputs=case.dvc_inputs,
    )
    runner = BenchmarkRunner(
        solver=solver,
        executor=executor,
        tracking_uri=tracking_uri,
        experiment=experiment,
        db_dsn=resolve_dsn(),
        solver_version=SOLVER_VERSION,
        stage="23",
    )
    started = time.monotonic()
    result = runner.run(
        case, provenance=provenance, repo_root=REPO, log_mlflow=True, log_scalars=("cf_mid",)
    )
    wall = time.monotonic() - started

    from mlflow.tracking import MlflowClient

    logged = MlflowClient(tracking_uri=tracking_uri).get_run(str(result.mlflow_run_id))
    tags, metrics = dict(logged.data.tags), dict(logged.data.metrics)
    cf_mid = float(metrics["cf_mid"])
    (diag,) = result.metrics
    record = {
        "format": RECORD_FORMAT,
        "case": case.name,
        "executor": args.executor,
        "host": executor.host if hasattr(executor, "host") else args.host,
        "experiment": experiment,
        "mlflow_run_id": result.mlflow_run_id,
        "tags": {k: tags[k] for k in PROVENANCE_TAGS if k in tags},
        "cf_mid": cf_mid,
        "cf_mid_hex": cf_mid.hex(),
        "diagnostic": {
            "metric": diag.name,
            "max_relative_error_vs_blasius": diag.error,
            "tolerance": diag.tolerance,
            "within_tolerance": diag.passed,
            "note": "a diagnostic only; the gated number is cf_mid against the cluster (ADR-050)",
        },
        "solver_version": SOLVER_VERSION,
        "wall_clock_s": round(wall, 1),
    }
    out = Path(args.record)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    configs = out.parent / "configs"
    configs.mkdir(exist_ok=True)
    preimage = canonical_config_bytes(spec.model_dump(mode="json"))
    (configs / f"{provenance.config_hash}.json").write_bytes(preimage)
    print(f"cf_mid = {cf_mid!r} ({cf_mid.hex()})  run {result.mlflow_run_id}  {wall:.0f} s")
    print(f"diagnostic: max |Cf - Blasius| / Blasius = {diag.error:.4%} (tolerance 5 %, not gated)")
    return 0


def _load(path: Path, fmt: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != fmt:
        raise SystemExit(f"{path}: not a {fmt} file (format {data.get('format')!r})")
    return data


def band_checks(record: dict[str, Any], reference: dict[str, Any]) -> list[tuple[bool, str]]:
    """Every check `band` makes, as (passed, line) — pure, for the tests."""
    checks: list[tuple[bool, str]] = []
    for key in SAME_TERMS:
        a, b = record["tags"].get(key), reference["tags"].get(key)
        checks.append((a is not None and a == b, f"{key} equals the reference"))
    for key, want in (
        ("dvc_input_hash_scheme", "declared-dvc-pointers-md5/v1"),
        ("container_sif_sha256_scheme", "sif-sha256-verified-at-launch/v1"),
    ):
        checks.append((record["tags"].get(key) == want, f"{key} is {want}"))
    for name, data in (("record", record), ("reference", reference)):
        sha = data["tags"].get("git_sha", "")
        checks.append(
            (len(sha) == 40 and "-" not in sha, f"the {name}'s git_sha is a clean commit")
        )
    hosted = float.fromhex(record["cf_mid_hex"])
    cluster = float.fromhex(reference["cf_mid_hex"])
    rel = abs(hosted - cluster) / abs(cluster) if cluster else float("inf")
    checks.append(
        (
            rel <= BAND,
            f"|cf_mid_h - cf_mid_c| / |cf_mid_c| = {rel:.3e} <= {BAND} "
            f"(hosted {hosted!r}, cluster {cluster!r})",
        )
    )
    return checks


def _band(args: argparse.Namespace) -> int:
    record = _load(Path(args.record), RECORD_FORMAT)
    reference = _load(Path(args.reference), REFERENCE_FORMAT)
    checks = band_checks(record, reference)
    for ok, line in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {line}")
    failed = sum(not ok for ok, _ in checks)
    print("BAND PASS" if not failed else f"BAND FAIL ({failed} check(s))")
    return 0 if not failed else 1


def reference_from(record: dict[str, Any]) -> dict[str, Any]:
    """The committed reference, from a cluster record — refused unless it is one."""
    if record.get("executor") != "local-ssh":
        raise SystemExit("the reference must be a cluster run (--executor local-ssh)")
    sha = record["tags"].get("git_sha", "")
    if len(sha) != 40 or "-" in sha:
        raise SystemExit(f"the reference must come from a clean tree, got git_sha {sha!r}")
    return {
        "format": REFERENCE_FORMAT,
        "case": record["case"],
        "mlflow_run_id": record["mlflow_run_id"],
        "experiment": record["experiment"],
        "host": record["host"],
        "tags": record["tags"],
        "cf_mid": record["cf_mid"],
        "cf_mid_hex": record["cf_mid_hex"],
        "band": BAND,
        "note": "committed before the hosted workflow's first execution (ADR-050 D5)",
    }


def _reference(args: argparse.Namespace) -> int:
    reference = reference_from(_load(Path(args.record), RECORD_FORMAT))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}: cf_mid {reference['cf_mid']!r} from run {reference['mlflow_run_id']}")
    return 0


_SHIM = '#!/usr/bin/env bash\ntouch "$AERO_NEGATIVE_MARK"\nexit 99\n'


def _negative(args: argparse.Namespace) -> int:
    from aero.adapters._base import SifPin, build_apptainer_exec
    from aero.provenance.four_fold import container_sif_sha256

    sif = Path(args.sif)
    with tempfile.TemporaryDirectory(prefix="aero-negative-") as tmp:
        root = Path(tmp)
        flipped = root / "swapped" / SIF_NAME
        flipped.parent.mkdir()
        shutil.copyfile(sif, flipped)
        with flipped.open("r+b") as handle:  # one byte, mid-file
            handle.seek(flipped.stat().st_size // 2)
            byte = handle.read(1)
            handle.seek(-1, os.SEEK_CUR)
            handle.write(bytes([byte[0] ^ 0xFF]))
        shim = root / "bin" / "apptainer"
        shim.parent.mkdir()
        shim.write_text(_SHIM, encoding="utf-8")
        shim.chmod(0o755)
        mark = root / "apptainer-started"
        pin = SifPin(path=str(flipped), sha256=container_sif_sha256(REPO, SIF_NAME))
        command = build_apptainer_exec(expected=pin, case_bind_source=tmp, command="true")
        env = dict(os.environ, PATH=f"{shim.parent}:{os.environ['PATH']}")
        env["AERO_NEGATIVE_MARK"] = str(mark)
        proc = subprocess.run(
            ["bash", "-c", command], capture_output=True, text=True, env=env, check=False
        )
        checks = [
            (proc.returncode == 86, f"the swapped SIF exits 86 (got {proc.returncode})"),
            ("AERO-SIF-REFUSED expected=" in proc.stderr, "stderr carries AERO-SIF-REFUSED"),
            (not mark.exists(), "apptainer never started"),
        ]
    for ok, line in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {line}")
    return 0 if all(ok for ok, _ in checks) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="solve blasius_flat_plate once and write the run record")
    run.add_argument("--executor", choices=("local-container", "local-ssh"), required=True)
    run.add_argument("--sif", help="local-container: the downloaded, checked openfoam-esi.sif")
    run.add_argument("--workdir", help="local-container: the case tree (default: a temp dir)")
    run.add_argument("--host", default="aero-build", help="local-ssh: the solve host")
    run.add_argument("--tracking-uri")
    run.add_argument("--experiment")
    run.add_argument("--record", required=True)
    band = sub.add_parser("band", help="the gated comparison against the committed reference")
    band.add_argument("--record", required=True)
    band.add_argument("--reference", required=True)
    ref = sub.add_parser("reference", help="turn a cluster record into the committed reference")
    ref.add_argument("--record", required=True)
    ref.add_argument("--out", required=True)
    neg = sub.add_parser("negative", help="a one-byte-flipped SIF is refused before apptainer")
    neg.add_argument("--sif", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "run" and args.executor == "local-container" and not args.sif:
        ap.error("--executor local-container needs --sif")
    handler = {"run": _run, "band": _band, "reference": _reference, "negative": _negative}
    return handler[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
