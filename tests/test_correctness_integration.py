from datetime import date, timedelta
from time import monotonic
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend.app.auth import create_token
from backend.app.errors import ServiceFailure
from backend.app.models import Claim, Item, Match, User, utcnow
from backend.app.processing import process_embeddings, process_matches, process_notifications

pytestmark = pytest.mark.integration
VECTOR = [1.0] + [0.0] * 767


@pytest.fixture
def records(app):
    with app.state.session_factory() as session:
        users = [
            User(
                name=f"User {i}",
                email=f"user{i}@example.com",
                password_hash="unused",
                role="admin" if i == 3 else "user",
            )
            for i in range(4)
        ]
        session.add_all(users)
        session.flush()
        items = [
            Item(
                type=kind,
                user_id=users[owner].id,
                category="bag",
                color="blue",
                brand="brand",
                title="Blue campus bag",
                description="Blue bag at the library",
                location="library",
                event_date=date(2026, 11, 1),
                private_detail="Secret label",
                consent_version="test",
                semantic_consent=True,
                consented_at=utcnow(),
                text_embedding=VECTOR,
                embedding_model="local-hash-768",
                embedding_dimensions=768,
                embedded_revision=1,
                embed_status="ready",
            )
            for kind, owner in [("lost", 0), ("found", 1), ("lost", 2)]
        ]
        session.add_all(items)
        session.commit()
        ids = [i.id for i in items]
        headers = [
            {"Authorization": f"Bearer {create_token(u.id, app.state.settings)}"} for u in users
        ]
    return ids, headers


def scan(app):
    with app.state.session_factory() as session:
        process_matches(session, app.state.settings)


def test_admin_failed_notification_list_requires_admin_and_omits_private_data(client, app, records):
    _, headers = records
    scan(app)
    with app.state.session_factory() as session:
        match = session.scalar(select(Match))
        match.notify_status = "failed"
        match.notify_last_error_code = "email_rejected"
        session.commit()
    assert client.get("/api/v1/admin/matches").status_code == 401
    assert client.get("/api/v1/admin/matches", headers=headers[0]).status_code == 403
    response = client.get("/api/v1/admin/matches?notify_status=failed", headers=headers[3])
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["notify_last_error_code"] == "email_rejected"
    assert "private_detail" not in response.text
    assert "Secret label" not in response.text


def test_claim_authorization_competition_and_pair_return(client, app, records):
    ids, headers = records
    scan(app)
    match = client.get("/api/v1/matches", headers=headers[0]).json()["items"][0]
    other = client.get("/api/v1/matches", headers=headers[2]).json()["items"][0]
    assert client.get(f"/api/v1/matches/{match['id']}", headers=headers[2]).status_code == 404
    for header in (headers[1], headers[2], headers[3]):
        response = client.post(
            "/api/v1/claims",
            headers=header,
            json={"match_id": match["id"], "answer": "My secret label"},
        )
        assert response.status_code == 404
    claims = []
    for candidate, header in ((match, headers[0]), (other, headers[2])):
        response = client.post(
            "/api/v1/claims",
            headers=header,
            json={"match_id": candidate["id"], "answer": "My secret label"},
        )
        assert response.status_code == 201, response.text
        claims.append(response.json()["id"])
    assert client.post(f"/api/v1/items/{ids[1]}/archive", headers=headers[1]).status_code == 409
    assert (
        client.patch(
            f"/api/v1/items/{ids[0]}",
            headers=headers[0],
            data={"expected_revision": 1, "private_detail": "New secret"},
        ).status_code
        == 409
    )
    review = f"/api/v1/admin/claims/{claims[0]}/review"
    assert client.post(review, headers=headers[3], json={"action": "approve"}).status_code == 200
    assert client.post(review, headers=headers[3], json={"action": "reject"}).status_code == 409
    assert client.get(f"/api/v1/matches/{other['id']}", headers=headers[2]).status_code == 404
    with app.state.session_factory() as session:
        assert session.get(Claim, UUID(claims[1])).status == "rejected"
        assert session.get(Item, ids[2]).status == "active"
    returned = client.post(f"/api/v1/admin/claims/{claims[0]}/return", headers=headers[3])
    assert returned.status_code == 200
    assert (
        client.post(f"/api/v1/admin/claims/{claims[0]}/return", headers=headers[3]).json()
        == returned.json()
    )
    with app.state.session_factory() as session:
        assert [session.get(Item, key).status for key in ids[:2]] == ["returned", "returned"]


def test_edit_revision_invalidation_and_private_edit(client, app, records):
    ids, headers = records
    scan(app)
    match = client.get("/api/v1/matches", headers=headers[0]).json()["items"][0]
    path = f"/api/v1/items/{ids[0]}"
    private = client.patch(
        path, headers=headers[0], data={"expected_revision": 1, "private_detail": "Different label"}
    )
    assert private.status_code == 200, private.text
    assert private.json()["content_revision"] == 1
    assert private.json()["embed_status"] == "ready"
    assert (
        client.patch(
            path, headers=headers[0], data={"expected_revision": 1, "title": "Another bag"}
        ).status_code
        == 409
    )
    changed = client.patch(
        path,
        headers=headers[0],
        data={"expected_revision": 2, "title": "Another blue bag", "consent": "true"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["content_revision"] == 2
    assert changed.json()["embed_status"] == "pending"
    assert changed.json()["match_pending"] is True
    assert client.get(f"/api/v1/matches/{match['id']}", headers=headers[0]).status_code == 404
    with app.state.session_factory() as session:
        assert session.get(Item, ids[0]).text_embedding is None
        assert session.get(Match, UUID(match["id"])).notify_status == "cancelled"


@pytest.mark.parametrize(
    "change",
    [
        "owner",
        "category",
        "before",
        "after",
        "status",
        "source_status",
    ],
)
def test_ineligible_pairs_never_match(app, records, change):
    ids, _ = records
    with app.state.session_factory() as session:
        lost, found, third = [session.get(Item, key) for key in ids]
        third.status = "archived"
        if change == "owner":
            found.user_id = lost.user_id
        elif change == "category":
            found.category = "keys"
        elif change == "before":
            found.event_date = lost.event_date - timedelta(days=1)
        elif change == "after":
            found.event_date = lost.event_date + timedelta(days=31)
        elif change == "status":
            found.status = "reserved"
        else:
            lost.status = "returned"
        session.commit()
        assert process_matches(session, app.state.settings) == 0
        assert session.scalar(select(Match.id)) is None


@pytest.mark.parametrize("change", ["model", "dimension", "revision", "source_revision"])
def test_semantic_incompatibility_still_allows_current_local_evidence(app, records, change):
    ids, _ = records
    app.state.settings.matching_mode = "hybrid"
    with app.state.session_factory() as session:
        lost, found, third = [session.get(Item, key) for key in ids]
        third.status = "archived"
        lost.embedding_model = found.embedding_model = "semantic-test-v1"
        if change == "model":
            found.embedding_model = "different"
        elif change == "dimension":
            found.embedding_dimensions = 128
        elif change == "revision":
            found.content_revision = 2
        else:
            lost.content_revision = 2
        session.commit()
        assert process_matches(session, app.state.settings) == 1
        match = session.scalar(select(Match))
        assert match.valid
        assert match.evidence["mode"] == "local"
        assert match.evidence["text"]["semantic"] is None
        assert match.lost_revision == lost.content_revision
        assert match.found_revision == found.content_revision


def test_scan_crash_and_budget_do_not_lose_work(app, records, monkeypatch):
    from backend.app import processing

    ids, _ = records
    original = processing.match_item

    def crash(session, item, settings):
        original(session, item, settings)
        session.flush()
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(processing, "match_item", crash)
    with app.state.session_factory() as session:
        with pytest.raises(RuntimeError):
            process_matches(session, app.state.settings)
        assert session.scalar(select(Match.id)) is None
        assert all(session.get(Item, key).match_pending for key in ids)
        assert process_matches(session, app.state.settings, budget=monotonic() - 1) == 0
        assert all(session.get(Item, key).match_pending for key in ids)
    monkeypatch.setattr(processing, "match_item", original)
    scan(app)
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Match)).all()) == 2


def test_image_failure_keeps_text_and_allows_matches(app, records):
    ids, _ = records
    with app.state.session_factory() as session:
        item = session.get(Item, ids[0])
        item.embed_status, item.text_embedding, item.embedded_revision = "pending", None, None
        item.image_path = "fake.jpg"
        session.commit()

    def fail_image(_):
        raise ServiceFailure("quota", retryable=True, retry_after=120)

    embedder = SimpleNamespace(
        model="local-hash-768", dimensions=768, embed_text=lambda _: VECTOR, embed_image=fail_image
    )
    storage = SimpleNamespace(read_bytes=lambda _: b"image")
    with app.state.session_factory() as session:
        assert process_embeddings(session, app.state.settings, embedder, storage) == 1
        item = session.get(Item, ids[0])
        assert item.text_embedding == VECTOR and item.image_embedding is None
        assert item.embedded_revision == item.content_revision
        assert item.embed_status == "pending"
        assert item.embed_next_attempt_at > utcnow() + timedelta(seconds=110)
        process_matches(session, app.state.settings)
        assert session.scalar(select(Match).where(Match.lost_id == ids[0])).image_sim is None


@pytest.mark.parametrize("replacement", ["lease", "revision"])
def test_embedding_write_is_fenced_and_network_has_no_transaction(app, records, replacement):
    ids, _ = records
    with app.state.session_factory() as session:
        item = session.get(Item, ids[0])
        item.embed_status, item.text_embedding, item.embedded_revision = "pending", None, None
        session.commit()
    new_token = uuid4()
    with app.state.session_factory() as worker:

        def embed(_):
            assert not worker.in_transaction()
            with app.state.session_factory() as concurrent:
                item = concurrent.get(Item, ids[0])
                if replacement == "lease":
                    item.embed_lease_token = new_token
                else:
                    item.content_revision += 1
                concurrent.commit()
            return VECTOR

        embedder = SimpleNamespace(model="local-hash-768", dimensions=768, embed_text=embed)
        assert process_embeddings(worker, app.state.settings, embedder, None) == 0
        item = worker.get(Item, ids[0])
        assert item.text_embedding is None
        if replacement == "lease":
            assert item.embed_lease_token == new_token


def test_permanent_embedding_failure_does_not_auto_retry(app, records):
    ids, _ = records
    with app.state.session_factory() as session:
        item = session.get(Item, ids[0])
        item.embed_status, item.text_embedding, item.embedded_revision = "pending", None, None
        session.commit()

        def fail(_):
            raise ServiceFailure("embedding_rejected")

        embedder = SimpleNamespace(model="local-hash-768", dimensions=768, embed_text=fail)
        assert process_embeddings(session, app.state.settings, embedder, None) == 1
        assert session.get(Item, ids[0]).embed_status == "failed"
        assert process_embeddings(session, app.state.settings, embedder, None) == 0


def test_notification_lease_fencing_and_invalid_cancellation(app, records):
    scan(app)
    with app.state.session_factory() as session:
        matches = session.scalars(select(Match).order_by(Match.id)).all()
        first_id = matches[0].id
        matches[1].valid = False
        session.commit()
    new_token = uuid4()
    calls = []
    with app.state.session_factory() as worker:

        def send(*args, **kwargs):
            assert not worker.in_transaction()
            calls.append(args)
            with app.state.session_factory() as concurrent:
                match = concurrent.get(Match, first_id)
                match.notify_lease_token = new_token
                concurrent.commit()

        assert (
            process_notifications(worker, app.state.settings, SimpleNamespace(send_match=send)) == 0
        )
        assert len(calls) == 1
        match = worker.get(Match, first_id)
        assert match.notify_lease_token == new_token
        assert match.notified_at is None


def test_owner_only_lists_and_admin_pagination(client, records):
    ids, headers = records
    for query in ("", "?mine=false", "?mine=true"):
        result = client.get(f"/api/v1/items{query}", headers=headers[0]).json()
        assert [row["id"] for row in result["items"]] == [str(ids[0])]
        assert result["total"] == 1
    assert client.get(f"/api/v1/items/{ids[1]}", headers=headers[0]).status_code == 404
    assert client.get("/api/v1/admin/items", headers=headers[0]).status_code == 403
    result = client.get("/api/v1/admin/items?limit=1&offset=1", headers=headers[3]).json()
    assert len(result["items"]) == 1 and result["total"] == 3


def test_concurrent_approvals_only_reserve_one_lost_report(client, app, records):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    ids, headers = records
    scan(app)
    claims = []
    for header in (headers[0], headers[2]):
        match = client.get("/api/v1/matches", headers=header).json()["items"][0]
        response = client.post(
            "/api/v1/claims",
            headers=header,
            json={"match_id": match["id"], "answer": "My secret label"},
        )
        claims.append(response.json()["id"])
    barrier = Barrier(2)

    def approve(claim):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v1/admin/claims/{claim}/review", headers=headers[3], json={"action": "approve"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve, claims)) == [200, 409]
    with app.state.session_factory() as session:
        assert sorted(session.scalars(select(Claim.status)).all()) == ["approved", "rejected"]
        assert sorted(session.get(Item, key).status for key in (ids[0], ids[2])) == [
            "active",
            "reserved",
        ]


def test_embedding_skip_locked_and_expired_lease_reclaim(app, records):
    ids, _ = records
    with app.state.session_factory() as session:
        item = session.get(Item, ids[0])
        item.embed_status, item.text_embedding, item.embedded_revision = "processing", None, None
        item.embed_lease_token = uuid4()
        item.embed_lease_until = utcnow() - timedelta(seconds=1)
        session.commit()
    embedder = SimpleNamespace(model="local-hash-768", dimensions=768, embed_text=lambda _: VECTOR)
    with app.state.session_factory() as locked, app.state.session_factory() as worker:
        locked.scalar(select(Item).where(Item.id == ids[0]).with_for_update())
        assert process_embeddings(worker, app.state.settings, embedder, None) == 0
        locked.rollback()
        assert process_embeddings(worker, app.state.settings, embedder, None) == 1
        item = worker.get(Item, ids[0])
        assert item.embed_status == "ready" and item.embed_lease_token is None


def test_candidate_image_authorization_and_no_store(client, app, records):
    ids, headers = records
    with app.state.session_factory() as session:
        session.get(Item, ids[1]).image_path = f"{uuid4()}/{uuid4().hex}.jpg"
        session.commit()
    path = f"/api/v1/items/{ids[1]}/image"
    assert client.get(path, headers=headers[0]).status_code == 404
    scan(app)
    response = client.get(path, headers=headers[0])
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["expires_in"] == 300
    assert client.get(f"/api/v1/items/{ids[1]}", headers=headers[0]).status_code == 404


def test_rejected_claim_cannot_be_resubmitted(client, app, records):
    _, headers = records
    scan(app)
    match = client.get("/api/v1/matches", headers=headers[0]).json()["items"][0]
    payload = {"match_id": match["id"], "answer": "My secret label"}
    claim = client.post("/api/v1/claims", headers=headers[0], json=payload).json()
    assert (
        client.post(
            f"/api/v1/admin/claims/{claim['id']}/review",
            headers=headers[3],
            json={"action": "reject", "review_note": "Evidence differs"},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/claims", headers=headers[0], json=payload).status_code == 409
    assert (
        client.get(f"/api/v1/matches/{match['id']}", headers=headers[0]).json()["can_claim"]
        is False
    )


def test_multipart_create_date_validation_and_size_bound(client, records):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from test_items_integration import item_form

    _, headers = records
    response = client.post(
        "/api/v1/items", headers=headers[0], data={**item_form(), "type": "lost"}
    )
    assert response.status_code == 201, response.text
    tomorrow = datetime.now(ZoneInfo("Asia/Dhaka")).date() + timedelta(days=1)
    response = client.post(
        "/api/v1/items",
        headers=headers[0],
        data={**item_form(event_date=tomorrow.isoformat()), "type": "lost"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"][0]["field"] == "event_date"
    response = client.post(
        "/api/v1/items?type=lost",
        headers=headers[0],
        data=item_form(),
        files={"image": ("huge.png", b"x" * (6 * 1024 * 1024), "image/png")},
    )
    assert response.status_code == 413, response.text


def test_failed_image_replacement_keeps_original(client, app, records, monkeypatch):
    from test_items_integration import photo_bytes

    ids, headers = records
    old_key = f"{uuid4()}/{uuid4().hex}.jpg"
    with app.state.session_factory() as session:
        session.get(Item, ids[0]).image_path = old_key
        session.commit()

    def fail_upload(*args):
        raise ServiceFailure("storage_unavailable")

    monkeypatch.setattr(app.state.storage, "put", fail_upload)
    response = client.patch(
        f"/api/v1/items/{ids[0]}",
        headers=headers[0],
        data={"expected_revision": 1, "consent": "true"},
        files={"image": ("image.png", photo_bytes(), "image/png")},
    )
    assert response.status_code == 503
    with app.state.session_factory() as session:
        item = session.get(Item, ids[0])
        assert item.image_path == old_key and item.revision == 1


def test_notification_retries_and_admin_retry_routes(client, app, records):
    ids, headers = records
    scan(app)
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise ServiceFailure("email_unavailable", retryable=True, retry_after=300)

    with app.state.session_factory() as session:
        assert (
            process_notifications(session, app.state.settings, SimpleNamespace(send_match=fail))
            == 0
        )
        match = session.scalar(select(Match).where(Match.lost_id == ids[0]))
        assert match.notify_status == "pending" and match.notify_attempts == 1
        assert match.notify_next_attempt_at > utcnow() + timedelta(seconds=290)
        assert (
            process_notifications(session, app.state.settings, SimpleNamespace(send_match=fail))
            == 0
        )
        assert len(calls) == 2
        match.notify_status = "failed"
        match_id = match.id
        item = session.get(Item, ids[0])
        item.embed_status = "failed"
        session.commit()
    for path in (f"/api/v1/admin/items/{ids[0]}/retry", f"/api/v1/admin/matches/{match_id}/retry"):
        assert client.post(path, headers=headers[0]).status_code == 403
        assert client.post(path, headers=headers[3]).status_code == 200
        assert client.post(path, headers=headers[3]).status_code == 409


def test_no_resend_after_recalculation_and_below_threshold_cancels_lease(app, records):
    ids, _ = records
    scan(app)
    with app.state.session_factory() as session:
        match = session.scalar(select(Match).where(Match.lost_id == ids[0]))
        match.notify_status = "sent"
        match.notified_at = utcnow()
        session.get(Item, ids[0]).match_pending = True
        session.commit()
        assert process_matches(session, app.state.settings) == 0
        assert match.notify_status == "sent"
        match.notify_status = "processing"
        match.notified_at = None
        match.notify_lease_token = uuid4()
        match.notify_lease_until = utcnow() + timedelta(minutes=2)
        item = session.get(Item, ids[0])
        item.title = "Red umbrella"
        item.description = "Large circular canopy"
        item.color, item.brand, item.location = "red", "different", "mosque"
        item.match_pending = True
        session.commit()
        process_matches(session, app.state.settings)
        session.refresh(match)
        assert match.valid is False and match.notify_status == "cancelled"
        assert match.notify_lease_token is None
