"""Seed of the Bike Anjo project: bot retrieval hints from the contract, approved terms kept."""
import sys
from pathlib import Path

import asyncpg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_bikeanjoall as seed  # noqa: E402


def test_bot_hints_come_from_the_contract():
    h = seed.bot_retrieval_hints()
    assert "24_instrucoes_resposta" in h["ports"]["ask"]["boost_path_substrings"]
    assert "governanca_legal" in h["intent_clusters"]
    assert set(h["intent_clusters"]["silencio"]) <= {"keywords", "boost_path_substrings", "extra_downrank"}


class _Conn:
    def __init__(self, rows=None, missing=False):
        self.rows, self.missing = rows or [], missing

    async def fetch(self, *_):
        if self.missing:
            raise asyncpg.UndefinedTableError("rating_proposals")
        return self.rows


@pytest.mark.asyncio
async def test_approved_terms_survive_the_seed():
    cfg = {"policies": {"forbidden_terms": ["De nada"]}}
    out = await seed.keep_approved_terms(_Conn([{"value": "bikeanjo.org/belem"}, {"value": "de nada"}]), "p", cfg)
    assert out["policies"]["forbidden_terms"] == ["De nada", "bikeanjo.org/belem"]
    out = await seed.keep_approved_terms(_Conn(missing=True), "p", {"policies": {"forbidden_terms": ["x"]}})
    assert out["policies"]["forbidden_terms"] == ["x"]
