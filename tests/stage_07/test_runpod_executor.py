"""Mocked unit tests for aero.orchestration.runpod.executor — Stage 07.

The tests do not hit RunPod's GraphQL endpoint; they monkeypatch
`RunPodExecutor._gql` and `RunPodExecutor._ssh_exec` so the lifecycle
(check_budget -> record_launch -> launch -> ssh-exec -> terminate ->
record_termination) is exercised end-to-end against a tmpdir ledger.
The live integration test (gated on `RUNPOD_API_KEY_SET=1`) is the
operator's `aero run taylor_green_p3_32 --executor runpod` invocation in
Stage 07 §G.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.orchestration.cost_cap import CostCap, CostCapExceeded
from aero.orchestration.runpod.executor import (
    POD_TYPE_HOURLY_USD,
    RunPodExecutor,
)

pytestmark = pytest.mark.stage_07


@pytest.fixture
def cost_cap(tmp_path: Path) -> CostCap:
    return CostCap(ledger_path=tmp_path / "runpod-ledger.json", cap_usd=50.0)


def _make_executor(
    cost_cap: CostCap,
    *,
    projected_hours: float = 0.1,
    hourly_rate_usd: float | None = None,
) -> RunPodExecutor:
    return RunPodExecutor(
        api_key="test-api-key",
        pod_type="NVIDIA H100 PCIe",
        container_image="ghcr.io/ernesto01louis/aero-pyfr:v1.15.0",
        cost_cap=cost_cap,
        projected_hours=projected_hours,
        hourly_rate_usd=hourly_rate_usd,
    )


class _MockGQL:
    """A scriptable RunPod GraphQL mock — drops in for _gql.

    Each `_gql` call pops one entry off `responses`. Tests build a list
    of (matcher_substring, response_dict) tuples; the matcher_substring
    must appear in the query text or KeyError raises.
    """

    def __init__(self, responses: list[tuple[str, dict[str, Any]]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((query, variables or {}))
        for i, (matcher, response) in enumerate(self.responses):
            if matcher in query:
                self.responses.pop(i)
                return response
        raise AssertionError(
            f"unexpected GraphQL call: query did not match any matcher in "
            f"{[m for m, _ in self.responses]!r}; query was:\n{query[:200]}"
        )


@pytest.fixture
def successful_lifecycle_responses() -> list[tuple[str, dict[str, Any]]]:
    """Three GraphQL responses for a successful launch -> exec -> terminate."""
    return [
        (
            "podFindAndDeployOnDemand",
            {"podFindAndDeployOnDemand": {"id": "pod-123", "machine": {"podHostId": "host-x"}}},
        ),
        (
            "pod(input: { podId: $podId })",
            {
                "pod": {
                    "id": "pod-123",
                    "desiredStatus": "RUNNING",
                    "runtime": {
                        "ports": [
                            {
                                "ip": "1.2.3.4",
                                "publicPort": 22001,
                                "privatePort": 22,
                                "type": "tcp",
                                "isIpPublic": True,
                            }
                        ]
                    },
                }
            },
        ),
        ("podTerminate", {"podTerminate": True}),
        (
            "pod(input: { podId: $podId })",
            {"pod": {"id": "pod-123", "desiredStatus": "TERMINATED"}},
        ),
    ]


def test_run_lifecycle_records_ok_on_zero_returncode(
    cost_cap: CostCap,
    successful_lifecycle_responses: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exe = _make_executor(cost_cap, projected_hours=0.1)
    mock_gql = _MockGQL(successful_lifecycle_responses)
    monkeypatch.setattr(exe, "_gql", mock_gql)
    monkeypatch.setattr(exe, "_ssh_exec", lambda info, command, timeout_s: (0, "hello\n", ""))

    result = exe.run("echo hello", session="run-123")

    assert result.returncode == 0
    # ExecResult uses str_strip_whitespace=True in its pydantic config, so the
    # trailing newline is stripped on validation. Match the post-validation form.
    assert result.stdout == "hello"
    assert result.host.endswith(":pod-123")
    # ledger has one entry, tagged ok, with actual_hours populated
    ledger = cost_cap.ensure_ledger()
    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry.tag == "ok"
    assert entry.run_id == "run-123"
    assert entry.actual_hours is not None
    assert entry.actual_cost_usd is not None
    # 4 GraphQL calls: createPod + pod (SSH poll) + terminate + pod (terminate poll)
    assert len(mock_gql.calls) == 4


def test_run_refuses_when_cost_cap_exceeded(cost_cap: CostCap) -> None:
    # 100 hours @ $2.49 = $249 — well over the $50 cap.
    exe = _make_executor(cost_cap, projected_hours=100.0)
    with pytest.raises(CostCapExceeded):
        exe.run("noop", session="never-runs")
    # No ledger entry should be created — check_budget runs before record_launch.
    ledger = cost_cap.ensure_ledger()
    assert ledger.entries == []


def test_run_tags_errored_on_nonzero_returncode(
    cost_cap: CostCap,
    successful_lifecycle_responses: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exe = _make_executor(cost_cap, projected_hours=0.1)
    mock_gql = _MockGQL(successful_lifecycle_responses)
    monkeypatch.setattr(exe, "_gql", mock_gql)
    monkeypatch.setattr(exe, "_ssh_exec", lambda info, command, timeout_s: (7, "", "boom"))

    result = exe.run("false", session="run-err")
    assert result.returncode == 7
    assert "boom" in result.stderr
    ledger = cost_cap.ensure_ledger()
    assert ledger.entries[0].tag == "errored"


def test_run_marks_orphaned_when_terminate_polling_fails(
    cost_cap: CostCap,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If terminate confirmation fails, ledger entry is tagged 'orphaned'."""
    # responses: launch ok; SSH-poll ok; terminate ok; pod-poll-after-terminate
    # never returns TERMINATED (keeps returning RUNNING, so the 300s deadline
    # would expire — we shortcut by exhausting the response list).
    responses = [
        (
            "podFindAndDeployOnDemand",
            {"podFindAndDeployOnDemand": {"id": "pod-orph", "machine": {}}},
        ),
        (
            "pod(input: { podId: $podId })",
            {
                "pod": {
                    "id": "pod-orph",
                    "desiredStatus": "RUNNING",
                    "runtime": {
                        "ports": [
                            {
                                "ip": "1.2.3.4",
                                "publicPort": 22002,
                                "privatePort": 22,
                                "type": "tcp",
                                "isIpPublic": True,
                            }
                        ]
                    },
                }
            },
        ),
        ("podTerminate", {"podTerminate": True}),
    ]
    exe = _make_executor(cost_cap, projected_hours=0.1)
    mock_gql = _MockGQL(responses)
    monkeypatch.setattr(exe, "_gql", mock_gql)
    monkeypatch.setattr(exe, "_ssh_exec", lambda info, command, timeout_s: (0, "", ""))

    # The post-terminate verification poll will get AssertionError from the
    # exhausted mock — wrapped by the `_terminate_pod` exception handler in
    # `run()`'s finally block as an orphan.
    result = exe.run("echo orphan", session="orph-1")

    # The exec itself succeeded — only termination went wrong.
    assert result.returncode == 0
    ledger = cost_cap.ensure_ledger()
    assert ledger.entries[0].tag == "orphaned"


def test_estimate_cost_matches_hourly_table() -> None:
    cost_cap = CostCap(ledger_path=Path("/tmp/never-written"), cap_usd=50.0)
    exe = _make_executor(cost_cap, projected_hours=0.25)
    expected = 0.25 * POD_TYPE_HOURLY_USD["NVIDIA H100 PCIe"]
    assert exe.estimate_cost_usd() == pytest.approx(expected)


def test_unknown_pod_type_without_hourly_rate_rejected(cost_cap: CostCap) -> None:
    with pytest.raises(ValueError, match="not in POD_TYPE_HOURLY_USD"):
        RunPodExecutor(
            api_key="k",
            pod_type="FUTURE GPU 9000",  # not in the table
            container_image="x",
            cost_cap=cost_cap,
        )


def test_unknown_pod_type_with_explicit_rate_accepted(cost_cap: CostCap) -> None:
    exe = RunPodExecutor(
        api_key="k",
        pod_type="FUTURE GPU 9000",
        container_image="x",
        cost_cap=cost_cap,
        hourly_rate_usd=12.34,
    )
    assert exe.hourly_rate_usd == 12.34


def test_empty_api_key_rejected(cost_cap: CostCap) -> None:
    with pytest.raises(ValueError, match="non-empty api_key"):
        RunPodExecutor(
            api_key="",
            pod_type="NVIDIA H100 PCIe",
            container_image="x",
            cost_cap=cost_cap,
        )
