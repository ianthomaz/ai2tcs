"""Minimal HTTP client for ai2tcs LLM API."""
from __future__ import annotations

import time
from typing import Any

import httpx


class LLMClient:
    def __init__(self, base_url: str, api_key: str, *, timeout_s: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout_s = timeout_s

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, headers=self.headers, timeout=self.timeout_s)

    def ask(
        self,
        question: str,
        *,
        project_id: str,
        model: str | None = None,
        callback_url: str | None = None,
        poll: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"project_id": project_id, "question": question}
        if model:
            body["model"] = model
        if callback_url:
            body["callback_url"] = callback_url
        with self._client() as client:
            r = client.post("/ask", json=body)
            r.raise_for_status()
            data = r.json()
            if not poll or callback_url:
                return data
            return self.ask_poll(data["job_id"], client=client)

    def ask_poll(self, job_id: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
        own = client is None
        c = client or self._client()
        try:
            deadline = time.time() + self.timeout_s
            while time.time() < deadline:
                st = c.get(f"/status/{job_id}")
                st.raise_for_status()
                if st.json()["status"] in ("done", "no_answer", "failed"):
                    break
                time.sleep(0.5)
            res = c.get(f"/result/{job_id}")
            res.raise_for_status()
            return res.json()
        finally:
            if own:
                c.close()

    def router(self, message: str, *, project_id: str | None = None, model: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"message": message}
        if project_id:
            body["project_id"] = project_id
        if model:
            body["model"] = model
        with self._client() as client:
            r = client.post("/router", json=body)
            r.raise_for_status()
            return r.json()

    def ingest(self, project_id: str, *, incremental: bool = True) -> dict[str, Any]:
        with self._client() as client:
            r = client.post("/ingest", json={"project_id": project_id, "incremental": incremental})
            r.raise_for_status()
            return r.json()

    def nf_extract_file(self, path: str, *, model: str | None = None) -> dict[str, Any]:
        with self._client() as client:
            with open(path, "rb") as fh:
                files = {"file": (path.split("/")[-1], fh)}
                data = {"model": model} if model else None
                r = client.post("/nfExtract", files=files, data=data)
            r.raise_for_status()
            return r.json()

    def boleto_extract_file(self, path: str, *, model: str | None = None) -> dict[str, Any]:
        with self._client() as client:
            with open(path, "rb") as fh:
                files = {"file": (path.split("/")[-1], fh)}
                data = {"model": model} if model else None
                r = client.post("/boletoExtract", files=files, data=data)
            r.raise_for_status()
            return r.json()
