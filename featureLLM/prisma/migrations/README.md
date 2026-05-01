# Migrations

Única migration: `20250307000000_consolidated` — schema completo (Project, themes, Job, conversation_history, user_profile, conversation_summary).

## Novo setup

- **setup.sh**: aplica o SQL diretamente via Python/asyncpg.
- **Docker**: `prisma migrate deploy` aplica o consolidado.

## Banco existente (já rodou migrations antigas)

Se o banco teve migrations `20250306000000_init`, `20250306100000_*`, etc., faça uma vez:

1. Remover entradas antigas e marcar consolidado como aplicado:

```bash
# Conecte no banco e execute:
psql "$DATABASE_URL" -c "
DELETE FROM _prisma_migrations WHERE migration_name IN (
  '20250306000000_init',
  '20250306100000_add_conversation_history',
  '20250306200000_add_user_profile_and_conv_summary',
  '20250306300000_add_job_user_context'
);
"
npx prisma migrate resolve --applied 20250307000000_consolidated
```

2. Depois disso, o deploy via Docker (`prisma migrate deploy`) funciona normalmente.
