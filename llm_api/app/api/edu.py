"""POST /edu/* routes for Educational API (sync Ollama)."""
import asyncio
import logging
import time

import ollama
from fastapi import APIRouter, Depends, HTTPException
from app.auth import require_token
from app.config import settings
from app.edu.chat_fallback import fallback_structured_parse
from app.models import (
    VocabularyItem,
    VocabularyCreateRequest,
    VocabularyListResponse,
    GrammarPoint,
    GrammarCreateRequest,
    GrammarListResponse,
    EduChatRequest,
    EduChatResponse,
    EduChatSegment,
    EduTranslationBlock,
    ExerciseRequest,
    ExerciseResponse,
    ProgressRecordRequest,
    ProgressRecordResponse,
)
from app.edu import db as edu_db
from app.edu import exercises as edu_exercises
from app.edu import prompt as edu_prompt
from app.edu.structured_reply import (
    json_retry_user_message,
    parse_edu_chat_response,
    structured_reply_valid,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/edu", tags=["edu"])


async def _ollama_edu_chat(
    messages: list, model_name: str, temperature: float, num_predict: int
) -> str:
    response = await asyncio.to_thread(
        ollama.chat,
        model=model_name,
        messages=messages,
        options={"temperature": temperature, "num_predict": num_predict},
    )
    return (response.get("message") or {}).get("content") or ""


def _to_edu_response(
    language: str, parsed
) -> EduChatResponse:
    segments = [
        EduChatSegment(
            hanzi=s["hanzi"],
            pinyin=s["pinyin"],
            translation=EduTranslationBlock(**s["translation"]),
        )
        for s in (parsed.reply_structured or [])
    ]
    return EduChatResponse(
        reply=parsed.reply,
        language=language,
        reply_structured=segments if segments else None,
        full_reply_text=parsed.full_reply_text,
    )

@router.post("/chat", response_model=EduChatResponse)
async def edu_chat(request: EduChatRequest, _: None = Depends(require_token)):
    # 1. Fetch relevant vocabulary and grammar points for the level
    vocab_items, _ = await edu_db.vocab_list(language=request.language, level=request.level, limit=8)
    grammar_items, _ = await edu_db.grammar_list(
        language=request.language, level=request.level, limit=8
    )

    # 2. Build messages
    messages = edu_prompt.build_edu_chat_messages(
        message=request.message,
        level=request.level or "HSK1",
        history=[{"role": t.role, "content": t.text} for t in request.history] if request.history else [],
        vocab_items=vocab_items,
        grammar_points=grammar_items
    )

    default_alias = (settings.edu_chat_default_model_alias or "fast").strip().lower()
    if default_alias not in ("fast", "compact", "smart", "reasoner"):
        default_alias = "fast"
    model_name = settings.get_model_name(request.model, default_alias=default_alias)
    np = max(64, min(settings.edu_chat_num_predict, 4096))
    np_retry = max(64, min(settings.edu_chat_retry_num_predict, 4096))
    t0 = time.perf_counter()
    try:
        content = await _ollama_edu_chat(
            messages,
            model_name,
            temperature=settings.edu_chat_temperature,
            num_predict=np,
        )
        parsed = parse_edu_chat_response(content)
        retry_used = False
        if not structured_reply_valid(parsed):
            retry_used = True
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {"role": "user", "content": json_retry_user_message()},
            ]
            content = await _ollama_edu_chat(
                repair_messages,
                model_name,
                temperature=settings.edu_chat_retry_temperature,
                num_predict=np_retry,
            )
            parsed = parse_edu_chat_response(content)
        fallback_used = False
        if not structured_reply_valid(parsed):
            fallback_used = True
            parsed = fallback_structured_parse()
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        n_seg = len(parsed.reply_structured or [])
        logger.info(
            "edu_chat level=%s segments=%d retry=%s fallback=%s ms=%d",
            request.level or "(default)",
            n_seg,
            retry_used,
            fallback_used,
            elapsed_ms,
        )
        return _to_edu_response(request.language, parsed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/exercise", response_model=ExerciseResponse)
async def edu_exercise(request: ExerciseRequest, _: None = Depends(require_token)):
    # 1. Fetch vocabulary items
    if request.vocab_ids:
        vocab_items = await edu_db.vocab_get_many(request.vocab_ids)
    else:
        # Fallback to level-based vocabulary
        vocab_items, _ = await edu_db.vocab_list(language=request.language, level=request.level, limit=20)

    if not vocab_items:
        raise HTTPException(status_code=400, detail="No vocabulary found for the specified level/IDs.")

    # 2. Build prompt
    messages = edu_prompt.build_exercise_messages(
        vocab_items=vocab_items,
        exercise_types=request.exercise_types,
        count=request.count,
        level=request.level
    )

    # 3. Call Ollama
    try:
        response = await asyncio.to_thread(
            ollama.chat,
            model=settings.get_model_name(request.model, default_alias="smart"),
            messages=messages,
            options={"temperature": 0.3, "num_predict": 1024}
        )
        content = (response.get("message") or {}).get("content") or ""

        # 4. Parse exercises
        parsed = edu_exercises.parse_exercises(content, vocab_ids=[str(v["id"]) for v in vocab_items])

        return ExerciseResponse(
            language=request.language,
            level=request.level,
            exercises=parsed,
            count=len(parsed)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/vocabulary", response_model=VocabularyListResponse)
async def list_vocabulary(
    language: str = "zh-CN", level: str = None, limit: int = 50, offset: int = 0,
    _: None = Depends(require_token)
):
    items, total = await edu_db.vocab_list(language, level, limit, offset)
    # Map from DB dict to Pydantic model
    return VocabularyListResponse(
        items=[VocabularyItem(**{k: str(v) if k == 'id' else v for k, v in item.items()}) for item in items],
        total=total
    )

@router.post("/vocabulary", response_model=VocabularyItem)
async def create_vocabulary(request: VocabularyCreateRequest, _: None = Depends(require_token)):
    item = await edu_db.vocab_create(request.model_dump())
    return VocabularyItem(**{k: str(v) if k == 'id' else v for k, v in item.items()})

@router.get("/grammar", response_model=GrammarListResponse)
async def list_grammar(
    language: str = "zh-CN", level: str = None,
    _: None = Depends(require_token)
):
    items, total = await edu_db.grammar_list(language, level)
    return GrammarListResponse(
        items=[GrammarPoint(**{k: str(v) if k == 'id' else v for k, v in item.items()}) for item in items],
        total=total
    )

@router.post("/grammar", response_model=GrammarPoint)
async def create_grammar(request: GrammarCreateRequest, _: None = Depends(require_token)):
    item = await edu_db.grammar_create(request.model_dump())
    return GrammarPoint(**{k: str(v) if k == 'id' else v for k, v in item.items()})

@router.post("/progress", response_model=ProgressRecordResponse)
async def record_progress(request: ProgressRecordRequest, _: None = Depends(require_token)):
    item = await edu_db.progress_upsert(request.user_id, request.vocab_id, request.correct)
    return ProgressRecordResponse(**{k: str(v) if k == 'id' else v for k, v in item.items()})
