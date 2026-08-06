"""External LLM provider stubs: OpenAI, Anthropic, Gemini.

These providers are DISABLED by default — no credentials are required or
configured in the public repository. To activate any of them:

  OpenAI / OpenAI-compatible (e.g. Gemini via compat layer):
    OPENAI_API_KEY=sk-...
    OPENAI_BASE_URL=https://api.openai.com/v1      # default
    OPENAI_DEFAULT_MODEL=gpt-4o-mini               # default

  Anthropic (Claude API):
    ANTHROPIC_API_KEY=sk-ant-...
    ANTHROPIC_DEFAULT_MODEL=claude-haiku-4-5-20251001  # default

  Gemini (native REST):
    GEMINI_API_KEY=AIza...
    GEMINI_DEFAULT_MODEL=gemini-2.0-flash          # default

Per-project activation: set "llm_provider" in the project's config_json.
Example: {"llm_provider": "openai", "llm_options": {"num_predict": 1024}}
"""
import json
import logging

import httpx

from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_NOT_CONFIGURED = (
    "External provider '{name}' is not configured. "
    "Set the required env vars (see app/llm/external_provider.py) to enable it."
)


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions API (also compatible with Gemini's OpenAI-compat endpoint)."""

    def __init__(self, api_key: str, base_url: str, default_model: str) -> None:
        if not api_key:
            raise RuntimeError(_NOT_CONFIGURED.format(name="openai"))
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def chat(self, model: str, messages: list[dict], options: dict) -> str:
        effective_model = model or self._default_model
        payload: dict = {
            "model": effective_model,
            "messages": messages,
            "max_tokens": options.get("num_predict", 1024),
            "temperature": options.get("temperature", 0.5),
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            resp.raise_for_status()
            data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API (Claude models)."""

    def __init__(self, api_key: str, default_model: str) -> None:
        if not api_key:
            raise RuntimeError(_NOT_CONFIGURED.format(name="anthropic"))
        self._api_key = api_key
        self._default_model = default_model

    async def chat(self, model: str, messages: list[dict], options: dict) -> str:
        effective_model = model or self._default_model
        # Separate system message from the conversation
        system_text = ""
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_text = msg.get("content", "")
            else:
                user_messages.append({"role": msg["role"], "content": msg.get("content", "")})

        payload: dict = {
            "model": effective_model,
            "max_tokens": options.get("num_predict", 1024),
            "temperature": options.get("temperature", 0.5),
            "messages": user_messages,
        }
        if system_text:
            payload["system"] = system_text

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
            )
            resp.raise_for_status()
            data = resp.json()
        content = data.get("content") or []
        return next((b.get("text", "") for b in content if b.get("type") == "text"), "")


class GeminiProvider(LLMProvider):
    """Google Gemini native REST API."""

    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, default_model: str) -> None:
        if not api_key:
            raise RuntimeError(_NOT_CONFIGURED.format(name="gemini"))
        self._api_key = api_key
        self._default_model = default_model

    async def chat(self, model: str, messages: list[dict], options: dict) -> str:
        effective_model = model or self._default_model
        system_text = ""
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_text = text
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": options.get("num_predict", 1024),
                "temperature": options.get("temperature", 0.5),
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        # Key goes in a header, not the ?key= query param: httpx logs the request URL
        # at INFO level (app/main.py sets logging.basicConfig(level=logging.INFO)),
        # so a key in the URL lands in cleartext in every log line, every request.
        # Google's Generative Language API accepts the key via x-goog-api-key too.
        url = f"{self._BASE}/{effective_model}:generateContent"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers={"x-goog-api-key": self._api_key})
            resp.raise_for_status()
            data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)
