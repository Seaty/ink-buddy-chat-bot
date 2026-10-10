BEGIN;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS client_request_id uuid;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chat_messages_request_user_check') THEN
 ALTER TABLE chat_messages ADD CONSTRAINT chat_messages_request_user_check CHECK (client_request_id IS NULL OR role='user');
 END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS chat_messages_request_uq ON chat_messages(session_id,client_request_id) WHERE client_request_id IS NOT NULL;
COMMIT;
