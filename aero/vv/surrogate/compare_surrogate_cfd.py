"""Surrogate-vs-CFD cross-check — the falsifiable evidence behind a cert claim.

Given a trained surrogate and a set of held-out cases (each carrying its packed
surface input + the CFD-reference coefficients), this produces a
:class:`SurrogateVVReport`: per-case errors, per-target RMSE, the Cd-within-5%
verdict (the bundle's headline number), and an applicability-envelope check.

This is *surrogate validation* (CONSTITUTION Invariant 9), distinct from the
solver-V&V / NASA-TMR dashboard (Invariant 5) — see ADR-010. The report is
logged as the ``surrogate_vv`` MLflow artifact by the on-pod training script so
the cert's claims are auditable after the fact.

Stage 09 uses this for DoMINO; Stage 10 reuses it for the ensemble. The module
is IO-free and pure (only ``surrogate.predict`` / ``surrogate.certificate`` are
called), so it unit-tests with a fake surrogate. PLATFORM-NOT-HUB: stdlib +
``aero._common`` only.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aero.surrogates._common.base import SurrogateProtocol

# The default Cd-within-CFD tolerance (the bundle's target; mirrors the
# smoke->validated gate in aero.surrogates.domino.certificate).
DEFAULT_CD_TOLERANCE: float = 0.05

# Default DrivAerML coefficient order.
DEFAULT_TARGET_NAMES: tuple[str, ...] = ("cd", "cl", "clf", "clr", "cs")

_EPS = 1e-12


@dataclass(frozen=True)
class SurrogateVVCase:
    """One cross-check case: its surface input, the CFD reference, optional regime.

    ``surface_input`` is the packed DoMINO input fed to ``surrogate.predict``;
    ``reference`` is the CFD ground-truth coefficient vector in ``target_names``
    order. ``re`` / ``mach`` / ``aoa_deg`` are optional regime coordinates used
    for the applicability-envelope check (skipped when absent).
    """

    case_id: str
    surface_input: tuple[float, ...]
    reference: tuple[float, ...]
    target_names: tuple[str, ...] = DEFAULT_TARGET_NAMES
    re: float | None = None
    mach: float | None = None
    aoa_deg: float | None = None


@dataclass(frozen=True)
class SurrogateCaseComparison:
    """Per-case predicted vs reference, with absolute + relative errors."""

    case_id: str
    target_names: tuple[str, ...]
    predicted: tuple[float, ...]
    reference: tuple[float, ...]
    abs_errors: tuple[float, ...]
    rel_errors: tuple[float, ...]
    in_envelope: bool


@dataclass(frozen=True)
class SurrogateVVReport:
    """Aggregate cross-check verdict for a surrogate over a case set."""

    surrogate_name: str
    model_architecture: str
    dataset_id: str
    cert_status: str
    target_names: tuple[str, ...]
    comparisons: tuple[SurrogateCaseComparison, ...]
    rmse: dict[str, float]
    rel_rmse: dict[str, float]
    max_rel_error: dict[str, float]
    cd_tolerance: float
    cd_within_tolerance: bool
    envelope_respected: bool
    n_cases: int
    n_envelope_checked: int

    @property
    def passed(self) -> bool:
        """Overall verdict: Cd within tolerance AND no envelope violation."""
        return self.cd_within_tolerance and self.envelope_respected

    def to_dict(self) -> dict[str, object]:
        return {
            "surrogate_name": self.surrogate_name,
            "model_architecture": self.model_architecture,
            "dataset_id": self.dataset_id,
            "cert_status": self.cert_status,
            "target_names": list(self.target_names),
            "n_cases": self.n_cases,
            "n_envelope_checked": self.n_envelope_checked,
            "rmse": self.rmse,
            "rel_rmse": self.rel_rmse,
            "max_rel_error": self.max_rel_error,
            "cd_tolerance": self.cd_tolerance,
            "cd_within_tolerance": self.cd_within_tolerance,
            "envelope_respected": self.envelope_respected,
            "passed": self.passed,
            "comparisons": [
                {
                    "case_id": c.case_id,
                    "predicted": list(c.predicted),
                    "reference": list(c.reference),
                    "abs_errors": list(c.abs_errors),
                    "rel_errors": list(c.rel_errors),
                    "in_envelope": c.in_envelope,
                }
                for c in self.comparisons
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        lines = [
            f"# Surrogate V&V — {self.surrogate_name} ({self.model_architecture})",
            "",
            f"- dataset: `{self.dataset_id}`  ·  cert: `{self.cert_status}`  ·  "
            f"cases: {self.n_cases}  ·  **{verdict}**",
            f"- Cd within {self.cd_tolerance:.0%}: **{self.cd_within_tolerance}**  ·  "
            f"envelope respected: **{self.envelope_respected}** "
            f"({self.n_envelope_checked}/{self.n_cases} checked)",
            "",
            "| metric | RMSE | rel-RMSE | max rel error |",
            "|---|---|---|---|",
        ]
        for name in self.target_names:
            lines.append(
                f"| {name} | {self.rmse[name]:.6g} | {self.rel_rmse[name]:.4%} | "
                f"{self.max_rel_error[name]:.4%} |"
            )
        return "\n".join(lines)


def _in_envelope(case: SurrogateVVCase, envelope: object) -> bool | None:
    """True/False if the case's regime is inside the cert envelope; None if unchecked.

    Only the coordinates the case actually carries are checked; a case with no
    ``re``/``mach``/``aoa_deg`` returns ``None`` (not measurable, not a violation).
    """
    checks: list[bool] = []
    for value, attr in (
        (case.re, "re_range"),
        (case.mach, "mach_range"),
        (case.aoa_deg, "aoa_range_deg"),
    ):
        if value is None:
            continue
        lo, hi = getattr(envelope, attr)
        checks.append(lo <= value <= hi)
    if not checks:
        return None
    return all(checks)


def compare_surrogate_cfd(
    surrogate: SurrogateProtocol,
    cases: Sequence[SurrogateVVCase],
    *,
    cd_tolerance: float = DEFAULT_CD_TOLERANCE,
) -> SurrogateVVReport:
    """Predict on each case, compare to its CFD reference, and aggregate.

    The Cd verdict uses the relative RMSE on the ``cd`` target against
    ``cd_tolerance`` (default 5%). Raises ``ValueError`` on an empty case set or
    a target-name mismatch — fail loud (Invariant 2).
    """
    if not cases:
        raise ValueError("compare_surrogate_cfd received no cases")

    cert = surrogate.certificate()
    target_names = cases[0].target_names
    envelope = cert.applicability_envelope

    comparisons: list[SurrogateCaseComparison] = []
    n_envelope_checked = 0
    envelope_ok = True
    for case in cases:
        if case.target_names != target_names:
            raise ValueError(
                f"case {case.case_id} target_names {case.target_names} != {target_names}"
            )
        predicted = surrogate.predict(case.surface_input)
        if len(predicted) != len(case.reference):
            raise ValueError(
                f"case {case.case_id}: prediction width {len(predicted)} != "
                f"reference width {len(case.reference)}"
            )
        abs_err = tuple(abs(p - r) for p, r in zip(predicted, case.reference, strict=True))
        rel_err = tuple(
            abs(p - r) / max(abs(r), _EPS) for p, r in zip(predicted, case.reference, strict=True)
        )
        env = _in_envelope(case, envelope)
        if env is not None:
            n_envelope_checked += 1
            envelope_ok = envelope_ok and env
        comparisons.append(
            SurrogateCaseComparison(
                case_id=case.case_id,
                target_names=target_names,
                predicted=predicted,
                reference=case.reference,
                abs_errors=abs_err,
                rel_errors=rel_err,
                in_envelope=env if env is not None else True,
            )
        )

    rmse: dict[str, float] = {}
    rel_rmse: dict[str, float] = {}
    max_rel: dict[str, float] = {}
    n = len(comparisons)
    for j, name in enumerate(target_names):
        sq = sum(c.abs_errors[j] ** 2 for c in comparisons) / n
        rel_sq = sum(c.rel_errors[j] ** 2 for c in comparisons) / n
        rmse[name] = math.sqrt(sq)
        rel_rmse[name] = math.sqrt(rel_sq)
        max_rel[name] = max(c.rel_errors[j] for c in comparisons)

    cd_within = "cd" in rel_rmse and rel_rmse["cd"] < cd_tolerance

    return SurrogateVVReport(
        surrogate_name=cert.surrogate_name,
        model_architecture=cert.model_architecture,
        dataset_id=cert.dataset_id,
        cert_status=cert.cert_status,
        target_names=target_names,
        comparisons=tuple(comparisons),
        rmse=rmse,
        rel_rmse=rel_rmse,
        max_rel_error=max_rel,
        cd_tolerance=cd_tolerance,
        cd_within_tolerance=cd_within,
        envelope_respected=envelope_ok,
        n_cases=n,
        n_envelope_checked=n_envelope_checked,
    )
