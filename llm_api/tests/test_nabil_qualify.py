"""Unit tests for POST /nabilvideomap/qualify-caption (validation, retries, no Ollama in CI)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.api import nabil_qualify as nq
from app.config import Settings


HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield

_MINIMAL_PROJECT = {
    "project_id": "nabilvideomap",
    "name": "nabil",
    "sources": [],
    "config_json": {},
}

_VALID_LLM = {
    "location_accuracy": "CLEAR",
    "location_granularity": "Neighborhood",
    "location_primary_label": "Centro",
    "llm_location_candidates": [{"label": "Centro", "kind": "neighborhood", "confidence": 0.9}],
    "location_ambiguity_notes": "",
    "location_confidence": 0.85,
    "theme_primary": "mobilidade",
    "theme_secondary": "",
    "theme_tags": "bike, sp",
    "llm_theme_notes": "",
    "summary_140": "Resumo curto em português.",
}


def test_truncate_codepoints_respects_length():
    s = "a" * 200 + "é"  # é is one codepoint
    out = nq._truncate_codepoints(s, 140)
    assert len(out) == 140


def test_user_prompt_uses_legenda_label_not_caption():
    u = nq._user_prompt("texto da publicação", None, None)
    assert u.startswith("Legenda:\n")
    assert "Caption:" not in u
    assert "A legenda discute" in u or "proibido começar" in u


def test_system_prompt_bans_meta_llm_theme_notes_openers():
    s = nq._system_prompt()
    assert "llm_theme_notes" in s
    assert "A legenda discute" in s
    assert "FORBIDDEN" in s
    assert "Variety" in s or "syntactic" in s


def test_nabil_qualify_effective_temperature_clamped():
    assert Settings(nabil_qualify_temperature=0.01).nabil_qualify_effective_temperature() == 0.1
    assert Settings(nabil_qualify_temperature=2.0).nabil_qualify_effective_temperature() == 0.85
    assert Settings(nabil_qualify_temperature=0.42).nabil_qualify_effective_temperature() == 0.42


def test_try_build_response_accepts_enum_case_insensitive():
    raw = dict(_VALID_LLM)
    raw["location_accuracy"] = "PARTIAL"
    raw["location_granularity"] = "POI"
    built, errs = nq._try_build_response(raw)
    assert not errs
    assert built is not None
    assert built.location_accuracy == "partial"
    assert built.location_granularity == "poi"


def test_try_build_response_rejects_bad_enum():
    built, errs = nq._try_build_response({**_VALID_LLM, "location_accuracy": "nope"})
    assert built is None
    assert any("location_accuracy" in e for e in errs)


def test_parse_candidates_invalid_string_returns_empty_and_note():
    lst, note = nq._parse_candidates_raw("not json {")
    assert lst == []
    assert "invalid JSON" in note.lower() or "normalized" in note.lower()


def test_parse_candidates_accepts_json_string():
    raw = '[{"label":"X","kind":"zone","confidence":0.5}]'
    lst, _ = nq._parse_candidates_raw(raw)
    assert len(lst) == 1
    assert lst[0]["kind"] == "zone"


@pytest.mark.asyncio
async def test_qualify_caption_404_when_project_missing(client):
    with patch("app.api.nabil_qualify.get_project", new_callable=AsyncMock, return_value=None), patch(
        "app.api.nabil_qualify.db_module.job_insert_terminal_audit", new_callable=AsyncMock
    ) as audit:
        r = await client.post(
            "/nabilvideomap/qualify-caption",
            json={"project_id": "ghost", "text": "uma legenda"},
            headers=HEADERS,
        )
    assert r.status_code == 404
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_qualify_caption_422_after_retries_bad_json(client):
    async def bad_chat(*_a, **_kw):
        return "not json at all"

    with patch("app.api.nabil_qualify.get_project", new_callable=AsyncMock, return_value=_MINIMAL_PROJECT), patch(
        "app.api.nabil_qualify._ollama_chat", side_effect=bad_chat
    ), patch("app.api.nabil_qualify.db_module.job_insert_terminal_audit", new_callable=AsyncMock) as audit:
        r = await client.post(
            "/nabilvideomap/qualify-caption",
            json={"project_id": "nabilvideomap", "text": "legenda"},
            headers=HEADERS,
        )
    assert r.status_code == 422
    assert "qualify_schema_retry_exhausted" in r.json().get("detail", "")
    assert audit.await_count == 1


@pytest.mark.asyncio
async def test_qualify_caption_success_writes_terminal_audit_job(client):
    good = (
        '{"location_accuracy":"clear","location_granularity":"none",'
        '"location_primary_label":"","llm_location_candidates":[],"location_ambiguity_notes":"",'
        '"location_confidence":null,"theme_primary":"","theme_secondary":"","theme_tags":"",'
        '"llm_theme_notes":"","summary_140":"ok"}'
    )

    async def one_good(*_a, **_kw):
        return good

    with patch("app.api.nabil_qualify.get_project", new_callable=AsyncMock, return_value=_MINIMAL_PROJECT), patch(
        "app.api.nabil_qualify._ollama_chat", side_effect=one_good
    ), patch("app.api.nabil_qualify.db_module.job_insert_terminal_audit", new_callable=AsyncMock) as audit:
        r = await client.post(
            "/nabilvideomap/qualify-caption",
            json={"project_id": "nabilvideomap", "text": "legenda curta"},
            headers=HEADERS,
        )
    assert r.status_code == 200
    audit.assert_awaited_once()
    kw = audit.await_args.kwargs
    assert kw.get("status") == "done"
    assert kw.get("job_kind") == "nabil_qualify_caption"


@pytest.mark.asyncio
async def test_qualify_caption_200_second_attempt_valid(client):
    calls: list[int] = []

    async def flaky_chat(*_a, **_kw):
        calls.append(1)
        if len(calls) == 1:
            return '{"location_accuracy": "clear"'  # truncated / invalid
        return (
            '{"location_accuracy":"clear","location_granularity":"citywide",'
            '"location_primary_label":"","llm_location_candidates":[],"location_ambiguity_notes":"",'
            '"location_confidence":null,"theme_primary":"t","theme_secondary":"","theme_tags":"",'
            '"llm_theme_notes":"","summary_140":"ok"}'
        )

    with patch("app.api.nabil_qualify.get_project", new_callable=AsyncMock, return_value=_MINIMAL_PROJECT), patch(
        "app.api.nabil_qualify._ollama_chat", side_effect=flaky_chat
    ), patch("app.api.nabil_qualify.db_module.job_insert_terminal_audit", new_callable=AsyncMock):
        r = await client.post(
            "/nabilvideomap/qualify-caption",
            json={"project_id": "nabilvideomap", "text": "legenda"},
            headers=HEADERS,
        )
    assert r.status_code == 200
    data = r.json()
    assert data["location_accuracy"] == "clear"
    assert data["location_granularity"] == "citywide"
    assert data["llm_location_candidates"] == []
    assert data["location_confidence"] is None
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_qualify_caption_503_on_ollama_infra(client):
    async def boom(*_a, **_kw):
        raise nq.OllamaQualifyInfraError("ollama_error: connection refused")

    with patch("app.api.nabil_qualify.get_project", new_callable=AsyncMock, return_value=_MINIMAL_PROJECT), patch(
        "app.api.nabil_qualify._ollama_chat", side_effect=boom
    ), patch("app.api.nabil_qualify.db_module.job_insert_terminal_audit", new_callable=AsyncMock) as audit:
        r = await client.post(
            "/nabilvideomap/qualify-caption",
            json={"project_id": "nabilvideomap", "text": "legenda"},
            headers=HEADERS,
        )
    assert r.status_code == 503
    assert "ollama_error" in r.json().get("detail", "")
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_qualify_caption_use_rag_builds_block(client):
    good = (
        '{"location_accuracy":"weak","location_granularity":"unknown",'
        '"location_primary_label":"","llm_location_candidates":[],"location_ambiguity_notes":"",'
        '"location_confidence":null,"theme_primary":"","theme_secondary":"","theme_tags":"",'
        '"llm_theme_notes":"","summary_140":"x"}'
    )

    async def one_good(*_a, **_kw):
        return good

    with patch("app.api.nabil_qualify.get_project", new_callable=AsyncMock, return_value=_MINIMAL_PROJECT), patch(
        "app.api.nabil_qualify._build_rag_block", new_callable=AsyncMock
    ) as m_rag, patch("app.api.nabil_qualify._ollama_chat", side_effect=one_good), patch(
        "app.api.nabil_qualify.db_module.job_insert_terminal_audit", new_callable=AsyncMock
    ):
        m_rag.return_value = "[doc.md]\nTrecho do índice."
        r = await client.post(
            "/nabilvideomap/qualify-caption",
            json={"project_id": "nabilvideomap", "text": "legenda", "use_rag": True},
            headers=HEADERS,
        )
    assert r.status_code == 200
    m_rag.assert_awaited_once()
