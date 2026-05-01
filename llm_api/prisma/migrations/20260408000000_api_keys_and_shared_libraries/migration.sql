-- CreateTable
CREATE TABLE "project_api_keys" (
    "id" TEXT NOT NULL,
    "project_id" TEXT NOT NULL,
    "key_hash" TEXT NOT NULL,
    "label" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "revoked_at" TIMESTAMP(3),
    "last_used_at" TIMESTAMP(3),

    CONSTRAINT "project_api_keys_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "shared_libraries" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "sources" TEXT[],
    "config_json" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "shared_libraries_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "project_api_keys_key_hash_key" ON "project_api_keys"("key_hash");

-- CreateIndex
CREATE UNIQUE INDEX "shared_libraries_slug_key" ON "shared_libraries"("slug");

-- AddForeignKey
ALTER TABLE "project_api_keys" ADD CONSTRAINT "project_api_keys_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "Project"("project_id") ON DELETE CASCADE ON UPDATE CASCADE;
