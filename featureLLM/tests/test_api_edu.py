"""Tests for Educational API (/edu/*)."""
import json

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

HEADERS = {"Authorization": "Bearer test-token"}

@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield

@pytest.mark.asyncio
async def test_edu_chat_plain_text_triggers_retry_then_structured_fallback(client):
    """Invalid model output twice → canned structured segment so UI toggles still work."""
    with patch("app.edu.db.vocab_list", new_callable=AsyncMock) as m_vocab:
        m_vocab.return_value = ([], 0)
        with patch("app.edu.db.grammar_list", new_callable=AsyncMock) as m_grammar:
            m_grammar.return_value = ([], 0)

            calls: list[str] = []

            async def fake_to_thread(func, *_a, **_kw):
                calls.append(func.__name__)
                return {"message": {"content": "Olá! Sou seu tutor de Mandarim."}}

            with patch("app.api.edu.asyncio.to_thread", side_effect=fake_to_thread):
                body = {
                    "message": "Oi tutor!",
                    "level": "HSK1",
                    "language": "zh-CN",
                }
                r = await client.post("/edu/chat", json=body, headers=HEADERS)
                assert r.status_code == 200
                data = r.json()
                assert data.get("reply_structured") is not None
                assert len(data["reply_structured"]) == 1
                assert data["reply_structured"][0]["hanzi"] == "请稍后再试。"
                assert "Não consegui preparar" in data["reply_structured"][0]["translation"]["pt"]
                assert data["full_reply_text"] == "请稍后再试。"
                assert data["reply"] == "请稍后再试。"
                assert calls.count("chat") == 2


@pytest.mark.asyncio
async def test_edu_chat_structured_response(client):
    payload = {
        "reply_structured": [
            {
                "hanzi": "你好！",
                "pinyin": "Nǐ hǎo!",
                "translation": {"pt": "Olá!", "en": "Hello!", "es": "¡Hola!"},
            }
        ],
        "full_reply_text": "你好！",
    }

    with patch("app.edu.db.vocab_list", new_callable=AsyncMock) as m_vocab:
        m_vocab.return_value = ([], 0)
        with patch("app.edu.db.grammar_list", new_callable=AsyncMock) as m_grammar:
            m_grammar.return_value = ([], 0)

            async def fake_to_thread(_func, *_a, **_kw):
                return {"message": {"content": json.dumps(payload, ensure_ascii=False)}}

            with patch("app.api.edu.asyncio.to_thread", side_effect=fake_to_thread):
                r = await client.post(
                    "/edu/chat",
                    json={"message": "Oi!", "level": "HSK1", "language": "zh-CN"},
                    headers=HEADERS,
                )
                assert r.status_code == 200
                data = r.json()
                assert data["full_reply_text"] == "你好！"
                assert data["reply"] == "你好！"
                assert len(data["reply_structured"]) == 1
                assert data["reply_structured"][0]["hanzi"] == "你好！"
                assert data["reply_structured"][0]["translation"]["pt"] == "Olá!"


@pytest.mark.asyncio
async def test_edu_chat_retry_then_valid_json(client):
    bad = "not json"
    good = {
        "reply_structured": [
            {
                "hanzi": "好",
                "pinyin": "hǎo",
                "translation": {"pt": "bem", "en": "", "es": ""},
            }
        ],
        "full_reply_text": "好",
    }

    with patch("app.edu.db.vocab_list", new_callable=AsyncMock) as m_vocab:
        m_vocab.return_value = ([], 0)
        with patch("app.edu.db.grammar_list", new_callable=AsyncMock) as m_grammar:
            m_grammar.return_value = ([], 0)

            n = 0

            async def fake_to_thread(func, *_a, **_kw):
                nonlocal n
                n += 1
                if n == 1:
                    return {"message": {"content": bad}}
                return {"message": {"content": json.dumps(good, ensure_ascii=False)}}

            with patch("app.api.edu.asyncio.to_thread", side_effect=fake_to_thread):
                r = await client.post(
                    "/edu/chat",
                    json={"message": "Oi!", "level": "HSK1", "language": "zh-CN"},
                    headers=HEADERS,
                )
                assert r.status_code == 200
                data = r.json()
                assert data["reply"] == "好"
                assert data["reply_structured"][0]["hanzi"] == "好"
                assert n == 2


@pytest.mark.asyncio
async def test_edu_exercise_returns_exercises(client):
    vocab_id = str(uuid4())
    mock_vocab = [{"id": vocab_id, "hanzi": "你好", "pinyin": "nǐ hǎo", "translation": "olá", "level": "HSK1"}]

    with patch("app.edu.db.vocab_list", new_callable=AsyncMock) as m_vocab:
        m_vocab.return_value = (mock_vocab, 1)

        async def fake_to_thread(_func, *_a, **_kw):
            return {"message": {"content": f'[{"{"}"type": "translation", "prompt": "Traduza: 你好", "answer": "Olá", "vocab_id": "{vocab_id}"{"}"}]'}}

        with patch("app.api.edu.asyncio.to_thread", side_effect=fake_to_thread):
            body = {
                "level": "HSK1",
                "count": 1,
                "exercise_types": ["translation"]
            }
            r = await client.post("/edu/exercise", json=body, headers=HEADERS)
            assert r.status_code == 200
            data = r.json()
            assert len(data["exercises"]) == 1
            assert data["exercises"][0]["type"] == "translation"
            assert data["exercises"][0]["vocab_id"] == vocab_id

@pytest.mark.asyncio
async def test_vocabulary_crud(client):
    vocab_id = str(uuid4())
    mock_item = {
        "id": vocab_id, "hanzi": "谢谢", "pinyin": "xièxie", "translation": "obrigado",
        "level": "HSK1", "category": "expressão", "example_sentence": "谢谢老师",
        "example_pinyin": "Xièxie lǎoshī", "example_translation": "Obrigado professor",
        "created_at": "2026-04-03T00:00:00Z"
    }

    # Test List
    with patch("app.edu.db.vocab_list", new_callable=AsyncMock) as m_list:
        m_list.return_value = ([mock_item], 1)
        r = await client.get("/edu/vocabulary?level=HSK1", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["hanzi"] == "谢谢"

    # Test Create
    with patch("app.edu.db.vocab_create", new_callable=AsyncMock) as m_create:
        m_create.return_value = mock_item
        body = {
            "hanzi": "谢谢", "pinyin": "xièxie", "translation": "obrigado", "level": "HSK1"
        }
        r = await client.post("/edu/vocabulary", json=body, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["id"] == vocab_id

@pytest.mark.asyncio
async def test_progress_record(client):
    vocab_id = str(uuid4())
    mock_progress = {
        "user_id": "user1", "vocab_id": vocab_id, "seen_count": 1,
        "correct_count": 1, "mastered": False
    }

    with patch("app.edu.db.progress_upsert", new_callable=AsyncMock) as m_upsert:
        m_upsert.return_value = mock_progress
        body = {
            "user_id": "user1",
            "vocab_id": vocab_id,
            "correct": True
        }
        r = await client.post("/edu/progress", json=body, headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["correct_count"] == 1
        assert data["user_id"] == "user1"
