-- AlterTable
ALTER TABLE "Job" ADD COLUMN "model_alias" TEXT NOT NULL DEFAULT 'smart';

-- CreateIndex
CREATE INDEX "Job_model_alias_status_idx" ON "Job"("model_alias", "status");
