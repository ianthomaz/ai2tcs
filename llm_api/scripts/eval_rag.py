#!/usr/bin/env python3
"""
Evaluate RAG answer quality against a gold-standard question set.

Usage:
  python scripts/eval_rag.py --project bikeanjoall_2026 --unique --report-only
  python scripts/eval_rag.py --dataset tests/eval/eval_questions.json
  python scripts/eval_rag.py --compare tests/eval/results/a.json tests/eval/results/b.json

Every run is written to tests/eval/results/ together with the project config that
produced it. Without that record two runs are indistinguishable in hindsight, and
"before vs after" cannot be argued — which is the whole point of measuring first.

Latency note: pass --unique when the number matters. /ask deduplicates identical
questions within its TTL and returns the earlier job in ~0s, which silently turns a
latency measurement into a measurement of the cache.

Requires LLM_API_URL and LLM_API_TOKEN in env (or --url / --token).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
LLM_ROOT = SCRIPT_DIR.parent
DEFAULT_DATASET = LLM_ROOT / "tests" / "eval" / "eval_questions.json"
RESULTS_DIR = LLM_ROOT / "tests" / "eval" / "results"


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


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile. Small samples make interpolation misleading here."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(p / 100.0 * len(ordered))))
    return ordered[rank - 1]


def summarize(rows: list[dict]) -> dict:
    latencies = [r["latency_s"] for r in rows]
    passed = sum(1 for r in rows if r["pass"])
    return {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": round(passed / len(rows), 4) if rows else 0.0,
        "latency_p50": round(percentile(latencies, 50), 2),
        "latency_p95": round(percentile(latencies, 95), 2),
        "latency_max": round(max(latencies), 2) if latencies else 0.0,
    }


async def fetch_project_config(client: httpx.AsyncClient, project_id: str) -> dict | None:
    """Effective config for a project, so a result file explains itself later."""
    try:
        r = await client.get(f"/projects/{project_id}")
        r.raise_for_status()
        return r.json().get("config_json")
    except Exception as exc:  # noqa: BLE001 — a missing config must not abort the run
        print(f"  (could not read config for {project_id}: {exc})", file=sys.stderr)
        return None


def result_path(project_filter: str | None, when: datetime) -> Path:
    label = project_filter or "all"
    return RESULTS_DIR / f"{label}-{when.strftime('%Y%m%dT%H%M%SZ')}.json"


def _flat(prefix: str, value: object, out: dict) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flat(f"{prefix}.{k}" if prefix else str(k), v, out)
    else:
        out[prefix] = value


def config_diff(before: dict | None, after: dict | None) -> list[tuple[str, object, object]]:
    """Flattened config differences — usually the reason the numbers moved."""
    a: dict = {}
    b: dict = {}
    _flat("", before or {}, a)
    _flat("", after or {}, b)
    changed = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            changed.append((key, a.get(key), b.get(key)))
    return changed


def _preview(value: object, width: int = 40) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def print_comparison(before: dict, after: dict) -> None:
    bs, as_ = before["summary"], after["summary"]
    print(f"antes:  {before['run']['timestamp']}  ({before['run']['dataset']})")
    print(f"depois: {after['run']['timestamp']}  ({after['run']['dataset']})\n")

    print(f"{'métrica':<16}{'antes':>10}{'depois':>10}{'delta':>10}")
    print("-" * 46)
    for label, key, fmt in (
        ("pass rate", "pass_rate", "{:.0%}"),
        ("passaram", "passed", "{:.0f}"),
        ("latência p50", "latency_p50", "{:.1f}s"),
        ("latência p95", "latency_p95", "{:.1f}s"),
    ):
        b, a = bs.get(key, 0), as_.get(key, 0)
        delta = a - b
        sign = "+" if delta > 0 else ""
        print(f"{label:<16}{fmt.format(b):>10}{fmt.format(a):>10}{sign + fmt.format(delta):>10}")

    before_rows = {(r["project_id"], r["question"]): r for r in before["rows"]}
    moved = []
    for row in after["rows"]:
        prev = before_rows.get((row["project_id"], row["question"]))
        if prev is not None and prev["pass"] != row["pass"]:
            moved.append((row, prev))
    if moved:
        print("\nmudaram de veredicto:")
        for row, prev in moved:
            arrow = "PASS→FAIL" if prev["pass"] else "FAIL→PASS"
            print(f"  [{arrow}] {row['project_id']}: {_preview(row['question'], 56)}")
            print(f"             {row['note']}")
    else:
        print("\nnenhuma pergunta mudou de veredicto.")

    all_projects = sorted(set(before.get("projects", {})) | set(after.get("projects", {})))
    diff_lines = []
    for project in all_projects:
        for key, old, new in config_diff(
            (before.get("projects") or {}).get(project),
            (after.get("projects") or {}).get(project),
        ):
            diff_lines.append(f"  {project}.{key}: {_preview(old)} → {_preview(new)}")
    if diff_lines:
        print("\nconfiguração que mudou entre as corridas:")
        print("\n".join(diff_lines))
    else:
        print("\nconfiguração idêntica nas duas corridas.")


def load_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for field in ("run", "summary", "rows"):
        if field not in data:
            raise ValueError(f"{path} is not an eval result file (missing '{field}')")
    return data


async def run_eval(args: argparse.Namespace) -> int:
    rows_in = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.project:
        rows_in = [r for r in rows_in if r.get("project_id") == args.project]
    if not rows_in:
        print("No eval rows to run", file=sys.stderr)
        return 1

    started = datetime.now(timezone.utc)
    headers = {"Authorization": f"Bearer {args.token}"}
    result_rows: list[dict] = []
    configs: dict[str, dict | None] = {}

    async with httpx.AsyncClient(base_url=args.url.rstrip("/"), headers=headers, timeout=180.0) as client:
        for project_id in sorted({r["project_id"] for r in rows_in}):
            configs[project_id] = await fetch_project_config(client, project_id)

        for row in rows_in:
            pid = row["project_id"]
            original = row["question"]
            q = f"{original} (ref {uuid.uuid4().hex[:8]})" if args.unique else original
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
            status = "PASS" if ok else "FAIL"
            preview = (answer or "")[:120].replace("\n", " ")
            # Store the dataset question, not the --unique variant, so runs line up.
            result_rows.append(
                {
                    "project_id": pid,
                    "question": original,
                    "model": model,
                    "pass": ok,
                    "note": note,
                    "latency_s": round(elapsed, 2),
                    "answer_preview": preview,
                }
            )
            print(f"[{status}] {pid} ({elapsed:.1f}s) {note}")
            print(f"  Q: {q}")
            print(f"  A: {preview}")

    summary = summarize(result_rows)
    payload = {
        "run": {
            "timestamp": started.isoformat(),
            "dataset": str(args.dataset.relative_to(LLM_ROOT) if args.dataset.is_relative_to(LLM_ROOT) else args.dataset),
            "url": args.url,
            "project_filter": args.project,
            "unique": args.unique,
        },
        "projects": configs,
        "summary": summary,
        "rows": result_rows,
    }

    out = result_path(args.project, started)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{summary['passed']}/{summary['total']} passed")
    print(f"latência p50 {summary['latency_p50']}s · p95 {summary['latency_p95']}s · máx {summary['latency_max']}s")
    if not args.unique:
        print("nota: sem --unique, o dedup do /ask pode ter devolvido jobs antigos e falseado a latência")
    print(f"resultado gravado em {out}")

    if args.report_only:
        return 0
    return 0 if summary["failed"] == 0 else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description="RAG eval against gold questions")
    parser.add_argument("--url", default=os.environ.get("LLM_API_URL", "http://127.0.0.1:28471"))
    parser.add_argument("--token", default=os.environ.get("LLM_API_TOKEN", ""))
    parser.add_argument("--project", help="Filter dataset to one project_id")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--unique", action="store_true", help="Append random ref to each question (avoid stale answers)")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Always exit 0: measuring a baseline is not a pass/fail gate",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("ANTES", "DEPOIS"),
        type=Path,
        help="Print a before/after table from two result files and exit",
    )
    args = parser.parse_args()

    if args.compare:
        try:
            before, after = (load_result(p) for p in args.compare)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Could not compare: {exc}", file=sys.stderr)
            return 1
        print_comparison(before, after)
        return 0

    if not args.token:
        print("Set LLM_API_TOKEN or pass --token", file=sys.stderr)
        return 1
    return await run_eval(args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
