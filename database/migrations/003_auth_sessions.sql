-- Apply once after migrations 001/002 to existing databases. Fresh init already includes this.
BEGIN;
CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CONSTRAINT auth_sessions_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT auth_sessions_revoked_check CHECK (revoked_at IS NULL OR revoked_at >= created_at),
    CONSTRAINT auth_sessions_id_user_uq UNIQUE (id, user_id)
);
CREATE INDEX auth_sessions_user_idx ON auth_sessions (user_id, expires_at);
CREATE INDEX auth_sessions_expires_idx ON auth_sessions (expires_at);

ALTER TABLE refresh_tokens
    ADD COLUMN session_id uuid,
    ADD COLUMN rotated_at timestamptz,
    ADD COLUMN replaced_by_id uuid REFERENCES refresh_tokens(id) ON DELETE SET NULL;
UPDATE refresh_tokens SET revoked_at=COALESCE(revoked_at, now()) WHERE session_id IS NULL;
ALTER TABLE refresh_tokens
    ADD CONSTRAINT refresh_tokens_session_fk FOREIGN KEY (session_id,user_id) REFERENCES auth_sessions(id,user_id) ON DELETE CASCADE,
    ADD CONSTRAINT refresh_tokens_session_check CHECK (session_id IS NOT NULL OR revoked_at IS NOT NULL),
    ADD CONSTRAINT refresh_tokens_rotation_check CHECK (rotated_at IS NULL OR (revoked_at IS NOT NULL AND rotated_at >= created_at));
CREATE INDEX refresh_tokens_session_idx ON refresh_tokens(session_id);
CREATE INDEX refresh_tokens_replaced_idx ON refresh_tokens(replaced_by_id) WHERE replaced_by_id IS NOT NULL;
COMMIT;
