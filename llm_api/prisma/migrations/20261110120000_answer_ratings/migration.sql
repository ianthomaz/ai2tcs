-- Human judgments of answers, sent by each project (docs/22-answer-ratings.md).
CREATE TABLE "answer_ratings" (
    "id" BIGSERIAL NOT NULL,
    "project_id" TEXT NOT NULL,
    "source_ref" TEXT NOT NULL,
    "question" TEXT NOT NULL,
    "answer" TEXT NOT NULL,
    "rating" TEXT NOT NULL,
    "reason" TEXT,
    "signals" JSONB,
    "rated_at" TIMESTAMP(3),
    "received_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "answer_ratings_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "answer_ratings_rating_check" CHECK ("rating" IN ('stop', 'bad', 'good', 'great')),
    CONSTRAINT "answer_ratings_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE
);

CREATE UNIQUE INDEX "answer_ratings_project_id_source_ref_key" ON "answer_ratings"("project_id", "source_ref");
CREATE INDEX "answer_ratings_project_id_rating_idx" ON "answer_ratings"("project_id", "rating");

-- What the ratings suggest changing in the project; applied only after a person approves.
CREATE TABLE "rating_proposals" (
    "id" BIGSERIAL NOT NULL,
    "project_id" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "value" TEXT NOT NULL,
    "source_refs" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "status" TEXT NOT NULL DEFAULT 'pending',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "decided_at" TIMESTAMP(3),
    "decided_by" TEXT,

    CONSTRAINT "rating_proposals_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "rating_proposals_kind_check" CHECK ("kind" IN ('forbidden_term')),
    CONSTRAINT "rating_proposals_status_check" CHECK ("status" IN ('pending', 'approved', 'rejected')),
    CONSTRAINT "rating_proposals_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE
);

CREATE UNIQUE INDEX "rating_proposals_project_id_kind_value_key" ON "rating_proposals"("project_id", "kind", "value");
