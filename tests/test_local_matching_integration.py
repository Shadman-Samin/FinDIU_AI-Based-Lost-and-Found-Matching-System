from types import SimpleNamespace
from uuid import UUID

import pytest
from conftest import auth_header, register
from pydantic import SecretStr
from sqlalchemy import select
from test_local_features import picture
from test_matching_integration import TICK, item_form, make_admin

from backend.app.errors import ServiceFailure
from backend.app.models import Claim, Item, Match
from backend.app.processing import process_embeddings

pytestmark = pytest.mark.integration


def pair(client, images=False, semantic=False):
    register(client)
    owner = auth_header(client)
    register(client, email="finder@diu.edu.bd")
    finder = auth_header(client, email="finder@diu.edu.bd")
    reports = []
    for kind, headers in (("lost", owner), ("found", finder)):
        response = client.post(
            f"/api/v1/items?type={kind}",
            data=item_form(brand="Acme", semantic_consent=str(semantic).lower()),
            files={"image": ("photo.jpg", picture(), "image/jpeg")} if images else None,
            headers=headers,
        )
        assert response.status_code == 201, response.text
        reports.append(response.json())
    return reports, owner


def test_local_tick_never_builds_a_hashed_or_hosted_provider(client, app, monkeypatch):
    from backend.app import providers

    def forbidden(*args):
        raise AssertionError("Local matching must not instantiate an embedding provider")

    monkeypatch.setattr(providers, "LocalEmbedder", forbidden)
    monkeypatch.setattr(providers, "GeminiEmbedder", forbidden)
    reports, owner = pair(client)
    response = client.post("/internal/tick", headers=TICK)
    assert response.status_code == 200, response.text
    assert response.json()["embedded"] == 0
    assert response.json()["matches_created"] == 1
    [match] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()["items"]
    assert match["evidence"]["mode"] == "local"
    assert match["evidence"]["text"]["local"] == 1
    assert "RIMI" not in str(match["evidence"])
    with app.state.session_factory() as session:
        assert all(row.text_embedding is None for row in session.scalars(select(Item)))


def test_hybrid_mode_without_a_key_still_matches_locally(client, app):
    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    reports, owner = pair(client)
    response = client.post("/internal/tick", headers=TICK)
    assert response.status_code == 200, response.text
    assert response.json()["matches_created"] == 1
    [match] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()["items"]
    assert match["evidence"]["mode"] == "local"


def test_permanent_semantic_failure_does_not_block_matching(client, app):
    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    app.state.settings.gemini_api_key = SecretStr("test-provider-key")

    def fail(_):
        raise ServiceFailure("embedding_rejected")

    app.state.embedder = SimpleNamespace(model="semantic-test", dimensions=768, embed_text=fail)
    reports, owner = pair(client, semantic=True)
    response = client.post("/internal/tick", headers=TICK)
    assert response.status_code == 200, response.text
    assert response.json()["matches_created"] == 1
    assert (
        client.get(f"/api/v1/items/{reports[0]['id']}", headers=owner).json()["embed_status"]
        == "failed"
    )
    [match] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()["items"]
    assert match["evidence"]["mode"] == "local"


def test_image_features_are_stored_but_not_exposed_and_removal_clears_them(client, app):
    reports, owner = pair(client, images=True)
    assert "image_features" not in reports[0]
    with app.state.session_factory() as session:
        item = session.get(Item, UUID(reports[0]["id"]))
        assert item.feature_version == 1
        assert item.image_features["dhash"]
    client.post("/internal/tick", headers=TICK)
    [match] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()["items"]
    assert match["image_sim"] == 1
    assert "image_features" not in str(match)
    removed = client.patch(
        f"/api/v1/items/{reports[0]['id']}",
        data={"expected_revision": 1, "consent": "true", "remove_image": "true"},
        headers=owner,
    )
    assert removed.status_code == 200, removed.text
    with app.state.session_factory() as session:
        item = session.get(Item, UUID(reports[0]["id"]))
        assert item.image_features is None and item.image_path is None
    client.post("/internal/tick", headers=TICK)
    [match] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()["items"]
    assert match["image_sim"] is None


def test_enabling_gemini_never_sends_reports_with_only_local_consent(client, app):
    reports, owner = pair(client)
    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    app.state.settings.gemini_api_key = SecretStr("test-provider-key")

    def forbidden(_):
        raise AssertionError("External processing requires this report's explicit consent")

    app.state.embedder = SimpleNamespace(
        model="semantic-test", dimensions=768, embed_text=forbidden
    )
    with app.state.session_factory() as session:
        for item in session.scalars(select(Item)):
            item.embed_status = "pending"
        session.commit()
    response = client.post("/internal/tick", headers=TICK)
    assert response.status_code == 200
    assert response.json()["embedded"] == 0
    assert response.json()["matches_created"] == 1
    assert (
        client.get(f"/api/v1/items/{reports[0]['id']}", headers=owner).json()["semantic_consent"]
        is False
    )


def test_explicit_semantic_consent_allows_optional_hybrid_evidence(client, app):
    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    app.state.settings.gemini_api_key = SecretStr("test-provider-key")
    app.state.embedder = SimpleNamespace(
        model="semantic-test", dimensions=768, embed_text=lambda _: [1.0] + [0.0] * 767
    )
    reports, owner = pair(client, semantic=True)
    assert reports[0]["semantic_consent"] is True
    response = client.post("/internal/tick", headers=TICK)
    assert response.status_code == 200
    assert response.json()["embedded"] == 2
    [match] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()["items"]
    assert match["evidence"]["mode"] == "hybrid"
    assert match["evidence"]["text"]["semantic"] == 1


def test_revoking_semantic_consent_stops_remaining_image_processing(client, app):
    from backend.app.processing import process_embeddings

    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    app.state.settings.gemini_api_key = SecretStr("test-provider-key")
    reports, owner = pair(client, images=True, semantic=True)
    image_calls = []

    def embed_text(_):
        revoked = client.patch(
            f"/api/v1/items/{reports[0]['id']}",
            headers=owner,
            data={"expected_revision": 1, "semantic_consent": "false", "consent": "true"},
        )
        assert revoked.status_code == 200
        return [1.0] + [0.0] * 767

    def embed_image(raw):
        image_calls.append(raw)
        return [1.0] + [0.0] * 767

    embedder = SimpleNamespace(
        model="semantic-test", dimensions=768, embed_text=embed_text, embed_image=embed_image
    )
    with app.state.session_factory() as session:
        assert (
            process_embeddings(session, app.state.settings, embedder, app.state.storage, limit=1)
            == 0
        )
        assert image_calls == []
        item = session.get(Item, UUID(reports[0]["id"]))
        assert not item.semantic_consent and item.text_embedding is None


def test_text_is_not_sent_after_consent_revoked_between_claim_and_embedding(
    client, app, monkeypatch
):
    from backend.app import processing

    reports, owner = pair(client, semantic=True)
    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    app.state.settings.gemini_api_key = SecretStr("test-provider-key")
    original = processing._embedding_authorized
    calls = []

    def revoke_then_authorize(session, item_id, token, revision):
        calls.append(item_id)
        item = session.get(Item, UUID(reports[0]["id"]))
        item.semantic_consent = False
        session.commit()
        return original(session, item_id, token, revision)

    def forbidden(_):
        raise AssertionError("Public text must not be transmitted after consent withdrawal")

    monkeypatch.setattr(processing, "_embedding_authorized", revoke_then_authorize)
    app.state.embedder = SimpleNamespace(
        model="semantic-test", dimensions=768, embed_text=forbidden
    )
    with app.state.session_factory() as session:
        assert (
            process_embeddings(
                session, app.state.settings, app.state.embedder, app.state.storage, limit=1
            )
            == 0
        )
        assert session.get(Item, UUID(reports[0]["id"])).text_embedding is None
    assert calls


def test_non_owner_edit_preserves_owner_external_consent(client, app):
    reports, owner = pair(client, semantic=True)
    make_admin(app)
    admin = auth_header(client, email="desk@diu.edu.bd", password="admin-password-123")
    response = client.patch(
        f"/api/v1/items/{reports[0]['id']}",
        headers=admin,
        data={"expected_revision": 1, "consent": "true", "title": "Admin edited title"},
    )
    assert response.status_code == 200, response.text
    assert (
        client.get(f"/api/v1/items/{reports[0]['id']}", headers=owner).json()["semantic_consent"]
        is True
    )


def test_owner_consent_is_honored_when_external_ai_is_enabled_later(client, app):
    reports, owner = pair(client, semantic=True)
    with app.state.session_factory() as session:
        assert session.get(Item, UUID(reports[0]["id"])).embed_status == "pending"
    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    app.state.settings.gemini_api_key = SecretStr("test-provider-key")
    app.state.embedder = SimpleNamespace(
        model="semantic-test", dimensions=768, embed_text=lambda _: [1.0] + [0.0] * 767
    )
    assert client.post("/internal/tick", headers=TICK).status_code == 200
    assert (
        client.get(f"/api/v1/items/{reports[0]['id']}", headers=owner).json()["embed_status"]
        == "ready"
    )


def test_metadata_reports_processing_scope_but_never_keys(client, app):
    local = client.get("/api/v1/metadata").json()
    assert local["matching_mode"] == "local" and local["semantic_enabled"] is False
    app.state.settings.matching_mode = "hybrid"
    app.state.settings.embedding_provider = "gemini"
    app.state.settings.gemini_api_key = SecretStr("test-provider-key")
    response = client.get("/api/v1/metadata")
    assert response.json()["semantic_enabled"] is True
    assert "test-provider-key" not in response.text


def test_administrator_cannot_grant_external_consent_for_another_owner(client, app):
    reports, owner = pair(client)
    make_admin(app)
    admin = auth_header(client, email="desk@diu.edu.bd", password="admin-password-123")
    response = client.patch(
        f"/api/v1/items/{reports[0]['id']}",
        headers=admin,
        data={"expected_revision": 1, "consent": "true", "semantic_consent": "true"},
    )
    assert response.status_code == 403
    assert (
        client.get(f"/api/v1/items/{reports[0]['id']}", headers=owner).json()["semantic_consent"]
        is False
    )


def test_claim_score_snapshot_survives_a_scoring_upgrade(client, app):
    reports, owner = pair(client)
    client.post("/internal/tick", headers=TICK)
    [original] = client.get(f"/api/v1/items/{reports[0]['id']}/matches", headers=owner).json()[
        "items"
    ]
    claimed = client.post(
        f"/api/v1/matches/{original['id']}/claims",
        json={"answer": "Hidden owner label"},
        headers=owner,
    )
    assert claimed.status_code == 201
    app.state.settings.match_threshold = 1
    with app.state.session_factory() as session:
        match = session.get(Match, UUID(original["id"]))
        match.scoring_version = "historical-test"
        for item in session.scalars(select(Item)):
            item.match_pending = True
        session.commit()
    client.post("/internal/tick", headers=TICK)
    updated = client.get(f"/api/v1/matches/{original['id']}", headers=owner).json()
    assert updated["id"] == original["id"]
    assert updated["evidence"] == original["evidence"]
    assert updated["threshold"] == original["threshold"]
    assert updated["scoring_version"] == "historical-test"
    make_admin(app)
    admin = auth_header(client, email="desk@diu.edu.bd", password="admin-password-123")
    assert (
        client.post(
            f"/api/v1/admin/claims/{claimed.json()['id']}/review",
            json={"action": "approve"},
            headers=admin,
        ).status_code
        == 200
    )
    with app.state.session_factory() as session:
        assert session.get(Claim, UUID(claimed.json()["id"])).status == "approved"


def test_backfill_is_idempotent_and_storage_reads_have_no_transaction(client, app, monkeypatch):
    from backend.app.processing import backfill_features

    reports, _ = pair(client, images=True)
    with app.state.session_factory() as session:
        for item in session.scalars(select(Item)):
            item.feature_version = 0
            item.image_features = None
            item.match_pending = False
        session.commit()
        original_read = app.state.storage.read_bytes

        def read(key):
            assert not session.in_transaction()
            return original_read(key)

        monkeypatch.setattr(app.state.storage, "read_bytes", read)
        assert backfill_features(session, app.state.storage) == {"processed": 2, "failed": 0}
        assert backfill_features(session, app.state.storage) == {"processed": 0, "failed": 0}
        for report in reports:
            item = session.get(Item, UUID(report["id"]))
            assert item.feature_version == 1 and item.image_features is not None
            assert item.match_pending and item.revision == 1


def test_backfill_cannot_write_features_after_a_concurrent_edit(client, app, monkeypatch):
    from backend.app.processing import backfill_features

    reports, _ = pair(client, images=True)
    key = UUID(reports[0]["id"])
    with app.state.session_factory() as session:
        item = session.get(Item, key)
        item.feature_version = 0
        item.image_features = None
        session.commit()
    original_read = app.state.storage.read_bytes

    def read(path):
        with app.state.session_factory() as concurrent:
            item = concurrent.get(Item, key)
            item.content_revision += 1
            concurrent.commit()
        return original_read(path)

    monkeypatch.setattr(app.state.storage, "read_bytes", read)
    with app.state.session_factory() as session:
        assert backfill_features(session, app.state.storage) == {"processed": 0, "failed": 0}
        assert session.get(Item, key).image_features is None
