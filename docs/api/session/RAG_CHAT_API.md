# RAG Chat — Postman

## Conversational RAG — 2026-10-14

คำถามต่อที่มีบริบทในแชตเดิมทำงานแล้ว: ขอสามรุ่นถูกที่สุด, ตัวที่สองราคาเท่าไร, รุ่นนี้มีสีแดงไหม. ชื่อใหม่หรือประเภทใหม่เปลี่ยน scope; กำกวมขอข้อมูลเพิ่มโดย catalog_policy. รูปแบบ request เดิมไม่รับ model/SQL/price จาก client

product_refs optional fields: price_source_ref, price_basis, price_verification, selling_unit, pack_quantity, ink_color, body_color, variants (สูงสุด 5 ProductFactReference ไม่มี nested variants ต่อ). ราคาเป็น snapshot; แหล่งสินค้าและแหล่งราคาต่างกันได้. NULL ไม่ถูกใช้เป็นศูนย์ สีอื่นไม่ปะปน ranking หลัก

Postman เพิ่ม folder Conversational price UAT: เริ่ม Guest/create chat ก่อน แล้วส่ง ranked query → ordinal → same-family color → new topic → history. ไม่ใช้แชตที่ไม่มีบริบทเพื่อคาดหวัง ordinal answer

ดู [Process / เคส manual และข้อจำกัด](../../architecture/RAG_CONVERSATION_PROCESS.md). ส่วน rendering update 2026-10-13 ด้านล่างเป็นประวัติ ก่อนเพิ่ม bounded context resolution

Use existing `POST /api/v1/chat-sessions/{id}/messages` with content and UUIDv7 client_request_id.
No new endpoint. Response adds optional `model_name` to messages; histories return it too.

## Setup

Set CHAT_ADAPTER=openrouter_catalog in backend/.env, keep configured OpenRouter key/model and restart.
Use an indexed catalog. Default code/example stays catalog_template.
Import rag-chat.postman_collection.json + rag-chat.postman_environment.json.
Choose Guest flow or User flow (enter your email/password privately); don't export populated credentials.
base_url defaults http://localhost:8000/api/v1 and Origin is http://localhost:3000.

Collection steps: credentials → create session → RAG send → replay same ID/content
→ scope refusal → no-match → read persisted history. Scripts generate UUIDv7 IDs using
Postman's random UUID plus current millisecond timestamp, and preserve the original ID for replay.

## Cases

Rendering update 2026-10-13: concise catalog quotes plus verified query-condition
reasons, up to 3 fact bullets per product. No-match with an explicit budget asks
to adjust the budget; other no-match asks to check model/brand/details. Ambiguous follow-up without resolvable session context still asks for its name. Request/response shape,
201 replay, rollback and no automatic retry/fallback are unchanged.

| Case | HTTP / behavior |
|---|---|
| Valid RAG selection | 201, pair of messages, actual model_name, catalog product_refs |
| Scope/clarification/no-match | 201, fixed response, catalog_policy, no Text LLM call |
| Same request/content | 201, existing pair, no AI/retrieval rerun |
| Same ID/different content or concurrent history | 409 |
| Other owner's/deleted chat | 404 |
| Credential expired/revoked | 401 |
| OpenRouter policy blocked | 403 OPENROUTER_POLICY_REJECTED |
| Malformed/truncated/ungrounded selection | 502 INVALID_ANSWER |
| Provider failure | 502 ANSWER_FAILED |
| Full deadline exceeded | 504 ANSWER_TIMEOUT |
| Executor saturated | 503 ANSWER_BUSY |

Errors do not commit either message. Retry is explicit; frontend preserves draft and request ID.
Price/source/availability come from DB snapshots. Score isn't confidence and output guardrails
check evidence consistency, not recommendation quality. See ../../architecture/RAG_CHAT_ANSWER_PROCESS.md.
