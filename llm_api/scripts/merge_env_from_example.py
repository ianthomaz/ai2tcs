#!/usr/bin/env python3
"""Rewrite llm_api/.env from .env.example order, keeping existing active KEY= values."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"

# Optional keys in .env.example: only auto-fill from comment default if key matches one of these prefixes.
AUTO_PREFIXES = (
    "API_",
    "DATA_DIR",
    "OLLAMA_",
    "NF_",
    "EDU_",
    "NABIL_",
    "WHISPER_",
    "AUDIO_",
    "DASHBOARD_OLLAMA_",
)


def load_existing(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    if not path.is_file():
        return d
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def auto_fill_key(key: str) -> bool:
    if key == "DATA_DIR":
        return True
    return any(key.startswith(p) for p in AUTO_PREFIXES if p != "DATA_DIR")


def placeholder_value(val: str) -> bool:
    v = val.strip().lower()
    if not v:
        return True
    if "paste" in v or "your_" in v or "sk-..." in v or "..." in val:
        return True
    if v.startswith("<") or "example.com" in v:
        return True
    return False


def main() -> int:
    if not EXAMPLE.is_file():
        print("missing .env.example", file=sys.stderr)
        return 1
    existing = load_existing(TARGET)
    out: list[str] = []
    seen: set[str] = set()

    for raw in EXAMPLE.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        m_act = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", s)
        if m_act and not s.startswith("#"):
            k, v = m_act.group(1), m_act.group(2)
            seen.add(k)
            out.append(f"{k}={existing.get(k, v)}")
            continue
        m_com = re.match(r"^#\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", s)
        if m_com:
            k, default = m_com.group(1), m_com.group(2)
            if k in existing:
                seen.add(k)
                out.append(f"{k}={existing[k]}")
            elif auto_fill_key(k) and not placeholder_value(default):
                seen.add(k)
                out.append(f"{k}={default.strip()}")
            else:
                out.append(raw)
            continue
        out.append(raw)

    extra = [f"{k}={v}" for k, v in sorted(existing.items()) if k not in seen]
    if extra:
        out.append("")
        out.append("# --- Extra keys from previous .env (not listed in .env.example) ---")
        out.extend(extra)

    TARGET.write_text("\n".join(out) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
