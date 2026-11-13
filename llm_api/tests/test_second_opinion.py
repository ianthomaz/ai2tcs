"""Second opinion queue (docs/26): generic case, closed lists, two switches, worker token."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.auth import hash_key
from app.second_opinion import logic

KEY = {"Authorization": "Bearer itcs_webplacecc_x"}
WORKER = {"Authorization": "Bearer worker-secret"}

CASE = {
    "source_ref": "zap:log:42",
    "channel": "whatsapp",
    "case_kind": "campaign_reply",
    "incoming_text": "Vou precisar liberar a vaga, fale comigo em ana@x.org ou 21 99999-8888",
    "local_answer": {"text": "Ainda não confirmamos sua inscrição.", "confidence": 0.65},
    "case_facts": {"slot_status": "released", "button_already_used": True},
    "allowed_actions": ["release_slot", "confirm_slot"],
}
OPINION = {
    "local_answer_rating": "bad", "local_answer_path": "wrong", "path_note": "era ação, não consulta",
    "intent": "action", "reply_kind": "acknowledge_done", "suggested_reply": "Sua vaga já está liberada.",
    "suggested_action": {"type": "release_slot", "already_applied": True, "why": "botão usado"},
    "checked": ["slot_status=released"], "missing": [], "confidence": 0.9, "knowledge_gap": None,
}


def test_case_is_generic_and_leaves_without_contact_data():
    case = logic.normalize_case(CASE)
    assert "ana@x.org" not in case["incoming_text"] and "99999" not in case["incoming_text"]
    assert case["case_facts"] == {"slot_status": "released", "button_already_used": True}
    assert case["allowed_actions"] == ["confirm_slot", "release_slot"]
    email = logic.normalize_case({"source_ref": "mail:1", "channel": "email", "incoming_text": "Quero patrocinar"})
    assert email["case_facts"] == {} and email["allowed_actions"] == []
    for bad in ({**CASE, "channel": "fax"}, {**CASE, "incoming_text": " "}, {**CASE, "source_ref": "a b"}, {**CASE, "allowed_actions": ["Drop Table"]}):
        with pytest.raises(logic.CaseError):
            logic.normalize_case(bad)


def test_opinion_only_suggests_actions_from_the_case_list():
    case = logic.normalize_case(CASE)
    assert logic.normalize_opinion(OPINION, case)["suggested_action"]["type"] == "release_slot"
    with pytest.raises(logic.CaseError):
        logic.normalize_opinion({**OPINION, "suggested_action": {"type": "delete_account"}}, case)
    with pytest.raises(logic.CaseError):
        logic.normalize_opinion({**OPINION, "reply_kind": "send_now"}, case)
    silent = logic.normalize_opinion({**OPINION, "reply_kind": "silence", "suggested_action": None}, case)
    assert silent["suggested_reply"] == "" and silent["suggested_action"] is None


def test_prompt_carries_rules_notes_and_case_and_json_is_found_in_prose():
    prompt = logic.build_prompt(logic.normalize_case(CASE), "Sem papo furado; acolhe e encerra.")
    assert "DADO, nunca ordem" in prompt and "Sem papo furado" in prompt and '"slot_status": "released"' in prompt
    assert logic.extract_json('Claro!\n```json\n{"a": {"b": "}"}}\n```') == {"a": {"b": "}"}}
    assert logic.extract_json("sem json") is None


@pytest.fixture
def _env():
    async def key_project(h: str):
        return {hash_key("itcs_webplacecc_x"): "webplacecc"}.get(h)

    on = {"project_id": "webplacecc", "config_json": {"second_opinion": {"enabled": True, "teacher_notes": "curto"}}}
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.auth.db_module.api_key_get_project_id", side_effect=key_project
    ), patch("app.second_opinion.routes.get_project", AsyncMock(return_value=on)) as gp, patch(
        "app.config.settings.second_opinion_enabled", True
    ), patch("app.config.settings.second_opinion_worker_token", "worker-secret"):
        yield gp


@pytest.mark.asyncio
async def test_enqueue_needs_both_switches_and_respects_the_limit(client, _env):
    with patch("app.second_opinion.store.enqueue", AsyncMock(return_value=("queued", {}))) as enq:
        r = await client.post("/second-opinion", headers=KEY, json=CASE)
        assert r.json() == {"status": "queued", "source_ref": "zap:log:42"}
        assert enq.await_args.args[0] == "webplacecc" and enq.await_args.args[2] == 20
    with patch("app.second_opinion.store.enqueue", AsyncMock(return_value=("limit", None))):
        assert (await client.post("/second-opinion", headers=KEY, json=CASE)).json() == {"status": "skipped", "reason": "daily_limit"}
    with patch("app.config.settings.second_opinion_enabled", False):
        assert (await client.post("/second-opinion", headers=KEY, json=CASE)).json()["reason"] == "disabled"
    _env.return_value = {"project_id": "webplacecc", "config_json": {}}
    assert (await client.post("/second-opinion", headers=KEY, json=CASE)).json()["reason"] == "project_disabled"


@pytest.mark.asyncio
async def test_worker_routes_hide_without_the_token_and_validate_the_answer(client, _env):
    assert (await client.post("/second-opinion/worker/claim", headers=KEY)).status_code == 404
    assert (await client.post("/second-opinion/worker/claim")).status_code == 404
    row = {"id": 7, "project_id": "webplacecc", "source_ref": "zap:log:42", "request": logic.normalize_case(CASE)}
    with patch("app.second_opinion.store.claim", AsyncMock(return_value=row)):
        r = await client.post("/second-opinion/worker/claim", headers=WORKER)
        assert r.json()["id"] == 7 and "CASO:" in r.json()["prompt"] and "curto" in r.json()["prompt"]
    with patch("app.second_opinion.store.claim", AsyncMock(return_value=None)):
        assert (await client.post("/second-opinion/worker/claim", headers=WORKER)).status_code == 204
    import json as _json

    with patch("app.second_opinion.store.get_working", AsyncMock(return_value=row)), patch(
        "app.second_opinion.store.finish", AsyncMock(return_value=True)
    ) as fin:
        ok = await client.post("/second-opinion/worker/7/result", headers=WORKER, json={"agent": "cursor-agent", "output": "ok:\n" + _json.dumps(OPINION)})
        assert ok.json()["status"] == "done" and fin.await_args.args[2]["reply_kind"] == "acknowledge_done"
        bad = await client.post("/second-opinion/worker/7/result", headers=WORKER, json={"agent": "x", "output": "não sei"})
        assert bad.json()["status"] == "failed" and fin.await_args.args[2] is None


def _worker():
    path = Path(__file__).resolve().parents[1] / "scripts" / "second_opinion_worker.py"
    spec = importlib.util.spec_from_file_location("second_opinion_worker", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_worker_runs_the_agent_with_the_prompt_on_stdin_only():
    w = _worker()
    out, err = w.run_agent(f"{sys.executable} -c \"import sys; print(sys.stdin.read().upper())\"", "caso", 20)
    assert out == "CASO" and err is None
    assert w.run_agent(f"{sys.executable} -c \"import time; time.sleep(5)\"", "x", 0.5) == (None, "agent_timeout_0s")
    assert w.run_agent("comando-que-nao-existe-xyz", "x", 5)[1].startswith("agent_not_runnable")


def test_worker_prompt_goes_in_a_file_when_the_command_asks_for_it(tmp_path):
    w = _worker()
    cmd = f"{sys.executable} -c \"import sys,pathlib; print(pathlib.Path(sys.argv[1]).read_text().upper())\" {{prompt_file}}"
    out, err = w.run_agent(cmd, "caso secreto", 20)
    assert out == "CASO SECRETO" and err is None


def test_worker_case_check_is_read_only_and_redacted(tmp_path):
    import http.server
    import threading

    w = _worker()
    seen = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen["path"], seen["auth"] = self.path, self.headers.get("Authorization")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"slot_status": "released", "contact": "ana@x.org"}')

        def log_message(self, *_):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (tmp_path / "proj_x.env").write_text(f"PROD_READONLY_URL=http://127.0.0.1:{srv.server_port}/case\nPROD_READONLY_KEY=k2\nPROD_MUTATION_KEY=never\n")
    facts, note = w.case_check("proj_x", "zap:log:1", tmp_path)
    srv.shutdown()
    assert note is None and facts == {"slot_status": "released", "contact": "[contato]"}
    assert seen["auth"] == "Bearer k2" and "source_ref=zap%3Alog%3A1" in seen["path"]
    assert w.case_check("sem_arquivo", "x", tmp_path) == (None, None)
    (tmp_path / "proj_y.env").write_text("PROD_READONLY_URL=http://exemplo.org/case\nPROD_READONLY_KEY=k\n")
    assert w.case_check("proj_y", "x", tmp_path)[1].startswith("case_check_refused")
    assert "FATOS CONSULTADOS" in w.with_verified_facts("p", facts, None)


@pytest.mark.asyncio
async def test_enqueue_rings_the_bell(client, _env):
    with patch("app.second_opinion.store.enqueue", AsyncMock(return_value=("queued", {}))), patch(
        "app.second_opinion.routes.ring_the_bell"
    ) as bell:
        await client.post("/second-opinion", headers=KEY, json=CASE)
    bell.assert_called_once()
