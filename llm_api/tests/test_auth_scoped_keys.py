"""Per-project keys (app/auth.py): a key never reaches another project; the global token is
refused by the projects that already migrated (SCOPED_KEY_REQUIRED_PROJECTS)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import hash_key, require_token

GLOBAL = {"Authorization": "Bearer test-token"}
BA_KEY = {"Authorization": "Bearer itcs_bikeanjoall_2026_x"}

app = FastAPI()


@app.post("/body")
async def _body(_: None = Depends(require_token)) -> dict:
    return {"ok": True}


@app.get("/path/{project_id}")
async def _path(project_id: str, _: None = Depends(require_token)) -> dict:
    return {"ok": True}


@pytest.fixture
async def c():
    async def key_project(key_hash: str):
        return {hash_key("itcs_bikeanjoall_2026_x"): "bikeanjoall_2026"}.get(key_hash)

    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.auth.db_module.api_key_get_project_id", side_effect=key_project
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            yield ac


@pytest.mark.asyncio
async def test_project_key_on_its_own_project(c):
    assert (await c.post("/body", json={"project_id": "bikeanjoall_2026"}, headers=BA_KEY)).status_code == 200
    assert (await c.get("/path/bikeanjoall_2026", headers=BA_KEY)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.post("/body", json={"project_id": "webplacecc"}, headers=BA_KEY),
        lambda c: c.post("/body", json={}, headers={**BA_KEY, "X-Project-Id": "webplacecc"}),
        lambda c: c.post("/body?project_id=webplacecc", json={}, headers=BA_KEY),
        lambda c: c.get("/path/webplacecc", headers=BA_KEY),
    ],
)
async def test_project_key_never_reaches_another_project(c, call):
    assert (await call(c)).status_code == 403


@pytest.mark.asyncio
async def test_global_token_stays_hybrid_by_default(c):
    """No project listed: every project still accepts the global token (clients not migrated)."""
    assert (await c.post("/body", json={"project_id": "bikeanjoall_2026"}, headers=GLOBAL)).status_code == 200
    assert (await c.get("/path/webplacecc", headers=GLOBAL)).status_code == 200


@pytest.mark.asyncio
async def test_listed_project_refuses_the_global_token(c):
    with patch("app.config.settings.scoped_key_required_projects", "bikeanjoall_2026"):
        assert (await c.post("/body", json={"project_id": "bikeanjoall_2026"}, headers=GLOBAL)).status_code == 403
        assert (await c.get("/path/bikeanjoall_2026", headers=GLOBAL)).status_code == 403
        assert (
            await c.post("/body", json={}, headers={**GLOBAL, "X-Project-Id": "bikeanjoall_2026"})
        ).status_code == 403
        # Other projects keep the hybrid mode.
        assert (await c.post("/body", json={"project_id": "webplacecc"}, headers=GLOBAL)).status_code == 200
        # The project's own key is untouched.
        assert (await c.post("/body", json={"project_id": "bikeanjoall_2026"}, headers=BA_KEY)).status_code == 200


@pytest.mark.asyncio
async def test_global_token_use_is_logged(c, caplog):
    with caplog.at_level("INFO", logger="app.auth"):
        await c.post("/body", json={"project_id": "webplacecc"}, headers=GLOBAL)
    assert any("auth=global" in r.message and "webplacecc" in r.message for r in caplog.records)
