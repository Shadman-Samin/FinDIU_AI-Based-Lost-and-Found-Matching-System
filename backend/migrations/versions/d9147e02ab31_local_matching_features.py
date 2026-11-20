"""Add versioned local image features and immutable matching evidence snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d9147e02ab31"
down_revision = "c312b6c89f01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "items", sa.Column("image_features", postgresql.JSONB(), nullable=True), schema="findiu"
    )
    op.add_column(
        "items",
        sa.Column("feature_version", sa.Integer(), nullable=False, server_default="0"),
        schema="findiu",
    )
    op.create_check_constraint(
        "ck_items_feature_version", "items", "feature_version >= 0", schema="findiu"
    )
    op.add_column(
        "matches", sa.Column("evidence", postgresql.JSONB(), nullable=True), schema="findiu"
    )
    # Claimed match snapshots are preserved by the worker, not deleted or re-scored.
    op.execute("UPDATE findiu.items SET match_pending = true WHERE status = 'active'")


def downgrade():
    op.drop_column("matches", "evidence", schema="findiu")
    op.drop_constraint("ck_items_feature_version", "items", type_="check", schema="findiu")
    op.drop_column("items", "feature_version", schema="findiu")
    op.drop_column("items", "image_features", schema="findiu")
