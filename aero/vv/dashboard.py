"""The V&V dashboard — a single self-contained HTML status page.

`render_dashboard` turns a set of V&V outcomes into an HTML page (the `vv-dashboard` CI
artifact): one colour-coded row per case, its solver stack, the per-metric errors, and the run's
git SHA / MLflow run id, under one verdict banner per solver stack (ADR-051 D2 (b), Stage 22).

No templating engine — plain stdlib string assembly, matching the case-writer
philosophy elsewhere in the adapter layer.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from aero.vv.status import STACK_ORDER, Disposition, StackName, Verdict, VVStatus, stack_verdicts

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class DashboardEntry(BaseModel):
    """One V&V case's latest outcome, as shown on the dashboard."""

    model_config = _STRICT

    case_name: str = Field(..., min_length=1)
    status: VVStatus = Field(..., description="Typed; an unknown string fails validation.")
    stack: StackName = Field(..., description="The solver stack the case measures.")
    disposition: Disposition = Field(..., description="active | frozen | deferred (ADR-051 D2).")
    git_sha: str = Field(default="", description="git SHA of the run.")
    mlflow_run_id: str = Field(default="", description="MLflow run id.")
    metric_errors: dict[str, float] = Field(
        default_factory=dict, description="Per-metric error fraction."
    )


# `missing` is rendered as loudly as `fail` on purpose. A registered case with no
# run is not a blank cell to be skipped over — it is an unevaluated gate, and the
# failure mode it guards against is a case that goes red, stops being run, and
# then quietly stops appearing at all, letting the suite reach "all green" by
# attrition rather than by anyone fixing the physics. `frozen` and `deferred` get
# their own colours (ADR-051 D2): visible, never mistaken for a pass.
_STATUS_COLOR: dict[VVStatus, str] = {
    "pass": "#1a7f37",
    "fail": "#cf222e",
    "missing": "#cf222e",
    "regress": "#bf8700",
    "unknown": "#9a6700",
    "frozen": "#0550ae",
    "deferred": "#57606a",
}

_VERDICT_TEXT: dict[Verdict, tuple[str, str]] = {
    "GREEN": ("ALL GREEN", "#1a7f37"),
    "RED": ("ATTENTION NEEDED", "#cf222e"),
    "FROZEN": ("FROZEN — not evaluated", "#0550ae"),
}


def _row(entry: DashboardEntry) -> str:
    color = _STATUS_COLOR[entry.status]
    errs = (
        ", ".join(f"{html.escape(k)} {v:.2%}" for k, v in sorted(entry.metric_errors.items()))
        or "&mdash;"
    )
    return (
        "    <tr>"
        f"<td>{html.escape(entry.case_name)}</td>"
        f"<td>{html.escape(entry.stack)}</td>"
        f'<td style="color:#fff;background:{color};font-weight:600">'
        f"{html.escape(entry.status.upper())}</td>"
        f"<td>{errs}</td>"
        f'<td class="mono">{html.escape(entry.git_sha[:12])}</td>'
        f'<td class="mono">{html.escape(entry.mlflow_run_id[:12])}</td>'
        "</tr>"
    )


def _banners(entries: list[DashboardEntry]) -> str:
    if not entries:
        return '<p class="banner" style="background:#cf222e">ATTENTION NEEDED — no cases</p>'
    verdicts = stack_verdicts((e.case_name, e.stack, e.disposition, e.status) for e in entries)
    lines = []
    for stack in STACK_ORDER:
        if stack not in verdicts:
            continue
        text, color = _VERDICT_TEXT[verdicts[stack].verdict]
        lines.append(
            f'<p class="banner" style="background:{color}">'
            f"{html.escape(stack)}: {html.escape(text)}</p>"
        )
    return "\n".join(lines)


def render_dashboard(entries: list[DashboardEntry], dest: Path) -> None:
    """Write the V&V status dashboard to `dest`, one verdict banner per solver stack."""
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    rows = "\n".join(_row(e) for e in entries) or '    <tr><td colspan="6">no runs</td></tr>'
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>aero-research-platform &mdash; V&amp;V Dashboard</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1f2328; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ border: 1px solid #d0d7de; padding: 0.4rem 0.8rem; text-align: left; }}
  th {{ background: #f6f8fa; }}
  .mono {{ font-family: ui-monospace, monospace; font-size: 0.85rem; }}
  .banner {{ color: #fff; padding: 0.5rem 1rem; display: inline-block;
             font-weight: 700; border-radius: 4px; margin: 0.2rem 0.5rem 0.2rem 0; }}
</style>
</head>
<body>
<h1>aero-research-platform &mdash; V&amp;V Dashboard</h1>
{_banners(entries)}
<p>Registered V&amp;V cases, newest run per case on its own solver stack. A
<code>production</code>-tagged run is gated by its own stack's verdict (ADR-005, scoped by
ADR-051 D2): frozen-optional stacks (ADR-013) and deferred cases (ADR-046 S4) are shown but
never count as a pass. Generated {generated}.</p>
<table>
  <thead>
    <tr><th>Case</th><th>Stack</th><th>Status</th><th>Metric errors</th>
        <th>git SHA</th><th>MLflow run</th></tr>
  </thead>
  <tbody>
{rows}
  </tbody>
</table>
</body>
</html>
"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding="utf-8")
