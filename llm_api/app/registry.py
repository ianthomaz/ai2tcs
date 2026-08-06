"""Project registry: resolve project config (sources live inside project folders)."""
from app.config import settings
from app import db as db_module


async def get_project(project_id: str) -> dict | None:
    """Load project from DB. Sources can be overridden by env (e.g. BIKEANJOALL_2026_SOURCES)."""
    proj = await db_module.project_get(project_id)
    if not proj:
        return None
    override = settings.project_sources_override(project_id)
    if override is not None:
        proj = {**proj, "sources": override}
    return proj


async def get_project_sources(project_id: str) -> list[str]:
    """Resolved list of source paths (folders) for the project."""
    proj = await get_project(project_id)
    if not proj:
        return []
    return proj.get("sources") or []


def get_chunking_config(project: dict) -> dict:
    """Chunking config from project config_json or defaults."""
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        c = cfg.get("chunking") or {}
        return {
            "chunk_size": c.get("chunk_size", 512),
            "chunk_overlap": c.get("chunk_overlap", 64),
            "separator": c.get("separator", "\n\n"),
        }
    return {"chunk_size": 512, "chunk_overlap": 64, "separator": "\n\n"}


def get_rag_policies(project: dict) -> dict:
    """RAG policies from project config_json or defaults.

    max_chunk_distance: cosine distance threshold (0.0-2.0). Chunks above this are
    discarded as irrelevant. Default 1.0 (was 1.2). Lower = stricter filtering.
    Reasoning: 1.0 filters weakly-related chunks that pollute context and cause
    generic/weak responses. Projects with dense, well-structured libraries benefit
    from stricter filtering. Use 0.8-0.9 for sales/support projects.

    search_depth: controls retrieval intensity.
    - standard: default behavior.
    - deep: increases top_k and distance threshold for follow-up or complex queries.
    """
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        p = cfg.get("policies") or {}
        dedup_raw = p.get("dedup_ttl_seconds", 600)
        try:
            dedup_ttl = int(dedup_raw)
        except (TypeError, ValueError):
            dedup_ttl = 600
        return {
            "prefer_cite_sources": p.get("prefer_cite_sources", True),
            "when_no_answer": p.get("when_no_answer", "no_answer"),
            "max_chunks_to_retrieve": p.get("max_chunks_to_retrieve", 5),
            "max_chunk_distance": p.get("max_chunk_distance", 1.0),
            "search_depth": p.get("search_depth", "standard"),
            "dedup_ttl_seconds": max(0, dedup_ttl),
        }
    return {
        "prefer_cite_sources": True,
        "when_no_answer": "no_answer",
        "max_chunks_to_retrieve": 5,
        "max_chunk_distance": 1.0,
        "search_depth": "standard",
        "dedup_ttl_seconds": 600,
    }


def get_rag_mode(project: dict) -> str:
    """RAG retrieval mode for this project.

    'required' (default): answer only when RAG context is found; no chunks → no_answer.
    'optional': run RAG but answer regardless (good for mixed knowledge + open chat).
    'disabled': skip retrieval entirely — pure LLM, no vector lookup.
    """
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        mode = (cfg.get("policies") or {}).get("rag_mode", "required")
        if mode in ("required", "optional", "disabled"):
            return mode
    return "required"


def get_rag_feature_flags(project: dict) -> dict:
    """Per-project RAG feature toggles; null in config falls back to global settings."""
    cfg = project.get("config_json") or {}
    policies = (cfg.get("policies") or {}) if isinstance(cfg, dict) else {}

    def _resolve(key: str, global_default: bool) -> bool:
        val = policies.get(key)
        if val is None:
            return global_default
        return bool(val)

    return {
        "rag_hybrid_enabled": _resolve("rag_hybrid_enabled", settings.rag_hybrid_enabled),
        "rag_rerank_enabled": _resolve("rag_rerank_enabled", settings.rag_rerank_enabled),
        "rag_reflection_enabled": _resolve("rag_reflection_enabled", settings.rag_reflection_enabled),
    }


def get_behavior_instruction_path(project: dict) -> str | None:
    """Relative path to behavior instruction file (e.g. instrucoes-llm.md) under first source dir.
    Resolved at runtime by the worker from project sources.
    """
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        return cfg.get("behavior_instruction_path") or None
    return None


def get_behavior_instruction_inline(project: dict) -> str | None:
    """Optional inline system instruction from config (overrides file if both set)."""
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        s = cfg.get("system_instruction")
        return s if isinstance(s, str) and s.strip() else None
    return None


def get_router_config(project: dict) -> dict:
    """Router-specific config from config_json.router."""
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        r = cfg.get("router") or {}
        if isinstance(r, dict):
            routes = r.get("routes")
            return {
                "routes": routes if isinstance(routes, list) else None,
                "extra_system_block": r.get("extra_system_block") or "",
                "default_escalate_model": r.get("default_escalate_model") or "smart",
            }
    return {"routes": None, "extra_system_block": "", "default_escalate_model": "smart"}


def get_extract_steps_config(project: dict) -> dict:
    """Optional per-project extract step overrides from config_json.extract_steps."""
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        steps = cfg.get("extract_steps")
        return steps if isinstance(steps, dict) else {}
    return {}


def get_llm_config(project: dict) -> dict:
    """LLM inference options from project config_json or defaults.

    Controls model behavior: temperature (creativity), top_k (diversity),
    top_p (nucleus sampling), and repeat_penalty (penalize repeated tokens).

    tone_of_voice: informal | friendly | technical | sales | direct (default: direct)
    message_size: short | medium | detailed (default: medium)
    """
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        llm = cfg.get("llm_options") or {}
        return {
            "temperature": llm.get("temperature", 0.5),
            "top_k": llm.get("top_k", 30),
            "top_p": llm.get("top_p", 0.9),
            "repeat_penalty": llm.get("repeat_penalty", 1.3),
            "num_predict": llm.get("num_predict", 1024),
            "tone_of_voice": llm.get("tone_of_voice", "direct"),
            "message_size": llm.get("message_size", "medium"),
        }
    return {
        "temperature": 0.5,
        "top_k": 30,
        "top_p": 0.9,
        "repeat_penalty": 1.3,
        "num_predict": 1024,
        "tone_of_voice": "direct",
        "message_size": "medium",
    }
