"""Local transcription via faster-whisper (Whisper weights)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_model = None
_model_lock = None


def _get_lock():
    global _model_lock
    if _model_lock is None:
        import threading

        _model_lock = threading.Lock()
    return _model_lock


@dataclass
class TranscriptionResult:
    """Output of a single file transcription."""

    text: str
    language: str | None
    duration_seconds: float | None
    segment_count: int


def _load_model():
    """Lazy singleton WhisperModel."""
    global _model
    if _model is not None:
        return _model
    with _get_lock():
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        logger.info(
            "Loading Whisper model size=%s device=%s compute_type=%s",
            settings.whisper_model_size,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        _model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            download_root=str(settings.resolved_whisper_download_root()),
        )
        return _model


def transcribe_audio_file(path: Path, language: str | None = None) -> TranscriptionResult:
    """Transcribe one audio file on disk. Runs synchronously (call via asyncio.to_thread)."""
    if not settings.whisper_enabled:
        raise RuntimeError("Whisper STT is disabled (WHISPER_ENABLED=false)")

    file_path = path.resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"audio file not found: {file_path}")

    lang = (language or settings.whisper_language or "").strip() or None

    t0 = time.perf_counter()
    model = _load_model()
    segments_gen, info = model.transcribe(
        str(file_path),
        language=lang,
        beam_size=settings.whisper_beam_size,
        vad_filter=settings.whisper_vad_filter,
    )
    parts: list[str] = []
    n = 0
    for seg in segments_gen:
        n += 1
        t = (seg.text or "").strip()
        if t:
            parts.append(t)
    text = " ".join(parts).strip()
    elapsed = time.perf_counter() - t0

    duration = getattr(info, "duration", None)
    detected = getattr(info, "language", None)

    logger.info(
        "STT done file=%s segments=%d lang=%s duration_audio=%s transcribe_s=%.2f",
        file_path.name,
        n,
        detected,
        duration,
        elapsed,
    )

    return TranscriptionResult(
        text=text,
        language=detected,
        duration_seconds=float(duration) if duration is not None else None,
        segment_count=n,
    )
