"""Optional smoke against a running API (Docker on localhost or public URL).

Run:
  LLM_LIVE_URL=http://127.0.0.1:28471 LLM_LIVE_TOKEN=<same as LLM_API_TOKEN> \\
    pytest tests/test_live_smoke.py -v
"""
from __future__ import annotations

import os

import pytest

LIVE_URL = os.environ.get("LLM_LIVE_URL", "").rstrip("/")
LIVE_TOKEN = os.environ.get("LLM_LIVE_TOKEN", "")


@pytest.mark.skipif(not LIVE_URL or not LIVE_TOKEN, reason="Set LLM_LIVE_URL and LLM_LIVE_TOKEN")
def test_live_health():
    import httpx

    r = httpx.get(f"{LIVE_URL}/health", timeout=10.0)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("ok", "degraded")


@pytest.mark.skipif(not LIVE_URL or not LIVE_TOKEN, reason="Set LLM_LIVE_URL and LLM_LIVE_TOKEN")
def test_live_ask_accepts_auth():
    import httpx

    h = {"Authorization": f"Bearer {LIVE_TOKEN}", "Content-Type": "application/json"}
    r = httpx.post(
        f"{LIVE_URL}/ask",
        headers=h,
        json={
            "project_id": "aiclaudia",
            "question": f"live smoke ping {os.getpid()}",
            "model": "fast",
        },
        timeout=30.0,
    )
    assert r.status_code in (202, 409), r.text
    if r.status_code == 202:
        assert "job_id" in r.json()
