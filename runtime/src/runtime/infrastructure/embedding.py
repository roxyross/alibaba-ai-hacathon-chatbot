"""Google embedding API client for RAG chunk vectors.

Uses the Gemini embedding API (REST) via httpx:
  POST /v1beta/models/{model}:embedContent

Returns a list[float] vector normalized to unit length (suitable for
cosine-similarity search with pgvector's vector_cosine_ops).
"""

from __future__ import annotations

import httpx
import structlog

from runtime.config import settings

log = structlog.get_logger()


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


async def embed_text(text: str) -> list[float]:
    """Generate a normalized embedding vector for `text` via the Gemini API.

    The returned vector has L2 norm == 1.0 (suitable for cosine similarity
    with pgvector's `vector_cosine_ops` operator).

    Args:
        text: The text to embed. Will be truncated to 2048 tokens internally.

    Returns:
        A list of floats (dimension 768 for `embedding-001`).

    Raises:
        EmbeddingError: If the API call fails or returns an unexpected shape.
    """
    if not settings.google_api_key:
        raise EmbeddingError("GOOGLE_API_KEY is not configured")

    url = settings.google_embedding_url
    payload = {
        "content": {
            "role": "user",
            "parts": [{"text": text}],
        },
        "taskType": "RETRIEVAL_DOCUMENT",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"embedding API unreachable: {exc}") from exc

    if not resp.is_success:
        raise EmbeddingError(
            f"embedding API returned {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()
    try:
        values: list[float] = data["embedding"]["values"]
    except (KeyError, TypeError) as exc:
        raise EmbeddingError(f"unexpected embedding response shape: {exc}") from exc

    # Normalize to unit length (L2 norm = 1.0) for cosine similarity
    magnitude = sum(v * v for v in values) ** 0.5
    if magnitude > 0:
        values = [v / magnitude for v in values]

    log.debug("embedding.generated", dimension=len(values), magnitude=round(magnitude, 4))
    return values


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed multiple texts.

    Gemini's embedContent API processes one text at a time. We run them
    concurrently with a semaphore to avoid overwhelming the API.

    Returns:
        A list of embedding vectors, one per input text.
    """
    import asyncio

    semaphore = asyncio.Semaphore(5)  # max 5 concurrent embedding calls

    async def _embed_one(text: str) -> list[float]:
        async with semaphore:
            return await embed_text(text)

    return await asyncio.gather(*[_embed_one(t) for t in texts])
