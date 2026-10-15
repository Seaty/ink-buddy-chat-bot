# Text RAG setup — 2026-10-13

For the reviewed local catalog and presentation process, see [Catalog RAG process](CATALOG_RAG_PROCESS.md) and [verified result](../report/CATALOG_INDEX_SUMMARY.md). Local DB now has 67 indexed products; price review and Vision synchronization limitations are documented there.

## Configuration

Secrets belong in `backend/.env`, never `.env.example` or frontend variables.
Restart the backend after changing configuration.

```dotenv
OPENROUTER_API_KEY=
TEXT_EMBED_MODEL=qwen/qwen3-embedding-4b
TEXT_EMBED_DIM=1024
TEXT_EMBED_BATCH_SIZE=16
TEXT_CHAT_MODEL=qwen/qwen3-14b
TEXT_CHAT_MAX_TOKENS=512
CHAT_ADAPTER=openrouter_catalog
```

Text indexing, hybrid retrieval, controlled answer adapter and catalog guardrails
are implemented. Code defaults remain `catalog_template`; set CHAT_ADAPTER above
and restart to enable RAG. Local development has this enabled already.
Image embeddings remain local and unchanged.

See [technical completion process](RAG_TECHNICAL_COMPLETION_PROCESS.md) for current
verification. Human evaluation and missing catalog facts still require team input.

## Evidence — 2026-10-11

- Mock client tests and existing OpenRouter regression: 23 passed.
- Paid live embedding request: Qwen3 Embedding 4B returned 1024 dimensions.
- Paid live chat request: Qwen3 14B returned nonempty text, 17 input / 6 output tokens.
- An earlier 16-output-token request returned no visible answer. Do not assume
  HTTP success means a valid answer; integration must check empty/truncated output.
- No database indexing or migrations performed. No catalog data sent in the smoke check.

## Smoke check

From `backend`, run `.venv/Scripts/python.exe scripts/check_text_openrouter.py`.
This uses paid API calls. It prints only model, dimensions and usage metadata.
The embedding client validates ordering, vector dimensions, finite values and
nonzero norms, and normalizes vectors. It does not retry or change models silently.
Provider failures are reported without exposing response bodies or credentials.

API reference: https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request

## Admin indexing
Set TEXT_INDEX_ADMIN_ENABLED=true locally and restart. Follow [Postman guide](../api/admin/TEXT_INDEX_API.md). Uses products/product_embeddings; no migration needed.
