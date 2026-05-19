"""Reachability fixtures for the Stage 04 end-to-end provenance test.

The `provenance-completeness` test needs the live MLflow server and the
`aero_provenance` Postgres DB. These fixtures let it skip cleanly off the
cluster (the slow gate in the root `conftest.py` already skips it by default).

The MLflow tracking URI is read from `conf/mlflow/default.yaml` — the single
source of truth — rather than hardcoded.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from omegaconf import OmegaConf

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def mlflow_tracking_uri() -> str:
    """The MLflow tracking URI from the Hydra config."""
    cfg = OmegaConf.load(_REPO_ROOT / "conf" / "mlflow" / "default.yaml")
    return str(cfg.tracking_uri)


@pytest.fixture(scope="session")
def aero_mlflow_reachable(mlflow_tracking_uri: str) -> bool:
    """True iff the aero-mlflow tracking server answers its health endpoint."""
    try:
        with urllib.request.urlopen(f"{mlflow_tracking_uri}/health", timeout=5) as resp:
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
