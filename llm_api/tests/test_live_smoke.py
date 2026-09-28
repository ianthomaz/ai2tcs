"""Live QA against a running API (Docker on localhost or a public URL).

Pytest (skips unless both variables are set):

  LLM_LIVE_URL=http://127.0.0.1:28471 LLM_LIVE_TOKEN=<LLM_API_TOKEN> \\
    pytest tests/test_live_smoke.py -v

Full route sweep plus one short LLM round-trip, from the repo root or llm_api/:

  python3 tests/test_live_smoke.py

The script reads LLM_LIVE_URL (default http://127.0.0.1:28471) and LLM_LIVE_TOKEN.
If the token is unset, it reads LLM_API_TOKEN from llm_api/.env and never prints it.
Routes that write or delete (ingest, project create/update/delete, uploads) are
checked only without a token, so a missing Authorization stays 401 and nothing is stored.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    import pytest
except ImportError:  # the live runner below uses only the stdlib
    pytest = None

LIVE_URL = os.environ.get("LLM_LIVE_URL", "").rstrip("/")
LIVE_TOKEN = os.environ.get("LLM_LIVE_TOKEN", "")

_PUBLIC = {"/health", "/metrics", "/openapi.json", "/docs", "/redoc"}
_BIKEANJO = ("/feedbackTriage", "/healthNormalize", "/replySuggest")
_MISSING_JOB = "00000000-0000-0000-0000-000000000001"


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):  # noqa: ARG002
        return response

    https_response = http_response


def _env_token(repo_llm_api: Path) -> str:
    if LIVE_TOKEN:
        return LIVE_TOKEN
    env_path = repo_llm_api / ".env"
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("LLM_API_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _call(base: str, method: str, path: str, token: str | None = None, body: dict | None = None, timeout: float = 20.0):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001 — report the failure, do not crash the sweep
        return 0, str(exc).encode()


def _json(raw: bytes) -> dict:
    try:
        out = json.loads(raw.decode() or "{}")
    except json.JSONDecodeError:
        return {}
    return out if isinstance(out, dict) else {}


def _fill(path: str) -> str:
    return (
        path.replace("{job_id}", _MISSING_JOB)
        .replace("{project_id}", "qa-probe")
        .replace("{user_id}", "qa-probe")
        .replace("{key_id}", "qa-probe")
    )


def _record(rows: list[tuple[str, str, str]], name: str, ok: bool, detail: str) -> None:
    rows.append(("PASS" if ok else "FAIL", name, detail))


def run_qa(base: str, token: str) -> list[tuple[str, str, str]]:
    """Return (PASS|FAIL, check, detail) for the live service at base."""
    rows: list[tuple[str, str, str]] = []
    status, raw = _call(base, "GET", "/openapi.json", timeout=15)
    spec = _json(raw)
    paths = spec.get("paths") if status == 200 else None
    _record(rows, "GET /openapi.json", status == 200 and isinstance(paths, dict), f"http {status}")
    if not isinstance(paths, dict):
        return rows

    for path in sorted(paths):
        ops = paths[path]
        for method in ("get", "post", "put", "delete"):
            if method not in ops:
                continue
            concrete = _fill(path)
            label = f"{method.upper()} {path} sem token"
            if path.startswith("/dashboard"):
                code, _ = _call(base, method.upper(), concrete, body={} if method != "get" else None)
                # 422 on POST /dashboard/login: the route is up and rejected an empty body.
                _record(rows, label, code in (200, 302, 303, 307, 400, 401, 403, 422), f"http {code}")
            elif path in _PUBLIC or path in ("/health", "/metrics"):
                code, body = _call(base, "GET", concrete)
                extra = ""
                if path == "/health" and code == 200:
                    extra = " status=" + str(_json(body).get("status"))
                _record(rows, f"GET {path}", code == 200, f"http {code}{extra}")
            else:
                code, _ = _call(
                    base,
                    method.upper(),
                    concrete,
                    body={} if method != "get" else None,
                )
                _record(rows, label, code == 401, f"http {code}")

    code, body = _call(base, "GET", "/projects", token=token)
    projects = _json(body).get("projects") if code == 200 else None
    ids = [p.get("project_id") for p in projects] if isinstance(projects, list) else []
    _record(rows, "GET /projects com token", code == 200 and bool(ids), f"http {code} n={len(ids)}")

    code, body = _call(base, "GET", "/jobs/stats", token=token)
    _record(rows, "GET /jobs/stats", code == 200 and "total" in _json(body), f"http {code}")

    code, _ = _call(base, "GET", "/jobs", token=token)
    _record(rows, "GET /jobs", code == 200, f"http {code}")

    code, _ = _call(base, "GET", f"/status/{_MISSING_JOB}", token=token)
    _record(rows, "GET /status job inexistente", code == 404, f"http {code}")

    code, _ = _call(base, "GET", f"/result/{_MISSING_JOB}", token=token)
    _record(rows, "GET /result job inexistente", code == 404, f"http {code}")

    for path in _BIKEANJO:
        code, _ = _call(base, "POST", path, token=token, body={})
        _record(rows, f"POST {path} com token global", code == 403, f"http {code}")

    code, body = _call(base, "POST", "/nfExtract", token=token, body={})
    nf = _json(body)
    nf_ok = code == 200 and nf.get("status") == "error" and bool(nf.get("errors"))
    _record(rows, "POST /nfExtract sem ficheiro", nf_ok, f"http {code} status={nf.get('status')}")

    code, body = _call(base, "POST", "/boletoExtract", token=token, body={})
    boleto = _json(body)
    boleto_ok = code == 200 and boleto.get("status") == "error"
    _record(rows, "POST /boletoExtract sem ficheiro", boleto_ok, f"http {code} status={boleto.get('status')}")

    def ask(project_id: str) -> None:
        question = f"QA {uuid.uuid4().hex[:8]}. Responda apenas a palavra ok."
        code, body = _call(
            base,
            "POST",
            "/ask",
            token=token,
            body={"project_id": project_id, "question": question, "model": "fast"},
            timeout=30,
        )
        job_id = _json(body).get("job_id")
        if code not in (202, 200) or not job_id:
            _record(rows, f"POST /ask {project_id}", False, f"http {code}")
            return
        deadline = time.time() + 120
        final = "timeout"
        while time.time() < deadline:
            sc, st_body = _call(base, "GET", f"/status/{job_id}", token=token, timeout=15)
            if sc == 0:
                time.sleep(2)
                continue
            final = str(_json(st_body).get("status") or sc)
            if final not in ("queued", "working", "processing"):
                break
            time.sleep(2)
        rc, result = _call(base, "GET", f"/result/{job_id}", token=token, timeout=20)
        answer = str(_json(result).get("answer") or "").strip()
        err = ""
        if final != "done":
            jc, jobs_body = _call(base, "GET", "/jobs?limit=20", token=token)
            if jc == 200:
                for job in _json(jobs_body).get("jobs") or []:
                    if job.get("job_id") == job_id:
                        err = str(job.get("error_message") or "")[:180]
                        break
        preview = answer.replace("\n", " ")[:80]
        _record(
            rows,
            f"POST /ask {project_id}",
            final == "done" and rc == 200 and bool(answer),
            f"status={final} answer={preview!r} {err}".strip(),
        )

    def route(project_id: str) -> None:
        code, body = _call(
            base,
            "POST",
            "/router",
            token=token,
            body={"message": "oi", "project_id": project_id, "model": "fast"},
            timeout=90,
        )
        action = _json(body).get("action")
        detail = f"http {code} action={action}"
        if code >= 500:
            detail += " " + body.decode(errors="replace").replace("\n", " ")[:180]
        _record(rows, f"POST /router {project_id}", code == 200 and action in ("answer_now", "escalate"), detail)

    if not ids:
        _record(rows, "POST /ask", False, "nenhum project_id")
        return rows
    canary = "ian_zap" if "ian_zap" in ids else ids[0]
    ask(canary)
    route(canary)
    if "webplacecc" in ids and "webplacecc" != canary:
        ask("webplacecc")
        route("webplacecc")
    return rows


if pytest is not None:

    @pytest.mark.skipif(not LIVE_URL or not LIVE_TOKEN, reason="Set LLM_LIVE_URL and LLM_LIVE_TOKEN")
    def test_live_health():
        import httpx

        r = httpx.get(f"{LIVE_URL}/health", timeout=10.0)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") in ("ok", "degraded")

    @pytest.mark.skipif(not LIVE_URL or not LIVE_TOKEN, reason="Set LLM_LIVE_URL and LLM_LIVE_TOKEN")
    def test_live_ask_accepts_auth():
        import httpx

        h = {"Authorization": f"Bearer {LIVE_TOKEN}", "Content-Type": "application/json"}
        r = httpx.post(
            f"{LIVE_URL}/ask",
            headers=h,
            json={
                "project_id": "aiclaudia",
                "question": f"live smoke ping {os.getpid()}",
                "model": "fast",
            },
            timeout=30.0,
        )
        assert r.status_code in (202, 409), r.text
        if r.status_code == 202:
            assert "job_id" in r.json()


def main() -> int:
    here = Path(__file__).resolve()
    llm_api = here.parents[1]
    base = (os.environ.get("LLM_LIVE_URL") or "http://127.0.0.1:28471").rstrip("/")
    token = _env_token(llm_api)
    if not token:
        print("LLM_LIVE_TOKEN / LLM_API_TOKEN em falta")
        return 2
    rows = run_qa(base, token)
    failed = 0
    for mark, name, detail in rows:
        failed += mark == "FAIL"
        print(f"{mark}  {name}  {detail}")
    print(f"\n{len(rows) - failed}/{len(rows)} passou, {failed} falhou")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
