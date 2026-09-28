"""Deterministic guards of the Bike Anjo ops ports, driven by the eval sets in contracts/bikeanjo/.

The eval sets measure the model (a rate, not a unit test). What is here is the part the service
guarantees whatever the model answers: grave is never lost, written health is never erased, a
suggestion never promises or invents a link, the RAG hints order the context.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.bikeanjo import feedback_triage as ft
from app.bikeanjo import health_normalize as hn
from app.bikeanjo import reply_suggest as rs
from app.bikeanjo.common import CONTRACTS_DIR


def _eval(stem: str) -> dict[str, dict]:
    lines = (CONTRACTS_DIR / f"{stem}.eval.jsonl").read_text(encoding="utf-8").splitlines()
    return {c["id"]: c for c in (json.loads(l) for l in lines if l.strip())}


TRIAGE = _eval("feedback-triage")
HEALTH = _eval("health-normalize")
REPLY = _eval("reply-suggest")

_BLAND = {
    "scores": {"text_quality": 3, "information_value": 3, "answer_solidity": 3},
    "tags": ["outro"],
    "urgency": "none",
    "anchor_quote": "",
    "named_people": [],
    "theme_free": None,
    "confidence": 0.5,
}


def _triage_req(case: dict) -> ft.FeedbackTriageRequest:
    return ft.FeedbackTriageRequest(
        source=case.get("source", "eba-feedback"),
        submission_id=case["id"],
        fields=case["fields"],
    )


def _health_req(case: dict) -> hn.HealthNormalizeRequest:
    return hn.HealthNormalizeRequest(
        person={"kind": "user", "id": "AABC4"}, known_codes=case["known_codes"], free_text=case["free_text"]
    )


# ---------------------------------------------------------------- feedbackTriage


@pytest.mark.parametrize("cid", [c for c, v in TRIAGE.items() if "grave" in v["expect"].get("tags_include", [])])
def test_grave_is_kept_even_when_the_model_misses_it(cid):
    out = ft.postprocess(dict(_BLAND), _triage_req(TRIAGE[cid]), "m")
    assert "grave" in out["tags"] and out["urgency"] == "urgent"


def test_grave_from_model_forces_urgent():
    req = _triage_req(TRIAGE["t03"])
    out = ft.postprocess({**_BLAND, "tags": ["grave"], "urgency": "none"}, req, "m")
    assert out["urgency"] == "urgent"


@pytest.mark.parametrize("cid", ["t03", "t10"])
def test_no_grave_invented_on_ordinary_text(cid):
    out = ft.postprocess(dict(_BLAND), _triage_req(TRIAGE[cid]), "m")
    assert "grave" not in out["tags"]


def test_tags_outside_allowlist_are_dropped():
    out = ft.postprocess({**_BLAND, "tags": ["elogio_geral", "urgente!!", "spam"]}, _triage_req(TRIAGE["t05"]), "m")
    assert out["tags"] == ["elogio_geral"]
    assert any(w.startswith("tag_dropped") for w in out["warnings"])


def test_named_person_must_be_in_the_text():
    req = _triage_req(TRIAGE["t04"])
    out = ft.postprocess({**_BLAND, "tags": ["elogio_pessoa"], "named_people": ["Júlia", "Carla"]}, req, "m")
    assert out["named_people"] == ["Júlia"]


def test_elogio_pessoa_without_a_name_becomes_elogio_geral():
    req = _triage_req(TRIAGE["t05"])
    out = ft.postprocess({**_BLAND, "tags": ["elogio_pessoa"], "named_people": ["Ana"]}, req, "m")
    assert out["named_people"] == []
    assert "elogio_pessoa" not in out["tags"] and "elogio_geral" in out["tags"]


def test_anchor_never_carries_the_contact_marker():
    req = _triage_req(TRIAGE["t09"])
    out = ft.postprocess({**_BLAND, "anchor_quote": "Me liga [contato]"}, req, "m")
    assert "[contato]" not in out["anchor_quote"]
    assert out["anchor_quote"] and len(out["anchor_quote"]) <= ft.ANCHOR_MAX


def test_invented_anchor_is_replaced_by_a_real_quote():
    req = _triage_req(TRIAGE["t03"])
    out = ft.postprocess({**_BLAND, "anchor_quote": "a oficina foi péssima"}, req, "m")
    assert out["anchor_quote"].lower() in TRIAGE["t03"]["fields"]["recado_livre"].lower()
    assert "anchor_quote_replaced" in out["warnings"]


def test_model_input_carries_no_person_ids():
    req = ft.FeedbackTriageRequest(
        source="eba-feedback",
        submission_id="812",
        subject={"user_id": "AABC4", "dependent_id": None},
        event_id="C-AA002-A026",
        fields={"recado_livre": "ok"},
    )
    prompt = ft.user_prompt(req)
    assert "AABC4" not in prompt and "812" not in prompt and "C-AA002" not in prompt


def test_missing_scores_ask_the_model_again():
    assert ft.validate_model_output({"scores": {"text_quality": 9}})
    assert not ft.validate_model_output(dict(_BLAND))


# ---------------------------------------------------------------- healthNormalize


@pytest.mark.parametrize(
    "cid", [c for c, v in HEALTH.items() if v["expect"].get("generic_statement") is False]
)
def test_written_health_is_never_erased(cid):
    """The rule that cannot fail: the model says generic, the text names something → kept."""
    case = HEALTH[cid]
    wrong = {"codes": [], "outras": None, "generic_statement": True, "changed": True, "confidence": 0.9}
    out = hn.postprocess(wrong, _health_req(case), case["known_codes"], "m")
    assert out["generic_statement"] is False
    assert out["codes"] or out["outras"]


@pytest.mark.parametrize("cid", ["h05", "h06"])
def test_generic_statement_is_honoured_when_the_text_is_generic(cid):
    case = HEALTH[cid]
    ok = {"codes": [], "outras": None, "generic_statement": True, "changed": True, "confidence": 0.9}
    out = hn.postprocess(ok, _health_req(case), [], "m")
    assert out["generic_statement"] is True and out["outras"] is None and out["codes"] == []


def test_code_outside_allowlist_goes_to_outras():
    case = HEALTH["h08"]
    out = hn.postprocess(
        {"codes": ["epilepsy"], "outras": None, "generic_statement": False}, _health_req(case), [], "m"
    )
    assert out["codes"] == [] and "epilepsy" in out["outras"]


def test_outras_follows_the_comparison_standard():
    assert hn.clean_outras("labirintite, enxaqueca e labirintite") == "labirintite, enxaqueca"
    assert hn.clean_outras("Tenho epilepsia desde criança") == "epilepsia desde criança"


def test_nothing_mapped_keeps_the_person_text():
    case = HEALTH["h03"]
    out = hn.postprocess({"codes": [], "outras": None, "generic_statement": False}, _health_req(case), [], "m")
    assert out["outras"] == "bronquite"


def test_health_model_input_has_no_person_id():
    req = hn.HealthNormalizeRequest(person={"kind": "user", "id": "AABC4"}, free_text="asma")
    assert "AABC4" not in hn.user_prompt(req, [])


# ---------------------------------------------------------------- replySuggest


def _reply_req(case: dict) -> rs.ReplySuggestRequest:
    return rs.ReplySuggestRequest(ticket_id=case["id"], channel="site", subject=case["subject"], message=case["message"])


@pytest.mark.asyncio
@pytest.mark.parametrize("cid", [c for c, v in REPLY.items() if v["expect"].get("no_answer") is True])
async def test_grave_ticket_never_reaches_the_model(cid):
    chat = AsyncMock()
    with patch("app.bikeanjo.reply_suggest.chat_json", chat), patch(
        "app.bikeanjo.reply_suggest.retrieve", new_callable=AsyncMock
    ) as ret:
        out = await rs.run(_reply_req(REPLY[cid]), "bikeanjoall_2026", {"config_json": {}})
    assert out["no_answer"] is True and out["suggested_reply"] == ""
    chat.assert_not_called()
    ret.assert_not_called()


@pytest.mark.parametrize(
    "reply",
    [
        "Pronto, já excluí sua conta.",
        "Sua conta foi excluída com sucesso.",
        "Vou te enviar o link amanhã.",
        "Já atualizei seu cadastro.",
        "Acesse https://bikeanjo.org/cadastro?magic=abc",
        "Inscreva-se em https://bit.ly/ba-sp",
        "Veja em https://inscricao-sp.com.br",
        "Veja em https://bikeanjo.org.golpe.com/sp",
        "Veja em https://naobikeanjo.org",
        "Escreva para fulano@gmail.com",
        "Ligue (11) 91234-5678",
    ],
)
def test_suggestion_that_promises_or_invents_is_blocked(reply):
    chunks = [{"path": "bibliotecaConteudoLLM/34_suporte_chamados_rascunho.md"}]
    out = rs.postprocess({"suggested_reply": reply, "no_answer": False, "sources": []}, chunks, "m")
    assert out["no_answer"] is True and out["suggested_reply"] == ""
    assert any(w.startswith("blocked:") for w in out["warnings"])


@pytest.mark.parametrize(
    "reply",
    [
        "Obrigado pelo contato! As datas das aulas ficam em https://bikeanjo.org.",
        "Complete seu cadastro em https://cadastro.bikeanjo.org e escreva para contato@bikeanjo.org.",
        "Veja a agenda em https://eventos.bikeanjo.org/sp.",
    ],
)
def test_canonical_links_are_allowed(reply):
    chunks = [{"path": "bibliotecaConteudoLLM/09_contato_e_parcerias.md"}]
    out = rs.postprocess({"suggested_reply": reply, "no_answer": False, "sources": ["09_contato_e_parcerias"]}, chunks, "m")
    assert out["no_answer"] is False and out["sources"] == ["09_contato_e_parcerias"]


def test_sources_are_limited_to_what_was_retrieved():
    chunks = [{"path": "bibliotecaConteudoLLM/34_suporte_chamados_rascunho.md"}]
    out = rs.postprocess(
        {"suggested_reply": "Obrigado!", "no_answer": False, "sources": ["99_inventado", "34_suporte_chamados_rascunho"]},
        chunks,
        "m",
    )
    assert out["sources"] == ["34_suporte_chamados_rascunho"]


def test_hints_boost_support_docs_and_downrank_statute_and_zap_maps():
    chunks = [
        {"path": "bibliotecaConteudoLLM/22_estatuto_2025_transcricao.md", "distance": 0.50},
        {"path": "mapaFluxosLLM/04_mapa_quero_pedalar_cep.md", "distance": 0.51},
        {"path": "bibliotecaConteudoLLM/34_suporte_chamados_rascunho.md", "distance": 0.60},
        {"path": "bibliotecaConteudoLLM/12_neutro.md", "distance": 0.55},
    ]
    order = [rs.doc_name(c["path"]) for c in rs.apply_port_hints(chunks)]
    assert order[0] == "34_suporte_chamados_rascunho"
    assert order[-2:] == ["22_estatuto_2025_transcricao", "04_mapa_quero_pedalar_cep"]


@pytest.mark.asyncio
async def test_no_context_is_no_answer_without_calling_the_model():
    chat = AsyncMock()
    with patch("app.bikeanjo.reply_suggest.chat_json", chat), patch(
        "app.bikeanjo.reply_suggest.retrieve", new_callable=AsyncMock, return_value=[]
    ):
        out = await rs.run(_reply_req(REPLY["r05"]), "bikeanjoall_2026", {"config_json": {}})
    assert out["no_answer"] is True and "no_context" in out["warnings"]
    chat.assert_not_called()
