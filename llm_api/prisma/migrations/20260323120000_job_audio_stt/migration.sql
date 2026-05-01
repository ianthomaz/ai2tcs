-- Audio jobs: local STT (Whisper) fields on Job
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "job_kind" TEXT NOT NULL DEFAULT 'ask';
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "audio_path" TEXT;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "transcript" TEXT;
ALTER TABLE "Job" ADD COLUMN IF NOT EXISTS "stt_metadata_json" JSONB;

CREATE INDEX IF NOT EXISTS "Job_job_kind_status_idx" ON "Job"("job_kind", "status");
