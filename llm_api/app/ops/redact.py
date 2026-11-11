"""Sanitizacao de linhas de log e textos antes de sair pela observacao (/api/ops/observe).

Remove telefones, CPFs/documentos, emails, bearer tokens, chaves itcs_*, sk-*, senhas,
chaves de banco de dados e ANSI escapes.
"""
import re

MAX_CHARS = 2000

SECRET_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "[redacted]"),
    (re.compile(r"itcs_[a-z0-9_]+", re.IGNORECASE), "[redacted]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[redacted]"),
    (re.compile(r"\b(token|password|senha|secret|apikey|api_key|access_token)=([^&\s\"']+)", re.IGNORECASE), r"\1=[redacted]"),
    (re.compile(r'"((?:token|password|senha|secret|authorization))"\s*:\s*"[^"]*"', re.IGNORECASE), r'"\1":"[redacted]"'),
    (re.compile(r"/m/[A-Za-z0-9_-]+"), "[redacted]"),
    (re.compile(r"[?&](token|code|magic)=[^&\s]+", re.IGNORECASE), r"\1=[redacted]"),
    (re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE), "[redacted]"),
    (re.compile(r'"userId"\s*:\s*"[^"]*"'), '"userId":"[id]"'),
    (re.compile(r"\buserId\s*=\s*[\"']?[A-Za-z0-9_]+"), "userId=[id]"),
    (re.compile(r"\buser_id\s*[:=]\s*[\"']?[A-Za-z0-9_]+", re.IGNORECASE), "user_id=[id]"),
    (re.compile(r"\b\d{4}[ .-]?\d{4}[ .-]?\d{4}[ .-]?\d{4}\b"), "[redacted]"),
    (re.compile(r"\b\d{11}\b"), "[documento]"),
]

# DDD brasileiro valido: 11 a 99
PHONE_PATTERNS = [
    re.compile(r"(?:\+55\s*)?(?:\b|\()([1-9][1-9])(?:\)|\s*)9\d{4}[-.\s]?\d{4}\b"),
    re.compile(r"(?:\+55\s*)?(?:\b|\()([1-9][1-9])(?:\)|\s*)[2-8]\d{3}[-.\s]?\d{4}\b"),
]
CPF_PATTERNS = [
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    re.compile(r"\b\d{11}\b"),
]
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def redact_contact_data(text: str) -> str:
    """Mascara emails, telefones e documentos (CPF)."""
    out = EMAIL_PATTERN.sub("[email]", text)
    for pat in PHONE_PATTERNS:
        out = pat.sub("[telefone]", out)
    for pat in CPF_PATTERNS:
        out = pat.sub("[documento]", out)
    return out


def redact_log_line(line: str) -> str:
    """Limpeza completa de uma linha de log antes de sair pela observacao."""
    out = redact_contact_data(line)
    for pattern, replacement in SECRET_RULES:
        out = pattern.sub(replacement, out)
    out = ANSI_PATTERN.sub("", out)
    out = out.strip()
    if len(out) > MAX_CHARS:
        return f"{out[:MAX_CHARS]}…"
    return out
