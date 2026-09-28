"""POST /healthNormalize — tidy the health residue the Bike Anjo taxonomy did not map. No RAG.

Contract: contracts/bikeanjo/health-normalize.schema.json · prompt health-v1.
The port does not judge health (no severity, no relevance, no diagnosis): it maps to the
closed code list and cleans the rest. The one rule that cannot fail: text that names a
condition, allergy, limitation or medicine is never marked generic_statement.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.bikeanjo.common import PortError, chat_json, clamp_confidence, compact_json, fold, load_prompt

PROMPT_VERSION = "health-v1"

CODES = ("diabetes", "hypertension", "asthma", "renal", "tdah", "tea", "t21")
FREE_TEXT_MAX = 500

# Sentence frames removed from the start of each item of `outras`.
_FRAMES = re.compile(
    r"^(eu\s+)?(tenho|sou|estou|faco uso de|faço uso de|uso|tomo|diagnostico de|diagnóstico de|"
    r"tenho diagnostico de|tenho diagnóstico de)\s+",
    re.IGNORECASE,
)

# Substance in the text: a condition, allergy, limitation or medicine. Matched on fold().
_SUBSTANCE = re.compile(
    r"alergi|remedi|medica|bombinha|insulina|\buso\b|\btomo\b|\btoma\b|crise|doenc|sindrom|"
    r"deficien|limitac|cirurg|operad|protese|marcapasso|epileps|convuls|ansiedad|depress|panico|"
    r"asma|asmat|diabet|pressao|hipertens|cardi|coracao|renal|rim\b|autis|\btea\b|tdah|down|"
    r"\bdor\b|joelho|coluna|hernia|labirint|enxaquec|visao|cego|surd|audit|cadeira de rodas|"
    r"gravid|\w{3,}ite\b|\w{3,}ose\b"
)


class Person(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: Literal["user", "dependent"]
    id: str


class HealthNormalizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source: Literal["health"] = "health"
    person: Person
    locale: str = "pt-BR"
    known_codes: list[str] = []
    free_text: str = Field(min_length=1, max_length=FREE_TEXT_MAX)


def has_substance(text: str) -> bool:
    return bool(_SUBSTANCE.search(fold(text)))


def system_prompt() -> str:
    return (
        load_prompt("health-normalize-v1.md")
        + "\n\nResponda com UM objeto JSON com as chaves codes, outras, generic_statement, "
        "changed, confidence — nada fora dele."
    )


def user_prompt(req: HealthNormalizeRequest, known: list[str]) -> str:
    # No person id: the model only needs the text and the codes already chosen.
    return compact_json({"known_codes": known, "free_text": req.free_text.strip()})


def validate_model_output(obj: dict[str, Any]) -> list[str]:
    problems = []
    if not isinstance(obj.get("generic_statement"), bool):
        problems.append("generic_statement precisa ser true ou false")
    if not isinstance(obj.get("codes", []), list):
        problems.append("codes precisa ser lista")
    return problems


def clean_outras(raw: str) -> str | None:
    """Comparison standard: lowercase, items once each, joined by ', ', no sentence frame."""
    items: list[str] = []
    seen: set[str] = set()
    for part in re.split(r",|;|\s+e\s+", raw.lower()):
        item = _FRAMES.sub("", part.strip(" .!\n\t")).strip(" .!")
        key = fold(item)
        if item and key not in seen:
            seen.add(key)
            items.append(item)
    out = ", ".join(items)[:FREE_TEXT_MAX]
    return out or None


def postprocess(
    obj: dict[str, Any], req: HealthNormalizeRequest, known: list[str], model: str
) -> dict[str, Any]:
    warnings: list[str] = []
    codes: list[str] = []
    rejected: list[str] = []
    for c in obj.get("codes") or []:
        cv = str(c or "").strip().lower()
        if cv in CODES:
            if cv not in codes:
                codes.append(cv)
        elif cv:
            rejected.append(cv)
    if rejected:
        warnings.append("code_outside_allowlist_moved_to_outras")

    outras_raw = obj.get("outras")
    outras_parts = [str(outras_raw)] if isinstance(outras_raw, str) and outras_raw.strip() else []
    outras = clean_outras(", ".join(outras_parts + rejected)) if (outras_parts or rejected) else None

    generic = obj.get("generic_statement") is True
    if generic and (codes or has_substance(req.free_text)):
        generic = False
        warnings.append("generic_statement_overridden")
        if outras is None and not codes:
            outras = clean_outras(req.free_text)
    if generic:
        codes, outras = [], None
    elif outras is None and not codes:
        # Nothing mapped and nothing cleaned: keep what the person wrote rather than lose it.
        outras = clean_outras(req.free_text)

    changed = generic or bool(set(codes) - set(known)) or fold(outras or "") != fold(req.free_text)

    return {
        "status": "ok",
        "codes": codes,
        "outras": outras,
        "generic_statement": generic,
        "changed": changed,
        "confidence": clamp_confidence(obj.get("confidence")),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "warnings": sorted(set(warnings)),
    }


async def run(req: HealthNormalizeRequest, project: dict | None) -> dict[str, Any]:
    if req.locale != "pt-BR":
        raise PortError("invalid_request", "locale suportado: pt-BR")
    known = [c for c in dict.fromkeys(str(c).strip().lower() for c in req.known_codes) if c in CODES]
    obj, model = await chat_json(
        project,
        system=system_prompt(),
        user=user_prompt(req, known),
        validate=validate_model_output,
    )
    return postprocess(obj, req, known, model)


def audit_summary(result: dict[str, Any]) -> dict[str, Any]:
    """What the Job row keeps: no codes, no text — health data stays with Bike Anjo."""
    return {
        "changed": result.get("changed"),
        "generic_statement": result.get("generic_statement"),
        "confidence": result.get("confidence"),
        "prompt_version": result.get("prompt_version"),
    }
