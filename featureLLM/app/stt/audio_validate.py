"""Validate uploaded audio: extension, size, and basic magic bytes."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

logger = logging.getLogger(__name__)

# OGG (Opus), MP3, WAV, M4A/MP4 — aligned with plan
_ALLOWED_EXT = frozenset({".ogg", ".oga", ".opus", ".mp3", ".wav", ".m4a", ".mp4", ".webm"})

# Minimal magic checks (first bytes)
_MAGIC = (
    (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"),
    (b"\xff\xf3", "mp3"),
    (b"\xff\xf2", "mp3"),
    (b"OggS", "ogg"),
    (b"RIFF", "wav"),
    (b"\x00\x00\x00", "mp4_m4a"),  # ftyp box often at offset 4
)


def normalize_extension(filename: str | None) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def is_allowed_extension(ext: str) -> bool:
    return ext in _ALLOWED_EXT


def sniff_format(head: bytes) -> str | None:
    if len(head) < 12:
        return None
    for prefix, name in _MAGIC:
        if head.startswith(prefix):
            return name
    if head[4:8] == b"ftyp":
        return "mp4_m4a"
    return None


async def validate_upload(file: UploadFile, max_bytes: int | None = None) -> tuple[bytes, str]:
    """Read file into memory up to max_bytes; return (raw_bytes, extension).

    Raises ValueError with a short message on validation failure.
    """
    limit = max_bytes if max_bytes is not None else settings.audio_max_bytes
    ext = normalize_extension(file.filename)
    if not is_allowed_extension(ext):
        raise ValueError(
            f"unsupported audio extension '{ext}'; allowed: {', '.join(sorted(_ALLOWED_EXT))}"
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"audio exceeds max size ({limit} bytes)")
        chunks.append(chunk)

    raw = b"".join(chunks)
    if not raw:
        raise ValueError("empty audio upload")

    fmt = sniff_format(raw[:12])
    if fmt is None:
        logger.warning("audio magic unknown for ext=%s size=%d", ext, len(raw))

    return raw, ext
