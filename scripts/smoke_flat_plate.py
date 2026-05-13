#!/usr/bin/env python3
"""Stage 5 smoke script: validate pre-flight + POST 02-flat-plate-riblet-bechert.

Pre-flight checks (audit D.3 + Stage 2 deviations — same five as Stage 4
but the templates-staged check looks for the flat-plate template):
    1. Prefect server is UP (audit D.3 — degraded-evidence avoidance).
    2. Orchestrator REST API is reachable.
    3. The aero-research SSH target is registered in /targets.
    4. The campaign YAML round-trips through the SDK's CampaignCreate.
    5. The case template + Python package are pushed to the aero LXC
       (looking for flat-plate-riblet-simpleFoam, not naca0012-simpleFoam).

Then it POSTs the campaign and writes campaign_id + run_ids to
``results/02-flat-plate-riblet-bechert/run-log.json``.

Use ``--no-launch`` to dry-run pre-flight + payload validation without
posting. Use ``--orchestrator-url`` to point at a non-default endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from ai_orchestrator_client import CampaignCreate

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAMPAIGN_YAML = REPO_ROOT / "campaigns" / "02-flat-plate-riblet-bechert.yaml"
DEFAULT_RESULTS_DIR = REPO_ROOT / "results" / "02-flat-plate-riblet-bechert"
PREFECT_HEALTH = "http://192.168.2.182:4200/api/health"
DEFAULT_ORCH_URL = "http://127.0.0.1:8000"


def _http_get_json(url: str, *, token: str | None = None, timeout: float = 10.0) -> Any:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _http_post_json(url: str, body: dict, *, token: str | None = None, timeout: float = 30.0) -> Any:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check_prefect_health() -> tuple[bool, str]:
    try:
        body = _http_get_json(PREFECT_HEALTH)
    except (urllib.error.URLError, OSError) as exc:
        return False, f"unreachable: {exc}"
    if body is True:
        return True, "ok (audit D.3 satisfied)"
    return False, f"unexpected body: {body!r}"


def check_orchestrator_health(base: str, token: str | None) -> tuple[bool, str]:
    try:
        body = _http_get_json(f"{base.rstrip('/')}/health", token=token)
    except (urllib.error.URLError, OSError) as exc:
        return False, f"unreachable: {exc}"
    if isinstance(body, dict) and body.get("uptime_indicator") == "ok":
        return True, f"ok ({body.get('active_runs', '?')} active runs)"
    return False, f"unexpected body: {body!r}"


def check_aero_target_registered(base: str, token: str | None) -> tuple[bool, str]:
    try:
        body = _http_get_json(f"{base.rstrip('/')}/targets", token=token)
    except (urllib.error.URLError, OSError) as exc:
        return False, f"unreachable: {exc}"
    targets = body.get("targets", body) if isinstance(body, dict) else body
    for t in targets:
        if isinstance(t, dict) and t.get("name") == "aero-research":
            return True, f"host={t.get('host')} user={t.get('username')}"
    return False, "aero-research not in /targets"


def validate_yaml(yaml_path: Path) -> CampaignCreate:
    raw = yaml.safe_load(yaml_path.read_text())
    return CampaignCreate.model_validate(raw)


def check_templates_pushed(target_user: str = "aero", target_host: str = "192.168.2.231") -> tuple[bool, str]:
    """SSH into the target and check ~/templates/flat-plate-riblet-simpleFoam/ exists."""
    import subprocess
    key = "/root/.ssh/id_ed25519_aero_target"
    cmd = [
        "ssh",
        "-i", key,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        f"{target_user}@{target_host}",
        "ls ~/templates/flat-plate-riblet-simpleFoam/system/controlDict 2>/dev/null && "
        "ls ~/aero-research-platform/aero_research_platform/meshing/periodic_riblet_strip.py 2>/dev/null",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode == 0 and "controlDict" in res.stdout and "periodic_riblet_strip.py" in res.stdout:
        return True, "templates + package present on aero LXC"
    return False, f"templates not staged (rc={res.returncode}): {res.stderr.strip() or res.stdout.strip()}"


def post_campaign(
    base: str,
    payload: dict,
    token: str | None,
) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/campaigns"
    print(f"POST {url}")
    return _http_post_json(url, payload, token=token)


def write_run_log(results_dir: Path, response: dict, payload: dict) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    log_path = results_dir / "run-log.json"
    state: dict[str, Any] = {}
    if log_path.exists():
        state = json.loads(log_path.read_text())
    history = state.setdefault("history", [])
    history.append(
        {
            "timestamp": int(time.time()),
            "campaign_id": response.get("campaign_id"),
            "flow_run_id": response.get("flow_run_id"),
            "run_count": response.get("run_count"),
            "yaml_name": payload.get("name"),
        }
    )
    state["latest"] = history[-1]
    log_path.write_text(json.dumps(state, indent=2) + "\n")
    return log_path


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--yaml", type=Path, default=DEFAULT_CAMPAIGN_YAML)
    p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    p.add_argument("--orchestrator-url", default=os.environ.get("ORCHESTRATOR_URL", DEFAULT_ORCH_URL))
    p.add_argument("--token", default=os.environ.get("ORCHESTRATOR_TOKEN") or None)
    p.add_argument(
        "--no-launch",
        action="store_true",
        help="Run pre-flight + validate YAML, but do not POST /campaigns",
    )
    p.add_argument(
        "--skip-templates-check",
        action="store_true",
        help="Skip the ssh-into-target template-staging check",
    )
    args = p.parse_args()

    fails: list[str] = []
    print("=" * 64)
    print(f"Stage-5 pre-flight @ {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    ok, msg = check_prefect_health()
    print(f"  [{'PASS' if ok else 'FAIL'}] Prefect health     : {msg}")
    if not ok:
        fails.append("prefect")

    ok, msg = check_orchestrator_health(args.orchestrator_url, args.token)
    print(f"  [{'PASS' if ok else 'FAIL'}] Orchestrator health : {msg}")
    if not ok:
        fails.append("orchestrator")

    ok, msg = check_aero_target_registered(args.orchestrator_url, args.token)
    print(f"  [{'PASS' if ok else 'FAIL'}] aero-research target: {msg}")
    if not ok:
        fails.append("target")

    try:
        validated = validate_yaml(args.yaml)
        print(f"  [PASS] YAML round-trips     : {args.yaml.name} -> CampaignCreate")
        print(f"           name = {validated.name}")
        print(f"           hitl_mode = {validated.template.hitl_mode}")
        print(f"           deploy_target = {validated.template.deploy_target}")
        print(f"           params = {dict(validated.params)}")
    except Exception as exc:
        print(f"  [FAIL] YAML round-trip      : {exc}")
        fails.append("yaml")

    if not args.skip_templates_check:
        ok, msg = check_templates_pushed()
        print(f"  [{'PASS' if ok else 'FAIL'}] templates staged    : {msg}")
        if not ok:
            fails.append("templates")

    if fails:
        print()
        print(f"PRE-FLIGHT FAILED: {', '.join(fails)}")
        return 2

    if args.no_launch:
        print()
        print("--no-launch set; would have POSTed:")
        print(json.dumps(yaml.safe_load(args.yaml.read_text()), indent=2))
        return 0

    print()
    print("=" * 64)
    print("Posting campaign")
    print("=" * 64)
    payload = yaml.safe_load(args.yaml.read_text())
    canonical = CampaignCreate.model_validate(payload).model_dump()
    response = post_campaign(args.orchestrator_url, canonical, args.token)
    print(json.dumps(response, indent=2))
    log_path = write_run_log(args.results_dir, response, payload)
    print(f"Wrote run log -> {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
