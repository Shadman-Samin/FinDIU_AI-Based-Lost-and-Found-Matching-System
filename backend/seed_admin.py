"""Create or promote the single FinDIU review account.

Usage:
    ADMIN_EMAIL=desk@diu.edu.bd ADMIN_PASSWORD='...' python -m backend.seed_admin
"""

import os
import sys

from sqlalchemy import select

from backend.app.auth import hash_password
from backend.app.config import Settings
from backend.app.db import create_session_factory
from backend.app.models import Role, User


def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or len(password) < 12:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD (at least 12 characters).")
        return 2
    settings = Settings()
    engine, factory = create_session_factory(settings.database_url)
    try:
        with factory() as session:
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                session.add(
                    User(
                        name="FinDIU review desk",
                        email=email,
                        password_hash=hash_password(password),
                        role=Role.ADMIN,
                    )
                )
            else:
                user.role = Role.ADMIN
            session.commit()
    finally:
        engine.dispose()
    print(f"Admin ready: {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
