"""Compact perceptual evidence extracted once from sanitized report images."""

import io
import math

from PIL import Image, UnidentifiedImageError

from backend.app.errors import ServiceFailure
from backend.app.image_utils import MAX_PIXELS

FEATURE_VERSION = 1
IMAGE_WEIGHTS = {"dhash": 0.45, "ahash": 0.20, "histogram": 0.35}


def image_features(jpeg: bytes) -> dict:
    try:
        with Image.open(io.BytesIO(jpeg)) as source:
            if source.width * source.height > MAX_PIXELS or getattr(source, "is_animated", False):
                raise ServiceFailure("invalid_image")
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise ServiceFailure("invalid_image") from None
    grey = image.convert("L")
    pixels = grey.resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    dhash = 0
    for y in range(8):
        for x in range(8):
            dhash = (dhash << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    pixels = grey.resize((8, 8), Image.Resampling.LANCZOS).tobytes()
    average = sum(pixels) / 64
    ahash = 0
    for pixel in pixels:
        ahash = (ahash << 1) | (pixel > average)
    # Central crop limits background bias; value bins distinguish black from white.
    w, h = image.size
    crop = image.crop((w // 10, h // 10, w - w // 10, h - h // 10))
    pixels = crop.resize((64, 64), Image.Resampling.BILINEAR).convert("HSV").tobytes()
    histogram = [0.0] * 48
    for offset in range(0, len(pixels), 3):
        hue, saturation, value = pixels[offset : offset + 3]
        index = (hue * 12 // 256) * 4 + 2 * (saturation >= 64) + (value >= 128)
        histogram[index] += 3 / len(pixels)
    return {"dhash": f"{dhash:016x}", "ahash": f"{ahash:016x}", "histogram": histogram}


def image_similarity(left: dict | None, right: dict | None, *, histogram=True) -> dict | None:
    if left is None or right is None:
        return None
    for features in (left, right):
        bins = features.get("histogram")
        if (
            not isinstance(bins, list)
            or len(bins) != 48
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0 <= value <= 1
                for value in bins
            )
            or not math.isclose(sum(bins), 1, abs_tol=1e-5)
        ):
            raise ValueError("Image histogram must be a normalized finite 48-bin vector")
    components = {
        "histogram_sim": sum(
            min(a, b) for a, b in zip(left["histogram"], right["histogram"], strict=True)
        )
    }
    weights = dict(IMAGE_WEIGHTS)
    if not histogram:
        weights["histogram"] = 0.0
    for key in ("dhash", "ahash"):
        if any(
            not isinstance(features.get(key), str) or len(features[key]) != 16
            for features in (left, right)
        ):
            raise ValueError("Perceptual hash must contain 16 hexadecimal characters")
        a, b = int(left[key], 16), int(right[key], 16)
        if not 0 <= a < 2**64 or not 0 <= b < 2**64:
            raise ValueError("Perceptual hash must contain 64 bits")
        distance = (a ^ b).bit_count()
        components[f"{key}_distance"] = distance
        components[f"{key}_sim"] = 1 - distance / 64
        # A flat image's identical zero hashes are not structural evidence.
        if not 2 < a.bit_count() < 62 or not 2 < b.bit_count() < 62:
            weights[key] = 0.0
    if weights["dhash"] == 0 and weights["ahash"] == 0:
        # Two blank/solid photos only duplicate the colour attribute; no image evidence.
        weights["histogram"] = 0.0
    total = sum(weights.values())
    if not total:
        return None
    weights = {key: value / total for key, value in weights.items()}
    return {
        **components,
        "weights": weights,
        "score": round(
            sum(weight * components[f"{key}_sim"] for key, weight in weights.items()), 10
        ),
    }
