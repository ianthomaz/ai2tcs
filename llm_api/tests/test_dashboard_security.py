"""Dashboard login: server-side expiry, verified Google email, secure cookie on https, constant-time compare."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dashboard import google_oauth, routes
from app.stt.audio_validate import sniff_format


def test_session_expires_on_the_server():
    sid = routes._new_session()
    assert routes._session_valid(sid)
    routes._sessions[sid] = 0.0
    assert not routes._session_valid(sid)
    assert sid not in routes._sessions
    assert not routes._session_valid(None)


def test_secure_cookie_follows_https():
    req = MagicMock()
    req.url.scheme = "http"
    req.headers = {"x-forwarded-proto": "https"}
    assert routes._cookie_secure(req)
    req.headers = {}
    assert not routes._cookie_secure(req)


def test_same_is_strict():
    assert routes._same("a", "a")
    assert not routes._same("a", "b")
    assert not routes._same("", "")
    assert not routes._same(None, "a")


@pytest.mark.asyncio
async def test_google_email_must_be_verified():
    def client(payload):
        resp = MagicMock()
        resp.json.return_value = payload
        resp.raise_for_status.return_value = None
        c = MagicMock()
        c.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=resp)))
        c.__aexit__ = AsyncMock(return_value=False)
        return c

    with patch("app.dashboard.google_oauth.httpx.AsyncClient", return_value=client({"email": "A@x.org", "email_verified": True})):
        assert await google_oauth.fetch_google_email("t") == "a@x.org"
    with patch("app.dashboard.google_oauth.httpx.AsyncClient", return_value=client({"email": "a@x.org", "email_verified": False})):
        with pytest.raises(ValueError):
            await google_oauth.fetch_google_email("t")


def test_webm_has_a_signature():
    assert sniff_format(b"\x1a\x45\xdf\xa3" + b"\x00" * 8) == "webm"
