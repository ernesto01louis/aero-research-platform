"""The self-test paired snapshot is what the estimator computes (Stage 21; ADR-047 format freeze).

The frozen format-v1 digests pin bytes, so the paired fixture is a committed snapshot rather
than a test-time numpy computation, whose last bits vary across CPUs. This test keeps the snapshot
honest: a fresh estimate from the same samples agrees with it to 1e-12, relative.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.unit._crate_fixtures import _paired, _paired_from_samples

pytestmark = pytest.mark.stage_21


def _numbers(obj: Any, path: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_numbers(v, f"{path}/{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_numbers(v, f"{path}/{i}"))
    else:
        out[path] = obj
    return out


def test_the_snapshot_matches_a_fresh_estimate() -> None:
    snap = _numbers(_paired().model_dump(mode="json"))
    fresh = _numbers(_paired_from_samples().model_dump(mode="json"))
    assert snap.keys() == fresh.keys()
    for key, value in snap.items():
        if isinstance(value, float) and math.isfinite(value):
            assert fresh[key] == pytest.approx(value, rel=1e-12, abs=1e-15), key
        else:
            assert fresh[key] == value, key
