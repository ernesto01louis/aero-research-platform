"""Minimal RunPod GPU executor — Stage 07's first paid cloud execution path.

Lifecycle of one `run()`:

1. estimate cost (`projected_hours * hourly_rate_usd`);
2. call `cost_cap.check_budget(estimated_usd)` — fails loud if MTD+est > cap
   (CONSTITUTION Invariant 8 — COST-CAP-ENFORCED-CLOUD-EXECUTION);
3. cost_cap.record_launch(... tag="running") — pre-execution ledger entry;
4. launch a pod via the RunPod GraphQL API; SSH in once it's ready;
5. exec the bind-mounted command (the same Apptainer command the local-SSH
   path runs — except RunPod pulls the GHCR-mirror of our SIF instead);
6. poll for sentinel + capture stdout;
7. terminate the pod and amend the ledger entry with actual_hours / tag.

What this module is **NOT** (Stage 13's job):
* multi-cloud routing (Lambda Labs, Vast.ai, spot-eviction handling);
* persistent pod pools / job queueing;
* a real cost router that picks the cheapest matching GPU across vendors.

PLATFORM-NOT-HUB: lives under `aero/orchestration/runpod/` so the base
`aero/orchestration/_base.py` stays SDK-free; `requests` is gated by the
`aero[gpu-rental]` extra.
"""

from __future__ import annotations

import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from aero.orchestration._base import ExecResult
from aero.orchestration.cost_cap import (
    CostCap,
    CostCapError,
    LedgerEntry,
)

DEFAULT_RUNPOD_ENDPOINT = "https://api.runpod.io/graphql"

# Public RunPod community-cloud rates as of 2026-05 (USD/hour). The executor
# uses these as the projected-cost basis for the ledger; the actual cost
# is reconciled at terminate from the pod's true uptime hours. Update when
# the operator's RunPod pricing tier changes (the cost cap is the safety
# net regardless).
POD_TYPE_HOURLY_USD: dict[str, float] = {
    "NVIDIA H100 PCIe": 2.49,
    "NVIDIA H100 80GB SXM": 4.69,
    "NVIDIA A100 80GB PCIe": 1.89,
    "NVIDIA A100 80GB SXM": 1.99,
    "NVIDIA L40S": 1.19,
    "NVIDIA RTX 4090": 0.69,
}


class RunPodLaunchError(RuntimeError):
    """A pod could not be launched (API error, schema drift, quota, etc.)."""


class _ConnectInfo(BaseModel):
    """Pod SSH connect details returned by the launch flow."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_assignment=True,
    )

    pod_id: str = Field(..., min_length=1)
    ssh_host: str = Field(..., min_length=1)
    ssh_port: int = Field(..., gt=0)
    ssh_user: str = Field(default="root", min_length=1)
    launched_at: datetime = Field(...)


class RunPodExecutor:
    """A single-pod RunPod executor satisfying `aero.orchestration.Executor`.

    Construct one per cloud-bound run-context. The executor is *not* a
    pool — each `run()` launches a fresh pod, executes one command,
    terminates. This matches the Stage-07 "first cloud run" scope (one
    paid H100 Taylor-Green smoke). Stage 13 introduces a pool/router.
    """

    def __init__(
        self,
        *,
        api_key: str,
        pod_type: str,
        container_image: str,
        cost_cap: CostCap,
        repo_root: Path | None = None,
        projected_hours: float = 0.5,
        hourly_rate_usd: float | None = None,
        endpoint: str = DEFAULT_RUNPOD_ENDPOINT,
        volume_in_gb: int = 50,
        host_label: str = "runpod",
    ) -> None:
        if not api_key:
            raise ValueError("RunPodExecutor requires a non-empty api_key")
        if pod_type not in POD_TYPE_HOURLY_USD and hourly_rate_usd is None:
            raise ValueError(
                f"pod_type {pod_type!r} not in POD_TYPE_HOURLY_USD; pass "
                "hourly_rate_usd=<USD> to override"
            )
        self.api_key = api_key
        self.pod_type = pod_type
        self.container_image = container_image
        self.cost_cap = cost_cap
        self.repo_root = repo_root
        self.projected_hours = float(projected_hours)
        self.hourly_rate_usd = float(
            hourly_rate_usd if hourly_rate_usd is not None else POD_TYPE_HOURLY_USD[pod_type]
        )
        self.endpoint = endpoint
        self.volume_in_gb = int(volume_in_gb)
        self.host = host_label  # ExecResult.host; concrete pod_id replaces it post-launch

    # ---- public Executor surface ---------------------------------------------
    def run(
        self,
        command: str,
        *,
        timeout_s: int | None = None,
        long_running: bool = False,
        session: str | None = None,
    ) -> ExecResult:
        """Launch a pod, run `command`, terminate, return `ExecResult`.

        The `session` argument names the ledger entry's `run_id` so the
        cost-cap pre-launch check and post-terminate true-up correlate. If
        not given, a synthetic id is generated.
        """
        run_id = session or f"runpod-{int(time.time())}"
        timeout = timeout_s if timeout_s is not None else (3600 if long_running else 600)

        # 1+2. Estimate cost; FAIL-LOUD if over budget (Invariant 8).
        estimated = self.projected_hours * self.hourly_rate_usd
        self.cost_cap.check_budget(estimated)
        logger.info(
            "cost-cap green for run {}: projected ${:.2f} ({:.3f}h @ ${:.2f}/h, pod {})",
            run_id,
            estimated,
            self.projected_hours,
            self.hourly_rate_usd,
            self.pod_type,
        )

        # 3. Pre-launch ledger entry. Discarded — record_termination matches by
        #    run_id, not by entry reference, so we don't need to hold this.
        self.cost_cap.record_launch(
            run_id=run_id,
            pod_type=self.pod_type,
            projected_hours=self.projected_hours,
            hourly_rate_usd=self.hourly_rate_usd,
        )

        info: _ConnectInfo | None = None
        started = time.monotonic()
        tag = "ok"
        captured_stdout = ""
        captured_stderr = ""
        rc = 1
        try:
            # 4. Launch pod + wait for SSH.
            info = self._launch_pod(run_id)
            logger.info("RunPod pod {} ready at {}:{}", info.pod_id, info.ssh_host, info.ssh_port)
            # 5. Exec command (long_running uses tmux pattern; short = direct ssh).
            rc, captured_stdout, captured_stderr = self._ssh_exec(info, command, timeout)
            tag = "ok" if rc == 0 else "errored"
        except CostCapError:
            raise  # already FAIL-LOUD via check_budget; do not record termination
        except RunPodLaunchError as exc:
            captured_stderr = f"RunPod launch failure: {exc}"
            tag = "errored"
            rc = 1
        except Exception as exc:
            captured_stderr = f"RunPod executor unexpected error: {exc!r}"
            tag = "errored"
            rc = 1
        finally:
            # 6+7. Terminate (always) + amend ledger.
            actual_hours = (time.monotonic() - started) / 3600.0
            terminate_tag: str = tag
            if info is not None:
                try:
                    self._terminate_pod(info.pod_id)
                except Exception as exc:
                    logger.error(
                        "terminate_pod({}) failed: {!r} — marking orphaned",
                        info.pod_id,
                        exc,
                    )
                    terminate_tag = "orphaned"
            self.cost_cap.record_termination(
                run_id=run_id,
                actual_hours=actual_hours,
                tag=(
                    "orphaned" if terminate_tag == "orphaned" else ("ok" if rc == 0 else "errored")
                ),
            )

        return ExecResult(
            command=command,
            returncode=rc,
            stdout=captured_stdout,
            stderr=captured_stderr,
            duration_s=time.monotonic() - started,
            host=f"{self.host}:{info.pod_id}" if info else self.host,
        )

    # ---- GraphQL transport ---------------------------------------------------
    def _gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """One GraphQL call to RunPod, with the API key as Bearer.

        `requests` is imported lazily so the orchestration package stays
        import-safe with no extras installed (PLATFORM-NOT-HUB: requests
        belongs to the `gpu-rental` extra).
        """
        import requests

        resp = requests.post(
            self.endpoint,
            json={"query": query, "variables": variables or {}},
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            raise RunPodLaunchError(f"RunPod GraphQL errors: {payload['errors']}")
        data: dict[str, Any] = payload.get("data") or {}
        return data

    def _launch_pod(self, run_id: str) -> _ConnectInfo:
        """Create a single GPU pod and poll until it's SSH-reachable.

        The pod_type string maps onto RunPod's `gpuTypeId` in the launch
        mutation (e.g. "NVIDIA H100 PCIe" → "NVIDIA H100 PCIe"). For
        Stage-07 we run community-cloud + bid-priced pods to keep the cost
        cap honest; the operator can override pod_type to a Secure Cloud
        SKU when reliability matters.
        """
        # createPod mutation — schema pinned at the doc revision dated 2026-05.
        mutation = """
            mutation CreatePod($input: PodFindAndDeployOnDemandInput) {
                podFindAndDeployOnDemand(input: $input) {
                    id
                    machine { podHostId }
                    runtime {
                        ports { ip publicPort privatePort type }
                    }
                }
            }
        """
        variables = {
            "input": {
                "name": f"aero-{run_id}",
                "gpuTypeId": self.pod_type,
                "imageName": self.container_image,
                "containerDiskInGb": self.volume_in_gb,
                "volumeInGb": 0,
                "ports": "22/tcp",
                "minVcpuCount": 8,
                "minMemoryInGb": 32,
                "supportPublicIp": True,
                "cloudType": "COMMUNITY",
                "dockerArgs": "sleep infinity",  # we exec our own command via ssh
            }
        }
        data = self._gql(mutation, variables)
        node = data.get("podFindAndDeployOnDemand")
        if not node or "id" not in node:
            raise RunPodLaunchError(f"createPod returned no pod id: {data}")
        pod_id = node["id"]
        launched_at = datetime.now(UTC)

        # Poll pod for SSH readiness (ports.ip + ports.publicPort populated).
        ssh_host, ssh_port = self._wait_for_ssh(pod_id, deadline_s=600)
        return _ConnectInfo(
            pod_id=pod_id,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            launched_at=launched_at,
        )

    def _wait_for_ssh(self, pod_id: str, *, deadline_s: int) -> tuple[str, int]:
        """Poll `getPod(podId)` until a public SSH port is reachable."""
        query = """
            query Pod($podId: String!) {
                pod(input: { podId: $podId }) {
                    id
                    desiredStatus
                    runtime {
                        ports { ip publicPort privatePort type isIpPublic }
                    }
                }
            }
        """
        end = time.monotonic() + deadline_s
        last_status = "unknown"
        while time.monotonic() < end:
            data = self._gql(query, {"podId": pod_id})
            pod = data.get("pod")
            if not pod:
                raise RunPodLaunchError(f"pod {pod_id} returned no pod row")
            last_status = pod.get("desiredStatus", last_status)
            runtime = pod.get("runtime") or {}
            for port in runtime.get("ports", []) or []:
                if port.get("privatePort") == 22 and port.get("isIpPublic"):
                    return str(port["ip"]), int(port["publicPort"])
            time.sleep(5)
        raise RunPodLaunchError(
            f"pod {pod_id} did not expose SSH within {deadline_s}s "
            f"(last desiredStatus={last_status!r})"
        )

    def _terminate_pod(self, pod_id: str) -> None:
        """Terminate a pod and confirm `desiredStatus = TERMINATED`."""
        mutation = """
            mutation Terminate($podId: String!) {
                podTerminate(input: { podId: $podId })
            }
        """
        self._gql(mutation, {"podId": pod_id})
        # Verify termination — terminate_pod returning 200 without the pod
        # actually stopping is the cost-overrun mode CostCap is built for.
        query = """
            query Pod($podId: String!) { pod(input: { podId: $podId }) { id desiredStatus } }
        """
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            data = self._gql(query, {"podId": pod_id})
            pod = data.get("pod")
            if pod is None or pod.get("desiredStatus") in {"TERMINATED", "EXITED"}:
                logger.info("pod {} confirmed terminated", pod_id)
                return
            time.sleep(5)
        raise RunPodLaunchError(f"pod {pod_id} did not confirm TERMINATED within 300s")

    # ---- SSH transport -------------------------------------------------------
    def _ssh_exec(
        self,
        info: _ConnectInfo,
        command: str,
        timeout_s: int,
    ) -> tuple[int, str, str]:
        """SSH into the pod, run `command`, return (rc, stdout, stderr)."""
        ssh_argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=30",
            "-p",
            str(info.ssh_port),
            f"{info.ssh_user}@{info.ssh_host}",
            command,
        ]
        logger.debug("ssh-exec on RunPod pod {}: {}", info.pod_id, command)
        try:
            proc = subprocess.run(
                ssh_argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return (
                124,
                _as_text(exc.stdout),
                f"ssh command on pod {info.pod_id} timed out after {timeout_s}s",
            )
        return proc.returncode, proc.stdout, proc.stderr

    # ---- inspection helpers (operator-facing) -------------------------------
    def estimate_cost_usd(self) -> float:
        """The pre-launch projected cost in USD (matches what check_budget uses)."""
        return self.projected_hours * self.hourly_rate_usd

    def last_ledger_entry(self, *, run_id: str) -> LedgerEntry | None:
        """Convenience for tests / debugging — find this run_id in the ledger."""
        ledger = self.cost_cap.ensure_ledger()
        for e in reversed(ledger.entries):
            if e.run_id == run_id:
                return e
        return None


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
