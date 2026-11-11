"""Endpoint GET /api/ops/observe para inspecao remota de producao por agentes.

Parametros:
- `source`: tail de arquivo de log limpo ('api', 'worker', 'pm2')
- `view`: visualizacao SQL fixa pre-definida (schema, migrations, health, jobs-queue, errors, etc.)
- `project_id`: opcional, restringe a visao ao projeto solicitado
- `lines`: quantidade de linhas do tail (padrao 200, max 2000)
- `grep`: filtro opcional de texto no log (max 100 caracteres)
- `days`: janela em dias para visoes que aceitam historico (ex: errors, 1..30)
- `since`: ISO timestamp para filtrar linhas de log a partir da data informada

Seguranca:
- Exige Bearer OPS_OBSERVE_TOKEN (>= 32 chars).
- Falha na autenticacao devolve HTTP 404 vazio com Cache-Control: no-store (stealth mode).
- Rate limit basico e teto de tempo de leitura.
- Sanitizacao automatica de dados pessoais e credenciais em todas as saidas.
"""
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request, Query, Response

from app.config import settings
from app.ops.access import ops_hidden, ops_json, ops_observe_check
from app.ops.redact import redact_log_line
from app.ops.views import OPS_OBSERVE_VIEWS, OPS_OBSERVE_DAYS_VIEWS

router = APIRouter(prefix="/api/ops", tags=["ops"])
logger = logging.getLogger("app.ops.observe")

MAX_LINES = 2000
DEFAULT_LINES = 200
MAX_GREP_CHARS = 100
MAX_DAYS = 30
TAIL_MAX_BYTES = 2 * 1024 * 1024  # 2MB


def _resolve_source_path(source: str) -> Path | None:
    source = source.strip().lower()
    base_dir = Path(settings.data_dir).parent  # raiz do llm_api
    logs_dir = base_dir / "logs"

    if source == "api":
        return logs_dir / "api.log"
    if source in ("worker", "jobs"):
        return logs_dir / "worker.log"
    if source == "pm2":
        pm2_dir = Path(settings.pm2_log_dir)
        return pm2_dir / "ai2tcs-out.log"
    if source == "pm2-err":
        pm2_dir = Path(settings.pm2_log_dir)
        return pm2_dir / "ai2tcs-error.log"
    return None


def _read_file_tail(file_path: Path, max_lines: int) -> list[str]:
    """Le as ultimas N linhas de um arquivo de log com teto em bytes."""
    if not file_path.exists() or not file_path.is_file():
        return []

    file_size = file_path.stat().st_size
    bytes_to_read = min(file_size, TAIL_MAX_BYTES)

    with open(file_path, "rb") as f:
        if file_size > bytes_to_read:
            f.seek(file_size - bytes_to_read)
        content = f.read(bytes_to_read).decode("utf-8", errors="replace")

    lines = content.splitlines()
    return lines[-max_lines:]


@router.get("/observe")
async def observe(
    request: Request,
    source: str | None = Query(None, description="Fonte de log (api, worker, pm2)"),
    view: str | None = Query(None, description="Visao SQL fixa (schema, migrations, health, jobs-queue, etc.)"),
    project_id: str | None = Query(None, description="Filtro opcional por projeto"),
    lines: int = Query(DEFAULT_LINES, ge=1, le=MAX_LINES, description="Numero de linhas para tail de log"),
    grep: str | None = Query(None, max_length=MAX_GREP_CHARS, description="Filtro case-insensitive de substring"),
    days: int | None = Query(None, ge=1, le=MAX_DAYS, description="Janela de dias para visoes com suporte (errors)"),
    since: str | None = Query(None, description="Timestamp ISO para filtrar logs"),
) -> Response:
    # 1. Checagem estrita de autorizacao (404 vazio se invalido)
    if not ops_observe_check(request):
        return ops_hidden()

    # 2. Exatamente um entre source ou view deve estar presente
    has_source = bool(source and source.strip())
    has_view = bool(view and view.strip())
    if has_source == has_view:
        return ops_json(400, {"error": "Must specify either 'source' or 'view', not both or neither"})

    generated_at = datetime.now(timezone.utc).isoformat()

    # 3. Rota de Leitura de Log (source)
    if has_source:
        assert source is not None
        log_file = _resolve_source_path(source)
        if not log_file:
            return ops_json(400, {"error": f"Unknown source: '{source}'. Allowed: api, worker, pm2, pm2-err"})

        raw_lines = _read_file_tail(log_file, lines)

        # Aplicar filtro since se informado
        if since:
            filtered_since = []
            for line in raw_lines:
                # Se linha comeca com timestamp ISO ou similar
                if since in line or line >= since:
                    filtered_since.append(line)
            raw_lines = filtered_since

        # Aplicar grep se informado
        if grep:
            grep_lower = grep.lower()
            raw_lines = [l for l in raw_lines if grep_lower in l.lower()]

        # Sanitizar cada linha
        cleaned_lines = [redact_log_line(l) for l in raw_lines]

        return ops_json(200, {
            "source": source,
            "count": len(cleaned_lines),
            "lines": cleaned_lines,
            "generated_at": generated_at,
        })

    # 4. Rota de Visao SQL Fixa (view)
    assert view is not None
    view_name = view.strip().lower()

    if days is not None and view_name not in OPS_OBSERVE_DAYS_VIEWS:
        return ops_json(400, {"error": f"View '{view_name}' does not accept 'days' parameter"})

    view_fn = OPS_OBSERVE_VIEWS.get(view_name)
    if not view_fn:
        return ops_json(400, {
            "error": f"Unknown view: '{view_name}'",
            "available_views": sorted(list(OPS_OBSERVE_VIEWS.keys())),
        })

    try:
        data = await view_fn(days=days, project_id=project_id)
        return ops_json(200, {
            "view": view_name,
            "project_id": project_id,
            "rows": data,
            "generated_at": generated_at,
        })
    except Exception as e:
        logger.exception("ops_observe_view_failed view=%s", view_name)
        return ops_json(500, {
            "view": view_name,
            "error": "Query execution failed or timed out",
            "generated_at": generated_at,
        })
