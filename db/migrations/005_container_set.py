"""stage 20 — multi-container provenance roster column

Revision ID: 005_container_set
Revises: 004_provenance
Create Date: 2026-07-30

The authoritative DDL is the sibling `005_container_set.sql`, executed verbatim by
`upgrade()` — alembic is the applicator and version tracker, the .sql file is the
human-reviewed source of truth. Same arrangement as 004. See ADR-038.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "005_container_set"
down_revision = "004_provenance"
branch_labels = None
depends_on = None

_DDL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    # Additive migration, so the downgrade is a clean drop: no historical row
    # depends on the column, and the four-fold contract predates it.
    op.execute("DROP INDEX IF EXISTS idx_provenance_container_set")
    op.execute("ALTER TABLE mlflow_artifact_provenance DROP COLUMN IF EXISTS container_sif_set")
