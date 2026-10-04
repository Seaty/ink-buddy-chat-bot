-- No changes to existing accounts, IDs or chat data.
BEGIN;
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id uuid PRIMARY KEY DEFAULT public.ink_buddy_uuid_v7(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    revoked_at timestamptz,
    CONSTRAINT password_reset_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT password_reset_used_check CHECK (used_at IS NULL OR used_at >= created_at),
    CONSTRAINT password_reset_revoked_check CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);
CREATE INDEX IF NOT EXISTS password_reset_user_recent_idx ON password_reset_tokens(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS password_reset_expires_idx ON password_reset_tokens(expires_at);
COMMIT;
