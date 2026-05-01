-- Consolidated migration: init + conversation_history + user_profile + conv_summary + job user_context
-- For existing DBs that already have these tables: prisma migrate resolve --applied 20250307000000_consolidated

-- CreateTable
CREATE TABLE "Project" (
    "id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "name" TEXT,
    "sources" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "config_json" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Project_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "project_themes" (
    "id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "theme" TEXT NOT NULL,

    CONSTRAINT "project_themes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Job" (
    "id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "user_id" TEXT,
    "question" TEXT NOT NULL,
    "question_hash" TEXT,
    "user_context_json" JSONB,
    "status" TEXT NOT NULL,
    "progress" TEXT,
    "answer" TEXT,
    "sources_json" JSONB,
    "confidence" TEXT,
    "error_message" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Job_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "conversation_history" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "job_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "conversation_history_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_profile" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "display_name" TEXT,
    "birth_date" DATE,
    "notes" TEXT,
    "metadata" JSONB DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "user_profile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "conversation_summary" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "period" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "message_count" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "conversation_summary_pkey" PRIMARY KEY ("id")
);

-- Indexes
CREATE UNIQUE INDEX "Project_project_id_key" ON "Project"("project_id");
CREATE UNIQUE INDEX "project_themes_project_id_theme_key" ON "project_themes"("project_id", "theme");
CREATE INDEX "Job_project_id_status_idx" ON "Job"("project_id", "status");
CREATE INDEX "Job_question_hash_created_at_idx" ON "Job"("question_hash", "created_at");
CREATE INDEX "Job_user_id_idx" ON "Job"("user_id");
CREATE INDEX "Job_user_id_project_id_created_at_idx" ON "Job"("user_id", "project_id", "created_at" DESC);
CREATE INDEX "conv_hist_user_project_idx" ON "conversation_history"("user_id", "project_id", "created_at" DESC);
CREATE UNIQUE INDEX "user_profile_user_project_idx" ON "user_profile"("user_id", "project_id");
CREATE UNIQUE INDEX "conv_summary_user_project_period_idx" ON "conversation_summary"("user_id", "project_id", "period");

-- Foreign keys
ALTER TABLE "project_themes" ADD CONSTRAINT "project_themes_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Job" ADD CONSTRAINT "Job_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "conversation_history" ADD CONSTRAINT "conv_hist_project_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "user_profile" ADD CONSTRAINT "user_profile_project_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "conversation_summary" ADD CONSTRAINT "conv_summary_project_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE ON UPDATE CASCADE;
