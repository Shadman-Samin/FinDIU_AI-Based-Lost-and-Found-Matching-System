from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_local_matching_integration import pair
from test_matching_integration import TICK

pytestmark = pytest.mark.integration


def test_legacy_rounding_noise_upgrades_without_rewriting_claim_history(client, app):
    reports, owner = pair(client)
    client.post("/internal/tick", headers=TICK)
    [match] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()["items"]
    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        headers=owner,
        json={"answer": "Synthetic migration proof"},
    ).json()
    root = Path(__file__).parents[1]
    config = Config(str(root / "backend/alembic.ini"))
    config.set_main_option("script_location", str(root / "backend/migrations"))
    config.attributes["database_url"] = app.state.settings.database_url
    upgraded = False
    try:
        command.downgrade(config, "8ba5121e81cd")
        with app.state.session_factory() as session:
            session.execute(
                text(
                    "UPDATE findiu.matches SET text_sim=0.62, image_sim=:image, attr_score=1, score=0.829 WHERE id=:id"
                ),
                {"image": 1.0000000000000002, "id": UUID(match["id"])},
            )
            session.commit()
        command.upgrade(config, "head")
        upgraded = True
        with app.state.session_factory() as session:
            row = session.execute(
                text("SELECT image_sim, score FROM findiu.matches WHERE id=:id"),
                {"id": UUID(match["id"])},
            ).one()
            assert row.image_sim == 1.0000000000000002
            assert row.score == 0.829
            assert session.scalar(
                text("SELECT match_id FROM findiu.claims WHERE id=:id"), {"id": UUID(claim["id"])}
            ) == UUID(match["id"])
            assert (
                session.scalar(
                    text("SELECT status FROM findiu.claims WHERE id=:id"), {"id": UUID(claim["id"])}
                )
                == "pending"
            )
            with pytest.raises(IntegrityError):
                session.execute(
                    text("UPDATE findiu.matches SET image_sim=1.01 WHERE id=:id"),
                    {"id": UUID(match["id"])},
                )
            session.rollback()
    finally:
        # Restore the dedicated test schema even when the expected RED migration fails.
        if not upgraded:
            with app.state.session_factory() as session:
                session.execute(
                    text("UPDATE findiu.matches SET image_sim=1 WHERE id=:id"),
                    {"id": UUID(match["id"])},
                )
                session.commit()
        command.upgrade(config, "head")
