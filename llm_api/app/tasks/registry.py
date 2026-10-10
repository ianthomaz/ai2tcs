"""Which text tasks exist and who may run them.

Two kinds, same route (POST /task/{task_id}):
- file task: llm_api/tasks/<task_id>.json (+ prompt in tasks/prompts/). A project runs it
  when its config_json.tasks has an entry for the task — that entry carries the project's
  vocabulary (e.g. {"text_triage": {"categories": [...]}}). New task = new file, no code.
- code task: a port with its own guards, registered here with its handler and the projects
  whose key may run it (`allowed_projects`). Today: the Bike Anjo ops ports
  (BIKEANJO_OPS_PROJECT_IDS) — same rule as their routes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

TASKS_DIR = Path(__file__).resolve().parents[2] / "tasks"
_TASK_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True)
class CodeTask:
    task_id: str
    request_model: type[BaseModel]
    run: Callable[[Any, str, dict | None], Awaitable[dict[str, Any]]]
    audit_summary: Callable[[dict[str, Any]], dict[str, Any]]
    allowed_projects: Callable[[], set[str]]
    description: str = ""


def _code_tasks() -> dict[str, CodeTask]:
    from app.bikeanjo import feedback_triage, health_normalize, reply_suggest
    from app.config import settings

    bikeanjo_ops = settings.bikeanjo_ops_project_id_set
    ops_doc = "porta de código (docs/18)"

    return {
        "feedback_triage": CodeTask(
            "feedback_triage",
            feedback_triage.FeedbackTriageRequest,
            lambda req, _pid, project: feedback_triage.run(req, project),
            feedback_triage.audit_summary,
            bikeanjo_ops,
            ops_doc,
        ),
        "health_normalize": CodeTask(
            "health_normalize",
            health_normalize.HealthNormalizeRequest,
            lambda req, _pid, project: health_normalize.run(req, project),
            health_normalize.audit_summary,
            bikeanjo_ops,
            ops_doc,
        ),
        "reply_suggest": CodeTask(
            "reply_suggest",
            reply_suggest.ReplySuggestRequest,
            reply_suggest.run,
            reply_suggest.audit_summary,
            bikeanjo_ops,
            ops_doc,
        ),
    }


def code_task(task_id: str) -> CodeTask | None:
    return _code_tasks().get(task_id)


def list_code_tasks() -> list[CodeTask]:
    return list(_code_tasks().values())


@lru_cache(maxsize=None)
def file_task(task_id: str) -> dict[str, Any] | None:
    if not _TASK_ID.match(task_id or ""):
        return None
    path = TASKS_DIR / f"{task_id}.json"
    if not path.is_file():
        return None
    spec = json.loads(path.read_text(encoding="utf-8"))
    return spec if spec.get("task_id") == task_id else None


@lru_cache(maxsize=None)
def task_prompt(prompt_file: str) -> str:
    """Prompt body: the text after the first `---` rule (above it are notes for people)."""
    text = (TASKS_DIR / "prompts" / prompt_file).read_text(encoding="utf-8")
    parts = re.split(r"^---\s*$", text, maxsplit=1, flags=re.MULTILINE)
    return (parts[1] if len(parts) == 2 else text).strip()


def project_task_config(project: dict | None, task_id: str) -> dict[str, Any] | None:
    """The project's entry for a file task (config_json.tasks.<task_id>); None = not enabled."""
    cfg = (project or {}).get("config_json") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            return None
    tasks = cfg.get("tasks") if isinstance(cfg, dict) else None
    entry = tasks.get(task_id) if isinstance(tasks, dict) else None
    return entry if isinstance(entry, dict) else None


def list_file_tasks() -> list[str]:
    return sorted(p.stem for p in TASKS_DIR.glob("*.json") if _TASK_ID.match(p.stem))
