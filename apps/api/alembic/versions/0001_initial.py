"""Initial schema — analyses and building_damages (Milestone F5).

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-06

Deliberately does NOT include search zones, recommendations, or routes —
see `app/db/models.py`'s module docstring for why F2/F3's own established
"recompute fresh, never cache" design principle means those are pure
functions of `AffectedArea`/`Resource`/config, not persisted state.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("storage_name", sa.String(length=128), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("model_metadata", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("analysis_id"),
    )
    op.create_index("ix_analyses_status", "analyses", ["status"])

    op.create_table(
        "building_damages",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("damage_class", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.Column("geometry", sa.JSON(), nullable=True),
        sa.Column("coordinate_reference_system", sa.String(length=16), nullable=False),
        sa.Column("georeferenced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["analyses.analysis_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_building_damages_analysis_id", "building_damages", ["analysis_id"]
    )
    op.create_index(
        "ix_building_damages_damage_class", "building_damages", ["damage_class"]
    )


def downgrade() -> None:
    op.drop_index("ix_building_damages_damage_class", table_name="building_damages")
    op.drop_index("ix_building_damages_analysis_id", table_name="building_damages")
    op.drop_table("building_damages")
    op.drop_index("ix_analyses_status", table_name="analyses")
    op.drop_table("analyses")
