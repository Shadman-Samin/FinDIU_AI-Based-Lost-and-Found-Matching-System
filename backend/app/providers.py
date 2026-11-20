"""Embedding providers.

Gemini is an optional semantic signal in hybrid mode. The hashed provider is
retained only to reproduce the historical offline evaluation baseline; local
production matching uses explicit lexical and perceptual features instead.
"""

import hashlib
import io
import math
import re
import unicodedata

from backend.app.errors import ServiceFailure

TOKEN = re.compile(r"[\w\u0980-\u09ff]+", re.UNICODE)


def _normalize(vector: list[float]) -> list[float]:
    if not vector or any(
        not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
        for value in vector
    ):
        raise ServiceFailure("embedding_response_invalid")
    scale = max(abs(value) for value in vector)
    if not scale:
        raise ServiceFailure("empty_embedding")
    vector = [value / scale for value in vector]
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        raise ServiceFailure("empty_embedding")
    return [value / norm for value in vector]


def validate_vector(vector, dimensions):
    if not isinstance(vector, list) or len(vector) != dimensions:
        raise ServiceFailure("embedding_response_invalid")
    return _normalize(vector)


class LocalEmbedder:
    """Hashed lexical + colour-grid fingerprint, 768 dimensions."""

    def __init__(self, dimensions: int = 768):
        self.model = f"local-hash-{dimensions}"
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        tokens = TOKEN.findall(normalized)
        features: dict[str, float] = {}
        for token in tokens:
            features[token] = features.get(token, 0.0) + 1.0
        for left, right in zip(tokens, tokens[1:], strict=False):
            bigram = f"{left} {right}"
            features[bigram] = features.get(bigram, 0.0) + 0.5
        vector = [0.0] * self.dimensions
        for feature, weight in features.items():
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[index] += sign * (1.0 + math.log(weight))
        return _normalize(vector)

    def embed_image(self, jpeg: bytes) -> list[float] | None:
        from PIL import Image

        with Image.open(io.BytesIO(jpeg)) as image:
            small = image.convert("RGB").resize((16, 16), Image.Resampling.BILINEAR)
            data = small.load()
            pixels = [data[x, y] for y in range(16) for x in range(16)]
        vector = [channel / 255.0 for pixel in pixels for channel in pixel]
        return _normalize((vector + [0.0] * self.dimensions)[: self.dimensions])


class GeminiEmbedder:
    def __init__(self, api_key: str, model: str, dimensions: int):
        from google import genai
        from google.genai import types

        self.model = model
        self.dimensions = dimensions
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=10_000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )

    def embed_text(self, text: str) -> list[float]:
        return self._embed([text])

    def _embed(self, contents):
        import httpx
        from google.genai.errors import APIError

        try:
            result = self._client.models.embed_content(
                model=self.model,
                contents=contents,
                config=self._types.EmbedContentConfig(output_dimensionality=self.dimensions),
            )
            return validate_vector(list(result.embeddings[0].values), self.dimensions)
        except APIError as error:
            code = error.code or 0
            from backend.app.errors import retry_after_seconds

            retry_after = (
                retry_after_seconds(error.response.headers.get("Retry-After"))
                if error.response is not None
                else None
            )
            raise ServiceFailure(
                "embedding_unavailable" if code == 429 or code >= 500 else "embedding_rejected",
                retryable=code == 429 or code >= 500,
                retry_after=retry_after,
            ) from None
        except httpx.HTTPError:
            raise ServiceFailure("embedding_unavailable", retryable=True) from None
        except (AttributeError, IndexError, TypeError):
            raise ServiceFailure("embedding_response_invalid", retryable=True) from None

    def embed_image(self, jpeg: bytes) -> list[float] | None:
        part = self._types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")
        return self._embed([part])


def build_embedder(settings):
    if not settings.semantic_enabled:
        return None
    key = settings.gemini_api_key.get_secret_value()
    return GeminiEmbedder(key, settings.gemini_embedding_model, settings.embedding_dimensions)
