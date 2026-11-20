"""Require report-scoped permission for optional external AI processing."""

import sqlalchemy as sa
from alembic import op

revision = "e620bf73ad14"
down_revision = "d9147e02ab31"
branch_labels = None
depends_on = None


def upgrade():
    # Unknown historical scope is local-only until the owner explicitly consents.
    op.add_column(
        "items",
        sa.Column("semantic_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="findiu",
    )


def downgrade():
    op.drop_column("items", "semantic_consent", schema="findiu")
