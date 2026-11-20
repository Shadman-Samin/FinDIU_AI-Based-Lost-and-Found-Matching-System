"""Constrain durable states and index worker eligibility."""

from alembic import op

revision = "c312b6c89f01"
down_revision = "8ba5121e81cd"
branch_labels = None
depends_on = None

CHECKS = {
    "users": {
        "ck_users_role": "role IN ('user', 'admin')",
        "ck_users_locale": "locale IN ('en', 'bn')",
        "ck_users_email_normalized": "email = lower(trim(email))",
    },
    "items": {
        "ck_items_embed_status": "embed_status IN ('pending', 'processing', 'ready', 'failed')",
        "ck_items_attempts": "embed_attempts >= 0",
    },
    "matches": {
        # Legacy dot products can exceed 1 by machine epsilon; keep their exact history.
        "ck_matches_components": "text_sim BETWEEN -1.000000001 AND 1.000000001 AND (image_sim IS NULL OR image_sim BETWEEN -1.000000001 AND 1.000000001) AND attr_score BETWEEN 0 AND 1.000000001",
        "ck_matches_notify_status": "notify_status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')",
        "ck_matches_attempts": "notify_attempts >= 0",
        "ck_matches_distinct_items": "lost_id <> found_id",
    },
    "claims": {"ck_claims_status": "status IN ('pending', 'approved', 'rejected')"},
}
INDEXES = {
    "ix_items_eligibility": ("items", ["status", "type", "category", "event_date"]),
    "ix_items_due": ("items", ["embed_status", "embed_next_attempt_at", "embed_lease_until"]),
    "ix_matches_due": (
        "matches",
        ["notify_status", "notify_next_attempt_at", "notify_lease_until"],
    ),
}


def upgrade():
    for table, checks in CHECKS.items():
        for name, condition in checks.items():
            op.create_check_constraint(name, table, condition, schema="findiu")
    for name, (table, columns) in INDEXES.items():
        op.create_index(name, table, columns, schema="findiu")


def downgrade():
    for name, (table, _) in INDEXES.items():
        op.drop_index(name, table_name=table, schema="findiu")
    for table, checks in CHECKS.items():
        for name in checks:
            op.drop_constraint(name, table, type_="check", schema="findiu")
