"""Reachability fixtures for the Stage 04 end-to-end provenance test.

The `provenance-completeness` test needs the live MLflow server and the
`aero_provenance` Postgres DB. These fixtures let it skip cleanly off the
cluster (the slow gate in the root `conftest.py` already skips it by default).
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest

_MLFLOW_HEALTH = "http://aero-mlflow:5000/health"


@pytest.fixture(scope="session")
def aero_mlflow_reachable() -> bool:
    """True iff the aero-mlflow tracking server answers its health endpoint."""
    try:
        with urllib.request.urlopen(_MLFLOW_HEALTH, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


@pytest.fixture(scope="session")
def aero_provenance_reachable() -> bool:
    """True iff the aero_provenance Postgres DB accepts a connection."""
    dsn = os.environ.get("AERO_PROVENANCE_DSN")
    if not dsn:
        return False
    try:
        import psycopg2

        conn = psycopg2.connect(dsn, connect_timeout=5)
        conn.close()
        return True
    except Exception:
        return False
