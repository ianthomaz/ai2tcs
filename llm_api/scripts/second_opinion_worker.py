#!/usr/bin/env python3
"""Host worker of the second opinion queue (docs/26-second-opinion.md).

Runs on the machine where the agent CLI is logged in (mini62, user session via launchd),
outside Docker. One case at a time: claim → run the agent with the prompt on stdin →
send the raw output back. The API validates the answer; this script never reads the
project's repositories, the database or any .env besides its own three variables.

  SECOND_OPINION_API_URL       default http://127.0.0.1:28471
  SECOND_OPINION_WORKER_TOKEN  same value as in the API's .env
  SECOND_OPINION_AGENT_CMD     command that reads the prompt on stdin and prints the answer
  SECOND_OPINION_AGENT_NAME    label stored with the answer (default: first word of the command)
  SECOND_OPINION_TIMEOUT_S     default 90

  python scripts/second_opinion_worker.py --once     # one case and exit (launchd StartInterval)
  python scripts/second_opinion_worker.py --dry-run  # claim nothing; run the agent on a sample
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

SAMPLE_PROMPT = 'Responda só com o JSON {"ok": true}.'


def run_agent(cmd: str, prompt: str, timeout_s: float) -> tuple[str | None, str | None]:
    """(output, error). Empty working directory, minimal environment, prompt only on stdin."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "USER", "LANG", "TMPDIR") if k in os.environ}
    with tempfile.TemporaryDirectory(prefix="second-opinion-") as cwd:
        try:
            proc = subprocess.run(
                shlex.split(cmd), input=prompt, capture_output=True, text=True, timeout=timeout_s, cwd=cwd, env=env,
            )
        except subprocess.TimeoutExpired:
            return None, f"agent_timeout_{int(timeout_s)}s"
        except OSError as e:
            return None, f"agent_not_runnable: {e}"
    if proc.returncode != 0:
        return None, f"agent_exit_{proc.returncode}: {(proc.stderr or '').strip()[:200]}"
    out = (proc.stdout or "").strip()
    return (out, None) if out else (None, "agent_empty_output")


def _post(url: str, token: str, body: dict | None) -> tuple[int, dict | None]:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def work_once(api: str, token: str, cmd: str, agent: str, timeout_s: float) -> str:
    """'empty' | 'done' | 'failed' | 'unauthorized'."""
    status, case = _post(f"{api}/second-opinion/worker/claim", token, None)
    if status == 204:
        return "empty"
    if status != 200 or not case:
        return "unauthorized" if status in (401, 403, 404) else "failed"
    output, error = run_agent(cmd, case["prompt"], timeout_s)
    body = {"agent": agent, "output": output} if output is not None else {"agent": agent, "error": error}
    _, result = _post(f"{api}/second-opinion/worker/{case['id']}/result", token, body)
    return (result or {}).get("status", "failed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cmd = os.environ.get("SECOND_OPINION_AGENT_CMD", "").strip()
    if not cmd:
        print("SECOND_OPINION_AGENT_CMD não definido", file=sys.stderr)
        return 2
    timeout_s = float(os.environ.get("SECOND_OPINION_TIMEOUT_S", "90"))
    agent = os.environ.get("SECOND_OPINION_AGENT_NAME") or os.path.basename(shlex.split(cmd)[0])
    if args.dry_run:
        out, err = run_agent(cmd, SAMPLE_PROMPT, timeout_s)
        print(out if out is not None else f"erro: {err}")
        return 0 if out is not None else 1
    token = os.environ.get("SECOND_OPINION_WORKER_TOKEN", "").strip()
    if not token:
        print("SECOND_OPINION_WORKER_TOKEN não definido", file=sys.stderr)
        return 2
    api = os.environ.get("SECOND_OPINION_API_URL", "http://127.0.0.1:28471").rstrip("/")
    while True:
        outcome = work_once(api, token, cmd, agent, timeout_s)
        print(outcome)
        if args.once or outcome in ("empty", "unauthorized"):
            return 0 if outcome != "unauthorized" else 1


if __name__ == "__main__":
    raise SystemExit(main())
