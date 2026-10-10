"""Run a file task: validate the input, give the model the project's vocabulary, validate the output.

The spec (llm_api/tasks/<task_id>.json) holds input_schema and output_schema (JSON Schema),
the prompt file and prompt_version. Closed lists come from:
- project_vocabulary {"field": "config_key"}: config_json.tasks.<task_id>.<config_key>;
- input_vocabulary {"field": "input_key"}: a list the caller sent in the input.
Those lists become the field's enum, are written at the end of the system prompt, and are
checked on the answer — a value outside them asks the model again, then fails as model_error.
"""
from __future__ import annotations

import copy
from typing import Any

from jsonschema import Draft202012Validator

from app.tasks import engine
from app.tasks.engine import PortError
from app.tasks.registry import project_task_config, task_prompt


def _errors(schema: dict, value: Any, limit: int = 5) -> list[str]:
    out = []
    for err in sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path))[:limit]:
        where = ".".join(str(p) for p in err.path) or "objeto"
        out.append(f"{where}: {err.message}")
    return out


def output_schema_for(spec: dict, project: dict | None, task_input: dict) -> dict:
    """Output schema with the closed lists of this project and this call filled in."""
    schema = copy.deepcopy(spec["output_schema"])
    props = schema.setdefault("properties", {})
    entry = project_task_config(project, spec["task_id"]) or {}
    for field, key in (spec.get("project_vocabulary") or {}).items():
        values = entry.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values) or not values:
            raise PortError("invalid_request", f"O projeto não declarou {key} para a tarefa {spec['task_id']}.")
        props[field] = {"enum": values}
    for field, key in (spec.get("input_vocabulary") or {}).items():
        values = task_input.get(key)
        if isinstance(values, list) and values and all(isinstance(v, str) for v in values):
            props[field] = {"enum": [*values, None]}
        else:
            props[field] = {"type": "null"}
    return schema


def system_prompt_for(spec: dict, schema: dict) -> str:
    lines = [task_prompt(spec["prompt_file"]), "", "## Valores permitidos (use exatamente como escrito)"]
    for field, rule in schema.get("properties", {}).items():
        enum = rule.get("enum")
        if enum:
            shown = ", ".join("null" if v is None else str(v) for v in enum)
            lines.append(f"- {field}: {shown}")
    keys = ", ".join(schema.get("properties", {}).keys())
    lines += ["", f"Responda com UM objeto JSON com as chaves {keys} — nada fora dele."]
    return "\n".join(lines)


async def run_file_task(spec: dict, project: dict | None, task_input: dict) -> dict[str, Any]:
    problems = _errors(spec["input_schema"], task_input)
    if problems:
        raise PortError("invalid_request", "Entrada inválida: " + "; ".join(problems))
    schema = output_schema_for(spec, project, task_input)
    omit = set(spec.get("omit_from_model") or [])
    model_input = {k: v for k, v in task_input.items() if k not in omit}
    obj, model = await engine.chat_json(
        project,
        system=system_prompt_for(spec, schema),
        user=engine.compact_json(model_input),
        validate=lambda o: _errors(schema, o),
        kind=f"task_{spec['task_id']}",
    )
    out = {k: obj.get(k) for k in schema.get("properties", {}) if k in obj}
    if "confidence" in out:
        out["confidence"] = engine.clamp_confidence(out["confidence"])
    return {
        "status": "ok",
        **out,
        "model": model,
        "prompt_version": spec["prompt_version"],
        "warnings": [],
    }


def audit_summary(spec: dict, result: dict[str, Any]) -> dict[str, Any]:
    """Only the labels the spec names — never the summary or any text of the person."""
    fields = spec.get("audit_fields") or []
    return {k: result.get(k) for k in [*fields, "prompt_version"] if k in result}
