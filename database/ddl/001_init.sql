-- Ink Buddy initial schema. Run once against an empty PostgreSQL database.
-- Requires PostgreSQL 13+ (gen_random_uuid), pgvector, and pg_trgm.
-- Apply subsequent schema changes through migrations rather than editing a used init script.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(50) NOT NULL UNIQUE,
    description text,
    CONSTRAINT roles_name_not_blank CHECK (length(btrim(name)) > 0)
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    email varchar(320) NOT NULL,
    password_hash text NOT NULL,
    display_name varchar(120),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_not_blank CHECK (length(btrim(email)) > 0),
    CONSTRAINT users_password_hash_not_blank CHECK (length(btrim(password_hash)) > 0)
);

CREATE UNIQUE INDEX users_email_lower_uq ON users (lower(email));
CREATE INDEX users_role_id_idx ON users (role_id);

CREATE TABLE refresh_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT refresh_tokens_hash_not_blank CHECK (length(btrim(token_hash)) > 0),
    CONSTRAINT refresh_tokens_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT refresh_tokens_revoked_check CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE INDEX refresh_tokens_user_expires_idx ON refresh_tokens (user_id, expires_at);
CREATE INDEX refresh_tokens_expires_idx ON refresh_tokens (expires_at);

CREATE TABLE chat_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title varchar(200),
    summary text,
    summary_checkpoint integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CONSTRAINT chat_sessions_summary_checkpoint_check CHECK (summary_checkpoint >= 0),
    CONSTRAINT chat_sessions_updated_check CHECK (updated_at >= created_at),
    CONSTRAINT chat_sessions_deleted_check CHECK (deleted_at IS NULL OR deleted_at >= created_at)
);

CREATE INDEX chat_sessions_owner_recent_idx
    ON chat_sessions (user_id, updated_at DESC, id DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE image_uploads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    storage_key text NOT NULL UNIQUE,
    mime_type varchar(100) NOT NULL,
    size_bytes bigint NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'ready',
    ocr_text text,
    analysis jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CONSTRAINT image_uploads_storage_key_not_blank CHECK (length(btrim(storage_key)) > 0),
    CONSTRAINT image_uploads_size_check CHECK (size_bytes > 0),
    CONSTRAINT image_uploads_mime_check CHECK (mime_type IN ('image/jpeg', 'image/png', 'image/webp')),
    CONSTRAINT image_uploads_status_check CHECK (status IN ('ready', 'processing', 'failed')),
    CONSTRAINT image_uploads_analysis_object_check CHECK (analysis IS NULL OR jsonb_typeof(analysis) = 'object'),
    CONSTRAINT image_uploads_deleted_check CHECK (deleted_at IS NULL OR deleted_at >= created_at)
);

CREATE INDEX image_uploads_owner_recent_idx
    ON image_uploads (user_id, created_at DESC, id DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE chat_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sequence_number integer NOT NULL,
    role varchar(20) NOT NULL,
    content text NOT NULL DEFAULT '',
    product_refs jsonb,
    image_id uuid REFERENCES image_uploads(id) ON DELETE RESTRICT,
    model_name varchar(100),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chat_messages_sequence_check CHECK (sequence_number > 0),
    CONSTRAINT chat_messages_role_check CHECK (role IN ('user', 'assistant', 'system')),
    CONSTRAINT chat_messages_content_check CHECK (length(btrim(content)) > 0 OR image_id IS NOT NULL),
    CONSTRAINT chat_messages_product_refs_array_check CHECK (product_refs IS NULL OR jsonb_typeof(product_refs) = 'array'),
    CONSTRAINT chat_messages_session_sequence_uq UNIQUE (session_id, sequence_number)
);

CREATE INDEX chat_messages_image_id_idx ON chat_messages (image_id) WHERE image_id IS NOT NULL;

CREATE TABLE products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sku varchar(100),
    name text NOT NULL,
    category varchar(100),
    brand varchar(100),
    description text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    price numeric(12, 2),
    currency char(3),
    availability varchar(30),
    source_ref text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT products_name_not_blank CHECK (length(btrim(name)) > 0),
    CONSTRAINT products_sku_not_blank CHECK (sku IS NULL OR length(btrim(sku)) > 0),
    CONSTRAINT products_attributes_object_check CHECK (jsonb_typeof(attributes) = 'object'),
    CONSTRAINT products_price_check CHECK (price IS NULL OR price >= 0),
    CONSTRAINT products_price_currency_check CHECK (price IS NULL OR currency IS NOT NULL),
    CONSTRAINT products_currency_check CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
    CONSTRAINT products_updated_check CHECK (updated_at >= created_at)
);

CREATE UNIQUE INDEX products_sku_uq ON products (sku) WHERE sku IS NOT NULL;
CREATE INDEX products_name_trgm_idx ON products USING gin (name gin_trgm_ops);
CREATE INDEX products_category_brand_idx ON products (category, brand, id);
CREATE INDEX products_brand_idx ON products (brand, id);

CREATE TABLE product_images (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    storage_key text NOT NULL UNIQUE,
    is_primary boolean NOT NULL DEFAULT false,
    alt_text text,
    CONSTRAINT product_images_storage_key_not_blank CHECK (length(btrim(storage_key)) > 0)
);

CREATE INDEX product_images_product_id_idx ON product_images (product_id);
CREATE UNIQUE INDEX product_images_one_primary_uq
    ON product_images (product_id) WHERE is_primary = true;

CREATE TABLE product_embeddings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    model_name varchar(100) NOT NULL,
    source_text text NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT product_embeddings_model_not_blank CHECK (length(btrim(model_name)) > 0),
    CONSTRAINT product_embeddings_source_not_blank CHECK (length(btrim(source_text)) > 0),
    CONSTRAINT product_embeddings_product_model_uq UNIQUE (product_id, model_name)
);

CREATE INDEX product_embeddings_cosine_hnsw_idx
    ON product_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    action varchar(100) NOT NULL,
    resource_type varchar(50),
    resource_id uuid,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT audit_logs_action_not_blank CHECK (length(btrim(action)) > 0),
    CONSTRAINT audit_logs_metadata_object_check CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX audit_logs_actor_recent_idx ON audit_logs (actor_user_id, created_at DESC, id DESC)
    WHERE actor_user_id IS NOT NULL;
CREATE INDEX audit_logs_action_recent_idx ON audit_logs (action, created_at DESC, id DESC);

INSERT INTO roles (name, description) VALUES
    ('user', 'Regular Ink Buddy user'),
    ('admin', 'Ink Buddy administrator');

COMMIT;
