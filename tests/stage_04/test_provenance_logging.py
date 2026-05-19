"""Stage 04 — hermetic tests for the MLflow logger and the Postgres mirror.

`mlflow` and `psycopg2` are mocked; no live tracking server or database is
touched. Run in the default CI suite.
"""

from __future__ import annotations

import psycopg2
import pytest
from aero.provenance import ProvenanceError, ProvenanceTuple
from aero.provenance.db import mirror_provenance_row, resolve_dsn
from aero.provenance.mlflow import start_provenance_run

pytestmark = pytest.mark.stage_04

_SHA = "a" * 64
_GITSHA = "0123456789abcdef0123456789abcdef01234567"


def _tuple() -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha=_GITSHA, dvc_input_hash="b" * 64, container_sif_sha256="c" * 64, config_hash=_SHA
    )


# --- resolve_dsn -------------------------------------------------------------


def test_resolve_dsn_present(monkeypatch) -> None:
    monkeypatch.setenv("AERO_PROVENANCE_DSN", "postgresql://u@h/aero_provenance")
    assert resolve_dsn() == "postgresql://u@h/aero_provenance"


def test_resolve_dsn_missing_fails_loud(monkeypatch) -> None:
    monkeypatch.delenv("AERO_PROVENANCE_DSN", raising=False)
    with pytest.raises(ProvenanceError, match="AERO_PROVENANCE_DSN"):
        resolve_dsn()


# --- mirror_provenance_row (psycopg2 mocked) ---------------------------------


class _FakeCursor:
    def __init__(self, calls: list) -> None:
        self.calls = calls

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple) -> None:
        self.calls.append((sql, params))


class _FakeConn:
    def __init__(self) -> None:
        self.calls: list = []
        self.closed = False
        self.committed = False

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, exc_type: object, *rest: object) -> bool:
        self.committed = exc_type is None
        return False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.calls)

    def close(self) -> None:
        self.closed = True


def test_mirror_provenance_row_inserts(monkeypatch) -> None:
    conn = _FakeConn()
    monkeypatch.setattr(psycopg2, "connect", lambda dsn: conn)

    mirror_provenance_row(run_id="run-1", provenance=_tuple(), db_dsn="postgresql://x")

    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "INSERT INTO mlflow_artifact_provenance" in sql
    assert params == ("run-1", _GITSHA, "b" * 64, "c" * 64, _SHA)
    assert conn.committed is True
    assert conn.closed is True


def test_mirror_provenance_row_connect_failure(monkeypatch) -> None:
    def _boom(dsn: str) -> None:
        raise psycopg2.OperationalError("connection refused")

    monkeypatch.setattr(psycopg2, "connect", _boom)
    with pytest.raises(ProvenanceError, match="cannot connect"):
        mirror_provenance_row(run_id="run-1", provenance=_tuple(), db_dsn="postgresql://x")


# --- start_provenance_run (mlflow + mirror mocked) ---------------------------


class _FakeInfo:
    run_id = "fake-run-123"


class _FakeRun:
    info = _FakeInfo()


class _FakeActiveRun:
    def __enter__(self) -> _FakeRun:
        return _FakeRun()

    def __exit__(self, *exc: object) -> bool:
        return False


def test_start_provenance_run_tags_all_four(monkeypatch) -> None:
    import mlflow

    recorded: dict = {}
    monkeypatch.setattr(mlflow, "set_tracking_uri", lambda uri: recorded.update(uri=uri))
    monkeypatch.setattr(mlflow, "set_experiment", lambda exp: recorded.update(exp=exp))
    monkeypatch.setattr(mlflow, "start_run", lambda: _FakeActiveRun())
    monkeypatch.setattr(mlflow, "set_tags", lambda tags: recorded.update(tags=tags))

    mirrored: dict = {}
    monkeypatch.setattr(
        "aero.provenance.db.mirror_provenance_row",
        lambda **kw: mirrored.update(kw),
    )

    with start_provenance_run(
        tracking_uri="http://aero-mlflow:5000",
        experiment="aero-provenance",
        provenance=_tuple(),
        case_name="naca0012",
        db_dsn="postgresql://x",
        extra_tags={"solver_version": "OpenFOAM-ESI v2412"},
    ) as run:
        assert run.info.run_id == "fake-run-123"

    assert recorded["uri"] == "http://aero-mlflow:5000"
    tags = recorded["tags"]
    for key in ("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash"):
        assert tags[key]
    assert tags["case_name"] == "naca0012"
    assert tags["stage"] == "04"
    assert tags["solver_version"] == "OpenFOAM-ESI v2412"
    assert mirrored["run_id"] == "fake-run-123"
