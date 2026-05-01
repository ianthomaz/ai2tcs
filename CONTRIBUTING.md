# Contributing

## Scope

- **Canonical API code:** `llm_api/`.
- **HTTP contracts and integration:** `docs/` (start at [`docs/01-overview.md`](docs/01-overview.md)).

## Conventions

- **Code, comments, and technical docs:** English.
- **User-facing UI copy:** Portuguese (Brazil), where applicable.
- **Checklists in Markdown:** `[ x ]` done, `[ ]` todo (no emoji markers in `.md` per project style).

## Before you open a PR

1. Run tests from `llm_api/`: `pytest` (with a valid `DATABASE_URL` / Postgres if tests need it — see [`llm_api/README.md`](llm_api/README.md) and [`docs/04-developer-guide.md`](docs/04-developer-guide.md)).
2. Do **not** commit secrets: use `.env` (gitignored) and `llm_api/.env.example` for documented variables only.
3. Keep changes focused on one concern per PR when possible.

## What we will not merge via public PR

- Organization-specific credentials, hostnames, or copies of `local-only/` content (those belong in private clones or internal repos).

---

**Maintained by:** ITCS-Webplace — CNPJ 65.998.990/0001-44 — [email@webplace.cc](mailto:email@webplace.cc).
