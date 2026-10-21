"""Stage 04 — end-to-end provenance-completeness check.

Runs the NACA 0012 case through the full Stage 04 pipeline and asserts the
four-fold contract held: the MLflow run carries all four well-formed tags and
the `mlflow_artifact_provenance` Postgres row exists with matching values.

Slow + cluster-bound: skipped unless `--run-slow` AND the aero-mlflow server
and aero_provenance DB are reachable. This is the assertion body of the
`provenance-completeness` CI job, which sets `AERO_PROVENANCE_REQUIRE_CLUSTER=1`
so an unreachable cluster FAILS instead of skipping to green (Stage 23: no job is
green when it measured nothing).

Since Stage 23 it also reads back the typed tuple (ADR-052 D4): the scheme tags,
`container_sif_name`, the digest's membership in `containers/SHA256SUMS`, and
the mirror's scheme columns, byte for byte against the tags.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.stage_04, pytest.mark.slow, pytest.mark.vv]

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_RE = re.compile(r"^[0-9a-f]{40}(-dirty)?$")
_FOUR = ("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash")
_SCHEMES = {
    "dvc_input_hash_scheme": {"repo-sync-state/v0", "declared-dvc-pointers-md5/v1"},
    "container_sif_sha256_scheme": {"sha256sums-lookup/v0", "sif-sha256-verified-at-launch/v1"},
}
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _unavailable(reason: str) -> None:
    if os.environ.get("AERO_PROVENANCE_REQUIRE_CLUSTER") == "1":
        pytest.fail(f"{reason} (AERO_PROVENANCE_REQUIRE_CLUSTER=1: this job must measure)")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def completed_run(aero_mlflow_reachable: bool, aero_provenance_reachable: bool) -> str:
    """Run `aero run naca0012` end-to-end; return the MLflow run id."""
    if not aero_mlflow_reachable:
        _unavailable("aero-mlflow tracking server not reachable")
    if not aero_provenance_reachable:
        _unavailable("aero_provenance Postgres DB not reachable")

    proc = subprocess.run(
        [sys.executable, "-m", "aero.cli", "run", "naca0012", "--executor", "local-ssh"],
        capture_output=True,
        text=True,
        check=False,
        timeout=1200,
    )
    assert proc.returncode == 0, f"`aero run` failed:\n{proc.stdout}\n{proc.stderr}"
    match = re.search(r"MLflow run\s+(\S+)", proc.stdout)
    assert match, f"could not parse run id from:\n{proc.stdout}"
    return match.group(1)


def test_mlflow_run_has_all_four_tags(completed_run: str, mlflow_tracking_uri: str) -> None:
    import mlflow

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    run = mlflow.get_run(completed_run)
    tags = run.data.tags
    for key in _FOUR:
        assert tags.get(key), f"missing/empty tag: {key}"
    assert _GIT_RE.match(tags["git_sha"])
    for key in ("dvc_input_hash", "container_sif_sha256", "config_hash"):
        assert _HASH_RE.match(tags[key]), f"malformed {key}: {tags[key]}"
    for key, names in _SCHEMES.items():
        assert tags.get(key) in names, f"{key} is {tags.get(key)!r}"
    # dvc_inputs is logged exactly under the declared-pointer scheme (ADR-052 D4).
    declared = tags["dvc_input_hash_scheme"] == "declared-dvc-pointers-md5/v1"
    assert ("dvc_inputs" in tags) == declared
    # The container digest is the committed SHA256SUMS entry of the container of record.
    sums = {}
    for line in (_REPO_ROOT / "containers" / "SHA256SUMS").read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and not line.lstrip().startswith("#"):
            sums[parts[1]] = parts[0]
    assert sums.get(tags["container_sif_name"]) == tags["container_sif_sha256"]


def test_postgres_mirror_row_matches(completed_run: str, mlflow_tracking_uri: str) -> None:
    import mlflow
    import psycopg2

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    tags = mlflow.get_run(completed_run).data.tags

    conn = psycopg2.connect(os.environ["AERO_PROVENANCE_DSN"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT git_sha, dvc_input_hash, container_sif_sha256, config_hash, "
                "container_sif_set, dvc_input_hash_scheme, container_sif_sha256_scheme, "
                "dvc_inputs FROM mlflow_artifact_provenance WHERE run_id = %s",
                (completed_run,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, f"no mirror row for run {completed_run}"
    # Byte for byte against the tags, including the roster and the Stage-23 columns (migration
    # 005 claimed this comparison for container_sif_set; it is implemented here at last).
    expected = (
        *(tags[k] for k in _FOUR),
        tags.get("container_sif_set"),
        tags["dvc_input_hash_scheme"],
        tags["container_sif_sha256_scheme"],
        tags.get("dvc_inputs"),
    )
    assert row == expected
