import io
import json
from datetime import date

import pytest
from PIL import Image, ImageDraw


def test_bengali_tokens_preserve_vowel_marks_and_normalize_digits():
    from backend.app.text_features import tokens

    assert tokens("নীল ব্যাগ ৫০২") == ["blue", "bag", "502"]


def test_normalization_removes_report_boilerplate_but_keeps_negation():
    from backend.app.text_features import tokens

    assert tokens("I found a BLACK bag, with no sticker!") == ["black", "bag", "no", "sticker"]


@pytest.mark.parametrize("text", ["", "  !  ", "I lost an item at the campus"])
def test_empty_or_boilerplate_text_has_no_agreement(text):
    from backend.app.text_features import text_similarity

    result = text_similarity({"title": text}, {"title": text})
    assert result["score"] == 0
    assert result["shared_terms"] == []


def test_bilingual_synonyms_match_without_hosted_embeddings():
    from backend.app.text_features import text_similarity

    left = {"title": "কালো ফোন সাদা স্টিকার"}
    right = {"title": "black mobile white sticker"}
    assert text_similarity(left, right)["score"] == 1
    assert text_similarity(left, right, synonyms=False)["score"] < 0.1


def test_character_trigrams_handle_a_typo_without_matching_an_unrelated_item():
    from backend.app.text_features import text_similarity

    query = {"title": "blue backpack zipper"}
    close = {"title": "blue backpak zipper"}
    other = {"title": "red umbrella stars"}
    assert text_similarity(query, close)["score"] > 0.6
    assert text_similarity(query, close)["score"] > text_similarity(query, other)["score"]


def test_generic_short_description_cannot_alone_be_a_strong_match():
    from backend.app.text_features import text_similarity

    result = text_similarity(
        {"title": "bag"},
        {"title": "blue backpack", "description": "three pockets broken zipper white sticker"},
    )
    assert 0 < result["score"] < 0.65


def test_only_public_text_is_used_and_shared_terms_are_capped():
    from backend.app.text_features import text_similarity

    left = {
        "title": "blue bag two pockets",
        "description": "zipper strap sticker canvas rounded small front silver dark",
        "brand": "not-a-text-input",
        "private_detail": "PRIVATE-SECRET-LABEL-221",
        "match_group_id": "truth-not-a-feature",
    }
    right = {**left, "private_detail": "different-secret", "match_group_id": "different-label"}
    result = text_similarity(left, right)
    assert result["score"] == 1
    assert len(result["shared_terms"]) == 8
    assert "secret" not in json.dumps(result).lower()
    assert "truth" not in json.dumps(result)
    assert "not-a-text-input" not in json.dumps(result)


def test_jaro_winkler_distinguishes_brand_typos_from_different_brands():
    from backend.app.text_features import jaro_winkler

    assert jaro_winkler("samsung", "samsung") == 1
    assert jaro_winkler("samsung", "samsng") > 0.9
    assert jaro_winkler("samsung", "nokia") < 0.6
    assert jaro_winkler("", "") == 0


def test_attributes_give_conservative_credit_for_shades_typos_and_academic_zone():
    from backend.app.attributes import attribute_score

    left = {
        "color": "navy",
        "brand": "Samsung",
        "location": "library",
        "event_date": date(2026, 11, 1),
    }
    right = {
        "color": "blue",
        "brand": "Samsng",
        "location": "classroom",
        "event_date": date(2026, 11, 1),
    }
    assert 0.7 < attribute_score(left, right) < 1
    right.update(color="white", brand="Nokia", location="mosque")
    assert attribute_score(left, right) == 0.1


def picture(color="blue", size=(160, 160)):
    image = Image.new("RGB", size, "#e8e1cf")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((45, 30, 115, 145), radius=15, fill=color)
    draw.rectangle((55, 70, 90, 83), fill="white")
    output = io.BytesIO()
    image.save(output, "JPEG", quality=88)
    return output.getvalue()


def test_image_features_are_compact_and_identical_images_agree():
    from backend.app.image_features import image_features, image_similarity

    features = image_features(picture())
    assert len(features["dhash"]) == len(features["ahash"]) == 16
    assert sum(features["histogram"]) == pytest.approx(1)
    result = image_similarity(features, features)
    assert result["score"] == 1
    assert result["dhash_distance"] == result["ahash_distance"] == 0


def test_image_compression_and_resize_keep_similarity():
    from backend.app.image_features import image_features, image_similarity

    raw = picture()
    image = Image.open(io.BytesIO(raw)).resize((240, 240))
    output = io.BytesIO()
    image.save(output, "JPEG", quality=55)
    result = image_similarity(image_features(raw), image_features(output.getvalue()))
    assert result["score"] > 0.9


def test_colour_histogram_can_be_ablated_without_false_uniform_hash_evidence():
    from backend.app.image_features import image_features, image_similarity

    features = image_features(picture())
    assert image_similarity(features, features, histogram=False)["score"] == 1
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, "JPEG")
    flat = image_features(output.getvalue())
    assert image_similarity(flat, flat, histogram=False) is None
    assert image_similarity(flat, flat) is None


def test_uniform_images_do_not_get_false_hash_agreement():
    from backend.app.image_features import image_features, image_similarity

    features = []
    for color in ("black", "white", "red", "blue"):
        output = io.BytesIO()
        Image.new("RGB", (32, 32), color).save(output, "JPEG")
        features.append(image_features(output.getvalue()))
    assert image_similarity(features[0], features[1]) is None
    assert image_similarity(features[2], features[3]) is None
    assert image_similarity(features[0], features[0]) is None
    assert image_similarity(features[2], features[2]) is None


@pytest.mark.parametrize("value", [-1, float("nan")])
def test_invalid_image_histogram_is_rejected(value):
    from backend.app.image_features import image_features, image_similarity

    features = image_features(picture())
    invalid = {**features, "histogram": [value] * len(features["histogram"])}
    with pytest.raises(ValueError):
        image_similarity(features, invalid)
