#!/usr/bin/env python3
"""Runner de Segunda Opinião usando o Antigravity Local (IDE/language_server no macOS).

Implementa o plano completo (docs/treinamento-llm/plano-conversas-professor-por-pessoa.md):
1. Autodescobre `ANTIGRAVITY_LS_ADDRESS` e `ANTIGRAVITY_CSRF_TOKEN` do processo
   `language_server` ativo na sessão do usuário (se não estiverem no env).
2. Gerencia:
   - **Pool pronto (`ready`)**: conversas pré-criadas e aquecidas (default 10) sem vínculo,
     para que o 1º caso de uma pessoa não pague o custo de `new-conversation` no caminho quente.
   - **Vínculo (`conversations`)**: relação auditável `(project_id, subject_key) <-> conversation_id`,
     com `subject_kind` (`user_id` | `email_hash` | `phone_hash` | `none`), `turns`, `bound_at`,
     `last_used_at` e `expires_at` (`last_used_at + 30 dias`).
   - **Expiração e Delete Real (30 dias)**: chama `DeleteCascadeTrajectory` no `language_server`
     (que apaga a conversa do hub da IDE + `conversations/<id>.db` + `brain/<id>/`) e atualiza
     o estado apenas quando o delete no hub confirma sucesso.
3. Envia o caso via POST HTTP local (`SendAgentMessage`) direto para o `language_server`
   (o caso NUNCA passa pelo argv/`ps` e o `user_id`/contato nunca vai no título nem no prompt).
4. Lê `transcript_full.jsonl` até surgir o novo `PLANNER_RESPONSE` (`status == "DONE"`),
   extrai o JSON e imprime no stdout.

Subcomandos de operação e auditoria:
  python3 antigravity_agent_runner.py --status         # lista pool ready e vínculos ativos/expirados
  python3 antigravity_agent_runner.py --ensure-pool 10 # pré-cria até 10 conversas no pool ready
  python3 antigravity_agent_runner.py --reset-pool 10  # apaga ready + vínculos bound no hub e recria com pso_llm_xxxx
  python3 antigravity_agent_runner.py --expire         # expira e apaga no hub conversas > 30 dias
  python3 antigravity_agent_runner.py <prompt_file>    # julga 1 caso (chamado pelo worker)

Títulos no Antigravity: pso_llm_0000, pso_llm_0001, … (código sequencial 0-9a-z).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENTAPI_BIN = Path.home() / ".gemini" / "antigravity" / "bin" / "agentapi"
BRAIN_DIR = Path.home() / ".gemini" / "antigravity" / "brain"
CONVERSATIONS_DB_DIR = Path.home() / ".gemini" / "antigravity" / "conversations"
STATE_FILE = Path.home() / ".gemini" / "antigravity" / "second_opinion_teacher_state.json"

NO_ACCOUNT_KEY = "_sem_conta"
DEFAULT_POOL_SIZE = 10
DEFAULT_TTL_DAYS = 30
SECONDS_PER_DAY = 86400
# Hub title for teacher threads: pso_llm_0000 … pso_llm_000z … pso_llm_0010 (base36, 0-9a-z).
LABEL_PREFIX = "pso_llm_"
LABEL_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
LABEL_WIDTH = 4
_LABEL_RE = re.compile(rf"^{re.escape(LABEL_PREFIX)}([{LABEL_ALPHABET}]+)$")

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
            # Probe listeners: the agentapi port answers GetConversationMetadata with JSON even
            # on unknown ids (often HTTP 404 + not_found). Other ports reset/401/400 without that.
            for p in ports:
                candidate = f"127.0.0.1:{p}"
                req = urllib.request.Request(
                    f"http://{candidate}/exa.language_server_pb.LanguageServerService/GetConversationMetadata",
                    data=b'{"conversationId":"__probe__"}',
                    headers={"x-codeium-csrf-token": token, "Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        raw = resp.read().decode("utf-8", errors="replace")
                        if raw.strip().startswith("{"):
                            addr = candidate
                            break
                except urllib.error.HTTPError as e:
                    raw = e.read().decode("utf-8", errors="replace")
                    if raw.strip().startswith("{") and e.code in (400, 404):
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


def _short_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def resolve_identity() -> tuple[str, str, str]:
    """Retorna (binding_key, subject_key, subject_kind) conforme § 3 do plano:
    1. user_id (SECOND_OPINION_SUBJECT_REF) -> user:<id> (kind=user_id)
    2. email (SECOND_OPINION_EMAIL_HASH ou SECOND_OPINION_EMAIL) -> email_hash:<sha>
    3. phone (SECOND_OPINION_PHONE_HASH ou SECOND_OPINION_PHONE) -> phone_hash:<sha>
    4. fallback -> _sem_conta (kind=none)
    Isolado por project_id quando presente (`<project_id>:<subject_key>`), mantendo compatibilidade.
    """
    project_id = os.environ.get("SECOND_OPINION_PROJECT_ID", "").strip()
    ref = os.environ.get("SECOND_OPINION_SUBJECT_REF", "").strip()
    email_hash = os.environ.get("SECOND_OPINION_EMAIL_HASH", "").strip()
    email_raw = os.environ.get("SECOND_OPINION_EMAIL", "").strip().lower()
    phone_hash = os.environ.get("SECOND_OPINION_PHONE_HASH", "").strip()
    phone_raw = re.sub(r"\D+", "", os.environ.get("SECOND_OPINION_PHONE", ""))

    if ref and re.fullmatch(r"[A-Za-z0-9:_-]{1,64}", ref):
        if ref.startswith(("user:", "email_hash:", "phone_hash:")):
            kind = ref.split(":", 1)[0]
            kind = "user_id" if kind == "user" else kind
            subj_key = ref
        else:
            subj_key = ref
            kind = "user_id"
    elif email_hash and re.fullmatch(r"[a-f0-9]{8,64}", email_hash):
        subj_key = f"email_hash:{email_hash[:16]}"
        kind = "email_hash"
    elif email_raw and "@" in email_raw:
        subj_key = f"email_hash:{_short_sha256(email_raw)}"
        kind = "email_hash"
    elif phone_hash and re.fullmatch(r"[a-f0-9]{8,64}", phone_hash):
        subj_key = f"phone_hash:{phone_hash[:16]}"
        kind = "phone_hash"
    elif len(phone_raw) >= 10:
        subj_key = f"phone_hash:{_short_sha256(phone_raw)}"
        kind = "phone_hash"
    else:
        subj_key = NO_ACCOUNT_KEY
        kind = "none"

    binding_key = f"{project_id}:{subj_key}" if project_id else subj_key
    return binding_key, subj_key, kind


def subject_key() -> str:
    """Compatibilidade direta com testes: devolve a chave do sujeito."""
    ref = os.environ.get("SECOND_OPINION_SUBJECT_REF", "").strip()
    return ref if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ref) else NO_ACCOUNT_KEY


def ttl_seconds() -> float:
    days = float(os.environ.get("ANTIGRAVITY_TTL_DAYS", str(DEFAULT_TTL_DAYS)))
    return max(1.0, days) * SECONDS_PER_DAY


def encode_label_code(n: int, width: int = LABEL_WIDTH) -> str:
    """Inteiro → código base36 com largura fixa (0 → 0000, 10 → 000a, 36 → 0010)."""
    if n < 0:
        raise ValueError("label seq must be >= 0")
    chars: list[str] = []
    x = n
    for _ in range(width):
        chars.append(LABEL_ALPHABET[x % 36])
        x //= 36
    if x:
        raise ValueError(f"label seq {n} overflows width {width}")
    return "".join(reversed(chars))


def decode_label_code(code: str) -> int | None:
    """Código base36 → inteiro; None se inválido."""
    if not code or any(c not in LABEL_ALPHABET for c in code):
        return None
    n = 0
    for ch in code:
        n = n * 36 + LABEL_ALPHABET.index(ch)
    return n


def teacher_label(n: int) -> str:
    return f"{LABEL_PREFIX}{encode_label_code(n)}"


def parse_teacher_label(label: str | None) -> int | None:
    if not isinstance(label, str):
        return None
    m = _LABEL_RE.fullmatch(label.strip())
    return decode_label_code(m.group(1)) if m else None


def _max_label_seq_in_state(state: dict) -> int:
    """Maior índice já usado em ready / conversations / deleted_log (−1 se nenhum)."""
    best = -1
    for item in state.get("ready") or []:
        if isinstance(item, dict):
            n = parse_teacher_label(item.get("label"))
            if n is not None:
                best = max(best, n)
    for entry in (state.get("conversations") or {}).values():
        if isinstance(entry, dict):
            n = parse_teacher_label(entry.get("label"))
            if n is not None:
                best = max(best, n)
    for row in state.get("deleted_log") or []:
        if isinstance(row, dict):
            n = parse_teacher_label(row.get("label"))
            if n is not None:
                best = max(best, n)
    return best


def allocate_teacher_label(state: dict) -> str:
    """Próximo pso_llm_xxxx livre; avança `label_seq` no state (caller grava)."""
    seq = int(state.get("label_seq") or 0)
    seq = max(seq, _max_label_seq_in_state(state) + 1)
    label = teacher_label(seq)
    state["label_seq"] = seq + 1
    return label


def load_state() -> dict:
    """Carrega `~/.gemini/antigravity/second_opinion_teacher_state.json`:
    {
      "label_seq": int,  # próximo código pso_llm_xxxx
      "ready": [ {"conversation_id", "label", "created_at", "expires_at", "status": "ready"} ],
      "conversations": {
        "<key>": {
          "project_id", "subject_key", "subject_kind", "conversation_id", "label",
          "status": "bound" | "expired", "turns", "bound_at", "last_used_at",
          "expires_at", "created_at"
        }
      },
      "deleted_log": [ ... ]
    }
    """
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    ready = raw.get("ready") if isinstance(raw.get("ready"), list) else []
    convs = raw.get("conversations") if isinstance(raw.get("conversations"), dict) else {}
    deleted_log = raw.get("deleted_log") if isinstance(raw.get("deleted_log"), list) else []
    label_seq = int(raw["label_seq"]) if isinstance(raw.get("label_seq"), int) else 0
    state = {
        "label_seq": label_seq,
        "ready": [r for r in ready if isinstance(r, dict) and r.get("conversation_id")],
        "conversations": convs,
        "deleted_log": deleted_log[-100:],
    }
    # Keep counter ahead of any label already stored (manual edits / old pools).
    state["label_seq"] = max(state["label_seq"], _max_label_seq_in_state(state) + 1)
    return state


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def is_expired(entry: dict, now: float | None = None) -> bool:
    """Verifica se um vínculo ou item do pool passou de `expires_at` (ou 30 dias sem uso)."""
    now = time.time() if now is None else now
    exp = entry.get("expires_at")
    if isinstance(exp, (int, float)) and exp > 0:
        return now > float(exp)
    ref_ts = entry.get("last_used_at") or entry.get("bound_at") or entry.get("created_at") or 0
    if not ref_ts:
        return False
    return now > (float(ref_ts) + ttl_seconds())


def reusable_conversation(state: dict, key: str, max_turns: int, now: float | None = None) -> str | None:
    """A conversa desta pessoa, se ainda cabe mais um caso nela e não expirou (30 dias)."""
    project_id = os.environ.get("SECOND_OPINION_PROJECT_ID", "").strip()
    scoped_key = f"{project_id}:{key}" if project_id and not key.startswith(f"{project_id}:") else key
    entry = state["conversations"].get(scoped_key) or state["conversations"].get(key) or {}
    if entry.get("status") in ("expired", "deleted"):
        return None
    if is_expired(entry, now=now):
        return None
    cid = entry.get("conversation_id") or ""
    return cid if cid and int(entry.get("turns", 0)) < max_turns else None


def remember(state: dict, key: str, cid: str, new: bool, label: str | None = None) -> None:
    """Atualiza vínculo pessoa <-> conversa com timestamps de auditoria e TTL de 30 dias."""
    now = time.time()
    ttl = ttl_seconds()
    project_id = os.environ.get("SECOND_OPINION_PROJECT_ID", "").strip() or "default"
    _, subj_key, subj_kind = resolve_identity()
    if key != NO_ACCOUNT_KEY and subj_key == NO_ACCOUNT_KEY:
        subj_key = key
        subj_kind = "user_id"

    entry = state["conversations"].get(key) or {}
    if new or entry.get("conversation_id") != cid:
        created_at = entry.get("created_at") or now
        entry = {
            "project_id": project_id,
            "subject_key": subj_key,
            "subject_kind": subj_kind,
            "conversation_id": cid,
            "status": "bound",
            "turns": 0,
            "created_at": created_at,
            "bound_at": now,
        }
    if label:
        entry["label"] = label
    entry["status"] = "bound"
    entry["turns"] = int(entry.get("turns", 0)) + 1
    entry["last_used_at"] = now
    entry["expires_at"] = now + ttl
    state["conversations"][key] = entry
    save_state(state)


def spawn_raw_conversation(addr: str, token: str, label: str) -> str:
    """Cria 1 conversa limpa no Antigravity com título pso_llm_xxxx e aguarda ficar pronta."""
    model = os.environ.get("ANTIGRAVITY_MODEL", "flash_lite")
    # Hub title is always the sequential id (ignore ANTIGRAVITY_TITLE so pool threads stay unique).
    env = os.environ.copy()
    env["ANTIGRAVITY_LS_ADDRESS"] = addr
    env["ANTIGRAVITY_CSRF_TOKEN"] = token

    cmd = [
        str(AGENTAPI_BIN),
        "new-conversation",
        f"--model={model}",
        f"--title={label}",
        INIT_TEACHER_PROMPT,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"agentapi new-conversation exit {proc.returncode}: {proc.stderr.strip()}")

    data = json.loads(proc.stdout.strip())
    cid = ((data.get("response") or {}).get("newConversation") or {}).get("conversationId")
    if not cid:
        raise RuntimeError(f"conversationId ausente na resposta do agentapi: {proc.stdout[:200]}")

    deadline = time.time() + 30.0
    while time.time() < deadline:
        if read_planner_responses(cid):
            break
        time.sleep(0.5)
    return cid


def delete_conversation_everywhere(addr: str, token: str, conv_id: str) -> bool:
    """Apaga a conversa nas 3 camadas:
    C. Hub Antigravity via RPC `DeleteCascadeTrajectory`
    B. Disco Mac (`brain/<id>/` e `conversations/<id>.db`)
    Retorna True somente se o delete no hub teve sucesso.
    """
    if not conv_id:
        return False
    res = rpc_post(addr, token, "DeleteCascadeTrajectory", {"cascadeId": conv_id}, timeout=10.0)
    if res is None:
        return False

    # Confirma e limpa eventuais resíduos em disco
    brain_path = BRAIN_DIR / conv_id
    db_path = CONVERSATIONS_DB_DIR / f"{conv_id}.db"
    if brain_path.exists():
        shutil.rmtree(brain_path, ignore_errors=True)
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass
    return True


def expire_and_cleanup(addr: str, token: str, now: float | None = None) -> dict:
    """Varre pool `ready` e `conversations` procurando itens com `now > expires_at` (ou > 30 dias).
    Apaga no hub via `DeleteCascadeTrajectory` e atualiza o estado.
    Se o delete no hub falhar, marca `status = "expired"` sem mentir `deleted`.
    """
    now = time.time() if now is None else now
    state = load_state()
    deleted_ids: list[str] = []
    failed_ids: list[str] = []

    # 1. Limpa itens velhos do pool ready
    still_ready: list[dict] = []
    for item in state["ready"]:
        cid = item.get("conversation_id", "")
        if is_expired(item, now=now):
            if delete_conversation_everywhere(addr, token, cid):
                deleted_ids.append(cid)
                state["deleted_log"].append(
                    {
                        "conversation_id": cid,
                        "label": item.get("label"),
                        "kind": "ready_pool",
                        "deleted_at": now,
                    }
                )
            else:
                item["status"] = "expired"
                failed_ids.append(cid)
                still_ready.append(item)
        else:
            still_ready.append(item)
    state["ready"] = still_ready

    # 2. Limpa vínculos de pessoas expirados (> 30 dias sem uso)
    for key, entry in list(state["conversations"].items()):
        if not isinstance(entry, dict):
            continue
        cid = entry.get("conversation_id", "")
        if entry.get("status") == "expired" or is_expired(entry, now=now):
            if delete_conversation_everywhere(addr, token, cid):
                deleted_ids.append(cid)
                state["deleted_log"].append(
                    {
                        "key": key,
                        "subject_key": entry.get("subject_key", key),
                        "project_id": entry.get("project_id", ""),
                        "conversation_id": cid,
                        "label": entry.get("label"),
                        "turns": entry.get("turns", 0),
                        "deleted_at": now,
                    }
                )
                del state["conversations"][key]
            else:
                entry["status"] = "expired"
                failed_ids.append(cid)

    save_state(state)
    return {"deleted": deleted_ids, "failed_retry": failed_ids}


def ensure_pool(addr: str, token: str, target_size: int = DEFAULT_POOL_SIZE) -> dict:
    """Garante que o pool `ready` tenha pelo menos `target_size` conversas vivas e prontas."""
    state = load_state()
    now = time.time()
    ttl = ttl_seconds()

    # Verifica se as conversas listadas em ready continuam vivas no hub
    valid_ready: list[dict] = []
    for item in state["ready"]:
        cid = item.get("conversation_id", "")
        if not cid or is_expired(item, now=now):
            continue
        meta = rpc_post(addr, token, "GetConversationMetadata", {"conversationId": cid}, timeout=5.0)
        if meta and "metadata" in meta:
            valid_ready.append(item)

    state["ready"] = valid_ready
    save_state(state)

    created: list[dict] = []
    while len(state["ready"]) < target_size:
        label = allocate_teacher_label(state)
        cid = spawn_raw_conversation(addr, token, label)
        now = time.time()
        item = {
            "conversation_id": cid,
            "label": label,
            "status": "ready",
            "created_at": now,
            "expires_at": now + ttl,
        }
        state["ready"].append(item)
        save_state(state)
        created.append({"conversation_id": cid, "label": label})
        if len(state["ready"]) < target_size:
            time.sleep(0.5)

    return {"ready_count": len(state["ready"]), "created": created, "ready": state["ready"]}


def reset_ready_pool(addr: str, token: str, target_size: int = DEFAULT_POOL_SIZE) -> dict:
    """Apaga ready + vínculos bound no hub e recria o pool com títulos pso_llm_xxxx novos."""
    state = load_state()
    deleted_ready: list[dict] = []
    deleted_bound: list[dict] = []
    failed: list[str] = []
    now = time.time()

    for item in list(state["ready"]):
        cid = item.get("conversation_id", "")
        label = item.get("label")
        if not cid:
            continue
        if delete_conversation_everywhere(addr, token, cid):
            deleted_ready.append({"conversation_id": cid, "label": label})
            state["deleted_log"].append(
                {"conversation_id": cid, "label": label, "kind": "ready_pool_reset", "deleted_at": now}
            )
        else:
            failed.append(cid)
    state["ready"] = []

    # Also wipe person bindings so reset does not leave old unlabeled teacher threads behind.
    for key, entry in list(state["conversations"].items()):
        if not isinstance(entry, dict):
            continue
        cid = entry.get("conversation_id", "")
        label = entry.get("label")
        if not cid:
            del state["conversations"][key]
            continue
        if delete_conversation_everywhere(addr, token, cid):
            row = {
                "key": key,
                "conversation_id": cid,
                "label": label,
                "kind": "bound_pool_reset",
                "deleted_at": now,
            }
            deleted_bound.append(row)
            state["deleted_log"].append(row)
            del state["conversations"][key]
        else:
            failed.append(cid)

    save_state(state)
    pool = ensure_pool(addr, token, max(0, target_size))
    return {
        "deleted_ready": deleted_ready,
        "deleted_bound": deleted_bound,
        "failed_delete": failed,
        "pool": pool,
    }


def pop_from_ready_pool(state: dict, addr: str, token: str) -> tuple[str | None, str | None]:
    """Consome 1 conversa do pool `ready`. Retorna (conversation_id, label)."""
    now = time.time()
    while state["ready"]:
        item = state["ready"].pop(0)
        cid = item.get("conversation_id", "")
        label = item.get("label") if isinstance(item.get("label"), str) else None
        if not cid or is_expired(item, now=now):
            continue
        meta = rpc_post(addr, token, "GetConversationMetadata", {"conversationId": cid}, timeout=5.0)
        if meta and "metadata" in meta:
            save_state(state)
            return cid, label
    save_state(state)
    return None, None


def trigger_background_pool_refill(min_ready: int) -> None:
    """Se o pool baixou, dispara um processo em background desacoplado para repor sem atrasar o caso."""
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--ensure-pool", str(min_ready)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def get_or_create_teacher_conversation(addr: str, token: str) -> str:
    """Fluxo do caminho quente (§ 5 do plano):
    1. Existe vínculo `bound` válido (< 30 dias e < max_turns) para a pessoa? Usa-o.
    2. Se não: consome 1 conversa pronta do pool `ready` e faz bind imediato.
    3. Só cria na hora (`spawn_raw_conversation`) se o pool `ready` estiver vazio.
    """
    forced_id = os.environ.get("SECOND_OPINION_CONVERSATION_ID", "").strip()
    if forced_id:
        return forced_id

    max_turns = int(os.environ.get("ANTIGRAVITY_MAX_TURNS_PER_CONVERSATION", "40"))
    pool_target = int(os.environ.get("ANTIGRAVITY_POOL_SIZE", str(DEFAULT_POOL_SIZE)))

    key = subject_key()
    state = load_state()

    # Se o vínculo existente daquela pessoa expirou (> 30 dias), apaga no hub antes de vincular nova
    existing = state["conversations"].get(key)
    if isinstance(existing, dict) and existing.get("conversation_id") and is_expired(existing):
        old_cid = existing["conversation_id"]
        if delete_conversation_everywhere(addr, token, old_cid):
            state["deleted_log"].append(
                {
                    "key": key,
                    "conversation_id": old_cid,
                    "label": existing.get("label"),
                    "reason": "expired_on_bind",
                    "deleted_at": time.time(),
                }
            )
            del state["conversations"][key]
            save_state(state)

    cid = reusable_conversation(state, key, max_turns)
    if cid:
        meta = rpc_post(addr, token, "GetConversationMetadata", {"conversationId": cid}, timeout=5.0)
        if meta and "metadata" in meta:
            bound = state["conversations"].get(key) or {}
            bound_label = bound.get("label") if isinstance(bound, dict) else None
            remember(state, key, cid, new=False, label=bound_label if isinstance(bound_label, str) else None)
            return cid

    # Tenta pegar conversa instantânea do pool ready
    cid, label = pop_from_ready_pool(state, addr, token)
    if cid:
        remember(state, key, cid, new=True, label=label)
        if len(state["ready"]) < pool_target:
            trigger_background_pool_refill(pool_target)
        return cid

    # Fallback se o pool estiver zerado: cria na hora e agenda reposição do pool
    label = allocate_teacher_label(state)
    cid = spawn_raw_conversation(addr, token, label)
    remember(state, key, cid, new=True, label=label)
    if pool_target > 0:
        trigger_background_pool_refill(pool_target)
    return cid


def print_status() -> int:
    state = load_state()
    now = time.time()
    out = {
        "state_file": str(STATE_FILE),
        "label_seq": state.get("label_seq", 0),
        "next_label": teacher_label(int(state.get("label_seq") or 0)),
        "ready_pool_count": len(state["ready"]),
        "bound_conversations_count": len(state["conversations"]),
        "ready": state["ready"],
        "conversations": {
            k: {
                **v,
                "days_until_expiry": round((float(v.get("expires_at", 0)) - now) / SECONDS_PER_DAY, 1)
                if v.get("expires_at")
                else None,
                "expired": is_expired(v, now=now),
            }
            for k, v in state["conversations"].items()
        },
        "recent_deleted_count": len(state["deleted_log"]),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--ensure-pool", type=int, metavar="N")
    ap.add_argument("--reset-pool", type=int, metavar="N")
    ap.add_argument("--expire", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    ap.add_argument("prompt_file", nargs="?")
    args = ap.parse_args()

    if args.help:
        print(__doc__.strip())
        sys.exit(0)

    if args.status:
        sys.exit(print_status())

    if args.ensure_pool is not None or args.expire or args.reset_pool is not None:
        addr, token = discover_language_server()
        if not addr or not token:
            sys.stderr.write("Erro: Language Server do Antigravity não encontrado.\n")
            sys.exit(1)
        result: dict = {}
        if args.expire:
            result["expire"] = expire_and_cleanup(addr, token)
        if args.reset_pool is not None:
            result["reset"] = reset_ready_pool(addr, token, max(0, args.reset_pool))
        elif args.ensure_pool is not None:
            result["pool"] = ensure_pool(addr, token, max(0, args.ensure_pool))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Modo padrão: julgar 1 caso (lendo {prompt_file} ou stdin)
    if args.prompt_file and args.prompt_file != "-":
        try:
            prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as e:
            sys.stderr.write(f"Erro ao ler arquivo de prompt: {e}\n")
            sys.exit(1)
    else:
        prompt_text = sys.stdin.read()

    if not prompt_text.strip():
        sys.stderr.write("Erro: prompt vazio.\n")
        sys.exit(1)

    addr, token = discover_language_server()
    if not addr or not token:
        sys.stderr.write(
            "Erro: Language Server do Antigravity não encontrado. Certifique-se de que o Antigravity.app está aberto.\n"
        )
        sys.exit(1)

    try:
        conv_id = get_or_create_teacher_conversation(addr, token)
    except Exception as e:
        sys.stderr.write(f"Erro ao preparar conversa no Antigravity: {e}\n")
        sys.exit(1)

    before = read_planner_responses(conv_id)
    last_step_idx = before[-1][0] if before else -1

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
