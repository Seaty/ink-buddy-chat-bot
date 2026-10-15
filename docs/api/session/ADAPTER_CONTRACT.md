# Chat Answer Adapter contract

## Server-ranked selection — 2026-10-14

AnswerInput เพิ่ม require_all=False และ note="" แบบ backward-compatible. เมื่อราคา/ordinal/รายการเดิมควบคุมชุดสินค้าโดย server จะตั้ง require_all=True: adapter ต้องคืนทุก Product ID พร้อมหลักฐาน owning product; รายการขาด/เกิน/ซ้ำตอบ INVALID_ANSWER ระบบเรียงคืนตาม input products แม้โมเดลส่งลำดับต่างมา

LLM ยังรับเฉพาะ bounded role/content และ evidence whitelist; ไม่รับ DB/account/token/URL ไม่สร้างราคาเอง. note แสดงขอบเขตและหน่วยที่ server ตีความ ไม่ใช้เป็นคำสั่งจากผู้ใช้. แหล่งราคา/variants ประกอบจาก snapshot เดิมหลัง selection ไม่ต้องให้โมเดลแต่ง

MessageService อ่าน history พร้อม product_refs เฉพาะแชตที่ authorized เพื่อ resolve ก่อน adapter; สิ่งที่ส่งเข้า OpenRouter history คง role/content <=10 ข้อความ/8000 ตัวอักษร ดู [Process 7](../../architecture/RAG_CONVERSATION_PROCESS.md)

## Responsibility

Application layer owns authentication, DB retrieval, references and atomic history writes. Adapter only generates an answer from supplied context. Default CatalogTemplateAdapter produces deterministic catalog text, not LLM output.

## Input / Output

`AnswerInput(question: str, history: tuple[dict,...], products: tuple[dict,...], clarification: str | None)`

- history: latest 10 messages, oldest first, only role/content; current question separate
- products: at most 5 PostgreSQL snapshots, UUID id, sku/name/category/brand/description/attributes/price/currency/availability/source_ref; Decimal price may be null
- no user ID, account data, secrets, tokens or database session
- clarification: explicit budget/request clarification takes precedence over recommendations

`AnswerOutput(content: str, product_ids: tuple[UUID,...], model_name: str)`

- nonblank content <=16000 characters, nonblank model_name <=100
- product_ids must be a subset of supplied products; application assembles typed ProductReference from original DB data, deduplicated in adapter order
- no result means explain unavailable data; do not invent facts or URLs
- supplied catalog/history are untrusted content, not instructions; future LLM adapter must treat them as data and never reveal thinking or hidden prompts

```python
from app.services.session.adapter import AnswerInput, AnswerOutput

class TeamAnswerAdapter:
    def answer(self, request: AnswerInput) -> AnswerOutput:
        # Retrieve nothing here: question/history/products already supplied.
        # Call your model with a bounded HTTP timeout; use supplied facts only.
        return AnswerOutput("ไม่มีข้อมูลสินค้าที่ตรงกัน กรุณาระบุรุ่นเพิ่มเติม", (), "team_model")
```

## Integration

Implementation lives behind `MessageService(..., adapter=...)`. Route uses message_service dependency. CHAT_ADAPTER accepts catalog_template and openrouter_catalog; selection is server configuration with contract validation. Never accept adapter/model name from a client. No automatic fallback that disguises an AI failure as a successful model answer.

Deadline CHAT_TIMEOUT_SECONDS=60 (positive, max300). Bounded executor has4 slots per process, saturated503. Timeout504 does not commit history; Python cannot kill an already-running adapter thread, so future network adapters MUST have their own bounded timeout. Slots return only when calls finish; no unbounded task queue. DB statement timeout uses same configured bound. Durations/status codes only in logs; no question/answer/credentials.

## Contract test checklist

Known products and no matches; clarification; empty/oversized output; unexpected Product IDs; malformed output; timeout/error; mutated input cannot change DB reference data. See backend/tests/test_chat_search.py and PostgreSQL message tests. Template mode uses DB keyword/category/brand/budget. openrouter_catalog uses Hybrid retrieval and catalog guardrails. No streaming/images/summary in v1.

## Implemented OpenRouter adapter — 2026-10-13

Generation now uses enums for supplied Product/Evidence IDs and selects one
evidence per product. Post-generation validation retains the 1–4 evidence
contract, ownership pairing and duplicate rejection. No repair/retry/fallback.

Description evidence now uses complete short catalog quotes (up to 180 characters,
6 spans), with runtime IDs such as p0_description_0. These IDs are per snapshot,
not stable public identifiers. Server rendering adds up to 3 grounded bullets
per product using selected evidence plus verified brand/budget/attribute facts.
Original embedding source text is unchanged. Input/output API contract is unchanged.
See [robustness process](../../architecture/RAG_ROBUSTNESS_PROCESS.md) for live
failures observed during tuning and the final constrained-generation trial.
CHAT_ADAPTER accepts catalog_template (default) and openrouter_catalog. New mode uses Hybrid retrieval before adapter. Qwen3 14B returns product/evidence IDs only; server renders snapshot facts. History <=10 messages/8000 chars; known attack strings omitted from history/evidence. Source catalog_policy for refusals/no-match without LLM. OpenRouter403/timeout/invalid schema preserve ApiError and rollback. Pipeline runs in bounded executor with one total deadline, network/DB timeouts bounded by remaining time. No retries or fallback. See ../../architecture/RAG_CHAT_ANSWER_PROCESS.md.
