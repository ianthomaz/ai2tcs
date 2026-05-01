"""Return the correct LLMProvider for a project based on its config_json."""
import logging

from app.llm.base import LLMProvider
from app.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


def get_provider(project: dict) -> LLMProvider:
    """Resolve provider from project config_json['llm_provider'].

    Defaults to 'ollama'. External providers require credentials set in .env.
    Supported values: 'ollama' | 'openai' | 'anthropic' | 'gemini'
    """
    cfg = project.get("config_json") or {}
    provider_name = (cfg.get("llm_provider") if isinstance(cfg, dict) else None) or "ollama"

    if provider_name == "ollama":
        return OllamaProvider()

    # Lazy import external providers so missing credentials only fail at call time
    from app.config import settings
    from app.llm.external_provider import AnthropicProvider, GeminiProvider, OpenAIProvider

    if provider_name == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            default_model=settings.openai_default_model,
        )
    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            default_model=settings.anthropic_default_model,
        )
    if provider_name == "gemini":
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            default_model=settings.gemini_default_model,
        )

    logger.warning("Unknown llm_provider '%s' for project %s — falling back to ollama", provider_name, project.get("project_id"))
    return OllamaProvider()
