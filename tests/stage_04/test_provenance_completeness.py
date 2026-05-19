"""Stage 04 — end-to-end provenance-completeness check.

Runs the NACA 0012 case through the full Stage 04 pipeline and asserts the
four-fold contract held: the MLflow run carries all four well-formed tags and
the `mlflow_artifact_provenance` Postgres row exists with matching values.

Slow + cluster-bound: skipped unless `--run-slow` AND the aero-mlflow server
and aero_provenance DB are reachable. This is the assertion body of the
`provenance-completeness` CI job.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.stage_04, pytest.mark.slow, pytest.mark.vv]

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_RE = re.compile(r"^[0-9a-f]{40}(-dirty)?$")
_FOUR = ("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash")


@pytest.fixture(scope="module")
def completed_run(aero_mlflow_reachable: bool, aero_provenance_reachable: bool) -> str:
    """Run `aero run naca0012` end-to-end; return the MLflow run id."""
    if not aero_mlflow_reachable:
        pytest.skip("aero-mlflow tracking server not reachable")
    if not aero_provenance_reachable:
        pytest.skip("aero_provenance Postgres DB not reachable")

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


def test_mlflow_run_has_all_four_tags(completed_run: str) -> None:
    import mlflow

    mlflow.set_tracking_uri("http://aero-mlflow:5000")
    run = mlflow.get_run(completed_run)
    tags = run.data.tags
    for key in _FOUR:
        assert tags.get(key), f"missing/empty tag: {key}"
    assert _GIT_RE.match(tags["git_sha"])
    for key in ("dvc_input_hash", "container_sif_sha256", "config_hash"):
        assert _HASH_RE.match(tags[key]), f"malformed {key}: {tags[key]}"


def test_postgres_mirror_row_matches(completed_run: str) -> None:
    import mlflow
    import psycopg2

    mlflow.set_tracking_uri("http://aero-mlflow:5000")
    tags = mlflow.get_run(completed_run).data.tags

    conn = psycopg2.connect(os.environ["AERO_PROVENANCE_DSN"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT git_sha, dvc_input_hash, container_sif_sha256, config_hash "
                "FROM mlflow_artifact_provenance WHERE run_id = %s",
                (completed_run,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, f"no mirror row for run {completed_run}"
    assert row == tuple(tags[k] for k in _FOUR)
