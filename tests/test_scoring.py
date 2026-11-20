from datetime import date

import pytest


def test_attribute_score_weights_exact_matches():
    from backend.app.attributes import attribute_score

    lost = {
        "color": "Blue",
        "brand": " ACME ",
        "location": "Library",
        "event_date": date(2026, 11, 10),
    }
    found = {
        "color": "blue",
        "brand": "acme",
        "location": "library",
        "event_date": date(2026, 11, 12),
    }
    assert attribute_score(lost, found, date_window=30) == pytest.approx(0.9933333333)


def test_missing_attributes_are_not_agreements():
    from backend.app.attributes import attribute_score

    report = {
        "color": "unknown",
        "brand": None,
        "location": "unknown",
        "event_date": date(2026, 11, 10),
    }
    assert attribute_score(report, report, date_window=30) == 0.1


def test_cosine_rejects_bad_vectors():
    from backend.app.attributes import cosine

    with pytest.raises(ValueError):
        cosine([1.0, float("nan")], [1.0, 0.0])
    with pytest.raises(ValueError):
        cosine([0.0, 0.0], [1.0, 0.0])
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 0.0])


def test_score_pair_reweights_when_images_are_missing():
    from backend.app.matcher import score_pair

    lost = {
        "title": "Blue bag",
        "description": "White sticker",
        "text_embedding": [1.0, 0.0],
        "image_embedding": None,
        "color": "blue",
        "brand": "x",
        "location": "library",
        "event_date": date(2026, 11, 10),
    }
    found = {
        "title": "Blue bag",
        "description": "White sticker",
        "text_embedding": [1.0, 0.0],
        "image_embedding": None,
        "color": "blue",
        "brand": "x",
        "location": "library",
        "event_date": date(2026, 11, 10),
    }
    result = score_pair(lost, found, date_window=30)
    assert result["text_sim"] == result["attr_score"] == result["score"] == 1.0
    assert result["image_sim"] is None
    assert result["evidence"]["weights"] == {"text": 0.6, "image": 0.0, "attributes": 0.4}


def public_report(**changes):
    return {
        "title": "Blue bag white sticker",
        "description": "Broken left zipper",
        "color": "blue",
        "brand": "acme",
        "location": "library",
        "event_date": date(2026, 11, 1),
        **changes,
    }


def test_local_scoring_works_without_any_vectors():
    from backend.app.matcher import score_pair

    result = score_pair(public_report(), public_report())
    assert result["score"] == 1
    assert result["evidence"]["mode"] == "local"
    assert result["evidence"]["text"]["semantic"] is None


def test_hybrid_blends_comparable_vectors_but_local_evidence_dominates():
    from backend.app.matcher import score_pair

    metadata = {"embedding_model": "semantic-test-v1", "embedding_dimensions": 2}
    result = score_pair(
        public_report(**metadata, text_embedding=[1.0, 0.0]),
        public_report(**metadata, text_embedding=[0.0, 1.0]),
        mode="hybrid",
    )
    assert result["text_sim"] == pytest.approx(0.65)
    assert result["score"] == pytest.approx(0.79)
    assert result["evidence"]["mode"] == "hybrid"


@pytest.mark.parametrize("problem", ["model", "dimensions", "revision", "invalid", "hashed"])
def test_unusable_semantic_vectors_never_block_or_pollute_local_scoring(problem):
    from backend.app.matcher import score_pair

    left = public_report(
        text_embedding=[1.0, 0.0], embedding_model="semantic-test-v1", embedding_dimensions=2
    )
    right = dict(left)
    if problem == "model":
        right["embedding_model"] = "different"
    elif problem == "dimensions":
        right["embedding_dimensions"] = 3
    elif problem == "revision":
        right.update(content_revision=2, embedded_revision=1)
    elif problem == "invalid":
        right["text_embedding"] = [float("nan"), 1.0]
    else:
        left["embedding_model"] = right["embedding_model"] = "local-hash-2"
    result = score_pair(left, right, mode="hybrid")
    assert result["score"] == 1
    assert result["evidence"]["mode"] == "local"
    assert result["evidence"]["text"]["semantic"] is None


def test_local_image_evidence_uses_paired_images_and_renormalizes_missing_images():
    from test_local_features import picture

    from backend.app.image_features import image_features
    from backend.app.matcher import score_pair

    report = public_report(image_features=image_features(picture()))
    result = score_pair(report, report)
    assert result["image_sim"] == 1
    assert result["score"] == 1
    assert result["evidence"]["weights"] == {"text": 0.45, "image": 0.25, "attributes": 0.3}
    assert score_pair(report, public_report())["image_sim"] is None
