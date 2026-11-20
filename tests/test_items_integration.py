import io
from datetime import date

import pytest
from conftest import auth_header, register
from PIL import Image

pytestmark = pytest.mark.integration


def photo_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (48, 48), (18, 60, 53)).save(buffer, format="PNG")
    return buffer.getvalue()


def item_form(**overrides) -> dict:
    form = {
        "category": "bag",
        "color": "blue",
        "title": "Blue backpack near library",
        "description": "A dark blue backpack with a broken left zipper pull.",
        "location": "library",
        "event_date": date.today().isoformat(),
        "private_detail": "Owner name sticker says RIMI",
        "consent": "on",
    }
    form.update(overrides)
    return form


def create_item(client, headers, kind="lost", **overrides):
    return client.post(
        f"/api/v1/items?type={kind}",
        data=item_form(**overrides),
        headers=headers,
    )


def test_owner_sees_private_detail_and_signed_image(client):
    register(client)
    headers = auth_header(client)
    response = client.post(
        "/api/v1/items?type=found",
        data=item_form(),
        files={"image": ("photo.png", photo_bytes(), "image/png")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["private_detail"] == "Owner name sticker says RIMI"
    assert item["status"] == "active"

    image = client.get(item["image_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert image.content[:2] == b"\xff\xd8"


def test_public_views_never_include_private_detail(client):
    register(client)
    owner = auth_header(client)
    created = create_item(client, owner).json()

    register(client, email="other@diu.edu.bd")
    other = auth_header(client, email="other@diu.edu.bd")

    board = client.get("/api/v1/items", headers=other)
    assert board.status_code == 200
    assert board.json()["items"] == []
    assert "private_detail" not in board.text

    detail = client.get(f"/api/v1/items/{created['id']}", headers=other)
    assert detail.status_code == 404
    assert "private_detail" not in detail.text
    assert "RIMI" not in detail.text


def test_tampered_or_expired_media_signature_is_refused(client):
    register(client)
    headers = auth_header(client)
    response = client.post(
        "/api/v1/items?type=lost",
        data=item_form(),
        files={"image": ("photo.png", photo_bytes(), "image/png")},
        headers=headers,
    )
    url = response.json()["image_url"]

    assert client.get(url.replace("signature=", "signature=0")).status_code == 404
    expired = url.split("expires=")[1].split("&")[0]
    assert client.get(url.replace(f"expires={expired}", "expires=1")).status_code == 404


def test_owner_filters_search_and_status_counts(client):
    register(client)
    headers = auth_header(client)
    lost = create_item(client, headers, kind="lost", title="Lost blue umbrella").json()
    keys = create_item(client, headers, kind="found", category="keys", title="Found keys").json()
    archived = create_item(client, headers, kind="found", title="Old bottle").json()
    response = client.post(f"/api/v1/items/{archived['id']}/archive", headers=headers)
    assert response.status_code == 200

    active = client.get("/api/v1/items?status=active", headers=headers).json()
    assert {row["id"] for row in active["items"]} == {lost["id"], keys["id"]}
    assert active["counts"] == {"active": 2, "reserved": 0, "returned": 0, "archived": 1}

    archived_only = client.get("/api/v1/items?status=archived", headers=headers).json()
    assert [row["id"] for row in archived_only["items"]] == [archived["id"]]
    assert archived_only["total"] == 1

    searched = client.get("/api/v1/items?q=umbrella", headers=headers).json()
    assert [row["id"] for row in searched["items"]] == [lost["id"]]
    assert searched["counts"]["active"] == 2

    combined = client.get("/api/v1/items?q=found&status=active", headers=headers).json()
    assert [row["id"] for row in combined["items"]] == [keys["id"]]


def test_unknown_vocabulary_and_missing_consent_are_rejected(client):
    register(client)
    headers = auth_header(client)

    unknown = create_item(client, headers, category="spaceship")
    assert unknown.status_code == 422

    no_consent = client.post(
        "/api/v1/items?type=lost",
        data=item_form(consent=""),
        headers=headers,
    )
    assert no_consent.status_code == 422
    assert no_consent.json()["error"]["code"] == "consent_required"


def test_board_filters_and_owner_archive_lifecycle(client):
    register(client)
    headers = auth_header(client)
    lost = create_item(client, headers, kind="lost", title="Lost blue umbrella").json()
    create_item(client, headers, kind="found", category="keys", title="Found keys")

    lost_only = client.get("/api/v1/items?type=lost", headers=headers).json()["items"]
    assert [row["id"] for row in lost_only] == [lost["id"]]

    patch = client.patch(
        f"/api/v1/items/{lost['id']}",
        json={"status": "archived", "expected_revision": lost["revision"]},
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "archived"
    board_ids = [row["id"] for row in client.get("/api/v1/items", headers=headers).json()["items"]]
    assert lost["id"] in board_ids

    stale = client.patch(
        f"/api/v1/items/{lost['id']}",
        json={"status": "active", "expected_revision": lost["revision"]},
        headers=headers,
    )
    assert stale.status_code == 409


def test_another_user_cannot_change_someone_elses_item(client):
    register(client)
    owner = auth_header(client)
    created = create_item(client, owner).json()

    register(client, email="other@diu.edu.bd")
    other = auth_header(client, email="other@diu.edu.bd")
    response = client.patch(
        f"/api/v1/items/{created['id']}",
        json={"status": "archived", "expected_revision": created["revision"]},
        headers=other,
    )
    assert response.status_code == 404


def test_items_require_authentication(client):
    assert client.get("/api/v1/items").status_code == 401
    assert client.post("/api/v1/items?type=lost", data=item_form()).status_code == 401
