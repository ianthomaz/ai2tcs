-- Second opinion queue: a bigger agent (the teacher) reviews the local LLM's answer to a
-- case sent by a project (docs/26-second-opinion.md). Read only: nothing here sends or acts.
CREATE TABLE "second_opinions" (
    "id" BIGSERIAL NOT NULL,
    "project_id" TEXT NOT NULL,
    "source_ref" TEXT NOT NULL,
    "channel" TEXT NOT NULL,
    "case_kind" TEXT,
    "status" TEXT NOT NULL DEFAULT 'queued',
    "request" JSONB NOT NULL,
    "response" JSONB,
    "agent" TEXT,
    "error" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "claimed_at" TIMESTAMP(3),
    "finished_at" TIMESTAMP(3),

    CONSTRAINT "second_opinions_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "second_opinions_status_check" CHECK ("status" IN ('queued', 'working', 'done', 'failed')),
    CONSTRAINT "second_opinions_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE
);

CREATE UNIQUE INDEX "second_opinions_project_id_source_ref_key" ON "second_opinions"("project_id", "source_ref");
CREATE INDEX "second_opinions_status_created_at_idx" ON "second_opinions"("status", "created_at");
