from types import SimpleNamespace

import pytest

from backend.app.errors import ServiceFailure
from backend.app.providers import GeminiEmbedder, validate_vector


@pytest.mark.parametrize("vector", [[0, 0], [float("nan"), 1], [float("inf"), 1], [1]])
def test_invalid_embedding_is_rejected(vector):
    with pytest.raises(ServiceFailure):
        validate_vector(vector, 2)


def test_gemini_never_passes_legacy_task_type():
    from google.genai import types

    calls = []

    def embed_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0])])

    embedder = GeminiEmbedder.__new__(GeminiEmbedder)
    embedder.model, embedder.dimensions = "gemini-embedding-2", 2
    embedder._types = types
    embedder._client = SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))
    assert embedder.embed_text("public description") == [0.6, 0.8]
    assert embedder.embed_image(b"image") == [0.6, 0.8]
    for call in calls:
        assert call["config"].model_dump(exclude_none=True) == {"output_dimensionality": 2}


@pytest.mark.parametrize("code,retryable", [(401, False), (403, False), (429, True), (503, True)])
def test_gemini_errors_are_sanitized_and_retry_after_preserved(code, retryable):
    import httpx
    from google.genai import types
    from google.genai.errors import APIError

    def fail(**kwargs):
        raise APIError(
            code, {"error": "upstream-secret"}, httpx.Response(code, headers={"Retry-After": "123"})
        )

    embedder = GeminiEmbedder.__new__(GeminiEmbedder)
    embedder.model, embedder.dimensions = "gemini-embedding-2", 768
    embedder._types = types
    embedder._client = SimpleNamespace(models=SimpleNamespace(embed_content=fail))
    with pytest.raises(ServiceFailure) as raised:
        embedder.embed_text("public")
    assert raised.value.retryable is retryable
    assert raised.value.retry_after == 123
    assert "secret" not in str(raised.value)
