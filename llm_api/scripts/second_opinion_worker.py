#!/usr/bin/env python3
"""Host worker of the second opinion queue (docs/26-second-opinion.md).

Runs on the machine where the agent CLI is logged in (mini62, user session), outside Docker.
One case at a time: claim → (optional) read-only case check in the project's system →
run the agent → send the raw output back. The API validates the answer.

The agent never gets network or credentials: when a project has a read-only check, the
worker itself calls it (key 2, PROD_READONLY_KEY) and puts the answer in the prompt as
verified facts. The agent only reads one file in an empty folder.

  SECOND_OPINION_API_URL       default http://127.0.0.1:28471
  SECOND_OPINION_WORKER_TOKEN  same value as in the API's .env
  SECOND_OPINION_AGENT_CMD     the agent command. Placeholders: {prompt_file} (the case, written
                               in an empty folder), {workdir} (that folder). Without placeholders
                               the prompt goes on stdin.
                               Antigravity local (mini62, reads {prompt_file}, never puts case in argv/ps):
                                 python3 /Users/ianthomaz/Documents/projects/ai2tcs/llm_api/scripts/antigravity_agent_runner.py {prompt_file}
  SECOND_OPINION_AGENT_NAME    label stored with the answer (default: first word of the command)
  SECOND_OPINION_TIMEOUT_S     default 180
  SECOND_OPINION_CREDENTIALS_DIR  default ../local-only/credentials (one <project_id>.env per project)
  SECOND_OPINION_LISTEN_PORT   default 9191 (the bell)

  Any of these may live in ../local-only/second_opinion_worker.env (KEY=value, outside Git);
  what is already in the environment wins. launchd: launchd/com.itcs.second-opinion-worker.plist.example

  python scripts/second_opinion_worker.py --dry-run   # the agent answers without a screen?
  python scripts/second_opinion_worker.py --once      # one case and exit
  python scripts/second_opinion_worker.py --listen    # wait for the API's bell on 127.0.0.1:9191
  python scripts/second_opinion_worker.py --try caso.json --project bikeanjoall_2026
                                                      # one case from a file, no API: prompt, check, agent, answer checked
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SAMPLE_PROMPT = 'Responda só com o JSON {"ok": true}.'
PROMPT_NAME = "caso.md"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){10,13}(?!\d)")
_CHECK_MAX_BYTES = 16000


def redact(text: str) -> str:
    return _PHONE.sub("[contato]", _CPF.sub("[documento]", _EMAIL.sub("[contato]", text)))


def run_agent(cmd: str, prompt: str, timeout_s: float) -> tuple[str | None, str | None]:
    """(output, error). Empty working folder, minimal environment, the prompt in a file there
    ({prompt_file}) or on stdin. The prompt never goes on the command line (visible in `ps`)."""
    allowed_env_keys = (
        "PATH", "HOME", "USER", "LANG", "TMPDIR",
        "CURSOR_API_KEY", "CURSOR_CONFIG_DIR",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL",
        "ANTIGRAVITY_LS_ADDRESS", "ANTIGRAVITY_CSRF_TOKEN", "ANTIGRAVITY_MODEL",
    )
    env = {k: os.environ[k] for k in allowed_env_keys if k in os.environ}
    with tempfile.TemporaryDirectory(prefix="second-opinion-") as cwd:
        prompt_file = Path(cwd) / PROMPT_NAME
        prompt_file.write_text(prompt, encoding="utf-8")
        uses_file = "{prompt_file}" in cmd or "{workdir}" in cmd
        argv = [a.replace("{prompt_file}", PROMPT_NAME).replace("{workdir}", cwd) for a in shlex.split(cmd)]
        try:
            proc = subprocess.run(
                argv, input=None if uses_file else prompt, capture_output=True, text=True,
                timeout=timeout_s, cwd=cwd, env=env, stdin=subprocess.DEVNULL if uses_file else None,
            )
        except subprocess.TimeoutExpired:
            return None, f"agent_timeout_{int(timeout_s)}s"
        except OSError as e:
            return None, f"agent_not_runnable: {e}"
    if proc.returncode != 0:
        return None, f"agent_exit_{proc.returncode}: {(proc.stderr or '').strip()[:200]}"
    out = (proc.stdout or "").strip()
    return (out, None) if out else (None, "agent_empty_output")


def read_credentials(project_id: str, folder: Path) -> dict[str, str]:
    """KEY=value lines of <folder>/<project_id>.env. Only the read-only check keys are used."""
    path = folder / f"{project_id}.env"
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", project_id or "") or not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def case_check(project_id: str, source_ref: str, folder: Path, subject_ref: str | None = None) -> tuple[dict | None, str | None]:
    """Read-only check of the case in the project's own system (GET, key 2).

    Needs PROD_READONLY_URL and PROD_READONLY_KEY in the project's credentials file. The
    answer goes to the prompt as verified facts, without contact data, at most 16 KB.
    Sends `source_ref` and, when the case has it, `subject_ref` (the person's id in the project).
    (None, None) when the project has no check.
    """
    creds = read_credentials(project_id, folder)
    url, key = creds.get("PROD_READONLY_URL"), creds.get("PROD_READONLY_KEY")
    if not url or not key:
        return None, None
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
        return None, "case_check_refused: url must be https"
    params = {"source_ref": source_ref}
    if subject_ref:
        params["subject_ref"] = subject_ref
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}{'&' if '?' in url else '?'}{q}", method="GET", headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(_CHECK_MAX_BYTES + 1)
    except (urllib.error.URLError, OSError) as e:
        return None, f"case_check_failed: {str(e)[:120]}"
    if len(raw) > _CHECK_MAX_BYTES:
        return None, "case_check_too_large"
    try:
        data = json.loads(redact(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "case_check_not_json"
    return (data, None) if isinstance(data, dict) else (None, "case_check_not_object")


def with_verified_facts(prompt: str, facts: dict | None, note: str | None) -> str:
    if facts is not None:
        return (prompt + "\n\nFATOS CONSULTADOS AGORA no sistema do projeto (só leitura, pela chave de "
                "consulta; valem mais que o pacote se discordarem):\n" + json.dumps(facts, ensure_ascii=False, indent=1))
    if note:
        return prompt + f"\n\nA consulta ao sistema do projeto não respondeu ({note}); use só o CASO."
    return prompt


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
    except (urllib.error.URLError, OSError, ValueError):
        return 0, None  # API down or answer not JSON


# Kill switch on the host: this file next to credentials/ stops the worker before it claims a case.
STOP_FILE = "DISABLE_SECOND_OPINION"


def work_once(api: str, token: str, cmd: str, agent: str, timeout_s: float, creds_dir: Path) -> str:
    """'paused' | 'empty' | 'done' | 'failed' | 'unauthorized' | 'unreachable'."""
    if (creds_dir.parent / STOP_FILE).exists():
        return "paused"
    status, case = _post(f"{api}/second-opinion/worker/claim", token, None)
    if status == 204:
        return "empty"
    if status != 200 or not case:
        return "unauthorized" if status in (401, 403, 404) else "unreachable"
    facts, note = case_check(case.get("project_id") or "", case.get("source_ref") or "", creds_dir, case.get("subject_ref"))
    output, error = run_agent(cmd, with_verified_facts(case["prompt"], facts, note), timeout_s)
    body = {"agent": agent, "output": output} if output is not None else {"agent": agent, "error": error}
    if facts is not None:
        body["case_check"] = "ok"
    _, result = _post(f"{api}/second-opinion/worker/{case['id']}/result", token, body)
    return (result or {}).get("status", "failed")


def drain(api: str, token: str, cmd: str, agent: str, timeout_s: float, creds_dir: Path) -> None:
    while True:
        outcome = work_once(api, token, cmd, agent, timeout_s, creds_dir)
        print(outcome, flush=True)
        if outcome in ("paused", "empty", "unauthorized", "unreachable"):
            return


def listen(port: int, on_ring) -> None:
    """The bell: POST /notify on 127.0.0.1 drains the queue in the background. Nothing else answers."""
    busy = threading.Lock()

    class Bell(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path != "/notify":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(202)
            self.end_headers()
            if busy.acquire(blocking=False):
                def run():
                    try:
                        on_ring()
                    finally:
                        busy.release()
                threading.Thread(target=run, daemon=True).start()

        def log_message(self, *_):
            pass

    HTTPServer(("127.0.0.1", port), Bell).serve_forever()


def _logic():
    """The API's pure rules (stdlib only), loaded from the repo: --try checks like the API does."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "app" / "second_opinion" / "logic.py"
    spec = importlib.util.spec_from_file_location("second_opinion_logic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def try_case(path: Path, project_id: str, cmd: str, timeout_s: float, creds_dir: Path) -> tuple[dict | None, str | None]:
    """One case from a JSON file, end to end on the host and without the API: the same prompt
    the API builds, the read-only check, the agent, and its answer checked against the case."""
    logic = _logic()
    try:
        case = logic.normalize_case(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, logic.CaseError) as e:
        return None, f"case_invalid: {e}"
    prompt = logic.build_prompt(case, None, project_id)
    facts, note = case_check(project_id, case["source_ref"], creds_dir, case.get("subject_ref"))
    output, error = run_agent(cmd, with_verified_facts(prompt, facts, note), timeout_s)
    if output is None:
        return None, error
    parsed = logic.extract_json(output)
    if parsed is None:
        return None, "agent_output_not_json"
    try:
        return logic.normalize_opinion(parsed, case), None
    except logic.CaseError as e:
        return None, f"answer_invalid: {e}"


WORKER_ENV_FILE = Path(__file__).resolve().parents[2] / "local-only" / "second_opinion_worker.env"


def load_env_file(path: Path) -> None:
    """KEY=value lines into the environment, without overriding what is already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env_file(WORKER_ENV_FILE)
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--listen", action="store_true")
    mode.add_argument("--try", dest="try_file", type=Path, metavar="CASO.json")
    ap.add_argument("--project", help="project_id for --try (its house rules, diretrizes and check)")
    args = ap.parse_args()
    cmd = os.environ.get("SECOND_OPINION_AGENT_CMD", "").strip()
    if not cmd:
        print("SECOND_OPINION_AGENT_CMD não definido", file=sys.stderr)
        return 2
    timeout_s = float(os.environ.get("SECOND_OPINION_TIMEOUT_S", "180"))
    agent = os.environ.get("SECOND_OPINION_AGENT_NAME") or os.path.basename(shlex.split(cmd)[0])
    creds_dir = Path(os.environ.get("SECOND_OPINION_CREDENTIALS_DIR") or Path(__file__).resolve().parents[2] / "local-only" / "credentials")
    if args.try_file:
        if not args.project:
            print("--try precisa de --project", file=sys.stderr)
            return 2
        opinion, err = try_case(args.try_file, args.project, cmd, timeout_s, creds_dir)
        print(json.dumps(opinion, ensure_ascii=False, indent=1) if opinion is not None else f"erro: {err}")
        return 0 if opinion is not None else 1
    if args.dry_run:
        out, err = run_agent(cmd, SAMPLE_PROMPT, timeout_s)
        print(out if out is not None else f"erro: {err}")
        return 0 if out is not None else 1
    token = os.environ.get("SECOND_OPINION_WORKER_TOKEN", "").strip()
    if not token:
        print("SECOND_OPINION_WORKER_TOKEN não definido", file=sys.stderr)
        return 2
    api = os.environ.get("SECOND_OPINION_API_URL", "http://127.0.0.1:28471").rstrip("/")
    if args.listen:
        port = int(os.environ.get("SECOND_OPINION_LISTEN_PORT", "9191"))
        print(f"campainha em 127.0.0.1:{port}/notify", flush=True)
        drain(api, token, cmd, agent, timeout_s, creds_dir)  # what queued while the worker was off
        listen(port, lambda: drain(api, token, cmd, agent, timeout_s, creds_dir))
        return 0
    if args.once:
        print(work_once(api, token, cmd, agent, timeout_s, creds_dir))
        return 0
    drain(api, token, cmd, agent, timeout_s, creds_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
