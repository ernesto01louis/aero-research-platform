"""Turek-Hron FSI3 — partitioned fluid-structure coupling verification (Stage 19).

FSI3 is the benchmark's hardest case: Re = 200, a highly flexible flag, and the largest
added-mass ratio of the Turek & Hron (2006) set. It is run here through the **supported
upstream preCICE tutorial** — OpenFOAM (pimpleFoam) fluid coupled to a Nutils
St. Venant-Kirchhoff solid — deliberately unmodified except for the two declared
mutations in :mod:`aero.adapters.precice.case`. Running the maintained tutorial rather
than a case of our own is what makes this evidence *about preCICE coupling* and not about
our ability to set up an FSI problem (ADR-016).

What is gated, and why those five quantities (ADR-036 D1-D5):

* the transverse tip amplitude and its frequency are the flag's motion — if the coupling
  is wrong, these are wrong;
* the streamwise tip amplitude and mean are second-order (the tip is ~13x smaller in x)
  and dominated by the solid model, so they carry a wider band;
* the streamwise frequency is a structural check that the harmonic content is right
  (streamwise is the second harmonic of transverse) and is declared **correlated** with
  the transverse frequency, not independent evidence.

What is NOT gated: the transverse **mean**. It is ~3 % of its own amplitude and, being
period-conditioned, moves ~50 % for a 1.5 % change in the assumed period — measured on
the published reference itself. A relative tolerance on it would say nothing about the
physics and everything about the segmentation. Same disposition as CFD3's near-zero mean
lift, but here established quantitatively rather than by analogy.

The reference of record is ``fsi3_recomputed.csv``: the published featflow FSI3 series
put through :func:`aero.postprocess.analyse_limit_cycle` — the *same function* that
measures our solve. Provenance, identification evidence and the agreement with the
published table are in the reference directory's ``reference.md``.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from aero.adapters.precice.case import CoupledCaseSpec, ParticipantSpec, TutorialPin
from aero.adapters.precice.config import PreciceConfigExpectation
from aero.vv._base import BenchmarkError, MetricSpec, ReferenceData, Series, SolverLike

__all__ = [
    "TUREK_HRON_FSI3_EXPECTATION",
    "TurekHronFSI3",
    "fsi3_case_spec",
    "is_gated_configuration",
]

_REFERENCE_DIR = Path("data") / "references" / "fsi" / "turek_hron_fsi3"
_RECOMPUTED = "fsi3_recomputed.csv"
_ARCHIVE = "precice-tutorials-turek-hron-fsi3.tar.gz"
_MANIFEST = "tutorials_pin_manifest.csv"

#: The pinned upstream tutorial commit (branch `develop`). `master` does not carry the
#: FSI participants at all — see reference.md.
TUTORIALS_COMMIT = "cd33e2dbacc5a2f4a1202e215890f54a2ce2e79e"

#: What the configuration MUST say before we run it (ADR-036 gate C1). Every value here
#: was read off the pinned upstream file; the point is that a future pin bump which
#: changes any of them stops the campaign instead of silently redefining the benchmark.
TUREK_HRON_FSI3_EXPECTATION = PreciceConfigExpectation(
    participants=("Fluid", "Solid"),
    coupling_scheme="parallel-implicit",
    m2n_kind="sockets",
    time_window_size=1e-3,
    max_iterations=100,
    convergence_limits={"Stress": 1e-4, "Displacement": 1e-4},
    convergence_kinds={
        "Stress": "relative-convergence-measure",
        "Displacement": "relative-convergence-measure",
    },
    watch_points={"Solid/Flap-Tip": (0.6, 0.2)},
    acceleration_kind="IQN-ILS",
)

#: Pre-registered analysis rule (ADR-036 S2/S3). The inlet ramp ends at t = 2 s and the
#: published reference window begins at t = 5 s; 4 s is the declared discard.
ANALYSIS_DISCARD_S = 4.0
ANALYSIS_MIN_CYCLES = 4

#: The rung and end-time ADR-036 B2 pre-registers for the GATED campaign. Any other
#: combination is, by construction, one of the B3 diagnostics — see `fsi3_case_spec`.
GATED_MESH_DICT = "blockMeshDict"
GATED_MAX_TIME = 8.0

#: Pre-registered displacement bands (ADR-036 D1-D5).
_BAND_UY_AMPLITUDE = 0.15
_BAND_UY_FREQUENCY = 0.05
_BAND_UX_AMPLITUDE = 0.25
_BAND_UX_MEAN = 0.25
_BAND_UX_FREQUENCY = 0.05


def is_gated_configuration(*, fluid_mesh_dict: str, max_time: float) -> bool:
    """Is this the ONE configuration ADR-036 B2 pre-registers as gated?

    Pure and filesystem-free on purpose, so the required CI job can guard it without a
    DVC pull. ADR-036 B3 declares the refined-mesh run non-gated "so it cannot become a
    second attempt at the gate"; that declaration is only worth anything if it is
    structural, and this predicate is where it is structural.
    """
    return fluid_mesh_dict == GATED_MESH_DICT and max_time == GATED_MAX_TIME


def _repo_root() -> Path:
    # aero/vv/fsi/turek_hron_fsi3.py -> repo root.
    return Path(__file__).resolve().parents[3]


def _verified(path: Path, *, what: str) -> str:
    """Return `path`'s sha256, checked against its git-tracked sidecar."""
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file():
        raise BenchmarkError(
            f"{sidecar} not found — the {what} has not been acquired "
            "(scripts/stage19_acquire_fsi_reference.py) or the checkout is incomplete"
        )
    recorded = sidecar.read_text(encoding="utf-8").strip()
    if not path.is_file():
        raise BenchmarkError(f"{path} not found — run `dvc pull` to fetch the {what}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != recorded:
        raise BenchmarkError(
            f"{path}: SHA-256 {actual[:12]}... != recorded {recorded[:12]}... — "
            f"the pulled {what} does not match the acquisition record"
        )
    return recorded


def _reference_scalar(repo_root: Path, quantity: str) -> float:
    """One value from the recomputed reference of record."""
    path = repo_root / _REFERENCE_DIR / _RECOMPUTED
    if not path.is_file():
        raise BenchmarkError(
            f"{path} not found — run scripts/stage19_acquire_fsi_reference.py to "
            "establish the FSI3 reference of record"
        )
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    for row in csv.DictReader(lines):
        if row["quantity"] == quantity:
            return float(row["value"])
    raise BenchmarkError(f"{path}: no reference quantity {quantity!r}")


def fsi3_case_spec(
    *,
    name: str = "turek_hron_fsi3",
    max_time: float,
    wall_clock_ceiling_s: int,
    fluid_mesh_dict: str = "blockMeshDict",
    sif: str = "precice-fsi.sif",
    run_as_uid: int = 1000,
    repo_root: Path | None = None,
) -> CoupledCaseSpec:
    """Build the coupled case spec, verifying the pinned artifacts as it goes."""
    root = repo_root or _repo_root()
    archive = root / _REFERENCE_DIR / _ARCHIVE
    archive_sha = _verified(archive, what="pinned preCICE tutorial archive")
    # `gated` is DERIVED, never passed in. ADR-036 B2 pre-registers exactly one gated
    # configuration; B3's refined-mesh run is declared non-gated from the start "so it
    # cannot become a second attempt at the gate". Letting a caller assert gated=True for
    # an arbitrary rung or a shortened end time would make that declaration decorative.
    gated = is_gated_configuration(fluid_mesh_dict=fluid_mesh_dict, max_time=max_time)
    return CoupledCaseSpec(
        name=name,
        pin=TutorialPin(
            commit=TUTORIALS_COMMIT,
            archive_sha256=archive_sha,
            manifest_path=root / _REFERENCE_DIR / _MANIFEST,
        ),
        archive_path=archive,
        tutorial_case="turek-hron-fsi3",
        participants=(
            ParticipantSpec(
                name="Fluid",
                workdir="fluid-openfoam",
                # The tutorial's own entry point, verbatim. tools/run-openfoam.sh runs
                # serial when given no -parallel flag, which is what the MPI-blocked
                # LXC needs anyway.
                command="../../tools/run-openfoam.sh",
                sif=sif,
                run_as_uid=run_as_uid,
            ),
            ParticipantSpec(
                name="Solid",
                workdir="solid-nutils",
                # PRECICE_TUTORIALS_NO_VENV makes upstream's run.sh use the interpreter
                # already on PATH instead of building a venv from the network, which the
                # SIF has neither the need nor the ability to do.
                command="./run.sh",
                sif=sif,
                env={"PRECICE_TUTORIALS_NO_VENV": "1"},
                run_as_uid=run_as_uid,
            ),
        ),
        container_of_record=sif,
        max_time=max_time,
        fluid_mesh_dict=fluid_mesh_dict,  # type: ignore[arg-type]
        wall_clock_ceiling_s=wall_clock_ceiling_s,
        analysis_discard_s=ANALYSIS_DISCARD_S,
        analysis_min_cycles=ANALYSIS_MIN_CYCLES,
        run_as_uid=run_as_uid,
        gated=gated,
    )


class TurekHronFSI3:
    """Turek-Hron FSI3 coupling verification against the published displacement bands."""

    name = "turek_hron_fsi3"
    description = (
        "Turek-Hron FSI3 partitioned FSI (OpenFOAM + Nutils via preCICE) — flag-tip "
        "displacement amplitude, mean and frequency vs the published Turek & Hron (2006) "
        "values."
    )
    sweep_metric = "tip_uy_amplitude"

    def __init__(self, spec: CoupledCaseSpec | None = None) -> None:
        self._spec = spec

    def case_spec(self) -> CoupledCaseSpec:
        if self._spec is None:
            self._spec = fsi3_case_spec(
                name=self.name,
                # Defaults match the pre-declared campaign budget (ADR-036 B2). The
                # campaign driver passes its own; these keep `aero vv run` usable.
                max_time=GATED_MAX_TIME,
                wall_clock_ceiling_s=172800,
            )
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        return ReferenceData(
            case_name=self.name,
            source=(
                "Turek & Hron (2006) FSI3, featflow level 4 / dt 2.5e-4, recomputed from "
                "the published ref_fsi3.point with aero.postprocess.analyse_limit_cycle"
            ),
            scalars={
                "tip_uy_amplitude": _reference_scalar(repo_root, "uy_amplitude"),
                "tip_uy_frequency": _reference_scalar(repo_root, "frequency"),
                "tip_ux_amplitude": _reference_scalar(repo_root, "ux_amplitude"),
                "tip_ux_mean": _reference_scalar(repo_root, "ux_mean"),
                "tip_ux_frequency": _reference_scalar(repo_root, "ux_frequency"),
            },
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # Pre-registered in ADR-036 BEFORE any campaign run; never relaxed. The
        # transverse mean is a diagnostic, not a metric — see the module docstring.
        return (
            MetricSpec(
                name="tip_uy_amplitude",
                kind="scalar",
                tolerance=_BAND_UY_AMPLITUDE,
                comparison="relative",
            ),
            MetricSpec(
                name="tip_uy_frequency",
                kind="scalar",
                tolerance=_BAND_UY_FREQUENCY,
                comparison="relative",
            ),
            MetricSpec(
                name="tip_ux_amplitude",
                kind="scalar",
                tolerance=_BAND_UX_AMPLITUDE,
                comparison="relative",
            ),
            MetricSpec(
                name="tip_ux_mean", kind="scalar", tolerance=_BAND_UX_MEAN, comparison="relative"
            ),
            MetricSpec(
                name="tip_ux_frequency",
                kind="scalar",
                tolerance=_BAND_UX_FREQUENCY,
                comparison="relative",
            ),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        """Measure the gated quantities.

        `solver.load()` is what enforces the fail-loud gates — the coupling converged in
        every time window (K1) and a periodic steady state was reached with enough
        settled cycles (S3). Both raise there rather than here, so no path to a number
        can skip them.
        """
        solve = solver.load(result)
        measured: dict[str, float | Series] = {}
        for metric in self.metrics():
            try:
                measured[metric.name] = solve.scalars[metric.name]
            except KeyError:
                raise BenchmarkError(
                    f"{self.name}: the solve reported no {metric.name!r} — "
                    f"available scalars: {', '.join(sorted(solve.scalars))}"
                ) from None
        return measured

    def refined(self, ratio: float) -> TurekHronFSI3:
        """Not available: the fluid mesh is chosen from upstream's own discrete variants.

        A continuous refinement ratio has no meaning here — the tutorial ships three
        hand-authored ``blockMeshDict`` variants and nothing in between, so there is no
        self-similar family to run a GCI over. The refined mesh is a declared,
        non-gated grid-sensitivity diagnostic instead (ADR-036 B3).
        """
        raise NotImplementedError(
            "turek_hron_fsi3 has no continuous refinement family: upstream ships three "
            "discrete blockMeshDict variants. Use fsi3_case_spec(fluid_mesh_dict=...) to "
            "select one; grid sensitivity is reported as a non-gated diagnostic."
        )
