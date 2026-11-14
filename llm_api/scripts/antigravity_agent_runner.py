#!/usr/bin/env python3
"""Runner de Segunda Opinião usando o Antigravity Local (IDE/language_server no macOS).

Como funciona (100% verificado contra o build 2.31.2 no mini62):
1. Autodescobre `ANTIGRAVITY_LS_ADDRESS` e `ANTIGRAVITY_CSRF_TOKEN` do processo
   `language_server` ativo na sessão do usuário (se não estiverem no env).
2. Reaproveita uma conversa contínua de professor (evita poluir o hub com dezenas
   de chats e garante que o caso NUNCA passe pelo argv/`ps`).
   - Se a conversa ainda não existir, cria apenas 1 vez via `agentapi new-conversation`
     com um prompt genérico sem dados de caso.
3. Envia o caso via POST HTTP local (`SendAgentMessage`) direto para o `language_server`.
4. Lê o arquivo `transcript.jsonl` / `transcript_full.jsonl` oficial em
   `~/.gemini/antigravity/brain/<conv_id>/.system_generated/logs/` (JSON Lines limpo,
   sem precisar decodificar BLOB Protobuf do SQLite) até surgir o novo `PLANNER_RESPONSE`
   com `status == "DONE"`.
5. Extrai o primeiro objeto JSON válido da resposta do modelo e imprime estritamente no stdout.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENTAPI_BIN = Path.home() / ".gemini" / "antigravity" / "bin" / "agentapi"
BRAIN_DIR = Path.home() / ".gemini" / "antigravity" / "brain"
STATE_FILE = Path.home() / ".gemini" / "antigravity" / "second_opinion_teacher_state.json"

INIT_TEACHER_PROMPT = (
    "Você é o professor silencioso da fila de segunda opinião (ai2tcs). "
    "Em cada mensagem futura, você receberá as regras, diretrizes e um CASO. "
    "NUNCA use nenhuma ferramenta (run_command, read_file, etc.). "
    "Responda SEMPRE única e exclusivamente com o objeto JSON cru solicitado, sem markdown."
)


def extract_json_block(text: str) -> dict | None:
    """Extrai o primeiro objeto JSON válido do texto."""
    if not isinstance(text, str) or not text.strip():
        return None
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def discover_language_server() -> tuple[str | None, str | None]:
    """Obtém (address, csrf_token) do ambiente ou inspecionando o language_server rodando."""
    addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS", "").strip()
    token = os.environ.get("ANTIGRAVITY_CSRF_TOKEN", "").strip()
    if addr and token:
        return addr, token

    try:
        ps_out = subprocess.check_output(["ps", "-ax", "-o", "pid,command"], text=True, timeout=5)
    except Exception:
        return None, None

    pid = None
    for line in ps_out.splitlines():
        if "language_server" in line and "--csrf_token" in line:
            parts = line.strip().split(None, 1)
            if parts:
                pid = parts[0]
            m = re.search(r"--csrf_token[=\s]+([A-Za-z0-9_-]+)", line)
            if m and not token:
                token = m.group(1)
            break

    if not pid or not token:
        return None, None

    if not addr:
        try:
            lsof_out = subprocess.check_output(
                ["lsof", "-Pan", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"],
                text=True,
                timeout=5,
            )
            ports = re.findall(r"127\.0\.0\.1:(\d+)\s+\(LISTEN\)", lsof_out)
            for p in ports:
                candidate = f"127.0.0.1:{p}"
                req = urllib.request.Request(
                    f"http://{candidate}/exa.language_server_pb.LanguageServerService/GetUserSettings",
                    data=b"{}",
                    headers={"x-codeium-csrf-token": token, "Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        if resp.status == 200:
                            addr = candidate
                            break
                except Exception:
                    continue
        except Exception:
            pass

    return (addr or None), (token or None)


def rpc_post(addr: str, token: str, method: str, payload: dict, timeout: float = 15.0) -> dict | None:
    """Chama um método JSON RPC no LanguageServerService."""
    url = f"http://{addr}/exa.language_server_pb.LanguageServerService/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-codeium-csrf-token": token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except Exception:
        return None


def read_planner_responses(conv_id: str) -> list[tuple[int, str]]:
    """Lê todos os steps PLANNER_RESPONSE concluídos (step_index, content) do transcript."""
    log_dir = BRAIN_DIR / conv_id / ".system_generated" / "logs"
    full_path = log_dir / "transcript_full.jsonl"
    compact_path = log_dir / "transcript.jsonl"
    target = full_path if full_path.is_file() else compact_path
    if not target.is_file():
        return []

    results: list[tuple[int, str]] = []
    try:
        for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                obj.get("type") == "PLANNER_RESPONSE"
                and obj.get("status") == "DONE"
                and isinstance(obj.get("content"), str)
                and obj["content"].strip()
            ):
                results.append((int(obj.get("step_index", 0)), obj["content"]))
    except OSError:
        return []
    return results


NO_ACCOUNT_KEY = "_sem_conta"


def subject_key() -> str:
    """De quem é o caso: o `user_id` que o worker passa no ambiente; sem conta, uma conversa geral."""
    ref = os.environ.get("SECOND_OPINION_SUBJECT_REF", "").strip()
    return ref if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ref) else NO_ACCOUNT_KEY


def load_state() -> dict:
    """`{"conversations": {chave: {conversation_id, turns, created_at}}}`; arquivo ilegível = vazio."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"conversations": {}}
    convs = state.get("conversations") if isinstance(state, dict) else None
    return {"conversations": convs if isinstance(convs, dict) else {}}


def reusable_conversation(state: dict, key: str, max_turns: int) -> str | None:
    """A conversa desta pessoa, se ainda cabe mais um caso nela."""
    entry = state["conversations"].get(key) or {}
    cid = entry.get("conversation_id") or ""
    return cid if cid and int(entry.get("turns", 0)) < max_turns else None


def remember(state: dict, key: str, cid: str, new: bool) -> None:
    """Conta o caso na conversa da pessoa e grava o arquivo (fica só no Mac)."""
    entry = state["conversations"].get(key) or {}
    if new or entry.get("conversation_id") != cid:
        entry = {"conversation_id": cid, "turns": 0, "created_at": time.time()}
    entry["turns"] = int(entry.get("turns", 0)) + 1
    state["conversations"][key] = entry
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_or_create_teacher_conversation(addr: str, token: str) -> str:
    """Uma conversa do professor por pessoa (`user_id`), criada na primeira vez. O título e a
    mensagem inicial não levam o id: a ligação id → conversa mora só no arquivo de estado."""
    forced_id = os.environ.get("ANTIGRAVITY_CONVERSATION_ID", "").strip()
    if forced_id:
        return forced_id

    max_turns = int(os.environ.get("ANTIGRAVITY_MAX_TURNS_PER_CONVERSATION", "40"))
    key = subject_key()
    state = load_state()
    cid = reusable_conversation(state, key, max_turns)
    if cid:
        meta = rpc_post(addr, token, "GetConversationMetadata", {"conversationId": cid}, timeout=5.0)
        if meta and "metadata" in meta:
            remember(state, key, cid, new=False)
            return cid

    # Precisa criar uma nova conversa (o prompt inicial é fixo, sem dados sensíveis no ps)
    model = os.environ.get("ANTIGRAVITY_MODEL", "flash_lite")
    title = os.environ.get("ANTIGRAVITY_TITLE", "Professor Segunda Opinião (ai2tcs)")
    env = os.environ.copy()
    env["ANTIGRAVITY_LS_ADDRESS"] = addr
    env["ANTIGRAVITY_CSRF_TOKEN"] = token

    cmd = [
        str(AGENTAPI_BIN),
        "new-conversation",
        f"--model={model}",
        f"--title={title}",
        INIT_TEACHER_PROMPT,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"agentapi new-conversation exit {proc.returncode}: {proc.stderr.strip()}")

    data = json.loads(proc.stdout.strip())
    cid = ((data.get("response") or {}).get("newConversation") or {}).get("conversationId")
    if not cid:
        raise RuntimeError(f"conversationId ausente na resposta do agentapi: {proc.stdout[:200]}")

    # Aguarda o turno de boas-vindas terminar antes de enviar o primeiro caso real
    deadline = time.time() + 30.0
    while time.time() < deadline:
        if read_planner_responses(cid):
            break
        time.sleep(0.5)

    remember(state, key, cid, new=True)
    return cid


def main() -> None:
    # 1. Lê o prompt do arquivo ({prompt_file}) ou da stdin
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        try:
            prompt_text = Path(sys.argv[1]).read_text(encoding="utf-8")
        except OSError as e:
            sys.stderr.write(f"Erro ao ler arquivo de prompt: {e}\n")
            sys.exit(1)
    else:
        prompt_text = sys.stdin.read()

    if not prompt_text.strip():
        sys.stderr.write("Erro: prompt vazio.\n")
        sys.exit(1)

    # 2. Descobre o Language Server do Antigravity
    addr, token = discover_language_server()
    if not addr or not token:
        sys.stderr.write(
            "Erro: Language Server do Antigravity não encontrado. Certifique-se de que o Antigravity.app está aberto.\n"
        )
        sys.exit(1)

    # 3. Obtém ou cria a conversa do professor
    try:
        conv_id = get_or_create_teacher_conversation(addr, token)
    except Exception as e:
        sys.stderr.write(f"Erro ao preparar conversa no Antigravity: {e}\n")
        sys.exit(1)

    # Registra o último step_index antes de enviar a mensagem
    before = read_planner_responses(conv_id)
    last_step_idx = before[-1][0] if before else -1

    # 4. Envia o caso via POST HTTP local (NUNCA passa pelo argv / ps!)
    instruction = (
        "AVALIE O CASO ABAIXO E RESPONDA APENAS COM O OBJETO JSON PURO (SEM MARKDOWN, SEM TOOLS):\n\n"
        + prompt_text
    )
    res = rpc_post(
        addr,
        token,
        "SendAgentMessage",
        {"recipient": conv_id, "content": instruction},
        timeout=15.0,
    )
    if res is None:
        sys.stderr.write(f"Erro ao enviar mensagem HTTP para a conversa {conv_id}\n")
        sys.exit(1)

    # 5. Aguarda o novo PLANNER_RESPONSE no transcript_full.jsonl
    timeout_wait = float(os.environ.get("ANTIGRAVITY_TIMEOUT", "160"))
    deadline = time.time() + timeout_wait

    while time.time() < deadline:
        time.sleep(1.0)
        responses = read_planner_responses(conv_id)
        for step_idx, content in reversed(responses):
            if step_idx > last_step_idx:
                json_obj = extract_json_block(content)
                if json_obj is not None:
                    print(json.dumps(json_obj, ensure_ascii=False))
                    sys.exit(0)

    sys.stderr.write(f"Timeout ({int(timeout_wait)}s) aguardando resposta JSON na conversa {conv_id}\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
