"""RunPod cloud GPU executor — Stage 07 minimal version.

This package provides `RunPodExecutor`, the first concrete cloud `Executor`
on the platform. Stage 07 keeps it stupid: launch one pod, upload one case
dir, run one command, pull results, terminate. Stage 13 promotes it into
the multi-cloud cost router (RunPod + Lambda Labs + Vast.ai).

All RunPod API calls hit the GraphQL endpoint via `requests` — no vendor
SDK dependency. The full schema lives at
<https://docs.runpod.io/api-reference/graphql>; we use a tiny pinned
subset (createPod / terminatePod / pod).
"""

from aero.orchestration.runpod.executor import (
    DEFAULT_RUNPOD_ENDPOINT,
    POD_TYPE_HOURLY_USD,
    RunPodExecutor,
    RunPodLaunchError,
)

__all__ = [
    "DEFAULT_RUNPOD_ENDPOINT",
    "POD_TYPE_HOURLY_USD",
    "RunPodExecutor",
    "RunPodLaunchError",
]
