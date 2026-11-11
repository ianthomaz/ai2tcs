"""Controle de acesso e respostas de seguranca para /api/ops/observe.

Sem sessao: a chave e o Bearer `OPS_OBSERVE_TOKEN` (>= 32 caracteres).
Chave ausente, curta ou incorreta devolve HTTP 404 vazio com Cache-Control: no-store,
como se a rota nao existisse (stealth mode).
Tentativas invalidas sao registradas em log de seguranca.
"""
import hmac
import logging
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger("app.ops.observe")


def ops_no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


def ops_hidden() -> Response:
    """Devolve 404 de corpo vazio sem denunciar a porta."""
    return ops_no_store(Response(content=None, status_code=404, media_type="text/plain"))


def ops_json(status_code: int, content: dict) -> Response:
    """Resposta JSON sem cache."""
    return ops_no_store(JSONResponse(status_code=status_code, content=content))


def configured_token() -> str | None:
    token = settings.ops_observe_token.strip()
    if len(token) < 32:
        return None
    return token


def ops_observe_check(request: Request) -> bool:
    """Verifica se o Bearer token confere com OPS_OBSERVE_TOKEN em tempo constante."""
    expected = configured_token()
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    if not expected:
        logger.warning("ops_observe_attempt_rejected reason=not_configured client_ip=%s", client_ip)
        return False

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("ops_observe_attempt_rejected reason=missing_or_bad_bearer client_ip=%s", client_ip)
        return False

    token = auth_header[7:].strip()
    if len(token) < 32:
        logger.warning("ops_observe_attempt_rejected reason=token_too_short client_ip=%s", client_ip)
        return False

    if not hmac.compare_digest(token.encode(), expected.encode()):
        logger.warning("ops_observe_attempt_rejected reason=invalid_token client_ip=%s", client_ip)
        return False

    return True
