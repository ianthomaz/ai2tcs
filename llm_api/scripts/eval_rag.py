#!/usr/bin/env python3
"""
Evaluate RAG answer quality against a gold-standard question set.

Usage:
  python scripts/eval_rag.py --project bikeanjoall_2026
  python scripts/eval_rag.py --dataset tests/eval/eval_questions.json

Requires LLM_API_URL and LLM_API_TOKEN in env (or --url / --token).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
LLM_ROOT = SCRIPT_DIR.parent
DEFAULT_DATASET = LLM_ROOT / "tests" / "eval" / "eval_questions.json"


async def ask_and_wait(
    client: httpx.AsyncClient,
    *,
    project_id: str,
    question: str,
    system_prompt: str | None = None,
    model: str = "smart",
    timeout_s: float = 120.0,
) -> tuple[str | None, float]:
    t0 = time.perf_counter()
    payload: dict = {"project_id": project_id, "question": question, "model": model}
    if system_prompt:
        payload["system_prompt"] = system_prompt
    r = await client.post("/ask", json=payload)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        st = await client.get(f"/status/{job_id}")
        st.raise_for_status()
        status = st.json()["status"]
        if status in ("done", "no_answer", "failed"):
            break
        await asyncio.sleep(0.5)
    res = await client.get(f"/result/{job_id}")
    res.raise_for_status()
    elapsed = time.perf_counter() - t0
    data = res.json()
    return data.get("answer"), elapsed


def score_answer(
    answer: str | None,
    expected_keywords: list[str],
    forbidden_keywords: list[str] | None = None,
    max_chars: int | None = None,
) -> tuple[bool, str]:
    if not answer:
        return False, "empty answer"
    if max_chars is not None and len(answer) > max_chars:
        return False, f"too long ({len(answer)} > {max_chars} chars)"
    low = answer.lower()
    forbidden = forbidden_keywords or []
    found_forbidden = [k for k in forbidden if k.lower() in low]
    if found_forbidden:
        return False, f"forbidden keywords: {', '.join(found_forbidden)}"
    if not expected_keywords:
        return True, "no keywords required"
    missing = [k for k in expected_keywords if k.lower() not in low]
    if missing:
        return False, f"missing keywords: {', '.join(missing)}"
    return True, "ok"


async def main() -> int:
    parser = argparse.ArgumentParser(description="RAG eval against gold questions")
    parser.add_argument("--url", default=os.environ.get("LLM_API_URL", "http://127.0.0.1:28471"))
    parser.add_argument("--token", default=os.environ.get("LLM_API_TOKEN", ""))
    parser.add_argument("--project", help="Filter dataset to one project_id")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--unique", action="store_true", help="Append random ref to each question (avoid stale answers)")
    args = parser.parse_args()

    if not args.token:
        print("Set LLM_API_TOKEN or pass --token", file=sys.stderr)
        return 1

    rows = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.project:
        rows = [r for r in rows if r.get("project_id") == args.project]
    if not rows:
        print("No eval rows to run", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {args.token}"}
    passed = 0
    async with httpx.AsyncClient(base_url=args.url.rstrip("/"), headers=headers, timeout=180.0) as client:
        for row in rows:
            pid = row["project_id"]
            q = row["question"]
            if args.unique:
                q = f"{q} (ref {uuid.uuid4().hex[:8]})"
            keywords = row.get("expected_keywords") or []
            forbidden = row.get("forbidden_keywords") or []
            max_chars = row.get("max_chars")
            system_prompt = row.get("system_prompt")
            model = row.get("model") or "smart"
            answer, elapsed = await ask_and_wait(
                client,
                project_id=pid,
                question=q,
                system_prompt=system_prompt,
                model=model,
            )
            ok, note = score_answer(answer, keywords, forbidden, max_chars)
            passed += int(ok)
            status = "PASS" if ok else "FAIL"
            preview = (answer or "")[:120].replace("\n", " ")
            print(f"[{status}] {pid} ({elapsed:.1f}s) {note}")
            print(f"  Q: {q}")
            print(f"  A: {preview}")

    print(f"\n{passed}/{len(rows)} passed")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
