-- Fallback Project for Job rows from sync LLM endpoints (NF extract, extract, router) when no project_id is supplied.
-- Satisfies FK Job.project_id → Project.project_id.

INSERT INTO "Project" (id, project_id, name, sources, config_json, created_at, updated_at)
VALUES (
    'cm_sync_audit_itcs_tools',
    'itcs_sync_tools',
    'ITCS sync tools (job audit fallback: nfExtract, extract, router)',
    ARRAY[]::TEXT[],
    '{}'::jsonb,
    NOW(),
    NOW()
)
ON CONFLICT (project_id) DO NOTHING;
