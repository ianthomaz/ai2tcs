"""LLM provider abstraction: Ollama (local) + optional external APIs."""
from app.llm.factory import get_provider

__all__ = ["get_provider"]
