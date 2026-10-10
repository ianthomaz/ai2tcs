"""A project key sees only its own project: jobs, job lists, project list. Operator
surfaces (create/delete project, global stats, maintenance) take the global token only."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.auth import hash_key

GLOBAL = {"Authorization": "Bearer test-token"}
BA_KEY = {"Authorization": "Bearer itcs_bikeanjoall_2026_x"}

_JOB_OTHER = {
    "id": "j-web",
    "project_id": "webplacecc",
    "status": "done",
    "answer": "segredo de outro projeto",
    "sources": [],
    "created_at": datetime(2026, 10, 1),
}
_JOB_OWN = {**_JOB_OTHER, "id": "j-ba", "project_id": "bikeanjoall_2026", "answer": "oi"}


@pytest.fixture(autouse=True)
def _keys():
    async def key_project(key_hash: str):
        return {hash_key("itcs_bikeanjoall_2026_x"): "bikeanjoall_2026"}.get(key_hash)

    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.auth.db_module.api_key_get_project_id", side_effect=key_project
    ):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/status/j-web", "/result/j-web"])
async def test_key_never_sees_a_job_of_another_project(client, path):
    with patch("app.api.ask.db_module.job_get", new_callable=AsyncMock, return_value=_JOB_OTHER):
        r = await client.get(path, headers=BA_KEY)
    assert r.status_code == 404
    assert "segredo" not in r.text


@pytest.mark.asyncio
async def test_key_reads_its_own_job_and_the_operator_reads_any(client):
    with patch("app.api.ask.db_module.job_get", new_callable=AsyncMock, return_value=_JOB_OWN):
        assert (await client.get("/result/j-ba", headers=BA_KEY)).json()["answer"] == "oi"
    with patch("app.api.ask.db_module.job_get", new_callable=AsyncMock, return_value=_JOB_OTHER):
        assert (await client.get("/result/j-web", headers=GLOBAL)).status_code == 200


@pytest.mark.asyncio
async def test_key_cannot_cancel_a_job_of_another_project(client):
    with patch("app.api.jobs.db_module.job_get", new_callable=AsyncMock, return_value={**_JOB_OTHER, "status": "queued"}), patch(
        "app.api.jobs.db_module.job_cancel", new_callable=AsyncMock
    ) as cancel:
        r = await client.post("/jobs/j-web/cancel", headers=BA_KEY)
    assert r.status_code == 404
    cancel.assert_not_called()


@pytest.mark.asyncio
async def test_job_list_with_a_key_is_its_own_project(client):
    with patch("app.api.jobs.db_module.job_list", new_callable=AsyncMock, return_value=([], 0)) as listing:
        r = await client.get("/jobs", headers=BA_KEY)
    assert r.status_code == 200
    assert listing.await_args.kwargs["project_id"] == "bikeanjoall_2026"


@pytest.mark.asyncio
async def test_project_list_with_a_key_is_its_own_project(client):
    projects = [{"project_id": "bikeanjoall_2026", "name": "BA"}, {"project_id": "webplacecc", "name": "W"}]
    with patch("app.api.projects.db_module.project_list_all", new_callable=AsyncMock, return_value=projects), patch(
        "app.api.projects.db_module.project_get_themes", new_callable=AsyncMock, return_value=[]
    ):
        r = await client.get("/projects", headers=BA_KEY)
        g = await client.get("/projects", headers=GLOBAL)
    assert [p["project_id"] for p in r.json()["projects"]] == ["bikeanjoall_2026"]
    assert g.json()["total"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/projects", {"project_id": "bikeanjoall_2026", "name": "x"}),
        ("delete", "/projects/bikeanjoall_2026", None),
        ("get", "/jobs/stats", None),
        ("post", "/users/conversation/maintenance", None),
    ],
)
async def test_operator_surfaces_refuse_a_project_key(client, method, path, body):
    kwargs = {"headers": BA_KEY}
    if body is not None:
        kwargs["json"] = body
    with patch("app.api.projects.db_module.project_delete", new_callable=AsyncMock) as deleted:
        r = await getattr(client, method)(path, **kwargs)
    assert r.status_code == 403
    deleted.assert_not_called()
