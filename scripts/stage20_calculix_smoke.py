#!/usr/bin/env python3
"""Stage 20 — the CalculiX perpendicular-flap smoke. NON-GATED, by construction.

Stage 19 built, signed and digest-recorded `calculix-precice.sif` but deliberately
deferred running it: the smoke is inherently TWO-container, which forces the
multi-container provenance decision Stage 20 has to make anyway (ADR-038).

**What this proves, and why it must pass before anything else is built.** Stage 19's
gated run put both participants inside ONE image, so nothing yet demonstrates that:

* `ccx_preCICE` runs under Apptainer in an unprivileged LXC at all;
* the calculix-adapter parses its `config.yml` and finds its interface node set;
* socket m2n works **across two containers** — a genuinely new path, since two
  processes in one image share far more than two processes in two images do;
* `--no-home` (mandatory on the OpenFOAM side, or the host `$HOME` shadows the
  adapter) does not break CalculiX;
* the ADR-038 roster survives a real run end to end.

It also teaches us the conventions the Stage-20 authored case must reproduce, from
UPSTREAM'S OWN BYTES rather than from our guesses — which is the whole reason this
runs the pinned tutorial verbatim instead of a case we wrote.

**It bears no verdict.** `gated=False`, and the physics is upstream's, not ours: a
flap in a channel, five seconds of it, with no reference of record. A passing smoke
says the plumbing is real. It says nothing about Heathcote-Gursul.

Usage:

    python scripts/stage20_calculix_smoke.py --host aero-dev
    python scripts/stage20_calculix_smoke.py --host aero-dev --max-time 0.5 --timeout 3600
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(_REPO_ROOT))

from aero.adapters.precice import (  # noqa: E402
    CoupledCaseSpec,
    ParticipantSpec,
    PreciceConfigExpectation,
    PreciceCoupledSolver,
    TutorialPin,
    TutorialSource,
)
from aero.adapters.precice.case import (  # noqa: E402
    CASE_ROOT_DIRNAME,
    assert_provenance_describes,
)
from aero.adapters.precice.launcher import read_coupled_status  # noqa: E402
from aero.adapters.precice.logs import (  # noqa: E402
    find_iterations_logs,
    read_iterations_log,
)
from aero.adapters.precice.watchpoint import read_watchpoint, watchpoint_path  # noqa: E402
from aero.orchestration.local_ssh import LocalSSHExecutor  # noqa: E402
from aero.provenance.four_fold import compute_provenance  # noqa: E402

_REFERENCE_DIR = _REPO_ROOT / "data" / "references" / "fsi" / "precice_perpendicular_flap"
_ARCHIVE = "precice-tutorials-perpendicular-flap.tar.gz"
_MANIFEST = "tutorials_pin_manifest.csv"

TUTORIALS_COMMIT = "cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e"

FLUID_SIF = "precice-fsi.sif"
SOLID_SIF = "calculix-precice.sif"

#: Read off upstream's own `perpendicular-flap/precice-config.xml` at the pinned commit.
#: Asserting it exercises the C-gate machinery against a SECOND case — Stage 19 only ever
#: ran it against FSI3 — and would catch upstream silently changing the coupling under a
#: pin we believe we control.
PERPENDICULAR_FLAP_EXPECTATION = PreciceConfigExpectation(
    participants=("Fluid", "Solid"),
    coupling_scheme="parallel-implicit",
    m2n_kind="sockets",
    time_window_size=1.0e-2,
    max_iterations=50,
    convergence_limits={"Displacement": 5.0e-3, "Force": 5.0e-3},
    # The KIND is compared, not just the limit: 5e-3 absolute is a different problem
    # from 5e-3 relative (ADR-036 C1).
    convergence_kinds={
        "Displacement": "relative-convergence-measure",
        "Force": "relative-convergence-measure",
    },
    watch_points={"Solid/Flap-Tip": (0.0, 1.0)},
    acceleration_kind="IQN-ILS",
)


def _verified(path: Path, *, what: str) -> Path:
    """Check a DVC-tracked artifact against its git-tracked sha256 sidecar."""
    import hashlib

    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file():
        raise SystemExit(
            f"{sidecar} is missing — run scripts/stage20_acquire_perpendicular_flap.py "
            f"to acquire {what}"
        )
    if not path.is_file():
        raise SystemExit(f"{path} is missing — run `dvc pull` to fetch {what}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = sidecar.read_text(encoding="utf-8").strip()
    if digest != expected:
        raise SystemExit(
            f"{path} does not match its recorded sha256\n  expected {expected}\n  got      {digest}"
        )
    return path


def smoke_case_spec(*, max_time: float, wall_clock_ceiling_s: int) -> CoupledCaseSpec:
    """The two-container, explicitly NON-GATED perpendicular-flap case."""
    archive = _verified(_REFERENCE_DIR / _ARCHIVE, what="the pinned perpendicular-flap tutorial")
    return CoupledCaseSpec(
        name="calculix_perpendicular_flap_smoke",
        source=TutorialSource(
            pin=TutorialPin(
                commit=TUTORIALS_COMMIT,
                archive_sha256=(_REFERENCE_DIR / f"{_ARCHIVE}.sha256").read_text().strip(),
                manifest_path=_REFERENCE_DIR / _MANIFEST,
            ),
            archive_path=archive,
            tutorial_case="perpendicular-flap",
            fluid_participant_dir="fluid-openfoam",
        ),
        participants=(
            ParticipantSpec(
                name="Fluid",
                workdir="fluid-openfoam",
                command="./run.sh",
                sif=FLUID_SIF,
                run_as_uid=1000,
            ),
            ParticipantSpec(
                name="Solid",
                workdir="solid-calculix",
                command="./run.sh",
                sif=SOLID_SIF,
                run_as_uid=1000,
            ),
        ),
        container_of_record=FLUID_SIF,
        max_time=max_time,
        wall_clock_ceiling_s=wall_clock_ceiling_s,
        # Unused: this driver never calls load(), because a smoke has no limit cycle to
        # analyse and asking for one would fail for the right reason at the wrong time.
        analysis_discard_s=0.0,
        run_as_uid=1000,
        # NOT a judgement call. The run spans two SIFs and has no reference of record;
        # ADR-038 permits a gated multi-container run, but this case is a plumbing check.
        gated=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="aero-dev", help="LXC to run on (default aero-dev)")
    parser.add_argument(
        "--max-time",
        type=float,
        default=0.5,
        help="coupled end time [s]; upstream's default is 5.0 (default: 0.5, ~50 windows)",
    )
    parser.add_argument("--timeout", type=int, default=3600, help="wall-clock ceiling [s]")
    parser.add_argument("--allow-dirty", action="store_true", help="permit a dirty tree")
    parser.add_argument("--host-nfs-root", default=None)
    parser.add_argument("--remote-nfs-root", default=None)
    parser.add_argument("--out", type=Path, default=Path("/tmp/stage20_calculix_smoke.json"))
    args = parser.parse_args(argv)

    spec = smoke_case_spec(max_time=args.max_time, wall_clock_ceiling_s=args.timeout)

    kwargs: dict[str, object] = {"expectation": PERPENDICULAR_FLAP_EXPECTATION}
    if args.host_nfs_root:
        kwargs["host_nfs_root"] = Path(args.host_nfs_root)
    if args.remote_nfs_root:
        kwargs["remote_nfs_root"] = Path(args.remote_nfs_root)
    solver = PreciceCoupledSolver(**kwargs)  # type: ignore[arg-type]
    executor = LocalSSHExecutor(
        host=args.host, repo_root=_REPO_ROOT, long_timeout_s=args.timeout + 900
    )

    # Provenance BEFORE anything runs, and describing BOTH containers (ADR-038). A tuple
    # naming only the fluid image would understate what ran even for a non-gated smoke.
    provenance = compute_provenance(
        repo_root=_REPO_ROOT,
        container_sif=spec.container_of_record,
        resolved_config=json.loads(spec.model_dump_json()),
        allow_dirty=args.allow_dirty,
        extra_container_sifs=spec.extra_container_sifs,
    )
    assert_provenance_describes(spec, provenance)
    print("provenance (two containers):")
    for key, value in sorted(provenance.as_mlflow_tags().items()):
        print(f"  {key} = {value}")

    record: dict[str, object] = {
        "case": spec.name,
        "gated": spec.gated,
        "verdict": "PENDING",
        "started_at": datetime.now(UTC).isoformat(),
        "host": args.host,
        "spec": json.loads(spec.model_dump_json()),
        "provenance": json.loads(provenance.model_dump_json()),
    }

    try:
        print("\nprepare: materializing the pinned tutorial and asserting the configuration")
        case_dir = solver.prepare(spec)
        record["run_id"] = case_dir.run_id

        print("mesh: blockMesh for the fluid participant")
        mesh = solver.mesh(case_dir, executor)
        record["mesh"] = {"ok": mesh.ok, "n_cells": mesh.n_elements, "failure": mesh.failure}
        if not mesh.ok:
            record["verdict"] = f"FAIL (mesh): {mesh.failure}"
            return _finish(record, args.out, ok=False)
        print(f"  {mesh.n_elements} cells")

        print(f"run: launching Fluid ({FLUID_SIF}) and Solid ({SOLID_SIF}) concurrently")
        result = solver.run(case_dir, executor)
        status = read_coupled_status(
            Path(case_dir.host_path) / CASE_ROOT_DIRNAME / "coupled-status.json",
            case_root_host=Path(case_dir.host_path) / CASE_ROOT_DIRNAME,
            executor_returncode=result.returncode,
        )
        record["coupled_status"] = json.loads(status.model_dump_json())
        print(f"  stopped_by={status.stopped_by} wall_clock={status.wall_clock_s:.0f}s")
        for outcome in status.outcomes:
            print(f"  {outcome.name}: {outcome.state} (rc={outcome.returncode})")

        case_root = Path(case_dir.host_path) / CASE_ROOT_DIRNAME / spec.case_subdir
        record["coupling"] = _coupling_summary(case_root)
        record["watchpoint"] = _watchpoint_summary(case_root, spec)

        ok = status.ok and record["watchpoint"] is not None  # type: ignore[truthy-bool]
        record["verdict"] = (
            "SMOKE PASS (non-gated; proves the two-container plumbing, nothing about physics)"
            if ok
            else f"FAIL: stopped_by={status.stopped_by}"
        )
        return _finish(record, args.out, ok=ok)
    except Exception as exc:
        record["verdict"] = f"FAIL ({type(exc).__name__}): {exc}"
        return _finish(record, args.out, ok=False)


def _coupling_summary(case_root: Path) -> dict[str, object]:
    """Per-participant iteration counts — diagnostics, never gated."""
    try:
        logs = find_iterations_logs(case_root)
    except Exception as exc:
        return {"error": str(exc)}
    summary: dict[str, object] = {}
    for participant, path in sorted(logs.items()):
        report = read_iterations_log(path, participant=participant, max_iterations_configured=50)
        summary[participant] = {
            "n_windows": report.n_windows,
            "n_nonconverged": report.n_nonconverged,
            "mean_iterations": report.mean_iterations,
            "max_iterations": report.max_observed_iterations,
        }
    return summary


def _watchpoint_summary(case_root: Path, spec: CoupledCaseSpec) -> dict[str, object] | None:
    """The flap-tip trace — present and non-empty is the whole assertion here."""
    path = watchpoint_path(case_root, "solid-calculix", "Solid", "Flap-Tip")
    if not path.is_file():
        return None
    trace = read_watchpoint(path, participant="Solid", watch_point="Flap-Tip")
    return {
        "path": str(path),
        "columns": list(trace.columns),
        "n_rows": trace.n_rows,
        "t_end": trace.t_end,
    }


def _finish(record: dict[str, object], out: Path, *, ok: bool) -> int:
    record["finished_at"] = datetime.now(UTC).isoformat()
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\n{record['verdict']}")
    print(f"bundle: {out}")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
