#!/usr/bin/env python3
"""
One-off script: process Drive links (NF + comprovantes) via local nfExtract,
pair them, output seed JSON for Bora de Bike.

Usage:
  cd featureLLM && python scripts/extract_bora_de_bike_links.py

Requires: API running (uvicorn), Ollama. Default: localhost:28471. NF_EXTRACT_BASE=https://llm.webplace.cc for prod.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Add parent so we can load app.config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

# Internal API token (same as LLM_API_TOKEN / ITCS_NF_EXTRACT_TOKEN)
_API_TOKEN = "4ec39015c8ced3d5b5fce6c40ab32928d97bc8ec238f14b7"

LINKS = [
    "https://drive.google.com/file/d/1lvVQ--VoLe8El6HAhy5Vse0rTQgPPA-M/view?usp=drive_link",
    "https://drive.google.com/file/d/1EAVRFuPGATT5mZTHNK5rF4v9MUm-nj8o/view?usp=drive_link",
    "https://drive.google.com/file/d/1lyF-Ts44LsX8LL0pBc8A9FSK98YFnRgO/view?usp=drive_link",
    "https://drive.google.com/file/d/1cJLnLpXfpMHZ8YotYqcegKqjAQZKTkhO/view?usp=drive_link",
    "https://drive.google.com/file/d/1TtWnioNuFBfxIJvC58MfhwDbBNfz6ETa/view?usp=drive_link",
    "https://drive.google.com/file/d/1_Cr2ZMWcEbXqt78ky8_x5PIwX6V5Joj1/view?usp=drive_link",
    "https://drive.google.com/file/d/1_jbIDUt5I5D9zkHjWpmjI806SKPMobY7/view?usp=drive_link",
    "https://drive.google.com/file/d/1sJah0rSaFNT7L8Zibliw_Jvah3df3JCr/view?usp=drive_link",
    "https://drive.google.com/file/d/1S7ZgdTzh4f0AC9uLyeU4MyVzt5lnBUcp/view?usp=drive_link",
    "https://drive.google.com/file/d/1zHRml0bqDRpU79KtnRTComIAM2cQBFWa/view?usp=drive_link",
    "https://drive.google.com/file/d/1WjaKcZkzEOa_9HO3FqQZXYxk30PUiQ82/view?usp=drive_link",
    "https://drive.google.com/file/d/1QscUKo2nkHSJo_Miqvhiq7tqTjpvAkM_/view?usp=drive_link",
    "https://drive.google.com/file/d/1N0rS40USMMzAZRFT4scsbDyFMqYiGool/view?usp=drive_link",
    "https://drive.google.com/file/d/10wTv_bG5DH2RgVeAh6U47f7KtoF3BWYE/view?usp=drive_link",
    "https://drive.google.com/file/d/10H_toXUPZbavX7yJ0emgZ9F9zkKxTvhH/view?usp=drive_link",
    "https://drive.google.com/file/d/1_WkV3JdzE7iW1jcFLtgsdssVy76mCijf/view?usp=drive_link",
    "https://drive.google.com/file/d/1hcAMyQxr4ujSI0UxHroA91-NZvF4BZaL/view?usp=drive_link",
    "https://drive.google.com/file/d/1bgiqYwCG2JwoxnW6lKMk9L8go4C7gYKb/view?usp=drive_link",
    "https://drive.google.com/file/d/13mSvRZ7QJyZQd6gf2KR6spVFSfmHyhkP/view?usp=drive_link",
    "https://drive.google.com/file/d/13phcZSiNoKrICb20pJmKyO2beMdLiRXl/view?usp=drive_link",
]


def drive_view_to_download(view_url: str) -> str:
    """Convert Drive view link to direct download URL."""
    m = re.search(r"/d/([a-zA-Z0-9_-]+)/", view_url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return view_url


def call_nf_extract(document_url: str, base_url: str, token: str, timeout: float = 120.0, use_download_url: bool = True) -> dict:
    """POST document_url to nfExtract, return JSON."""
    url = drive_view_to_download(document_url) if use_download_url else document_url
    form = {"document_url": url}
    headers = {"Authorization": f"Bearer {token}"}
    r = httpx.post(
        f"{base_url}/nfExtract",
        data=form,
        headers=headers,
        timeout=timeout,
    )
    return r.json()


def main() -> None:
    base = os.environ.get("NF_EXTRACT_BASE", "http://127.0.0.1:28471").rstrip("/")
    limit = int(os.environ.get("LIMIT", "2"))
    to_process = LINKS[:limit]
    results = []
    for i, link in enumerate(to_process):
        print(f"[{i+1}/{limit}] {link[:60]}...", flush=True)
        try:
            # try view URL (Drive may serve PDF directly when shared)
            out = call_nf_extract(link, base, _API_TOKEN, use_download_url=False)
            results.append({"link": link, "ok": out.get("status") == "ok", "data": out})
        except Exception as e:
            results.append({"link": link, "ok": False, "error": str(e)})
    print("\n" + "=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
