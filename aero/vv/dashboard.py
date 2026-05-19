"""The V&V dashboard — a single self-contained HTML status page.

`render_dashboard` turns a set of V&V outcomes into `docs/vv-dashboard.html`:
one colour-coded row per case (green = pass, red = fail), the per-metric
errors, and the run's git SHA / MLflow run id. mkdocs publishes it from
Stage 16; it is produced from Stage 05 on.

No templating engine — plain stdlib string assembly, matching the case-writer
philosophy elsewhere in the adapter layer.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class DashboardEntry(BaseModel):
    """One V&V case's latest outcome, as shown on the dashboard."""

    model_config = _STRICT

    case_name: str = Field(..., min_length=1)
    status: str = Field(..., description="pass | fail | regress | unknown")
    git_sha: str = Field(default="", description="git SHA of the run.")
    mlflow_run_id: str = Field(default="", description="MLflow run id.")
    metric_errors: dict[str, float] = Field(
        default_factory=dict, description="Per-metric error fraction."
    )


_STATUS_COLOR = {"pass": "#1a7f37", "fail": "#cf222e", "regress": "#bf8700"}


def _row(entry: DashboardEntry) -> str:
    color = _STATUS_COLOR.get(entry.status, "#57606a")
    errs = (
        ", ".join(f"{html.escape(k)} {v:.2%}" for k, v in sorted(entry.metric_errors.items()))
        or "&mdash;"
    )
    return (
        "    <tr>"
        f"<td>{html.escape(entry.case_name)}</td>"
        f'<td style="color:#fff;background:{color};font-weight:600">'
        f"{html.escape(entry.status.upper())}</td>"
        f"<td>{errs}</td>"
        f'<td class="mono">{html.escape(entry.git_sha[:12])}</td>'
        f'<td class="mono">{html.escape(entry.mlflow_run_id[:12])}</td>'
        "</tr>"
    )


def render_dashboard(entries: list[DashboardEntry], dest: Path) -> None:
    """Write the V&V status dashboard to `dest` (typically docs/vv-dashboard.html)."""
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    overall = (
        "ALL GREEN" if entries and all(e.status == "pass" for e in entries) else "ATTENTION NEEDED"
    )
    overall_color = "#1a7f37" if overall == "ALL GREEN" else "#cf222e"
    rows = "\n".join(_row(e) for e in entries) or '    <tr><td colspan="5">no runs</td></tr>'
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
  .banner {{ color: #fff; background: {overall_color}; padding: 0.5rem 1rem;
             display: inline-block; font-weight: 700; border-radius: 4px; }}
</style>
</head>
<body>
<h1>aero-research-platform &mdash; V&amp;V Dashboard</h1>
<p class="banner">{overall}</p>
<p>Canonical NASA TMR verification cases. A red dashboard blocks
<code>production</code>-tagged runs (ADR-005). Generated {generated}.</p>
<table>
  <thead>
    <tr><th>Case</th><th>Status</th><th>Metric errors</th>
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
