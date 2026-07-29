"""Embeddings via Ollama (default: mxbai-embed-large; override per project config_json.embedding_model)."""
import asyncio
import logging
from collections import OrderedDict

import httpx

from app.config import settings

DEFAULT_MODEL = "mxbai-embed-large"
# Ollama embedding models have context limits; truncate to avoid 500
MAX_PROMPT_CHARS = 4000
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SEC = 2
# Pause every N requests to avoid overheating/OOM on Ollama
PAUSE_EVERY_N = 100
PAUSE_SEC = 1.0

logger = logging.getLogger(__name__)
_EMBED_CACHE_MAX = 512
_embed_cache: "OrderedDict[str, list[float]]" = OrderedDict()
_embed_cache_lock = asyncio.Lock()


def _ollama_embed_url() -> str:
    return f"{settings.ollama_host.rstrip('/')}/api/embeddings"


def get_embedding(text: str, model: str = DEFAULT_MODEL) -> list[float]:
    """Sync single text embedding. For batch, call in loop or use async."""
    with httpx.Client(timeout=60.0) as client:
        r = client.post(_ollama_embed_url(), json={"model": model, "prompt": text})
        r.raise_for_status()
        return r.json()["embedding"]


async def get_embedding_async(text: str, model: str = DEFAULT_MODEL) -> list[float]:
    """Async single text embedding."""
    prompt = _truncate_prompt(text).strip() or " "
    cache_key = f"{model}::{prompt}"
    if settings.embedding_cache_enabled:
        async with _embed_cache_lock:
            cached = _embed_cache.get(cache_key)
            if cached is not None:
                _embed_cache.move_to_end(cache_key)
                return cached
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(_ollama_embed_url(), json={"model": model, "prompt": prompt})
        r.raise_for_status()
        embedding = r.json()["embedding"]
    if settings.embedding_cache_enabled:
        async with _embed_cache_lock:
            _embed_cache[cache_key] = embedding
            _embed_cache.move_to_end(cache_key)
            while len(_embed_cache) > _EMBED_CACHE_MAX:
                _embed_cache.popitem(last=False)
    return embedding


def _truncate_prompt(text: str) -> str:
    """Truncate to avoid Ollama context limit (reduces 500 errors)."""
    if len(text) <= MAX_PROMPT_CHARS:
        return text
    return text[: MAX_PROMPT_CHARS - 3] + "..."


async def get_embeddings_batch(texts: list[str], model: str = DEFAULT_MODEL) -> tuple[list[list[float]], int]:
    """Embed a list of texts (sequential, with truncation, retries, and skip on persistent failure).

    Returns (embeddings, skipped_count).
    """
    url = _ollama_embed_url()
    # Get embedding dimension once (from first successful request or fallback)
    dim: int | None = None
    skipped = 0

    async with httpx.AsyncClient(timeout=120.0) as client:
        out: list[list[float]] = []
        for i, t in enumerate(texts):
            if (i + 1) % PAUSE_EVERY_N == 0:
                await asyncio.sleep(PAUSE_SEC)
            prompt = _truncate_prompt(t).strip() or " "
            last_error = None
            for attempt in range(RETRY_ATTEMPTS):
                try:
                    r = await client.post(url, json={"model": model, "prompt": prompt})
                    r.raise_for_status()
                    emb = r.json()["embedding"]
                    if dim is None:
                        dim = len(emb)
                    out.append(emb)
                    break
                except (httpx.HTTPStatusError, httpx.RequestError) as e:
                    last_error = e
                    if attempt < RETRY_ATTEMPTS - 1:
                        delay = RETRY_BASE_DELAY_SEC * (2**attempt)
                        await asyncio.sleep(delay)
            else:
                # Skip this chunk: use zero vector so index size stays aligned with ids/documents
                skipped += 1
                if dim is None:
                    try:
                        small = await client.post(url, json={"model": model, "prompt": "x"})
                        small.raise_for_status()
                        dim = len(small.json()["embedding"])
                    except Exception:
                        dim = 768
                logger.warning("Skipping chunk %s after %s attempts: %s", i + 1, RETRY_ATTEMPTS, last_error)
                out.append([0.0] * dim)
        if skipped:
            logger.warning(
                "Embedding batch finished with %s skipped of %s chunks (model=%s)",
                skipped,
                len(texts),
                model,
            )
        return out, skipped
