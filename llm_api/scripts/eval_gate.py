#!/usr/bin/env python3
"""Gate before changing a prompt, a model or llm_options: run the evals, compare with the
project's baseline, exit 1 on any regression.

  # once, with the configuration that is in production:
  python scripts/eval_gate.py --project bikeanjoall_2026 --save-baseline
  # after the change, before it goes live:
  python scripts/eval_gate.py --project bikeanjoall_2026

Runs, against the live API (LLM_API_URL / LLM_API_TOKEN):
  - gold questions of the project (scripts/eval_rag.py, tests/eval/eval_questions.json);
  - for bikeanjoall_2026, the text ports (scripts/eval_bikeanjo_ops.py, contracts/bikeanjo/*.eval.jsonl).

Regression = a case that passed in the baseline and fails now, a hard case (grave, written
health, promise in a reply) failing, or the pass rate dropping by more than --tolerance.
New cases only inform. The baseline lives next to the eval results
(tests/eval/results/baseline-<project>.json) — it describes one machine and one corpus.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import eval_bikeanjo_ops  # noqa: E402
import eval_rag  # noqa: E402

OPS_PROJECTS = {"bikeanjoall_2026"}


def baseline_path(project: str) -> Path:
    return eval_rag.RESULTS_DIR / f"baseline-{project}.json"


def snapshot(rag_rows: list[dict], ops_rows: list[dict]) -> dict:
    """Case → pass, keyed so two runs line up: rag:<question> and <port>:<id>."""
    cases: dict[str, dict] = {}
    for row in rag_rows:
        cases[f"rag:{row['question']}"] = {"pass": bool(row["pass"]), "hard": False}
    for row in ops_rows:
        cases[f"{row['port']}:{row['id']}"] = {"pass": bool(row["pass"]), "hard": bool(row["hard"])}
    total = len(cases)
    passed = sum(1 for c in cases.values() if c["pass"])
    return {
        "cases": cases,
        "summary": {"total": total, "passed": passed, "pass_rate": round(passed / total, 4) if total else 1.0},
    }


def compare(baseline: dict | None, current: dict, tolerance: float = 0.0) -> tuple[list[str], list[str]]:
    """(problems, notes). Any problem fails the gate."""
    problems: list[str] = []
    notes: list[str] = []
    now = current["cases"]
    for key, case in sorted(now.items()):
        if case["hard"] and not case["pass"]:
            problems.append(f"caso obrigatório falhou: {key}")
    if baseline is None:
        notes.append("sem referência salva: rode com --save-baseline na configuração que está no ar")
        return problems, notes
    before = baseline.get("cases", {})
    for key, case in sorted(now.items()):
        prev = before.get(key)
        if prev is None:
            notes.append(f"caso novo: {key} ({'passa' if case['pass'] else 'falha'})")
        elif prev["pass"] and not case["pass"] and not case["hard"]:
            problems.append(f"passava e agora falha: {key}")
        elif not prev["pass"] and case["pass"]:
            notes.append(f"melhorou: {key}")
    for key in sorted(set(before) - set(now)):
        notes.append(f"caso saiu do conjunto: {key}")
    drop = baseline.get("summary", {}).get("pass_rate", 0) - current["summary"]["pass_rate"]
    if drop > tolerance:
        problems.append(
            f"taxa caiu {drop:.0%} (de {baseline['summary']['pass_rate']:.0%} para {current['summary']['pass_rate']:.0%})"
        )
    return problems, notes


def _latest_rag_result(project: str, since: datetime) -> list[dict]:
    files = sorted(eval_rag.RESULTS_DIR.glob(f"{project}-*.json"))
    for path in reversed(files):
        if path.stat().st_mtime >= since.timestamp() - 1:
            return json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    return []


def run_rag(args: argparse.Namespace) -> list[dict]:
    started = datetime.now(timezone.utc)
    ns = argparse.Namespace(
        url=args.url,
        token=args.token,
        project=args.project,
        dataset=eval_rag.DEFAULT_DATASET,
        unique=True,
        report_only=True,
        compare=None,
    )
    asyncio.run(eval_rag.run_eval(ns))
    return _latest_rag_result(args.project, started)


def run_ops(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    headers = {"Authorization": f"Bearer {args.token}"}
    with httpx.Client(base_url=args.url.rstrip("/"), headers=headers, timeout=120) as client:
        for port in eval_bikeanjo_ops.PORTS:
            eval_bikeanjo_ops.run_port(client, port, record=rows)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--url", default=os.environ.get("LLM_API_URL", "http://127.0.0.1:28471"))
    ap.add_argument("--token", default=os.environ.get("LLM_API_TOKEN", ""))
    ap.add_argument("--save-baseline", action="store_true", help="grava esta rodada como referência")
    ap.add_argument("--tolerance", type=float, default=0.0, help="queda de taxa aceita (0.05 = 5 pontos)")
    ap.add_argument("--skip-rag", action="store_true")
    ap.add_argument("--skip-ops", action="store_true")
    args = ap.parse_args()
    if not args.token:
        print("LLM_API_TOKEN missing", file=sys.stderr)
        return 2

    rag_rows = [] if args.skip_rag else run_rag(args)
    ops_rows = [] if (args.skip_ops or args.project not in OPS_PROJECTS) else run_ops(args)
    current = snapshot(rag_rows, ops_rows)
    current["run"] = {"timestamp": datetime.now(timezone.utc).isoformat(), "project": args.project}

    path = baseline_path(args.project)
    if args.save_baseline:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"referência gravada: {path} ({current['summary']['passed']}/{current['summary']['total']})")
        return 0

    baseline = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    problems, notes = compare(baseline, current, args.tolerance)
    print(f"\n{current['summary']['passed']}/{current['summary']['total']} casos passam")
    for n in notes:
        print(f"  · {n}")
    for p in problems:
        print(f"  ✗ {p}")
    print("PORTÃO: " + ("REPROVADO" if problems else "APROVADO"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
