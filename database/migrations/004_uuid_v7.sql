-- Preserve existing IDs and foreign keys. Only future default-generated IDs change.
BEGIN;

-- RFC 9562 section 5.7: 48-bit Unix milliseconds + 74 random bits.
-- PostgreSQL 16 compatibility; gen_random_uuid supplies cryptographic randomness.
CREATE OR REPLACE FUNCTION public.ink_buddy_uuid_v7() RETURNS uuid
LANGUAGE plpgsql VOLATILE PARALLEL SAFE SET search_path = pg_catalog AS $$
DECLARE
    value bytea := uuid_send(gen_random_uuid());
    milliseconds bigint := floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint;
BEGIN
    value := overlay(value placing substring(int8send(milliseconds) from 3 for 6) from 1 for 6);
    value := set_byte(value, 6, (get_byte(value, 6) & 15) | 112);
    value := set_byte(value, 8, (get_byte(value, 8) & 63) | 128);
    RETURN encode(value, 'hex')::uuid;
END;
$$;

ALTER TABLE public.roles ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.users ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.auth_sessions ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.refresh_tokens ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.guest_sessions ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.chat_sessions ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.image_uploads ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.chat_messages ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.products ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.product_images ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.product_embeddings ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();
ALTER TABLE public.audit_logs ALTER COLUMN id SET DEFAULT public.ink_buddy_uuid_v7();

COMMIT;
