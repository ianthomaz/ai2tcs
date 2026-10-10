"""Text retention: after N days a job keeps its numbers, not its words."""
from unittest.mock import AsyncMock, patch

import pytest

from app.jobs import retention


def test_retention_days_project_wins_over_global():
    assert retention.retention_days({"config_json": {}}) == 0
    with patch("app.config.settings.job_text_retention_days", 90):
        assert retention.retention_days({"config_json": {}}) == 90
        assert retention.retention_days({"config_json": {"policies": {"text_retention_days": 30}}}) == 30
        assert retention.retention_days({"config_json": {"policies": {"text_retention_days": 0}}}) == 0


@pytest.mark.asyncio
async def test_purge_runs_only_for_projects_with_retention():
    projects = [
        {"project_id": "bikeanjoall_2026", "config_json": {"policies": {"text_retention_days": 60}}},
        {"project_id": "webplacecc", "config_json": {}},
    ]
    with patch("app.jobs.retention.db_module.project_list_all", new_callable=AsyncMock, return_value=projects), patch(
        "app.jobs.retention.db_module.job_purge_text", new_callable=AsyncMock, return_value=12
    ) as purge:
        out = await retention.purge_old_job_text()
    assert out == {"bikeanjoall_2026": 12}
    purge.assert_awaited_once_with("bikeanjoall_2026", 60)


@pytest.mark.asyncio
async def test_purge_sql_keeps_numbers_and_skips_running_jobs():
    from app import db

    class _Conn:
        sql = ""

        async def execute(self, sql, *args):
            _Conn.sql, _Conn.args = sql, args
            return "UPDATE 7"

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    with patch("app.db.get_pool", new_callable=AsyncMock, return_value=_Pool()):
        assert await db.job_purge_text("p1", 30) == 7
        assert await db.job_purge_text("p1", 0) == 0
    sql = _Conn.sql
    assert "'__metrics'" in sql and "'__signals'" in sql
    assert "answer = NULL" in sql and "question = '[purged]'" in sql
    assert "NOT IN ('queued', 'working')" in sql
    assert _Conn.args == ("p1", 30)
