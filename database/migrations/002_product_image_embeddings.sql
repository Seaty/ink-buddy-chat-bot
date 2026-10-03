-- Apply ONCE after 001 to the previous schema.
-- IF NOT EXISTS preserves the table if previously created by SQLAlchemy.
-- Verify an existing table matches backend/app/models/product.py before use.
BEGIN;

-- Matches backend/app/models/product.py; a separate vector space from BGE-M3.
CREATE TABLE IF NOT EXISTS product_image_embeddings (
    id serial PRIMARY KEY,
    sku varchar(64) NOT NULL,
    chunk_type varchar(16) NOT NULL,
    variant smallint NOT NULL DEFAULT 0,
    content text NOT NULL,
    content_hash varchar(64) NOT NULL,
    embedding vector(2048) NOT NULL,
    embed_model varchar(128) NOT NULL,
    metadata jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_chunk UNIQUE (sku, chunk_type, variant),
    CONSTRAINT ck_chunk_type CHECK (chunk_type IN ('image', 'image_aug', 'caption'))
);
CREATE INDEX IF NOT EXISTS ix_product_image_embeddings_sku ON product_image_embeddings (sku);
CREATE INDEX IF NOT EXISTS ix_product_image_embeddings_meta ON product_image_embeddings USING gin (metadata);
-- No HNSW on vector(2048): current index supports at most 2000 vector dimensions.
-- Use exact scan for the small catalog; evaluate halfvec expression indexing at scale.

COMMIT;
