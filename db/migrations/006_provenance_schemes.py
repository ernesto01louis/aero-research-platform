"""stage 23 — per-term provenance semantics columns (no backfill)

Revision ID: 006_provenance_schemes
Revises: 005_container_set
Create Date: 2026-10-21

The authoritative DDL is the sibling `006_provenance_schemes.sql`, executed verbatim by
`upgrade()` — alembic is the applicator and version tracker, the .sql file is the
human-reviewed source of truth. Same arrangement as 004 and 005. See ADR-052 and ADR-053.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "006_provenance_schemes"
down_revision = "005_container_set"
branch_labels = None
depends_on = None

_DDL = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    # Additive migration, so the downgrade is a clean drop: the columns are NULL on every row
    # written before Stage 23, and only Stage-23 writers fill them.
    op.execute(
        "ALTER TABLE mlflow_artifact_provenance "
        "DROP CONSTRAINT IF EXISTS provenance_schemes_consistent"
    )
    op.execute(
        "ALTER TABLE mlflow_artifact_provenance "
        "DROP COLUMN IF EXISTS dvc_inputs, "
        "DROP COLUMN IF EXISTS container_sif_sha256_scheme, "
        "DROP COLUMN IF EXISTS dvc_input_hash_scheme"
    )
