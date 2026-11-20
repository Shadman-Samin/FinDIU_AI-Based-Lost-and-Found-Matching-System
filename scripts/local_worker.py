"""Process the loopback-only, offline demo queue without sending email.

Run once with `python -m scripts.local_worker`, or poll with `--watch`.
Production uses /internal/tick with its secret and a hosted cron scheduler.
"""

import argparse
import time

from sqlalchemy.engine import make_url

from backend.app.config import Settings
from backend.app.db import create_session_factory
from backend.app.processing import run_tick
from backend.app.providers import build_embedder
from backend.app.storage import build_storage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings()
    url = make_url(settings.database_url)
    if (
        url.host not in {"localhost", "127.0.0.1", "::1"}
        or not (url.database or "").endswith(("_dev", "_demo"))
        or settings.embedding_provider != "local"
        or settings.storage_provider != "local"
    ):
        parser.error("Local worker requires a loopback _dev/_demo database and local providers")
    engine, factory = create_session_factory(settings.database_url)
    embedder, storage = build_embedder(settings), build_storage(settings)
    try:
        while True:
            with factory() as session:
                result = run_tick(session, settings, embedder, storage, notifier=None)
            print(result, flush=True)
            if not args.watch:
                break
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
