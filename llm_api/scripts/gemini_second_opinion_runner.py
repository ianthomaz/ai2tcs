#!/usr/bin/env python3
"""Runner de Segunda Opinião via Gemini REST API (zero dependências externas).

Lê o prompt via stdin ou de arquivo ({prompt_file}), chama o endpoint v1beta da API
do Gemini com `response_mime_type="application/json"` e cospe estritamente o JSON no stdout.
Não requer pacotes pip adicionais (usa apenas urllib e json da biblioteca padrão do Python).
"""

import json
import os
import sys
import urllib.error
import urllib.request

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def main():
    if not API_KEY:
        sys.stderr.write("Erro: GEMINI_API_KEY ou GOOGLE_API_KEY não definida no ambiente.\n")
        sys.exit(1)

    # Lê o prompt: por argumento posicional (arquivo) ou stdin
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        filepath = sys.argv[1]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                prompt_text = f.read()
        except OSError as e:
            sys.stderr.write(f"Erro ao ler arquivo de prompt '{filepath}': {e}\n")
            sys.exit(1)
    else:
        prompt_text = sys.stdin.read()

    if not prompt_text.strip():
        sys.stderr.write("Erro: prompt vazio recebido.\n")
        sys.exit(1)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt_text}]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)
            # Extrai o texto gerado pelo modelo
            candidates = res_json.get("candidates", [])
            if not candidates:
                sys.stderr.write("Erro: Gemini não retornou candidates.\n")
                sys.exit(1)
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                sys.stderr.write("Erro: formato de resposta inesperado do Gemini.\n")
                sys.exit(1)
            raw_text = parts[0]["text"].strip()
            # Valida se é JSON de fato antes de imprimir no stdout
            json.loads(raw_text)
            print(raw_text)
            sys.exit(0)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"Erro HTTP {e.code}: {err_msg[:300]}\n")
        sys.exit(2)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Erro de conexão: {e.reason}\n")
        sys.exit(3)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Erro: resposta não foi JSON parseável: {e}\n")
        sys.exit(4)
    except Exception as e:
        sys.stderr.write(f"Erro inesperado: {e}\n")
        sys.exit(5)


if __name__ == "__main__":
    main()
