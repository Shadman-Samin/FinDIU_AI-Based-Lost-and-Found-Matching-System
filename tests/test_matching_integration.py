from datetime import date

import pytest
from conftest import auth_header, register
from sqlalchemy import select

pytestmark = pytest.mark.integration

TICK = {"Authorization": "Bearer test-tick-token"}


def item_form(**overrides) -> dict:
    form = {
        "category": "bag",
        "color": "blue",
        "title": "Blue backpack with broken zipper",
        "description": "Dark blue campus backpack, broken left zipper pull, one white sticker.",
        "location": "library",
        "event_date": date.today().isoformat(),
        "private_detail": "Label inside says RIMI 221",
        "consent": "on",
    }
    form.update(overrides)
    return form


def make_admin(app, email="desk@diu.edu.bd") -> None:
    from backend.app.auth import hash_password
    from backend.app.models import Role, User

    with app.state.session_factory() as session:
        session.add(
            User(
                name="Review desk",
                email=email,
                password_hash=hash_password("admin-password-123"),
                role=Role.ADMIN,
            )
        )
        session.commit()


def test_tick_locally_creates_an_explainable_match(client):
    register(client)
    owner = auth_header(client)
    lost = client.post("/api/v1/items?type=lost", data=item_form(), headers=owner).json()

    register(client, email="finder@diu.edu.bd")
    finder = auth_header(client, email="finder@diu.edu.bd")
    found = client.post("/api/v1/items?type=found", data=item_form(), headers=finder).json()

    tick = client.post("/internal/tick", headers=TICK)
    assert tick.status_code == 200, tick.text
    assert tick.json()["embedded"] == 0
    assert tick.json()["matches_created"] == 1

    matches = client.get(f"/api/v1/items/{lost['id']}/matches", headers=owner)
    assert matches.status_code == 200
    [match] = matches.json()["matches"]
    assert match["lost"]["id"] == lost["id"]
    assert match["found"]["id"] == found["id"]
    assert match["score"] >= 0.75
    assert 0 <= match["text_sim"] <= 1
    assert match["attr_score"] > 0.5
    assert "RIMI" not in matches.text

    again = client.post("/internal/tick", headers=TICK)
    assert again.json()["matches_created"] == 0


def test_match_is_private_to_participants(client):
    register(client)
    owner = auth_header(client)
    lost = client.post("/api/v1/items?type=lost", data=item_form(), headers=owner).json()
    register(client, email="finder@diu.edu.bd")
    finder = auth_header(client, email="finder@diu.edu.bd")
    client.post("/api/v1/items?type=found", data=item_form(), headers=finder)
    register(client, email="stranger@diu.edu.bd")
    stranger = auth_header(client, email="stranger@diu.edu.bd")
    client.post("/internal/tick", headers=TICK)

    assert client.get(f"/api/v1/items/{lost['id']}/matches", headers=stranger).status_code == 404
    assert client.get(f"/api/v1/items/{lost['id']}/matches").status_code == 401


def test_tick_requires_the_shared_secret(client):
    assert client.post("/internal/tick").status_code == 401
    assert (
        client.post("/internal/tick", headers={"Authorization": "Bearer wrong"}).status_code == 401
    )


def test_claim_flow_and_admin_decision(client, app):
    register(client)
    owner = auth_header(client)
    lost = client.post("/api/v1/items?type=lost", data=item_form(), headers=owner).json()
    register(client, email="finder@diu.edu.bd")
    finder = auth_header(client, email="finder@diu.edu.bd")
    client.post("/api/v1/items?type=found", data=item_form(), headers=finder)
    client.post("/internal/tick", headers=TICK)
    match = client.get(f"/api/v1/items/{lost['id']}/matches", headers=owner).json()["matches"][0]

    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        json={"answer": "There is a name label inside: RIMI 221"},
        headers=owner,
    )
    assert claim.status_code == 201, claim.text
    assert claim.json()["status"] == "pending"
    duplicate = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        json={"answer": "There is a name label inside: RIMI 221"},
        headers=owner,
    )
    assert duplicate.status_code == 409

    make_admin(app)
    admin = auth_header(client, email="desk@diu.edu.bd", password="admin-password-123")
    queue = client.get("/api/v1/admin/claims", headers=admin)
    assert queue.status_code == 200
    [pending] = queue.json()["claims"]
    assert pending["answer"].startswith("There is a name label")
    assert pending["match"]["lost_private_detail"] == "Label inside says RIMI 221"
    assert pending["match"]["text_sim"] >= 0
    assert pending["match"]["lost"]["id"] == lost["id"]
    assert pending["match"]["lost"]["category"] == "bag"
    assert pending["match"]["lost_title"] == "Blue backpack with broken zipper"
    assert queue.json()["counts"] == {
        "pending": 1,
        "approved": 0,
        "returned": 0,
        "rejected": 0,
    }

    decided = client.patch(
        f"/api/v1/admin/claims/{pending['id']}",
        json={"action": "approve", "note": "Matched the hidden label."},
        headers=admin,
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"

    from backend.app.models import Item

    with app.state.session_factory() as session:
        statuses = {
            row.status for row in session.scalars(select(Item).where(Item.id.in_([lost["id"]])))
        }
    assert statuses == {"reserved"}
    assert client.get("/api/v1/admin/claims", headers=admin).json()["counts"] == {
        "pending": 0,
        "approved": 1,
        "returned": 0,
        "rejected": 0,
    }

    assert client.get("/api/v1/admin/claims", headers=owner).status_code == 403
