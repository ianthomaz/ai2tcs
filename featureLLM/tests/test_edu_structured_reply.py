"""Unit tests for edu structured JSON reply parsing."""
import json

import pytest

from app.edu.structured_reply import parse_edu_chat_response, structured_reply_valid


def test_parse_valid_json():
    payload = {
        "reply_structured": [
            {
                "hanzi": "你好！",
                "pinyin": "Nǐ hǎo!",
                "translation": {"pt": "Olá!", "en": "Hello!", "es": "¡Hola!"},
            },
            {
                "hanzi": "你想学习什么？",
                "pinyin": "Nǐ xiǎng xuéxí shénme?",
                "translation": {
                    "pt": "O que você quer estudar?",
                    "en": "What do you want to study?",
                    "es": "¿Qué quieres estudiar?",
                },
            },
        ],
        "full_reply_text": "你好！你想学习什么？",
    }
    raw = json.dumps(payload, ensure_ascii=False)
    p = parse_edu_chat_response(raw)
    assert p.reply_structured is not None
    assert len(p.reply_structured) == 2
    assert p.full_reply_text == "你好！你想学习什么？"
    assert p.reply == "你好！你想学习什么？"


def test_parse_json_in_markdown_fence():
    payload = {"reply_structured": [{"hanzi": "好", "pinyin": "hǎo", "translation": {"pt": "bem", "en": "good", "es": "bien"}}], "full_reply_text": "好"}
    inner = json.dumps(payload, ensure_ascii=False)
    raw = f"```json\n{inner}\n```"
    p = parse_edu_chat_response(raw)
    assert p.reply_structured is not None
    assert len(p.reply_structured) == 1


def test_parse_plain_text_fallback():
    p = parse_edu_chat_response("Just a sentence without JSON.")
    assert p.reply_structured is None
    assert p.full_reply_text is None
    assert p.reply == "Just a sentence without JSON."


def test_parse_fills_full_reply_from_segments_if_missing():
    payload = {
        "reply_structured": [
            {"hanzi": "A", "pinyin": "a", "translation": {"pt": "a", "en": "a", "es": "a"}},
            {"hanzi": "B", "pinyin": "b", "translation": {"pt": "b", "en": "b", "es": "b"}},
        ]
    }
    p = parse_edu_chat_response(json.dumps(payload))
    assert p.full_reply_text == "AB"
    assert p.reply == "AB"


@pytest.mark.parametrize(
    "translation_raw,expected_pt",
    [
        ({"pt": "x", "en": "y", "es": "z"}, "x"),
        ("only one string", "only one string"),
    ],
)
def test_translation_normalization(translation_raw, expected_pt):
    payload = {
        "reply_structured": [{"hanzi": "字", "pinyin": "zì", "translation": translation_raw}],
    }
    p = parse_edu_chat_response(json.dumps(payload))
    assert p.reply_structured is not None
    assert p.reply_structured[0]["translation"]["pt"] == expected_pt


def test_structured_reply_valid_requires_pinyin_and_pt():
    p = parse_edu_chat_response(
        json.dumps(
            {
                "reply_structured": [
                    {"hanzi": "好", "pinyin": "", "translation": {"pt": "ok", "en": "", "es": ""}},
                ],
                "full_reply_text": "好",
            }
        )
    )
    assert not structured_reply_valid(p)

    p2 = parse_edu_chat_response(
        json.dumps(
            {
                "reply_structured": [
                    {"hanzi": "好", "pinyin": "hǎo", "translation": {"pt": "", "en": "", "es": ""}},
                ],
                "full_reply_text": "好",
            }
        )
    )
    assert not structured_reply_valid(p2)

    p3 = parse_edu_chat_response(
        json.dumps(
            {
                "reply_structured": [
                    {"hanzi": "好", "pinyin": "hǎo", "translation": {"pt": "bem", "en": "", "es": ""}},
                ],
                "full_reply_text": "好",
            }
        )
    )
    assert structured_reply_valid(p3)


def test_structured_reply_valid_rejects_plain_parse():
    p = parse_edu_chat_response("hello")
    assert not structured_reply_valid(p)
