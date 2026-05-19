"""stage 04 — mlflow_artifact_provenance mirror table

Revision ID: 004_provenance
Revises:
Create Date: 2026-05-19

The authoritative DDL is the sibling `004_provenance.sql`, executed verbatim by
`upgrade()` — alembic is the applicator and version tracker, the .sql file is
the human-reviewed source of truth. See ADR-004.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "004_provenance"
down_revision = None
branch_labels = None
depends_on = None

_DDL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mlflow_artifact_provenance")
