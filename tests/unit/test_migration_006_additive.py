"""Migration 006 is strictly additive and never relabels a historical row (ADR-052, ADR-053).

The mirror gains the per-term scheme columns and the declared inputs. NULL in all three means
"recorded before Stage 23", so the migration may add nullable columns and a consistency CHECK,
and nothing else: no default (which would label every old row), no UPDATE, no INSERT. The
alembic wrapper is read with `ast`, because the required unit job installs no alembic.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_23

REPO = Path(__file__).resolve().parents[2]
SQL = REPO / "db" / "migrations" / "006_provenance_schemes.sql"
PY = REPO / "db" / "migrations" / "006_provenance_schemes.py"

# The names ADR-052 freezes; the db.py writer and the MLflow tags use the same ones.
NEW_COLUMNS = ("dvc_input_hash_scheme", "container_sif_sha256_scheme", "dvc_inputs")


def _statements() -> list[str]:
    raw = SQL.read_text(encoding="utf-8")
    body = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))
    return [" ".join(s.split()).upper() for s in body.split(";") if s.strip()]


def test_the_migration_adds_exactly_the_three_nullable_columns_and_one_check() -> None:
    statements = _statements()
    assert len(statements) == 2, statements
    add, check = statements
    assert add.startswith("ALTER TABLE MLFLOW_ARTIFACT_PROVENANCE ")
    for column in NEW_COLUMNS:
        assert f"ADD COLUMN IF NOT EXISTS {column.upper()} TEXT" in add, column
    assert add.count("ADD COLUMN") == len(NEW_COLUMNS)
    assert check.startswith("ALTER TABLE MLFLOW_ARTIFACT_PROVENANCE ADD CONSTRAINT ")
    assert "CHECK (" in check
    assert "DVC_INPUT_HASH_SCHEME IS NULL) = (CONTAINER_SIF_SHA256_SCHEME IS NULL" in check
    # dvc_inputs is set exactly when the DVC term is the declared-pointer scheme: a v0 row must
    # never read as "declared no inputs".
    assert "(DVC_INPUTS IS NOT NULL)" in check
    assert "IS NOT DISTINCT FROM 'DECLARED-DVC-POINTERS-MD5/V1'" in check


@pytest.mark.parametrize(
    "forbidden",
    ["UPDATE ", "INSERT ", "DELETE ", "DROP ", "DEFAULT", "RENAME", "ALTER COLUMN"],
)
def test_the_migration_never_relabels_or_removes_anything(forbidden: str) -> None:
    for statement in _statements():
        assert forbidden not in statement, f"{forbidden!r} in: {statement}"


def test_the_new_columns_are_nullable() -> None:
    """A NOT NULL column would fail on the ALTER (every historical row is NULL) or need a default."""
    add = _statements()[0]
    assert "NOT NULL" not in add, add


def test_the_alembic_wrapper_chains_after_005_and_runs_the_sql_verbatim() -> None:
    tree = ast.parse(PY.read_text(encoding="utf-8"))
    assigned = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert assigned["revision"] == "006_provenance_schemes"
    assert assigned["down_revision"] == "005_container_set"
    source = PY.read_text(encoding="utf-8")
    assert 'with_suffix(".sql")' in source and "op.execute(_DDL)" in source
