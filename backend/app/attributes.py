import math

from backend.app.metadata import COLORS, LOCATIONS
from backend.app.text_features import jaro_winkler, normalize

ATTRIBUTE_WEIGHTS = {"color": 0.4, "brand": 0.3, "location": 0.2, "date": 0.1}
COLOR_NAMES = {normalize(name): code for code, names in COLORS.items() for name in (code, *names)}
SHADES = {"navy": "blue", "maroon": "red", "olive": "green"}
COLOR_NAMES.update({"gray": "grey", **SHADES})
LOCATION_NAMES = {
    normalize(name): code for code, names in LOCATIONS.items() for name in (code, *names)
}
UNKNOWN = {"unknown", "other", "অজানা", "অন্যান্য"}


def _value(value) -> str | None:
    if value is None:
        return None
    normalized = normalize(str(value))
    return normalized if normalized and normalized not in UNKNOWN else None


def attribute_components(lost, found, date_window: int = 30, *, location_zones=True) -> dict:
    if date_window < 1:
        raise ValueError("Date window must be positive")
    components = {"color": 0.0, "brand": 0.0, "location": 0.0}
    for field in components:
        left, right = _value(lost.get(field)), _value(found.get(field))
        if not left or not right:
            continue
        if left == right:
            components[field] = 1.0
        elif (
            field == "color"
            and COLOR_NAMES.get(left) is not None
            and COLOR_NAMES.get(left) == COLOR_NAMES.get(right)
        ):
            components[field] = 0.85 if left in SHADES or right in SHADES else 1.0
        elif field == "brand":
            if jaro_winkler(left, right) >= 0.9:
                components[field] = 0.85
            elif set(left.split()) <= set(right.split()) or set(right.split()) <= set(left.split()):
                components[field] = 0.7
        elif field == "location":
            a, b = LOCATION_NAMES.get(left), LOCATION_NAMES.get(right)
            if a is not None and a == b:
                components[field] = 1.0
            elif location_zones and {a, b} == {"library", "classroom"}:
                components[field] = 0.5
    left_date, right_date = lost["event_date"], found["event_date"]
    gap = abs((right_date - left_date).days)
    components["date"] = max(0.0, 1 - gap / date_window)
    components["date_gap_days"] = gap
    return components


def attribute_score(lost, found, date_window: int = 30) -> float:
    components = attribute_components(lost, found, date_window)
    return round(sum(weight * components[key] for key, weight in ATTRIBUTE_WEIGHTS.items()), 10)


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding dimensions must match")
    if any(not math.isfinite(value) for value in [*left, *right]):
        raise ValueError("Embedding values must be finite")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        raise ValueError("Embedding vectors must be nonzero")
    return max(
        -1.0,
        min(1.0, sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)),
    )
