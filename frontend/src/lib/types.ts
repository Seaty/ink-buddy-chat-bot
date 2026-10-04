export type Guest = {
  id: string;
  expires_at: string;
  image_uploads_remaining: number;
};
export type Profile = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
};
export type Identity =
  { kind: "user"; profile: Profile } | { kind: "guest"; guest: Guest };
export type ChatSession = {
  id: string;
  title: string | null;
  summary: string | null;
  created_at: string;
  updated_at: string;
};
export type Message = {
  id: string;
  session_id: string;
  sequence_number: number;
  role: "user" | "assistant" | "system";
  content: string;
  image_id: string | null;
};
export type Page<T> = { items: T[]; next_cursor: string | null };
