#!/usr/bin/env python3
"""Stage 07 — first paid H100 PyFR Taylor-Green run.

Driver script for the inaugural cloud-GPU run. Uses a stock RunPod PyTorch
template (has sshd + CUDA 12.4 + Python pre-configured) and pip-installs
PyFR at pod-boot — the operationally-fastest path for the FIRST run. Our
custom `ghcr.io/ernesto01louis/aero-pyfr:v1.15.0` image is published and
ready for production runs once Stage 13 ships the executor-aware Solver
dispatch (the current `PyFRSolver.run` wraps in `apptainer exec`, which
needs apptainer-in-Docker on RunPod — out of scope for tonight).

What this script DOES end-to-end:
  1. Loads secrets from /root/.config/aero/operator-secrets.env
  2. Pre-launch cost-cap check (Invariant 8 — fails loud if MTD+est > cap)
  3. Records the launch in the ledger (tag="running")
  4. Writes the Taylor-Green case files locally via the typed `_meshing`
     + `case_writer` helpers (so the bytes are bit-identical to what the
     SIF path would produce — provenance honesty)
  5. Launches an H100 PCIe pod via RunPod GraphQL
  6. Polls until SSH is reachable
  7. SCP case files up; SSH-execs `pip install pyfr` + `pyfr import` +
     `pyfr run -b cuda`; SCP results back
  8. Terminates the pod + polls `desiredStatus=TERMINATED`; ledger entry
     amended with actual_hours + actual_cost_usd + tag (ok/errored/orphaned)
  9. Parses out/integrate.csv via PyFRSolver.load → typed SolveResult
 10. Prints peak dissipation vs the Brachet 1983 Re=1600 reference

What this script does NOT do (deferred):
  * MLflow logging — the four-tuple is logged to stdout + a JSON sidecar
    instead, since MLflow tracking-server reachability + the OpenFOAM-
    centric Hydra config wiring is a Stage-13 / Stage-04 cleanup item.
  * Apptainer-in-Docker. Stage 13 fixes the executor abstraction so
    `PyFRSolver` works uniformly across local-SSH+SIF and cloud-OCI.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path("/root/projects/aero-research-platform")
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402 — must follow sys.path insert above
from aero.adapters._meshing.gmsh_high_order import (  # noqa: E402 — depends on sys.path
    write_taylor_green_msh2,
)
from aero.adapters.pyfr.case_writer import write_taylor_green_ini  # noqa: E402
from aero.adapters.pyfr.schemas import PyFRTaylorGreenSpec  # noqa: E402
from aero.orchestration.cost_cap import CostCap  # noqa: E402

SECRETS_FILE = Path("/root/.config/aero/operator-secrets.env")
RUNPOD_ENDPOINT = "https://api.runpod.io/graphql"
PROJECTED_HOURS = 0.25
STOCK_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"

# GPU fallback ladder, sorted by lowest hourly rate. IDs MUST match the exact
# strings RunPod's `gpuTypes` query returns — even "GeForce" matters. For the
# FIRST run we need any modern NVIDIA GPU with CUDA 12 — Taylor-Green at
# N=16 p=3 fits comfortably in 24 GB VRAM. pip-installed pyfr+pycuda compile
# their own kernels at runtime, so sm_70+ GPUs all work.
GPU_FALLBACK_LADDER: list[tuple[str, float]] = [
    ("NVIDIA RTX A5000", 0.16),  # 24 GB sm_86  — cheapest available
    ("NVIDIA GeForce RTX 4090", 0.34),  # 24 GB sm_89
    ("NVIDIA GeForce RTX 5090", 0.69),  # 32 GB sm_120
    ("NVIDIA A100 80GB PCIe", 1.19),  # 80 GB sm_80
    ("NVIDIA A100-SXM4-80GB", 1.39),  # 80 GB sm_80 + NVLink
    ("NVIDIA H100 NVL", 2.59),  # 94 GB sm_90
    ("NVIDIA H100 80GB HBM3", 2.69),  # 80 GB sm_90 — the workhorse H100
    ("NVIDIA H200", 3.59),  # 141 GB sm_90 + HBM3e
]

# Use a SMALL TG case for the first run so wall-clock and cost are bounded.
# Workshop-canonical is N=32 p=3 (t_end=20.0, ~5-8 min); for the first paid
# run we step down to N=16 p=3 (~1-2 min) to keep the cost cushion safer.
TG_N = 16
TG_P = 3
TG_T_END = 10.0
TG_DT = 1.0e-3
TG_MONITOR_DT = 0.2


def load_secrets() -> dict[str, str]:
    out: dict[str, str] = {}
    with SECRETS_FILE.open() as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def gql(token: str, query: str, variables: dict | None = None) -> dict:
    r = requests.post(
        RUNPOD_ENDPOINT,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(f"RunPod GraphQL errors: {payload['errors']}")
    return payload.get("data") or {}


def main() -> int:
    secrets = load_secrets()
    api_key = secrets["RUNPOD_API_KEY"]

    # --- 1. Cost-cap pre-flight ------------------------------------------------
    # Estimate against the cheapest fallback so the pre-flight check is
    # representative; per-pod-type check happens inside the launch loop.
    cost_cap = CostCap()
    cheapest_estimate = PROJECTED_HOURS * GPU_FALLBACK_LADDER[0][1]
    ledger = cost_cap.check_budget(cheapest_estimate)
    print(
        f"[cost-cap] GREEN: cheapest est ${cheapest_estimate:.4f}, "
        f"MTD ${ledger.month_to_date_usd():.2f}, cap ${cost_cap.cap_usd:.2f}"
    )

    # --- 2. Build the case + write files --------------------------------------
    spec = PyFRTaylorGreenSpec(
        name="taylor_green_p3_16",
        n_elements_per_dir=TG_N,
        polynomial_order=TG_P,
        t_end=TG_T_END,
        dt=TG_DT,
        monitor_dt=TG_MONITOR_DT,
    )
    run_id = f"{spec.name}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    local_case_dir = Path(f"/mnt/aero-nfs/runs/{run_id}")
    local_case_dir.mkdir(parents=True, exist_ok=True)
    (local_case_dir / "out").mkdir(exist_ok=True)
    n_hex = write_taylor_green_msh2(
        local_case_dir / "mesh.msh2", n_elements_per_dir=spec.n_elements_per_dir
    )
    write_taylor_green_ini(local_case_dir / "solver.ini", spec)
    print(f"[prepare] case_dir={local_case_dir} ({n_hex} hex elements, p={TG_P})")

    # --- 3. Try launching across the GPU fallback ladder ---------------------
    launch_mutation = """
    mutation Create($input: PodFindAndDeployOnDemandInput) {
        podFindAndDeployOnDemand(input: $input) { id machine { podHostId } }
    }
    """
    pod_id: str | None = None
    pod_type: str | None = None
    hourly_rate: float | None = None
    started_at = time.monotonic()

    for try_pod, try_rate in GPU_FALLBACK_LADDER:
        try_estimated = PROJECTED_HOURS * try_rate
        try:
            cost_cap.check_budget(try_estimated)
        except Exception as exc:
            print(f"[cost-cap] {try_pod} @ ${try_rate}/hr would exceed cap — skipping: {exc}")
            continue
        launch_input = {
            "input": {
                "name": f"aero-{run_id}",
                "gpuTypeId": try_pod,
                "imageName": STOCK_IMAGE,
                "containerDiskInGb": 50,
                "volumeInGb": 0,
                "ports": "22/tcp",
                "minVcpuCount": 4,
                "minMemoryInGb": 16,
                "supportPublicIp": True,
                "cloudType": "COMMUNITY",
                "dockerArgs": "bash -c 'service ssh start && sleep infinity'",
            }
        }
        print(f"[launch] trying {try_pod} (community, ${try_rate}/hr, est ${try_estimated:.4f})...")
        try:
            data = gql(api_key, launch_mutation, launch_input)
            node = data.get("podFindAndDeployOnDemand")
            if node and node.get("id"):
                pod_id = node["id"]
                pod_type = try_pod
                hourly_rate = try_rate
                print(f"[launch] SUCCESS — pod {pod_id} on {try_pod}")
                break
            print(f"[launch] {try_pod} returned no pod id; trying next")
        except Exception as exc:
            print(f"[launch] {try_pod} failed: {exc} — trying next")

    if not pod_id or not pod_type or hourly_rate is None:
        print("[launch] all GPUs in fallback ladder unavailable — aborting", file=sys.stderr)
        return 4

    # Pre-launch ledger entry now that we know which pod_type actually got booked.
    cost_cap.record_launch(
        run_id=run_id,
        pod_type=pod_type,
        projected_hours=PROJECTED_HOURS,
        hourly_rate_usd=hourly_rate,
    )

    # --- 5. Poll for SSH readiness --------------------------------------------
    poll_q = """
    query Pod($podId: String!) {
        pod(input: { podId: $podId }) {
            id desiredStatus
            runtime { ports { ip publicPort privatePort type isIpPublic } }
        }
    }
    """
    ssh_host: str | None = None
    ssh_port: int | None = None
    poll_deadline = time.monotonic() + 600  # 10 min
    last_status = "unknown"
    while time.monotonic() < poll_deadline:
        time.sleep(8)
        d = gql(api_key, poll_q, {"podId": pod_id})
        pod = d.get("pod") or {}
        last_status = pod.get("desiredStatus", last_status)
        runtime = pod.get("runtime") or {}
        for port in runtime.get("ports") or []:
            if port.get("privatePort") == 22 and port.get("isIpPublic"):
                ssh_host = str(port["ip"])
                ssh_port = int(port["publicPort"])
                break
        if ssh_host:
            break
        print(f"  [poll] pod desiredStatus={last_status} — waiting for SSH port...")
    if not ssh_host or ssh_port is None:
        print(
            f"[launch] FAILED: pod never exposed SSH within 600s "
            f"(last status={last_status!r}) — terminating",
            file=sys.stderr,
        )
        gql(
            api_key, "mutation T($p: String!) { podTerminate(input: { podId: $p }) }", {"p": pod_id}
        )
        cost_cap.record_termination(run_id=run_id, actual_hours=0.0, tag="errored")
        return 3
    print(f"[launch] pod ready: ssh -p {ssh_port} root@{ssh_host}  (status={last_status})")

    # --- 6. SCP + SSH workflow ------------------------------------------------
    ssh_opts = [
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=30",
    ]
    rc_solve = -1
    try:
        # SSH-wait until sshd is actually responsive (RunPod marks port up
        # a few seconds before sshd is ready).
        for attempt in range(30):
            r = subprocess.run(
                ["ssh", "-p", str(ssh_port), *ssh_opts, f"root@{ssh_host}", "echo ready"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if r.returncode == 0:
                print(f"[ssh] sshd responsive on attempt {attempt + 1}")
                break
            time.sleep(5)
        else:
            raise RuntimeError("sshd never became responsive within 150s")

        print(f"[scp] uploading case dir → /workspace/{run_id}/ ...")
        subprocess.run(
            [
                "scp",
                "-r",
                "-P",
                str(ssh_port),
                *ssh_opts,
                str(local_case_dir),
                f"root@{ssh_host}:/workspace/",
            ],
            check=True,
            timeout=300,
        )

        # The pod is the stock RunPod PyTorch image — pip-install PyFR at runtime.
        # setuptools<70 keeps pkg_resources available (Stage-07 PyFR gotcha).
        install_cmd = (
            "pip install --quiet 'setuptools<70' 'numpy>=1.26,<2.1' 'mako>=1.3' "
            "'h5py>=3.10' 'mpi4py>=4.0' 'pycuda>=2024.1' 'pytools>=2024.1' "
            "'pyfr==1.15.0' 2>&1 | tail -20"
        )
        print("[install] pip-installing PyFR 1.15.0 + deps on the H100 pod...")
        r = subprocess.run(
            ["ssh", "-p", str(ssh_port), *ssh_opts, f"root@{ssh_host}", install_cmd],
            capture_output=True,
            text=True,
            timeout=600,
        )
        print(r.stdout)
        if r.returncode != 0:
            print(f"[install] FAILED: {r.stderr[-500:]}", file=sys.stderr)
            raise RuntimeError(f"pip install rc={r.returncode}")

        solve_cmd = (
            f"cd /workspace/{run_id} && "
            f"pyfr import -t gmsh mesh.msh2 mesh.pyfrm 2>&1 | tail -5 && "
            f"echo '=== STARTING pyfr run -b cuda ===' && "
            f"pyfr run -b cuda -p solver.ini mesh.pyfrm 2>&1 | tail -60"
        )
        print("[solve] running pyfr import + pyfr run -b cuda ...")
        solve_start = time.monotonic()
        r = subprocess.run(
            ["ssh", "-p", str(ssh_port), *ssh_opts, f"root@{ssh_host}", solve_cmd],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        rc_solve = r.returncode
        solve_seconds = time.monotonic() - solve_start
        print(f"[solve] pyfr exit={rc_solve}  wall={solve_seconds:.1f}s")
        print(r.stdout)
        if r.stderr:
            print("--- stderr (tail) ---")
            print(r.stderr[-2000:])

        # Pull the integrate.csv back regardless of rc — it'll still have
        # whatever ran before crash.
        print("[scp] downloading out/ back...")
        subprocess.run(
            [
                "scp",
                "-r",
                "-P",
                str(ssh_port),
                *ssh_opts,
                f"root@{ssh_host}:/workspace/{run_id}/out",
                str(local_case_dir),
            ],
            check=False,
            timeout=300,
        )
    finally:
        # --- 7. Terminate + poll TERMINATED -------------------------------
        print("[terminate] requesting pod terminate...")
        try:
            gql(
                api_key,
                "mutation T($p: String!) { podTerminate(input: { podId: $p }) }",
                {"p": pod_id},
            )
        except Exception as exc:
            print(f"[terminate] mutation failed: {exc}", file=sys.stderr)
        terminated = False
        term_deadline = time.monotonic() + 300
        while time.monotonic() < term_deadline:
            try:
                d = gql(api_key, poll_q, {"podId": pod_id})
                pod = d.get("pod")
                ds = (pod or {}).get("desiredStatus")
                if pod is None or ds in ("TERMINATED", "EXITED"):
                    terminated = True
                    break
            except Exception:
                pass
            time.sleep(5)
        if terminated:
            print("[terminate] confirmed TERMINATED")
        else:
            print("[terminate] could not confirm within 300s — marking ORPHANED", file=sys.stderr)

        actual_hours = (time.monotonic() - started_at) / 3600.0
        actual_cost = actual_hours * (hourly_rate or 0.0)
        tag = "orphaned" if not terminated else ("ok" if rc_solve == 0 else "errored")
        cost_cap.record_termination(
            run_id=run_id,
            actual_hours=actual_hours,
            tag=tag,
        )
        print(
            f"[ledger] actual_hours={actual_hours:.4f}  actual_cost=${actual_cost:.4f}  tag={tag}"
        )

    # --- 8. Parse integrate.csv → result + Brachet comparison ----------------
    csv_path = local_case_dir / "out" / "integrate.csv"
    if not csv_path.is_file():
        print(
            f"[result] {csv_path} missing — solve may have crashed before first monitor write",
            file=sys.stderr,
        )
        return 1 if rc_solve != 0 else 0

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    if len(rows) < 2:
        print(
            "[result] integrate.csv has <2 samples; insufficient for dissipation", file=sys.stderr
        )
        return 1

    t_vals = [float(r["t"]) for r in rows]
    ke_vals = [float(r["ke-int"]) for r in rows]
    # central-difference dissipation rate eps(t) = -d(KE)/dt
    diss = []
    for i in range(1, len(t_vals) - 1):
        dt = t_vals[i + 1] - t_vals[i - 1]
        if dt > 0:
            diss.append((-(ke_vals[i + 1] - ke_vals[i - 1]) / dt, t_vals[i]))
    peak_diss, peak_t = max(diss, key=lambda p: p[0]) if diss else (0.0, 0.0)

    print()
    print("=" * 60)
    print(f"TAYLOR-GREEN VORTEX RUN — RESULT ({pod_type})")
    print("=" * 60)
    print(f"run_id              {run_id}")
    print(f"pod_type            {pod_type}  @ ${hourly_rate:.2f}/hr")
    print(f"spec                N={TG_N}^3 elements, p={TG_P}, t_end={TG_T_END}")
    print(f"DOF                 {TG_N**3 * (TG_P + 1) ** 3:,}")
    print(f"samples             {len(t_vals)}")
    print(f"final KE            {ke_vals[-1]:.6e}")
    print(f"peak dissipation    {peak_diss:.6e}  (at t={peak_t:.3f})")
    print("Brachet 1983 ref    ~1.30e-2 (at t~9.0, Re=1600)")
    ratio = peak_diss / 1.30e-2 if peak_diss > 0 else 0
    print(f"ratio vs Brachet    {ratio:.3f}x")
    print(f"actual cost         ${actual_cost:.4f}")
    print(f"pod uptime          {actual_hours:.4f} h")
    print()

    # Sidecar JSON for posterity (since MLflow logging is deferred).
    sidecar = {
        "run_id": run_id,
        "spec": spec.model_dump(),
        "pod_id": pod_id,
        "actual_hours": actual_hours,
        "actual_cost_usd": actual_cost,
        "tag": tag,
        "rc_solve": rc_solve,
        "final_ke": ke_vals[-1],
        "peak_dissipation": peak_diss,
        "peak_dissipation_t": peak_t,
        "samples": len(t_vals),
        "completed_at_utc": datetime.now(UTC).isoformat(),
    }
    sidecar_path = local_case_dir / "run-result.json"
    sidecar_path.write_text(json.dumps(sidecar, indent=2, default=str))
    print(f"sidecar             {sidecar_path}")

    return 0 if rc_solve == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
