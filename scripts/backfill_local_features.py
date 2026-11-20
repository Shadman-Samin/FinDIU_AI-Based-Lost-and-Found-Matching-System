"""Preview or backfill local image features without deleting reports or claims.

    python -m scripts.backfill_local_features
    python -m scripts.backfill_local_features --apply --limit 100

Remote database/storage access requires --allow-remote. Re-run bounded batches
until the preview reports no pending rows; failures remain eligible for retry.
"""

import argparse
import json

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from backend.app.config import Settings
from backend.app.db import create_session_factory
from backend.app.image_features import FEATURE_VERSION
from backend.app.models import Item
from backend.app.processing import backfill_features
from backend.app.storage import build_storage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write one bounded batch; default is preview only"
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="explicitly authorize configured remote database/storage access",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    settings = Settings()
    remote = make_url(settings.database_url).host not in {"localhost", "127.0.0.1", "::1"}
    if not args.allow_remote and (remote or (args.apply and settings.storage_provider != "local")):
        parser.error("Remote backfill requires explicit --allow-remote authorization")
    engine, factory = create_session_factory(settings.database_url)
    try:
        with factory() as session:
            pending = session.scalar(
                select(func.count())
                .select_from(Item)
                .where(
                    Item.status == "active",
                    (Item.feature_version != FEATURE_VERSION)
                    | (Item.image_path.is_not(None) & Item.image_features.is_(None)),
                )
            )
            session.rollback()
            result = (
                backfill_features(session, build_storage(settings), args.limit)
                if args.apply
                else {}
            )
        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry_run",
                    "pending_before": pending,
                    "batch_limit": args.limit,
                    **result,
                }
            )
        )
        return 1 if result.get("failed") else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
