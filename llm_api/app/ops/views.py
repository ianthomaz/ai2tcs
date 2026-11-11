"""Visoes SQL fixas da observacao para ai2tcs (/api/ops/observe).

Regras de seguranca:
- Transacoes estritamente READ ONLY com statement_timeout = '5s'.
- Sem SQL dinamico/livre vindo do cliente.
- Zero dados de pessoa (sem user_id, email, telefone, nome, documentos, perguntas/respostas brutas).
- Toda saida de erro ou texto e sanitizada via redact_log_line.
"""
from datetime import datetime
from typing import Any
from pathlib import Path
import asyncpg

from app.db import get_pool
from app.ops.redact import redact_log_line


async def _run_readonly(query: str, *args) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            await conn.execute("SET LOCAL statement_timeout = '5s'")
            rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]


def _json_safe(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (int, float, str, bool)) or val is None:
        return val
    if isinstance(val, list):
        return [_json_safe(v) for v in val]
    if isinstance(val, dict):
        return {k: _json_safe(v) for k, v in val.items()}
    return str(val)


# --- Visoes Fixas ---

async def view_schema(days: int | None = None, project_id: str | None = None) -> Any:
    """Tabelas publicas, colunas, tipos e contagem aproximada de linhas sem expor dados."""
    query = """
    SELECT
        c.table_name,
        c.column_name,
        c.data_type,
        c.is_nullable
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
    ORDER BY c.table_name, c.ordinal_position;
    """
    rows = await _run_readonly(query)
    tables: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        tname = r["table_name"]
        tables.setdefault(tname, []).append({
            "column": r["column_name"],
            "type": r["data_type"],
            "nullable": r["is_nullable"],
        })
    return _json_safe(tables)


async def view_migrations(days: int | None = None, project_id: str | None = None) -> Any:
    """Historico recente de migracoes do Prisma."""
    query = """
    SELECT migration_name, finished_at, rolled_back_at, applied_steps_count
    FROM _prisma_migrations
    ORDER BY started_at DESC
    LIMIT 30;
    """
    try:
        rows = await _run_readonly(query)
        return _json_safe(rows)
    except Exception:
        return {"note": "_prisma_migrations table not found or accessible"}


async def view_health(days: int | None = None, project_id: str | None = None) -> Any:
    """Latencia do Postgres e contagem rapida de jobs pendentes."""
    query = """
    SELECT
        count(*) FILTER (WHERE status = 'queued')::int AS queued,
        count(*) FILTER (WHERE status = 'working')::int AS working,
        count(*) FILTER (WHERE status = 'failed' AND created_at > NOW() - INTERVAL '24 hours')::int AS failed_24h,
        count(*) FILTER (WHERE status = 'done' AND created_at > NOW() - INTERVAL '24 hours')::int AS done_24h
    FROM "Job";
    """
    rows = await _run_readonly(query)
    return _json_safe(rows[0] if rows else {})


async def view_jobs_queue(days: int | None = None, project_id: str | None = None) -> Any:
    """Jobs em fila ou em execucao agrupados por projeto e alias de modelo."""
    if project_id:
        query = """
        SELECT project_id, model_alias, status, job_kind, count(*)::int AS count,
               min(created_at) AS oldest_job, max(created_at) AS newest_job
        FROM "Job"
        WHERE status IN ('queued', 'working') AND project_id = $1
        GROUP BY project_id, model_alias, status, job_kind
        ORDER BY count DESC;
        """
        rows = await _run_readonly(query, project_id)
    else:
        query = """
        SELECT project_id, model_alias, status, job_kind, count(*)::int AS count,
               min(created_at) AS oldest_job, max(created_at) AS newest_job
        FROM "Job"
        WHERE status IN ('queued', 'working')
        GROUP BY project_id, model_alias, status, job_kind
        ORDER BY count DESC;
        """
        rows = await _run_readonly(query)
    return _json_safe(rows)


async def view_jobs_summary(days: int | None = None, project_id: str | None = None) -> Any:
    """Volume de jobs nas ultimas 24h e 7 dias por projeto e status."""
    if project_id:
        query = """
        SELECT project_id, status, job_kind,
               count(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours')::int AS count_24h,
               count(*)::int AS count_7d
        FROM "Job"
        WHERE created_at > NOW() - INTERVAL '7 days' AND project_id = $1
        GROUP BY project_id, status, job_kind
        ORDER BY count_7d DESC;
        """
        rows = await _run_readonly(query, project_id)
    else:
        query = """
        SELECT project_id, status, job_kind,
               count(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours')::int AS count_24h,
               count(*)::int AS count_7d
        FROM "Job"
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY project_id, status, job_kind
        ORDER BY count_7d DESC;
        """
        rows = await _run_readonly(query)
    return _json_safe(rows)


async def view_errors(days: int | None = None, project_id: str | None = None) -> Any:
    """Erros de jobs nos ultimos N dias (default 2, max 30) com mensagens sanitizadas."""
    d = min(max(days or 2, 1), 30)
    interval_str = f"{d} days"

    if project_id:
        query = f"""
        SELECT project_id, job_kind, model_alias, error_message, count(*)::int AS occurrences,
               max(created_at) AS last_seen
        FROM "Job"
        WHERE status = 'failed' AND created_at > NOW() - INTERVAL '{interval_str}' AND project_id = $1
        GROUP BY project_id, job_kind, model_alias, error_message
        ORDER BY occurrences DESC
        LIMIT 50;
        """
        rows = await _run_readonly(query, project_id)
    else:
        query = f"""
        SELECT project_id, job_kind, model_alias, error_message, count(*)::int AS occurrences,
               max(created_at) AS last_seen
        FROM "Job"
        WHERE status = 'failed' AND created_at > NOW() - INTERVAL '{interval_str}'
        GROUP BY project_id, job_kind, model_alias, error_message
        ORDER BY occurrences DESC
        LIMIT 50;
        """
        rows = await _run_readonly(query)

    sanitized = []
    for r in rows:
        err = r.get("error_message") or "Unknown error"
        sanitized.append({
            "project_id": r["project_id"],
            "job_kind": r["job_kind"],
            "model_alias": r["model_alias"],
            "error_sample": redact_log_line(err),
            "occurrences": r["occurrences"],
            "last_seen": _json_safe(r["last_seen"]),
        })
    return sanitized


async def view_llm_heavy(days: int | None = None, project_id: str | None = None) -> Any:
    """Chamadas que excederam tokens (heavy) ou chegaram perto do limite de contexto nas ultimas 24h."""
    query = """
    SELECT project_id, job_kind, model_alias,
           (user_context_json->'__metrics'->>'prompt_tokens')::int AS prompt_tokens,
           (user_context_json->'__metrics'->>'output_tokens')::int AS output_tokens,
           (user_context_json->'__metrics'->>'total_ms')::int AS total_ms,
           (user_context_json->'__metrics'->>'heavy')::boolean AS heavy,
           (user_context_json->'__metrics'->>'near_ctx_limit')::boolean AS near_ctx_limit,
           created_at
    FROM "Job"
    WHERE created_at > NOW() - INTERVAL '24 hours'
      AND (
        (user_context_json->'__metrics'->>'heavy')::boolean = true
        OR (user_context_json->'__metrics'->>'near_ctx_limit')::boolean = true
      )
    ORDER BY created_at DESC
    LIMIT 50;
    """
    rows = await _run_readonly(query)
    return _json_safe(rows)


async def view_ratings(days: int | None = None, project_id: str | None = None) -> Any:
    """Julgamentos shadow (great, good, bad, stop) agrupados por projeto."""
    if project_id:
        query = """
        SELECT project_id, rating, count(*)::int AS count,
               max(received_at) AS last_rated_at
        FROM "answer_ratings"
        WHERE project_id = $1
        GROUP BY project_id, rating
        ORDER BY count DESC;
        """
        rows = await _run_readonly(query, project_id)
    else:
        query = """
        SELECT project_id, rating, count(*)::int AS count,
               max(received_at) AS last_rated_at
        FROM "answer_ratings"
        GROUP BY project_id, rating
        ORDER BY project_id, count DESC;
        """
        rows = await _run_readonly(query)
    return _json_safe(rows)


async def view_projects(days: int | None = None, project_id: str | None = None) -> Any:
    """Catalogo de projetos ativos no Postgres com seus slugs e datas gerais."""
    if project_id:
        query = """
        SELECT project_id, created_at, updated_at
        FROM "Project"
        WHERE project_id = $1;
        """
        rows = await _run_readonly(query, project_id)
    else:
        query = """
        SELECT project_id, created_at, updated_at
        FROM "Project"
        ORDER BY project_id;
        """
        rows = await _run_readonly(query)
    return _json_safe(rows)


async def view_db_health(days: int | None = None, project_id: str | None = None) -> Any:
    """Saude do PostgreSQL: cache hit ratio, conexoes e queries ativas longas."""
    query_cache = """
    SELECT round(100.0 * sum(blks_hit) / nullif(sum(blks_hit + blks_read), 0), 2)::float AS cache_hit_ratio
    FROM pg_stat_database
    WHERE datname = current_database();
    """
    query_conns = """
    SELECT COALESCE(state, 'unknown') AS state, count(*)::int AS count
    FROM pg_stat_activity
    WHERE datname = current_database()
    GROUP BY state;
    """
    query_long = """
    SELECT round(EXTRACT(EPOCH FROM max(NOW() - query_start)))::int AS longest_query_sec
    FROM pg_stat_activity
    WHERE state = 'active' AND pid <> pg_backend_pid();
    """
    cache = await _run_readonly(query_cache)
    conns = await _run_readonly(query_conns)
    long_q = await _run_readonly(query_long)

    return _json_safe({
        "cache_hit_ratio": cache[0]["cache_hit_ratio"] if cache else None,
        "connections": conns,
        "longest_active_query_sec": long_q[0]["longest_query_sec"] if long_q else 0,
    })


async def view_db_tables(days: int | None = None, project_id: str | None = None) -> Any:
    """Tamanho em disco das tabelas e indices no banco."""
    query = """
    SELECT
        relname AS table_name,
        pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
        pg_total_relation_size(c.oid)::bigint AS total_bytes,
        reltuples::bigint AS approx_rows
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
    ORDER BY pg_total_relation_size(c.oid) DESC;
    """
    rows = await _run_readonly(query)
    return _json_safe(rows)


OPS_OBSERVE_VIEWS = {
    "schema": view_schema,
    "migrations": view_migrations,
    "health": view_health,
    "jobs-queue": view_jobs_queue,
    "jobs-summary": view_jobs_summary,
    "errors": view_errors,
    "llm-heavy": view_llm_heavy,
    "ratings": view_ratings,
    "projects": view_projects,
    "db-health": view_db_health,
    "db-tables": view_db_tables,
}

OPS_OBSERVE_DAYS_VIEWS = {"errors"}
