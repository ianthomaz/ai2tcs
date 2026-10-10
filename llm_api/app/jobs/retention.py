"""Text retention for Job rows: after N days a job keeps its numbers, not its words.

N per project: config_json.policies.text_retention_days, else JOB_TEXT_RETENTION_DAYS, else
keep forever (0). Runs with the madrugada maintenance (app/jobs/worker.py). Counts, status,
metrics (__metrics) and signals (__signals) stay, so /metrics and the dashboard stats still add up.
"""
from __future__ import annotations

import logging

from app import db as db_module
from app.config import settings

logger = logging.getLogger(__name__)


def retention_days(project: dict) -> int:
    cfg = project.get("config_json") or {}
    policies = (cfg.get("policies") or {}) if isinstance(cfg, dict) else {}
    raw = policies.get("text_retention_days") if isinstance(policies, dict) else None
    try:
        return max(0, int(raw)) if raw is not None else max(0, int(settings.job_text_retention_days))
    except (TypeError, ValueError):
        return 0


async def purge_old_job_text() -> dict[str, int]:
    """Purge per project; returns {project_id: rows purged} for projects with a retention."""
    out: dict[str, int] = {}
    for project in await db_module.project_list_all():
        days = retention_days(project)
        if days <= 0:
            continue
        pid = project["project_id"]
        try:
            out[pid] = await db_module.job_purge_text(pid, days)
        except Exception:
            logger.exception("job text retention failed for %s", pid)
    if any(out.values()):
        logger.info("job text retention: %s", out)
    return out
