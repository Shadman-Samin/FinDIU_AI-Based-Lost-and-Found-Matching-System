import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from backend.app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def database_url() -> str:
    # Tests inject an explicit URL; deployments supply DATABASE_URL (Render uses postgres://).
    raw = config.attributes.get("database_url") or os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError("DATABASE_URL is required to run migrations")
    return make_url(raw).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def run_migrations_offline():
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
