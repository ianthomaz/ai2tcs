"""External LLM providers had zero test coverage.

The Gemini API key must never travel in the URL: httpx logs the full request URL
at INFO level (app/main.py sets logging.basicConfig(level=logging.INFO), and does
not silence the httpx logger), so a key in a ?key=... query param lands in
cleartext in every log line, every request. Reproduced directly before fixing:
httpx really does log the query string verbatim at INFO.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.external_provider import GeminiProvider


class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_gemini_key_travels_in_header_not_url():
    provider = GeminiProvider(api_key="AIza-SECRET", default_model="gemini-2.0-flash")
    fake_data = {"candidates": [{"content": {"parts": [{"text": "oi"}]}}]}

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=_FakeResponse(fake_data))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.llm.external_provider.httpx.AsyncClient", return_value=mock_client):
        answer = await provider.chat(model="", messages=[{"role": "user", "content": "oi"}], options={})

    assert answer == "oi"
    mock_client.post.assert_called_once()
    _args, kwargs = mock_client.post.call_args
    url = _args[0] if _args else kwargs.get("url", "")
    assert "AIza-SECRET" not in url
    assert "key=" not in url
    assert kwargs["headers"]["x-goog-api-key"] == "AIza-SECRET"


def test_gemini_requires_api_key():
    with pytest.raises(RuntimeError, match="not configured"):
        GeminiProvider(api_key="", default_model="gemini-2.0-flash")
