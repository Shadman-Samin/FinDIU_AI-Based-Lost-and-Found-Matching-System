"""Local-first fusion. Optional semantic vectors never gate candidate eligibility."""

import math

from backend.app.attributes import ATTRIBUTE_WEIGHTS, attribute_components, cosine
from backend.app.image_features import FEATURE_VERSION, image_similarity
from backend.app.text_features import TEXT_WEIGHTS, text_similarity

SCORING_VERSION = "2.0-local-hybrid"


def _semantic(lost, found, field, allow_hashed=False):
    model, dimensions = lost.get("embedding_model"), lost.get("embedding_dimensions")
    if (
        not model
        or model != found.get("embedding_model")
        or (model.startswith("local-hash-") and not allow_hashed)
        or not isinstance(dimensions, int)
        or dimensions != found.get("embedding_dimensions")
    ):
        return None
    for report in (lost, found):
        vector = report.get(field)
        if (
            (
                "content_revision" in report
                and report.get("embedded_revision") != report["content_revision"]
            )
            or not isinstance(vector, list)
            or len(vector) != dimensions
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in vector
            )
        ):
            return None
    try:
        return cosine(lost[field], found[field])
    except ValueError:
        return None


def _blend(local, semantic):
    if semantic is None:
        return local, {"local": 1.0, "semantic": 0.0}
    if local is None:
        return max(0.0, semantic), {"local": 0.0, "semantic": 1.0}
    return 0.65 * local + 0.35 * max(0.0, semantic), {"local": 0.65, "semantic": 0.35}


def score_pair(
    lost,
    found,
    date_window: int = 30,
    *,
    mode="local",
    synonyms=True,
    images=True,
    location_zones=True,
    color_histogram=True,
) -> dict:
    if mode not in {"local", "hybrid", "semantic"}:
        raise ValueError("Unknown matching mode")
    semantic_text = (
        _semantic(lost, found, "text_embedding", mode == "semantic") if mode != "local" else None
    )
    semantic_image = (
        _semantic(lost, found, "image_embedding", mode == "semantic")
        if mode != "local" and images
        else None
    )
    if mode == "semantic" and semantic_text is None:
        raise ValueError("Semantic baseline requires comparable current text vectors")
    lexical = text_similarity(lost, found, synonyms) if mode != "semantic" else None
    perceptual = (
        image_similarity(
            lost.get("image_features"), found.get("image_features"), histogram=color_histogram
        )
        if mode != "semantic" and images
        else None
    )
    text_sim, text_weights = _blend(
        lexical["score"] if lexical is not None else None, semantic_text
    )
    image_sim, image_weights = _blend(
        perceptual["score"] if perceptual is not None else None, semantic_image
    )
    details = attribute_components(lost, found, date_window, location_zones=location_zones)
    attributes = round(sum(weight * details[key] for key, weight in ATTRIBUTE_WEIGHTS.items()), 10)
    weights = (
        {"text": 0.6, "image": 0.0, "attributes": 0.4}
        if image_sim is None
        else {"text": 0.45, "image": 0.25, "attributes": 0.3}
    )
    score = (
        weights["text"] * max(0.0, text_sim)
        + weights["image"] * (image_sim or 0.0)
        + weights["attributes"] * attributes
    )
    return {
        "text_sim": round(text_sim, 10),
        "image_sim": round(image_sim, 10) if image_sim is not None else None,
        "attr_score": attributes,
        "score": round(score, 10),
        "evidence": {
            "mode": "semantic"
            if mode == "semantic"
            else "hybrid"
            if semantic_text is not None or semantic_image is not None
            else "local",
            "feature_version": FEATURE_VERSION,
            "scoring_version": SCORING_VERSION,
            "weights": weights,
            "text": {
                "local": lexical["score"] if lexical is not None else None,
                "semantic": semantic_text,
                "weights": text_weights,
                "lexical": {**lexical, "weights": TEXT_WEIGHTS} if lexical is not None else None,
            },
            "image": {
                "local": perceptual["score"] if perceptual is not None else None,
                "semantic": semantic_image,
                "weights": image_weights,
                "perceptual": perceptual,
            }
            if image_sim is not None
            else None,
            "attributes": {**details, "weights": ATTRIBUTE_WEIGHTS},
        },
    }
