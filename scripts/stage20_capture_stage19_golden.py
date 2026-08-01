#!/usr/bin/env python3
"""Build the Stage-19 load-path fixtures and capture their goldens.

**Why this script exists, and why it must be run BEFORE the Stage-20 `source`-seam
refactor.** `tests/stage_20/test_stage19_load_path_unchanged.py` pins
`PreciceCoupledSolver.load()` against a committed golden. A golden produced by
post-refactor code proves nothing at all — it would simply record whatever the refactor
did. So the fixtures and the goldens are captured here, on the pre-refactor tree, and
committed in their own commit; the refactor lands afterwards and has to reproduce them.

The ordering is provable after the fact, not merely asserted:

    git log --oneline -- tests/stage_20/fixtures/stage19_load_path/   # exactly one commit
    git merge-base --is-ancestor <that commit> <the refactor commit>  # true

There is deliberately **no** ``--regenerate`` flag on the test itself. An escape hatch in
the test is how a golden gets silently rewritten to match a regression.

Nothing here is a real Turek-Hron solve. The fixtures are a synthetic record shaped like
one, chosen so that every branch of `load()` is exercised and so that the FFT-detected
period is bin-exact and therefore deterministic:

* 512 rows at dt = 1 ms, the first at t = dt (preCICE writes one row per COMPLETED
  window, so a real watch-point never starts at t = 0);
* an absolute discard of 0.0645 s keeps rows 65..512, i.e. exactly 448 samples;
* the transverse signal completes exactly 16 cycles in those 448 samples, so it sits on
  DFT bin 16 and the parabolic peak interpolation contributes ~0;
* the streamwise signal is a pure SECOND harmonic with a non-zero mean, which is the real
  FSI3 structure and is what makes `tip_ux_mean` / `tip_ux_frequency` meaningful;
* the iteration logs carry one capped window and one flagged-non-converged window, both
  strictly BELOW the analysis window's first index — so deleting `.within()` from
  `load()` turns the test red.

The same reasoning covers the *materialization* fixture built here: a tiny committed
tutorial archive plus its pin manifest, driven through the real `_write_case`, whose
`aero-manifest.json` bytes are the golden the refactor must reproduce.

Usage:  python scripts/stage20_capture_stage19_golden.py [--fixtures] [--golden]
        (no flag = do both)
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aero.adapters._base import CaseDir, ResultHandle  # noqa: E402
from aero.adapters.precice.case import (  # noqa: E402
    CoupledCaseSpec,
    ParticipantSpec,
    TutorialPin,
)
from aero.adapters.precice.solver import PreciceCoupledSolver  # noqa: E402

FIXTURE_ROOT = _REPO_ROOT / "tests" / "stage_20" / "fixtures" / "stage19_load_path"
MATERIALIZATION_ROOT = _REPO_ROOT / "tests" / "stage_20" / "fixtures" / "materialization"

# --- the synthetic record -------------------------------------------------------------

TUTORIAL_CASE = "turek-hron-fsi3"
FLUID_DIR = "fluid-openfoam"
SOLID_DIR = "solid-nutils"

N_ROWS = 512
DT = 1.0e-3
#: Absolute discard, on the solver clock. Chosen so `t >= DISCARD_S` keeps rows 65..512.
DISCARD_S = 0.0645
MIN_CYCLES = 4
FIRST_KEPT_ROW = 65
N_KEPT = N_ROWS - FIRST_KEPT_ROW + 1  # 448
N_CYCLES_IN_WINDOW = 16  # -> DFT bin 16 of 448 samples: exactly on-bin
MAX_ITERATIONS = 100

UY_AMPLITUDE = 3.4e-2
UX_MEAN = -2.7e-3
UX_AMPLITUDE = 2.8e-3
#: The watch-point's undeformed coordinate — FSI3 benchmark point A.
WATCH_COORDINATE = (0.6, 0.2)

#: Windows that must NOT reach the gate: both sit below the analysis window's first index
#: (64), so `.within()` is what excludes them. One hits the cap, one is flagged.
CAPPED_WINDOW = 5
FLAGGED_WINDOW = 63
#: The one window carrying the maximum in-window iteration count, so the golden's
#: `coupling_max_iterations` is sensitive to the window range actually gated.
PEAK_WINDOW = 200
PEAK_ITERATIONS = 9


def _num(value: float) -> str:
    """17 significant digits — round-trips a float64 exactly, so the golden is stable."""
    return f"{value:.16e}"


def _txt_table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    """preCICE `TXTTableWriter` shape: two-space leading delimiter, rows PREFIXED by \\n.

    The file therefore has no trailing newline. `_txt_table.read_txt_table` splits on
    whitespace so the separator width is cosmetic, but the fixture reproduces the real
    shape so that a future reader change is tested against something honest.
    """
    out = "  " + "  ".join(header)
    for row in rows:
        out += "\n  " + "  ".join(row)
    return out


def _watchpoint_text() -> str:
    header = (
        "Time",
        "Coordinate0",
        "Coordinate1",
        "Displacement0",
        "Displacement1",
        "Stress0",
        "Stress1",
    )
    rows: list[tuple[str, ...]] = []
    for k in range(1, N_ROWS + 1):
        t = k * DT
        # Phase by SAMPLE INDEX, not by time: that is what makes the kept window exactly
        # on-bin regardless of floating-point time arithmetic.
        j = k - FIRST_KEPT_ROW
        phase = 2.0 * math.pi * N_CYCLES_IN_WINDOW * j / N_KEPT
        uy = UY_AMPLITUDE * math.sin(phase)
        ux = UX_MEAN + UX_AMPLITUDE * math.cos(2.0 * phase)
        rows.append(
            (
                _num(t),
                _num(WATCH_COORDINATE[0]),
                _num(WATCH_COORDINATE[1]),
                _num(ux),
                _num(uy),
                _num(0.0),
                _num(0.0),
            )
        )
    return _txt_table(header, rows)


def _iterations_for(window: int) -> tuple[int, int]:
    """(iterations, convergence) for one time window."""
    if window == CAPPED_WINDOW:
        return MAX_ITERATIONS, 1  # hit the cap -> non-converged by K1's definition
    if window == FLAGGED_WINDOW:
        return 7, 0  # preCICE's own verdict: did not converge
    if window == PEAK_WINDOW:
        return PEAK_ITERATIONS, 1
    return 3 + (window % 5), 1  # 3..7, deterministic


def _iterations_text(*, quasi_newton: bool) -> str:
    header = ["TimeWindow", "TotalIterations", "Iterations", "Convergence"]
    if quasi_newton:
        header += ["QNColumns", "DeletedQNColumns", "DroppedQNColumns"]
    rows: list[tuple[str, ...]] = []
    total = 0
    for window in range(N_ROWS):
        iterations, converged = _iterations_for(window)
        total += iterations
        row = [str(window), str(total), str(iterations), str(converged)]
        if quasi_newton:
            row += [str(min(iterations, 8)), "0", "0"]
        rows.append(tuple(row))
    return _txt_table(tuple(header), rows)


_PRECICE_CONFIG = """<?xml version="1.0" encoding="UTF-8" ?>
<precice-configuration>
  <data:vector name="Stress" />
  <data:vector name="Displacement" />

  <mesh name="Fluid-Mesh" dimensions="2">
    <use-data name="Displacement" />
    <use-data name="Stress" />
  </mesh>

  <mesh name="Solid-Mesh" dimensions="2">
    <use-data name="Displacement" />
    <use-data name="Stress" />
  </mesh>

  <participant name="Fluid">
    <provide-mesh name="Fluid-Mesh" />
    <receive-mesh name="Solid-Mesh" from="Solid" />
    <read-data name="Displacement" mesh="Fluid-Mesh" />
    <write-data name="Stress" mesh="Fluid-Mesh" />
    <mapping:nearest-neighbor
      direction="write"
      from="Fluid-Mesh"
      to="Solid-Mesh"
      constraint="conservative" />
    <mapping:nearest-neighbor
      direction="read"
      from="Solid-Mesh"
      to="Fluid-Mesh"
      constraint="consistent" />
  </participant>

  <participant name="Solid">
    <provide-mesh name="Solid-Mesh" />
    <read-data name="Stress" mesh="Solid-Mesh" />
    <write-data name="Displacement" mesh="Solid-Mesh" />
    <watch-point mesh="Solid-Mesh" name="Flap-Tip" coordinate="0.6;0.2" />
  </participant>

  <m2n:sockets acceptor="Fluid" connector="Solid" exchange-directory=".." />

  <coupling-scheme:parallel-implicit>
    <participants first="Fluid" second="Solid" />
    <max-time value="0.512" />
    <time-window-size value="1e-3" />
    <max-iterations value="100" />
    <exchange data="Stress" mesh="Solid-Mesh" from="Fluid" to="Solid" />
    <exchange data="Displacement" mesh="Solid-Mesh" from="Solid" to="Fluid" />
    <relative-convergence-measure limit="1e-4" data="Displacement" mesh="Solid-Mesh" />
    <relative-convergence-measure limit="1e-4" data="Stress" mesh="Solid-Mesh" />
    <acceleration:IQN-ILS>
      <data name="Displacement" mesh="Solid-Mesh" scaling="1" />
      <preconditioner type="residual-sum" />
      <filter type="QR2" limit="1e-2" />
      <initial-relaxation value="0.1" />
      <max-used-iterations value="100" />
      <time-windows-reused value="15" />
    </acceleration:IQN-ILS>
  </coupling-scheme:parallel-implicit>
</precice-configuration>
"""

#: The C4 negative: `Stress` declared BEFORE `Displacement` on the watched mesh, so the
#: predicted header no longer matches the file. Without this, gate C4 is decorative.
_PRECICE_CONFIG_STRESS_FIRST = _PRECICE_CONFIG.replace(
    """  <mesh name="Solid-Mesh" dimensions="2">
    <use-data name="Displacement" />
    <use-data name="Stress" />
  </mesh>""",
    """  <mesh name="Solid-Mesh" dimensions="2">
    <use-data name="Stress" />
    <use-data name="Displacement" />
  </mesh>""",
)


def _status(
    *,
    stopped_by: str,
    fluid_rc: int | None,
    solid_rc: int | None,
    wall_clock_s: float,
) -> str:
    payload = {
        "run_id": "turek_hron_fsi3-fixture",
        "wall_clock_s": wall_clock_s,
        "stopped_by": stopped_by,
        "participants": [
            {
                "name": "Fluid",
                "returncode": fluid_rc,
                "state_hint": "recorded by the supervisor; re-derived from returncode on read",
                "started_epoch": 1000.0,
                "ended_epoch": 1000.0 + wall_clock_s,
                "log_path": "/mnt/aero/runs/fixture/tutorial/Fluid.log",
            },
            {
                "name": "Solid",
                "returncode": solid_rc,
                "state_hint": "recorded by the supervisor; re-derived from returncode on read",
                "started_epoch": 1000.0,
                "ended_epoch": 1000.0 + wall_clock_s,
                "log_path": "/mnt/aero/runs/fixture/tutorial/Solid.log",
            },
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


#: `stopped_by` / participant exit codes -> the four endings `load()`'s K2 must separate.
#: 143 is 128+SIGTERM, which `read_coupled_status` classifies as "killed".
STATUS_VARIANTS: dict[str, str] = {
    "all-exited": _status(stopped_by="all-exited", fluid_rc=0, solid_rc=0, wall_clock_s=73123.0),
    "ceiling-ok": _status(stopped_by="ceiling", fluid_rc=143, solid_rc=143, wall_clock_s=172800.0),
    # The desynchronised ceiling: Fluid had already exited when the ceiling fired.
    "ceiling-desync": _status(
        stopped_by="ceiling", fluid_rc=0, solid_rc=143, wall_clock_s=172800.0
    ),
    "participant-died": _status(
        stopped_by="participant-died", fluid_rc=1, solid_rc=143, wall_clock_s=311.0
    ),
}

#: Status variants that reach a `SolveResult` (the other two must raise).
GOLDEN_VARIANTS = ("all-exited", "ceiling-ok")


def write_fixtures(root: Path = FIXTURE_ROOT) -> None:
    """(Re)write the committed fixture INPUTS. Deterministic — byte-identical every run.

    `golden/` is deliberately left alone. It is an OUTPUT, captured from the code under
    test; wiping it here would mean a bare `--fixtures` silently discards the very thing
    the ordering rule exists to protect, and the next `--golden` would re-capture it from
    whatever code happened to be checked out.
    """
    for owned in ("tutorial", "status", "bad"):
        if (root / owned).exists():
            shutil.rmtree(root / owned)
    tutorial = root / "tutorial"
    case = tutorial / TUTORIAL_CASE
    (case / FLUID_DIR).mkdir(parents=True)
    (case / SOLID_DIR).mkdir(parents=True)
    (root / "status").mkdir()
    (root / "golden").mkdir(exist_ok=True)
    (root / "bad").mkdir()

    (tutorial / "Fluid.log").write_text(
        "Time = 0.512\nCourant Number mean: 0.0121 max: 0.318\nEnd\n", encoding="utf-8"
    )
    (tutorial / "Solid.log").write_text(
        "solid: time window 512\nsolid: finished\n", encoding="utf-8"
    )
    (case / "precice-config.xml").write_text(_PRECICE_CONFIG, encoding="utf-8")
    (root / "bad" / "precice-config.stress-first.xml").write_text(
        _PRECICE_CONFIG_STRESS_FIRST, encoding="utf-8"
    )
    (case / FLUID_DIR / "precice-Fluid-iterations.log").write_text(
        _iterations_text(quasi_newton=False), encoding="utf-8"
    )
    (case / SOLID_DIR / "precice-Solid-iterations.log").write_text(
        _iterations_text(quasi_newton=True), encoding="utf-8"
    )
    (case / SOLID_DIR / "precice-Solid-watchpoint-Flap-Tip.log").write_text(
        _watchpoint_text(), encoding="utf-8"
    )
    for name, text in STATUS_VARIANTS.items():
        (root / "status" / f"coupled-status.{name}.json").write_text(text, encoding="utf-8")


# --- the fake ResultHandle, shared with the test --------------------------------------


def fixture_spec() -> CoupledCaseSpec:
    """A `CoupledCaseSpec` shaped like the gated FSI3 one.

    `archive_path` / `manifest_path` are never touched on the load path (they are read at
    materialization, which this fixture deliberately does not exercise), so they point at
    the real files only so the spec reads honestly.
    """
    reference = _REPO_ROOT / "data" / "references" / "fsi" / "turek_hron_fsi3"
    return CoupledCaseSpec(
        name="turek_hron_fsi3",
        pin=TutorialPin(
            commit="cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e",
            archive_sha256="0" * 64,
            manifest_path=reference / "tutorials_pin_manifest.csv",
        ),
        archive_path=reference / "precice-tutorials-turek-hron-fsi3.tar.gz",
        tutorial_case=TUTORIAL_CASE,
        participants=(
            ParticipantSpec(
                name="Fluid", workdir=FLUID_DIR, command="./run.sh", sif="precice-fsi.sif"
            ),
            ParticipantSpec(
                name="Solid", workdir=SOLID_DIR, command="./run.sh", sif="precice-fsi.sif"
            ),
        ),
        container_of_record="precice-fsi.sif",
        max_time=0.512,
        wall_clock_ceiling_s=172800,
        analysis_discard_s=DISCARD_S,
        analysis_min_cycles=MIN_CYCLES,
    )


def stage_fixture_tree(destination: Path, *, status: str, config: str | None = None) -> Path:
    """Copy the committed `tutorial/` tree into `destination`, with one status file.

    `config` names a replacement `precice-config.xml` from the fixture's `bad/` directory
    (used by the gate-C4 negative test); the default keeps the committed one.
    """
    tutorial = destination / "tutorial"
    shutil.copytree(FIXTURE_ROOT / "tutorial", tutorial)
    shutil.copy2(
        FIXTURE_ROOT / "status" / f"coupled-status.{status}.json",
        tutorial / "coupled-status.json",
    )
    if config is not None:
        shutil.copy2(FIXTURE_ROOT / "bad" / config, tutorial / TUTORIAL_CASE / "precice-config.xml")
    return tutorial


def fake_result(tutorial: Path, *, run_id: str = "turek_hron_fsi3-fixture") -> ResultHandle:
    """A `ResultHandle` over a staged fixture tree — no cluster, no solve."""
    return ResultHandle(
        case_dir=CaseDir(
            run_id=run_id,
            spec=fixture_spec(),
            host_path=tutorial.parent,
            remote_path=Path("/mnt/aero/runs") / run_id,
        ),
        returncode=0,
        output_host_path=tutorial,
        solver_log="fixture",
    )


def capture_goldens(root: Path = FIXTURE_ROOT) -> None:
    """Run the REAL `load()` over the fixtures and write the goldens."""
    for variant in GOLDEN_VARIANTS:
        with tempfile.TemporaryDirectory() as tmp:
            tutorial = stage_fixture_tree(Path(tmp), status=variant)
            solver = PreciceCoupledSolver()
            solve = solver.load(fake_result(tutorial))
        payload = json.loads(
            solve.model_copy(
                update={"source": "<fixture>", "run_id": "<fixture>"}
            ).model_dump_json()
        )
        (root / "golden" / f"solve_result.{variant}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"captured {variant}: {len(payload['scalars'])} scalars")


# --- the materialization fixture ------------------------------------------------------
#
# A *tiny* stand-in for the pinned tutorial archive, deliberately not the real one:
#
#  * the real FSI3 archive is DVC-tracked and gitignored, so a test built on it cannot run
#    in the required unit job (it gets a DVC-gated sibling instead, which is the one that
#    actually protects the Stage-19 record);
#  * the real gated spec selects the DEFAULT `blockMeshDict`, so `select_fluid_mesh`
#    returns early and produces ONE mutation. A golden with one mutation cannot detect a
#    mutation-ORDERING regression. This fixture ships two variants and selects the
#    non-default one, so the ledger carries `(fluid-mesh-dict, max-time)` in that order.
#
# The archive is COMMITTED rather than built at test time: building it would make
# `TutorialPin.archive_sha256` unpinnable (the test would have to compute the digest it is
# supposed to be checking), and `tarfile`'s gzip wrapper stamps the current time anyway.
# Everything below is therefore pinned to fixed mtimes/uids so a rebuild is byte-identical.

TINY_TUTORIAL_CASE = "turek-hron-fsi3"

_TINY_CONFIG = """<?xml version="1.0" encoding="UTF-8" ?>
<precice-configuration>
  <data:vector name="Stress" />
  <data:vector name="Displacement" />

  <mesh name="Fluid-Mesh" dimensions="2">
    <use-data name="Displacement" />
    <use-data name="Stress" />
  </mesh>

  <mesh name="Solid-Mesh" dimensions="2">
    <use-data name="Displacement" />
    <use-data name="Stress" />
  </mesh>

  <participant name="Fluid">
    <provide-mesh name="Fluid-Mesh" />
    <receive-mesh name="Solid-Mesh" from="Solid" />
    <read-data name="Displacement" mesh="Fluid-Mesh" />
    <write-data name="Stress" mesh="Fluid-Mesh" />
  </participant>

  <participant name="Solid">
    <provide-mesh name="Solid-Mesh" />
    <read-data name="Stress" mesh="Solid-Mesh" />
    <write-data name="Displacement" mesh="Solid-Mesh" />
    <watch-point mesh="Solid-Mesh" name="Flap-Tip" coordinate="0.6;0.2" />
  </participant>

  <m2n:sockets acceptor="Fluid" connector="Solid" exchange-directory=".." />

  <coupling-scheme:parallel-implicit>
    <participants first="Fluid" second="Solid" />
    <max-time value="8.0" />
    <time-window-size value="1e-3" />
    <max-iterations value="100" />
    <exchange data="Stress" mesh="Solid-Mesh" from="Fluid" to="Solid" />
    <exchange data="Displacement" mesh="Solid-Mesh" from="Solid" to="Fluid" />
    <relative-convergence-measure limit="1e-4" data="Displacement" mesh="Solid-Mesh" />
    <relative-convergence-measure limit="1e-4" data="Stress" mesh="Solid-Mesh" />
    <acceleration:IQN-ILS>
      <data name="Displacement" mesh="Solid-Mesh" scaling="1" />
      <initial-relaxation value="0.1" />
    </acceleration:IQN-ILS>
  </coupling-scheme:parallel-implicit>
</precice-configuration>
"""

#: `tools/` is a SIBLING of the case directory, exactly as upstream lays it out — the
#: run.sh scripts source `../../tools/log.sh`, so a fixture that flattened the tree would
#: not test the layout `materialize_tutorial` promises to preserve.
TINY_TUTORIAL_FILES: dict[str, str] = {
    "tools/log.sh": "#!/bin/sh\n# stand-in for upstream's logging helper\n",
    f"{TINY_TUTORIAL_CASE}/precice-config.xml": _TINY_CONFIG,
    f"{TINY_TUTORIAL_CASE}/fluid-openfoam/system/blockMeshDict": (
        "// stand-in: the upstream default fluid mesh\nconvertToMeters 1;\nnCells 20969;\n"
    ),
    f"{TINY_TUTORIAL_CASE}/fluid-openfoam/system/blockMeshDict_refined": (
        "// stand-in: the upstream refined fluid mesh\nconvertToMeters 1;\nnCells 46421;\n"
    ),
    f"{TINY_TUTORIAL_CASE}/solid-nutils/run.sh": "#!/bin/sh\n. ../../tools/log.sh\n",
}

#: sha256 of `tiny-tutorial.tar.gz`. Pinned, and re-verified on every rebuild: if this
#: moves, the archive is no longer byte-reproducible and `TutorialPin.archive_sha256`
#: in the test would be pinning a moving target.
TINY_ARCHIVE_SHA256 = "0d576d1ff7410cf7d272b0cef70c15343f17b3bae95ff68ad986a4ac33079033"


def _tiny_archive_bytes() -> bytes:
    """The tiny tutorial as a byte-reproducible .tar.gz (fixed mtimes, uids, order)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name in sorted(TINY_TUTORIAL_FILES):
            payload = TINY_TUTORIAL_FILES[name].encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            tar.addfile(info, io.BytesIO(payload))
    packed = io.BytesIO()
    with gzip.GzipFile(fileobj=packed, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    return packed.getvalue()


def _tiny_manifest_csv() -> str:
    lines = [
        "# Per-file sha256 manifest for the tiny materialization fixture.",
        "# Regenerate: python scripts/stage20_capture_stage19_golden.py --fixtures",
        "sha256,path",
    ]
    for name in sorted(TINY_TUTORIAL_FILES):
        digest = hashlib.sha256(TINY_TUTORIAL_FILES[name].encode("utf-8")).hexdigest()
        lines.append(f"{digest},{name}")
    return "\n".join(lines) + "\n"


def write_materialization_fixture(root: Path = MATERIALIZATION_ROOT) -> str:
    """(Re)write the tiny archive + manifest. Returns the archive's sha256."""
    root.mkdir(parents=True, exist_ok=True)
    archive = _tiny_archive_bytes()
    (root / "tiny-tutorial.tar.gz").write_bytes(archive)
    (root / "tiny_pin_manifest.csv").write_text(_tiny_manifest_csv(), encoding="utf-8")
    digest = hashlib.sha256(archive).hexdigest()
    if TINY_ARCHIVE_SHA256 != "PENDING" and digest != TINY_ARCHIVE_SHA256:
        raise SystemExit(
            f"tiny-tutorial.tar.gz is no longer byte-reproducible: {digest} != "
            f"{TINY_ARCHIVE_SHA256}. Update TINY_ARCHIVE_SHA256 only if the change is "
            "intentional — the test pins this digest as TutorialPin.archive_sha256."
        )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true", help="write the fixture tree")
    parser.add_argument("--golden", action="store_true", help="capture the goldens")
    args = parser.parse_args()
    do_all = not (args.fixtures or args.golden)
    if args.fixtures or do_all:
        write_fixtures()
        print(f"wrote fixtures under {FIXTURE_ROOT.relative_to(_REPO_ROOT)}")
        digest = write_materialization_fixture()
        print(f"wrote materialization fixture (archive sha256 {digest})")
    if args.golden or do_all:
        capture_goldens()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
