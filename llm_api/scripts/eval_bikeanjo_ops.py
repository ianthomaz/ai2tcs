#!/usr/bin/env python3
"""Run the Bike Anjo eval sets (contracts/bikeanjo/*.eval.jsonl) against a live ai2tcs.

Measures the model, so it calls it: one request per case (30 in all). Nothing is sent to anyone.

  LLM_API_URL=http://127.0.0.1:28471 LLM_API_TOKEN=itcs_bikeanjoall_2026_... \\
    python scripts/eval_bikeanjo_ops.py [--port feedbackTriage|healthNormalize|replySuggest]

Exit code 0 only when every port meets the "pronto" criteria of CHECKLIST_AI2TCS.md:
  feedbackTriage  every grave case right, the rest >= 80%
  healthNormalize zero written health marked generic_statement, the rest >= 80%
  replySuggest    zero promise / invented link, grave always no_answer
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts" / "bikeanjo"
RATE = 0.8


def _cases(stem: str) -> list[dict]:
    lines = (CONTRACTS / f"{stem}.eval.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines if l.strip()]


def _triage_request(c: dict) -> dict:
    return {
        "source": c.get("source", "eba-feedback"),
        "submission_id": c["id"],
        "subject": {"user_id": None, "dependent_id": None},
        "event_id": None,
        "locale": "pt-BR",
        "fields": c["fields"],
        "scales": {},
    }


def _health_request(c: dict) -> dict:
    return {
        "source": "health",
        "person": {"kind": "user", "id": "AABC4"},
        "locale": "pt-BR",
        "known_codes": c["known_codes"],
        "free_text": c["free_text"],
    }


def _reply_request(c: dict) -> dict:
    return {
        "source": "support_ticket",
        "ticket_id": c["id"],
        "channel": "site",
        "subject": c["subject"],
        "message": c["message"],
        "context": {"has_account": False, "page_url": "/contato", "city": None, "state": None},
    }


def check(expect: dict, out: dict) -> list[str]:
    """Failed expectations, by name. Empty list = case passed."""
    if out.get("status") != "ok":
        return [f"status={out.get('status')} {out.get('error')}"]
    fails: list[str] = []
    tags = set(out.get("tags") or [])
    for t in expect.get("tags_include", []):
        if t not in tags:
            fails.append(f"tag {t} missing")
    for t in expect.get("tags_exclude", []):
        if t in tags:
            fails.append(f"tag {t} present")
    for key in ("urgency", "generic_statement", "no_answer", "codes", "outras", "named_people"):
        if key in expect and out.get(key) != expect[key]:
            fails.append(f"{key}={out.get(key)!r} expected {expect[key]!r}")
    for n in expect.get("named_people_include", []):
        if n not in (out.get("named_people") or []):
            fails.append(f"named_people lacks {n}")
    for k, mx in (expect.get("scores_max") or {}).items():
        if (out.get("scores") or {}).get(k, 0) > mx:
            fails.append(f"scores.{k} > {mx}")
    if "anchor_not_contains" in expect and expect["anchor_not_contains"] in (out.get("anchor_quote") or ""):
        fails.append("anchor carries marker")
    outras = (out.get("outras") or "").lower()
    if "outras_contains" in expect and expect["outras_contains"].lower() not in outras:
        fails.append(f"outras lacks {expect['outras_contains']!r}")
    if "outras_excludes" in expect and expect["outras_excludes"].lower() in outras:
        fails.append(f"outras has {expect['outras_excludes']!r}")
    reply = (out.get("suggested_reply") or "").lower()
    for s in expect.get("must_not_contain", []):
        if s.lower() in reply:
            fails.append(f"reply contains {s!r}")
    if "max_chars" in expect and len(reply) > expect["max_chars"]:
        fails.append(f"reply longer than {expect['max_chars']}")
    return fails


def is_hard(port: str, expect: dict) -> bool:
    """Cases that must all pass (the rest only count towards the 80% rate)."""
    if port == "feedbackTriage":
        return "grave" in expect.get("tags_include", [])
    if port == "healthNormalize":
        return expect.get("generic_statement") is False
    return expect.get("no_answer") is True or bool(expect.get("must_not_contain"))


PORTS = {
    "feedbackTriage": ("feedback-triage", _triage_request),
    "healthNormalize": ("health-normalize", _health_request),
    "replySuggest": ("reply-suggest", _reply_request),
}


def run_port(client: httpx.Client, port: str) -> bool:
    stem, build = PORTS[port]
    hard_fail, soft_total, soft_ok = 0, 0, 0
    versions: set[str] = set()
    for c in _cases(stem):
        r = client.post(f"/{port}", json=build(c))
        out = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200:
            out = {"status": f"http_{r.status_code}"}
        versions.add(str(out.get("prompt_version")))
        fails = check(c["expect"], out)
        hard = is_hard(port, c["expect"])
        if hard and fails:
            hard_fail += 1
        if not hard:
            soft_total += 1
            soft_ok += not fails
        mark = "ok " if not fails else ("HARD" if hard else "miss")
        print(f"  {mark} {c['id']}  {'; '.join(fails) or c.get('why', '')}")
    rate = soft_ok / soft_total if soft_total else 1.0
    ready = hard_fail == 0 and rate >= RATE
    print(f"{port} {'/'.join(sorted(versions))}: hard failures {hard_fail} · rate {rate:.0%} → {'PRONTO' if ready else 'não pronto'}\n")
    return ready


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", choices=list(PORTS))
    args = ap.parse_args()
    base = os.environ.get("LLM_API_URL", "http://127.0.0.1:28471").rstrip("/")
    token = os.environ.get("LLM_API_TOKEN", "")
    if not token:
        print("LLM_API_TOKEN missing", file=sys.stderr)
        return 2
    ports = [args.port] if args.port else list(PORTS)
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=120) as client:
        results = [run_port(client, p) for p in ports]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
