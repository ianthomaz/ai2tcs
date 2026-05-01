#!/usr/bin/env python3
"""
Smoke client for ITCS POST /nfExtract — same shape as BikeAnjo extractNfViaItcs
(multipart field `file`, Authorization Bearer). Stdlib only.

Usage from repo root:
  ITCS_NF_EXTRACT_TOKEN=... python3 scripts/nf_extract_smoke.py --file path/to/nf.pdf
  python3 scripts/nf_extract_smoke.py --file nf.xml --base-url http://127.0.0.1:28471 --token SECRET
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _build_multipart(fields: list[tuple[str, str]], file_field: tuple[str, str, bytes]) -> tuple[str, bytes]:
    """fields: (name, value); file_field: (name, filename, content)."""
    boundary = f"----nfSmoke{secrets.token_hex(12)}"
    crlf = b"\r\n"
    parts: list[bytes] = []

    for name, value in fields:
        parts.append(f"--{boundary}".encode())
        parts.append(crlf)
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(crlf)
        parts.append(crlf)
        parts.append(value.encode())
        parts.append(crlf)

    name, filename, content = file_field
    parts.append(f"--{boundary}".encode())
    parts.append(crlf)
    parts.append(
        f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode(),
    )
    parts.append(crlf)
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(f"Content-Type: {ctype}".encode())
    parts.append(crlf)
    parts.append(crlf)
    parts.append(content)
    parts.append(crlf)
    parts.append(f"--{boundary}--".encode())
    parts.append(crlf)

    body = b"".join(parts)
    return boundary, body


def _contract_checks(obj: dict) -> list[str]:
    notes: list[str] = []
    if obj.get("status") != "ok":
        notes.append(f"status is {obj.get('status')!r}, not ok")
    warns = obj.get("warnings") or []
    if warns:
        notes.append(f"warnings non-empty ({len(warns)}): {warns[:3]!r}")
    desc = obj.get("description")
    if isinstance(desc, str) and desc.strip():
        if not desc.lstrip().lower().startswith("nf emitida"):
            notes.append("description does not start with 'NF emitida …' (contract §5.5)")
    pt = obj.get("payment_type")
    if pt is not None and pt not in (
        "pix",
        "boleto",
        "transferencia",
        "cartao_credito",
        "dinheiro",
    ):
        notes.append(f"payment_type unexpected: {pt!r}")
    return notes


def main() -> int:
    p = argparse.ArgumentParser(description="POST /nfExtract smoke test (BikeAnjo-style multipart).")
    p.add_argument("--file", required=True, type=Path, help="PDF, XML, or image to upload")
    p.add_argument(
        "--base-url",
        default=os.environ.get("ITCS_NF_EXTRACT_URL", "http://127.0.0.1:28471").rstrip("/"),
        help="API base without trailing slash (default: env ITCS_NF_EXTRACT_URL or localhost)",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("ITCS_NF_EXTRACT_TOKEN") or os.environ.get("LLM_API_TOKEN") or "",
        help="Bearer token (default: env ITCS_NF_EXTRACT_TOKEN or LLM_API_TOKEN)",
    )
    p.add_argument("--model", default="", help="Optional model form field (alias e.g. smart)")
    p.add_argument("--timeout", type=float, default=180.0, help="HTTP read timeout seconds (default 180)")
    args = p.parse_args()

    if not args.token.strip():
        print("error: missing token (use --token or ITCS_NF_EXTRACT_TOKEN / LLM_API_TOKEN)", file=sys.stderr)
        return 2

    path: Path = args.file
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2

    raw = path.read_bytes()
    fields: list[tuple[str, str]] = []
    if args.model.strip():
        fields.append(("model", args.model.strip()))

    boundary, body = _build_multipart(fields, ("file", path.name, raw))
    url = f"{args.base_url.rstrip('/')}/nfExtract"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {args.token.strip()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            elapsed = time.perf_counter() - t0
            text = resp.read().decode("utf-8", errors="replace")
            print(f"HTTP {resp.status} in {elapsed:.2f}s")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                print(text[:2000])
                return 1
            print(json.dumps(data, ensure_ascii=False, indent=2))
            checks = _contract_checks(data)
            if checks:
                print("\n-- contract notes --", file=sys.stderr)
                for line in checks:
                    print(line, file=sys.stderr)
            return 0
    except urllib.error.HTTPError as e:
        elapsed = time.perf_counter() - t0
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} in {elapsed:.2f}s", file=sys.stderr)
        print(err_body[:4000], file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        print(f"request failed after {elapsed:.2f}s: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
