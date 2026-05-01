"""Google OAuth2 (authorization code) for dashboard login — server-side only."""
from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
OAUTH_SCOPES = "openid email profile"


def build_authorize_redirect_uri(redirect_base: str) -> str:
    base = redirect_base.rstrip("/")
    return f"{base}/dashboard/auth/google/callback"


def authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    q = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": OAUTH_SCOPES,
            "state": state,
            "access_type": "online",
            "include_granted_scopes": "true",
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{q}"


async def exchange_code(*, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        return r.json()


async def fetch_google_email(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        data = r.json()
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Google did not return an email")
    return email


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)
