"""Split text into chunks for embedding."""
import json
import re
from pathlib import Path

# Notion export boilerplate: lines we strip so real content ranks better in retrieval
_NOTION_NOISE_LINES = frozenset({"created", "subtítulo", "tags", "status", "url"})
_NOTION_DATE_LINE = re.compile(
    r"^(?:[A-Zaçã]+\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+de\s+[a-zçã]+\.?\s+de\s+\d{4})\s+\d{1,2}:\d{2}\s*[AP]M$",
    re.IGNORECASE,
)
# Consolidated-library metadata: keep in file for humans, strip from index for retrieval (estudosMobi etc.)
_SOURCE_LINE = re.compile(r"^Source:\s*https?://", re.IGNORECASE)
_ORIGINAL_FILE_LINE = re.compile(r"^Original file:\s*\S+", re.IGNORECASE)


def _normalize_markdown_for_indexing(text: str) -> str:
    """Reduce Notion-export boilerplate so chunks contain more meaningful text for retrieval."""
    if not text or not text.strip():
        return text
    # Strip YAML frontmatter (keep body)
    if text.startswith("---"):
        idx = text.find("\n---", 3)
        if idx != -1:
            text = text[idx + 4 :].lstrip()
    out: list[str] = []
    first_heading = None
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            out.append("")
            continue
        if s.lower() in _NOTION_NOISE_LINES:
            continue
        if _NOTION_DATE_LINE.match(s):
            continue
        if _SOURCE_LINE.match(s) or _ORIGINAL_FILE_LINE.match(s):
            continue
        # Keep first # heading to reinforce first chunk for retrieval
        if first_heading is None and s.startswith("#"):
            first_heading = re.sub(r"^#+\s*", "", s).strip()
        out.append(line)
    # Collapse 3+ newlines to 2
    body = "\n".join(out)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = body.strip()
    # Prepend "Sobre: ..." and keywords from title so first chunk ranks for topic/city queries
    if first_heading and len(first_heading) > 5:
        # Extract likely keywords (e.g. "NFS-e | Osasco - SP" -> "NFS-e Osasco emissão nota fiscal")
        parts = re.split(r"[|\-–]", first_heading)
        words = []
        for p in parts:
            words.extend(w.strip() for w in p.split() if len(w.strip()) > 1)
        # Avoid duplicate tokens; keep order; limit length
        seen = set()
        keywords = []
        for w in words[:12]:
            wl = w.lower()
            if wl not in seen and wl not in {"de", "da", "do", "em", "e", "o", "a", "sp", "rj", "mg", "sc"}:
                seen.add(wl)
                keywords.append(w)
        kw_line = " ".join(keywords[:8])
        if kw_line:
            body = f"Sobre: {first_heading}. Palavras-chave: {kw_line}.\n\n{body}"
        else:
            body = f"Sobre: {first_heading}.\n\n{body}"
    return body


def _json_to_text(obj: object) -> str:
    """Flatten JSON to searchable text (strings and scalar values)."""
    if isinstance(obj, dict):
        return "\n".join(f"{k}: {_json_to_text(v)}" for k, v in obj.items())
    if isinstance(obj, list):
        return "\n\n".join(_json_to_text(i) for i in obj)
    if isinstance(obj, str):
        return obj
    return str(obj)


_HEADING_RE = re.compile(r"^#{1,4}\s+", re.MULTILINE)


def _split_by_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text into (heading, body) sections.

    Returns a list of tuples where heading is the section heading (or "" for
    content before the first heading) and body is the section text.
    Used to create more cohesive chunks that align with document structure.
    Added: março 2026 — improves retrieve precision by keeping section context together.
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]
    sections: list[tuple[str, str]] = []
    # Content before first heading
    if matches[0].start() > 0:
        pre = text[: matches[0].start()].strip()
        if pre:
            sections.append(("", pre))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        heading = text[m.start() : line_end].strip()
        body = text[line_end:end].strip()
        sections.append((heading, body))
    return sections


def split_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    separator: str = "\n\n",
) -> list[str]:
    """Split text by markdown sections first, then by separator/size with overlap.

    Markdown files are split by headings (## / ###) so each chunk corresponds to
    a thematic section. The heading is preserved at the top of each chunk for
    retrieval context. Non-markdown text falls back to separator-based splitting.
    """
    if not text or not text.strip():
        return []

    # Try section-based splitting for markdown-like content
    sections = _split_by_sections(text)
    if len(sections) > 1:
        chunks: list[str] = []
        for heading, body in sections:
            section_text = f"{heading}\n\n{body}".strip() if heading else body
            if len(section_text) <= chunk_size:
                if section_text:
                    chunks.append(section_text)
            else:
                # Section too large: split by separator, prepend heading to first sub-chunk
                sub_chunks = _split_by_separator(section_text, chunk_size, chunk_overlap, separator)
                if heading and sub_chunks and not sub_chunks[0].startswith(heading):
                    sub_chunks[0] = f"{heading}\n\n{sub_chunks[0]}"
                chunks.extend(sub_chunks)
        return chunks if chunks else _split_by_separator(text, chunk_size, chunk_overlap, separator)

    return _split_by_separator(text, chunk_size, chunk_overlap, separator)


def _split_by_separator(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    separator: str = "\n\n",
) -> list[str]:
    """Original separator-based splitting logic."""
    parts = text.split(separator)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        part_len = len(part) + (len(separator) if current else 0)
        if current_len + part_len <= chunk_size and current:
            current.append(part)
            current_len += part_len
        else:
            if current:
                chunk = separator.join(current)
                chunks.append(chunk)
                # overlap: keep last segment(s) that fit in overlap
                overlap_len = 0
                overlap_parts: list[str] = []
                for j in range(len(current) - 1, -1, -1):
                    seg = current[j]
                    if overlap_len + len(seg) <= chunk_overlap:
                        overlap_parts.insert(0, seg)
                        overlap_len += len(seg)
                    else:
                        break
                current = overlap_parts
                current_len = overlap_len
            current = [part] if part else []
            current_len = len(part)
    if current:
        chunks.append(separator.join(current))
    return chunks


def iter_files(paths: list[str], extensions: set[str] | None = None) -> list[tuple[Path, str]]:
    """Yield (path, text_content) for supported files under path. paths are folders."""
    if extensions is None:
        extensions = {".txt", ".md", ".markdown", ".rst", ".json"}
    out: list[tuple[Path, str]] = []
    for base in paths:
        p = Path(base)
        if not p.exists():
            continue
        if p.is_file():
            if p.suffix.lower() in extensions:
                try:
                    text = _read_file_text(p)
                    if text:
                        out.append((p, text))
                except Exception:
                    pass
            continue
        for f in p.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in extensions:
                continue
            try:
                text = _read_file_text(f)
                if text:
                    out.append((f, text))
            except Exception:
                pass
    return out


def _read_file_text(path: Path) -> str:
    """Read file as text; for .json flatten to text for indexing. .md gets Notion boilerplate stripped."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(raw)
            return _json_to_text(data)
        except (json.JSONDecodeError, TypeError):
            return raw
    if path.suffix.lower() in (".md", ".markdown"):
        return _normalize_markdown_for_indexing(raw)
    return raw
