import os
from unittest.mock import patch, AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ops.redact import redact_log_line
from app.ops.views import OPS_OBSERVE_VIEWS

client = TestClient(app)

TEST_TOKEN = "a" * 32  # 32 characters


def test_redact_log_line():
    # Secrets
    assert redact_log_line("Bearer secret_token_12345") == "[redacted]"
    assert redact_log_line("Using key itcs_myproject_abcdef12345") == "Using key [redacted]"
    assert redact_log_line("OpenAI key sk-1234567890abcdef") == "OpenAI key [redacted]"
    assert redact_log_line("Connect postgresql://user:pass@localhost:5432/db") == "Connect [redacted]"
    
    # Personal contacts
    assert redact_log_line("Contact test.user@example.com for help") == "Contact [email] for help"
    assert redact_log_line("Call +55 11 99123-4567 or 11987654321") == "Call [telefone] or [telefone]"
    assert redact_log_line("Document 12345678901") == "Document [documento]"


def test_ops_observe_auth_hidden():
    # Sem token -> 404 vazio
    r = client.get("/api/ops/observe")
    assert r.status_code == 404
    assert r.headers.get("cache-control") == "no-store"
    assert r.text == ""

    # Token curto -> 404 vazio
    r = client.get("/api/ops/observe", headers={"Authorization": "Bearer short"})
    assert r.status_code == 404
    assert r.text == ""

    # Token errado -> 404 vazio
    with patch("app.config.settings.ops_observe_token", TEST_TOKEN):
        r = client.get("/api/ops/observe", headers={"Authorization": "Bearer wrong_token_that_is_long_enough_32ch"})
        assert r.status_code == 404
        assert r.text == ""


def test_ops_observe_source_or_view_required():
    with patch("app.config.settings.ops_observe_token", TEST_TOKEN):
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        # Nem source nem view -> 400
        r = client.get("/api/ops/observe", headers=headers)
        assert r.status_code == 400

        # Ambos source e view -> 400
        r = client.get("/api/ops/observe?source=api&view=schema", headers=headers)
        assert r.status_code == 400


def test_ops_observe_source_log(tmp_path):
    log_file = tmp_path / "api.log"
    log_file.write_text("2026-11-10 06:00:00 INFO normal line\n2026-11-10 06:01:00 ERROR itcs_secret_key phone 11999998888\n")

    with patch("app.config.settings.ops_observe_token", TEST_TOKEN), \
         patch("app.api.ops_observe._resolve_source_path", return_value=log_file):
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        r = client.get("/api/ops/observe?source=api&lines=10", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "api"
        assert len(data["lines"]) == 2
        assert "[redacted]" in data["lines"][1]
        assert "[telefone]" in data["lines"][1]


@pytest.mark.asyncio
async def test_ops_observe_views_no_personal_columns_in_select():
    """Garante que nenhuma view selecione colunas proibidas de dados pessoais."""
    banned = {"user_id", "email", "phone", "telefone", "cpf", "name", "nome", "birth_date"}
    import inspect
    import app.ops.views as views_module

    source = inspect.getsource(views_module)
    # Procurar selects
    import re
    selects = re.findall(r"SELECT\s+([\s\S]+?)\s+FROM", source, re.IGNORECASE)
    for sel in selects:
        tokens = [t.strip().strip('"').lower() for t in re.split(r"[\s,]+", sel)]
        for t in tokens:
            col = t.split(".")[-1]
            assert col not in banned, f"Banned column '{col}' found in view SELECT: {sel}"
