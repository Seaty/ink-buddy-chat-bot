-- Apply ONCE to the previous schema, not to the updated fresh init.
-- Existing user-owned rows remain valid. No data deletion.
BEGIN;

CREATE TABLE guest_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL UNIQUE,
    image_upload_limit smallint NOT NULL DEFAULT 3,
    image_uploads_used smallint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    claimed_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
    claimed_at timestamptz,
    CONSTRAINT guest_sessions_hash_not_blank CHECK (length(btrim(token_hash)) > 0),
    CONSTRAINT guest_sessions_limit_check CHECK (image_upload_limit = 3),
    CONSTRAINT guest_sessions_usage_check CHECK (image_uploads_used BETWEEN 0 AND image_upload_limit),
    CONSTRAINT guest_sessions_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT guest_sessions_revoked_check CHECK (revoked_at IS NULL OR revoked_at >= created_at),
    CONSTRAINT guest_sessions_claim_check CHECK (
        (claimed_by_user_id IS NULL AND claimed_at IS NULL) OR
        (claimed_by_user_id IS NOT NULL AND claimed_at IS NOT NULL
         AND claimed_at >= created_at AND revoked_at IS NOT NULL)
    )
);

CREATE INDEX guest_sessions_expires_idx ON guest_sessions (expires_at);
CREATE INDEX guest_sessions_claimed_user_idx ON guest_sessions (claimed_by_user_id)
    WHERE claimed_by_user_id IS NOT NULL;

ALTER TABLE chat_sessions
    ALTER COLUMN user_id DROP NOT NULL,
    ADD COLUMN guest_session_id uuid REFERENCES guest_sessions(id) ON DELETE RESTRICT,
    ADD CONSTRAINT chat_sessions_owner_check CHECK ((user_id IS NOT NULL) <> (guest_session_id IS NOT NULL));
CREATE INDEX chat_sessions_guest_recent_idx ON chat_sessions (guest_session_id, updated_at DESC, id DESC)
    WHERE deleted_at IS NULL AND guest_session_id IS NOT NULL;
CREATE INDEX chat_sessions_guest_fk_idx ON chat_sessions (guest_session_id) WHERE guest_session_id IS NOT NULL;

ALTER TABLE image_uploads
    ALTER COLUMN user_id DROP NOT NULL,
    ADD COLUMN guest_session_id uuid REFERENCES guest_sessions(id) ON DELETE RESTRICT,
    ADD CONSTRAINT image_uploads_owner_check CHECK ((user_id IS NOT NULL) <> (guest_session_id IS NOT NULL));
CREATE INDEX image_uploads_guest_recent_idx ON image_uploads (guest_session_id, created_at DESC, id DESC)
    WHERE deleted_at IS NULL AND guest_session_id IS NOT NULL;
CREATE INDEX image_uploads_guest_fk_idx ON image_uploads (guest_session_id) WHERE guest_session_id IS NOT NULL;

COMMIT;
