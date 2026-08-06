"""App settings from environment."""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = "127.0.0.1"  # use "0.0.0.0" to accept tailnet IP access (no Funnel)
    api_port: int = 28471
    llm_api_token: str = ""
    ollama_host: str = "http://127.0.0.1:11434"  # use host.docker.internal in Docker
    ollama_chat_model: str = "gemma3:12b"  # legacy/fallback (aligned with smart)
    ollama_fast_model: str = "llama3:8b"
    ollama_compact_model: str = "qwen2.5:7b-instruct"
    ollama_smart_model: str = "gemma3:12b"
    ollama_reasoner_model: str = "deepseek-r1:14b"
    # NF Extract: Ollama /api/chat read budget (s). Clients (e.g. ITCS_NF_EXTRACT_TIMEOUT_MS) should exceed this + ~30s.
    nf_extract_ollama_timeout_s: float = 120.0
    # /ask and /router main chat call: without this, provider.chat() had no timeout
    # at all — a hung Ollama call blocked its worker's job queue forever.
    llm_chat_timeout_s: float = 120.0
    # /edu/chat: default to fast model for lower latency on short structured replies; override per-request with body.model or env.
    edu_chat_default_model_alias: str = "fast"
    edu_chat_num_predict: int = 512
    edu_chat_retry_num_predict: int = 640
    edu_chat_temperature: float = 0.55
    edu_chat_retry_temperature: float = 0.28
    # POST /nabilvideomap/qualify-caption — output token budget (clamped to hard max in route)
    nabil_qualify_num_predict: int = 1536
    nabil_qualify_num_predict_hard_max: int = 2048
    nabil_qualify_rag_context_max_chars: int = 8000
    # Ollama sampling: higher → less repetitive phrasing in theme notes / summary (JSON keys stay strict).
    nabil_qualify_temperature: float = 0.42
    # Dashboard /usage: max GiB for Ollama memory bar (unified RAM / VRAM reference, e.g. 32 GB Mac)
    dashboard_ollama_memory_reference_gib: float = 32.0
    # Legacy HTML login (only if Google OAuth is not configured)
    dashboard_user: str = ""
    dashboard_password: str = ""
    # Google OAuth for /dashboard (Web application client in GCP)
    dashboard_google_client_id: str = ""
    dashboard_google_client_secret: str = ""
    # Public origin users open in the browser, no trailing slash, e.g. http://127.0.0.1:28471 or https://api.example.com
    dashboard_oauth_redirect_base: str = ""
    # Comma-separated emails allowed after Google login (normalized lowercase)
    # Comma-separated allowlist; define in .env for production (no personal defaults in public tree).
    dashboard_allowed_emails: str = ""
    database_url: str = "postgresql://localhost:5432/llmapi"
    # Resolve to project root (llm_api/data) so worker and CLI use same index regardless of cwd
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    # Session secret for dashboard cookies
    session_secret: str = "change-me-in-production"

    # Local STT (faster-whisper)
    whisper_enabled: bool = True
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = "pt"
    whisper_beam_size: int = 5
    whisper_vad_filter: bool = True
    whisper_download_root: str | None = None

    # Audio uploads (multipart)
    audio_max_bytes: int = 25 * 1024 * 1024
    # Global safety net, checked before any body/multipart parsing runs. audio.py's
    # own audio_max_bytes check only fires after Starlette has already spooled the
    # whole upload to disk/memory (SpooledTemporaryFile per multipart part), and
    # /ingest/upload had no size limit of any kind. Generous on purpose — this is
    # a backstop against a broken/abusive client, not a per-route content policy.
    max_request_body_bytes: int = 50 * 1024 * 1024
    audio_temp_subdir: str = "audio_tmp"
    # Runtime feature flags (safe defaults keep existing behavior)
    rag_rerank_enabled: bool = False
    rag_hybrid_enabled: bool = False
    rag_reflection_enabled: bool = False
    embedding_cache_enabled: bool = True
    # Request observability
    request_logging_enabled: bool = True

    def project_sources_override(self, project_id: str) -> list[str] | None:
        """Override sources for any project via env: <PROJECT_ID>_SOURCES (comma-separated paths)."""
        env_key = f"{project_id.upper()}_SOURCES"
        val = os.environ.get(env_key)
        if val:
            return [p.strip() for p in val.split(",") if p.strip()]
        return None

    def get_model_name(self, alias: str | None, default_alias: str = "smart") -> str:
        """Resolve 'fast'/'compact'/'smart'/'reasoner' aliases to actual model names from settings."""
        m = (alias or default_alias).strip().lower()
        if m == "fast":
            return self.ollama_fast_model
        if m == "compact":
            return self.ollama_compact_model
        if m == "smart":
            return self.ollama_smart_model
        if m == "reasoner":
            return self.ollama_reasoner_model
        # If it's not an alias, assume it's a direct model name or return default
        if m and m not in ("fast", "compact", "smart", "reasoner", "default"):
            return alias  # type: ignore
        if default_alias == "fast":
            return self.ollama_fast_model
        if default_alias == "compact":
            return self.ollama_compact_model
        if default_alias == "reasoner":
            return self.ollama_reasoner_model
        return self.ollama_smart_model

    def resolved_whisper_download_root(self) -> Path:
        if self.whisper_download_root:
            return Path(self.whisper_download_root)
        return self.data_dir / "whisper_models"

    def nabil_qualify_effective_num_predict(self) -> int:
        """Clamp configured num_predict for Nabil qualify-caption (abuse guard)."""
        capped = min(int(self.nabil_qualify_num_predict), int(self.nabil_qualify_num_predict_hard_max))
        return max(256, capped)

    def nabil_qualify_effective_temperature(self) -> float:
        """Clamp temperature for qualify-caption (JSON still needs to be valid)."""
        t = float(self.nabil_qualify_temperature)
        return max(0.1, min(0.85, t))

    # External LLM providers — disabled by default (leave empty to keep Ollama-only).
    # Set in .env to activate. See app/llm/external_provider.py for full documentation.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-haiku-4-5-20251001"
    gemini_api_key: str = ""
    gemini_default_model: str = "gemini-2.0-flash"

    def dashboard_google_oauth_configured(self) -> bool:
        return bool(
            self.dashboard_google_client_id.strip()
            and self.dashboard_google_client_secret.strip()
            and self.dashboard_oauth_redirect_base.strip()
        )

    def dashboard_allowed_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.dashboard_allowed_emails.split(",") if e.strip()}


settings = Settings()
