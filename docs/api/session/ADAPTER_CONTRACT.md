# Chat Answer Adapter contract

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

Implementation lives behind `MessageService(..., adapter=...)`. Route uses message_service dependency. Current CHAT_ADAPTER allows catalog_template only; when teammate implementation is ready add explicit configuration choice/factory and contract tests. Never accept adapter/model name from a client. No automatic fallback that disguises an AI failure as a successful model answer.

Deadline CHAT_TIMEOUT_SECONDS=60 (positive, max300). Bounded executor has4 slots per process, saturated503. Timeout504 does not commit history; Python cannot kill an already-running adapter thread, so future network adapters MUST have their own bounded timeout. Slots return only when calls finish; no unbounded task queue. DB statement timeout uses same configured bound. Durations/status codes only in logs; no question/answer/credentials.

## Contract test checklist

Known products and no matches; clarification; empty/oversized output; unexpected Product IDs; malformed output; timeout/error; mutated input cannot change DB reference data. See backend/tests/test_chat_search.py and PostgreSQL message tests. Search now uses DB keyword/category/brand/budget, not embeddings or semantic RAG. No streaming/images/summary in v1.
