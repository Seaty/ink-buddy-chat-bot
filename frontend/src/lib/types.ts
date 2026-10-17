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
export type ProductReference = {
  id: string;
  sku: string | null;
  name: string;
  price: string | null;
  currency: string | null;
  availability: string | null;
  source_ref: string | null;
  price_source_ref?: string | null;
  price_basis?: string | null;
  price_verification?: string | null;
  selling_unit?: string | null;
  pack_quantity?: number | null;
  ink_color?: string | null;
  body_color?: string | null;
  variants?: ProductReference[];
  match_type?: "exact" | "similar" | "suggestion" | null;
  match_score?: number | null;
  match_method?: "image_embedding" | "vision_text_catalog" | null;
};
export type SendMessageResult = {
  user_message: Message;
  assistant_message: Message;
};
export type Message = {
  model_name?: string | null;
  id: string;
  session_id: string;
  sequence_number: number;
  role: "user" | "assistant" | "system";
  content: string;
  image_id: string | null;
  product_refs?: ProductReference[] | null;
};
export type Page<T> = { items: T[]; next_cursor: string | null };
