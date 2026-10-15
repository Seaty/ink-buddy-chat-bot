# Text catalog indexing — Postman guide

## Setup

1. Set `TEXT_INDEX_ADMIN_ENABLED=true` in `backend/.env` and restart backend.
2. Keep `OPENROUTER_API_KEY` only in `backend/.env`. Replace the previously exposed key.
3. Create an admin from backend: `.venv/Scripts/python.exe -m scripts.create_user --email your@email.com --role admin`. Password input is hidden.
4. Import `text-index.postman_collection.json` and `text-index.postman_environment.json` from this folder.
5. Select the environment and enter your admin email/password privately. Never export populated secrets.
6. Run Login, then Validate catalog. Copy a Product ID from warnings/errors; if there are none, use an existing ID from the products table.
7. Set `product_id`, run Validate selected product, Index one product, then Replay unchanged product.

Login requires Origin `http://localhost:3000` matching configured CORS origins.
Bearer credentials protect the admin APIs. Tokens expire after 15 minutes; rerun Login.
OpenRouter key is never sent from Postman; only backend uses it.

## APIs

Both operations require admin access. Missing token: 401; non-admin: 403;
disabled feature: 404; malformed/unknown IDs: 422; concurrent indexing: 409.
Requests reject unknown fields. `product_ids` accepts 1–100 UUIDs; omit to select catalog.

### POST /api/v1/admin/text-index/validate

```json
{}
```

Response fields: `examined`, `valid`, `invalid`, `errors`, `warnings`.
Issues contain `product_id`, `field`, `code`. Missing name / text exceeding
16000 characters blocks indexing; missing category/brand/description/price/source
is a warning. Empty catalog returns zero counts. This endpoint costs no credits.

### POST /api/v1/admin/text-index

```json
{"product_ids": ["<existing UUID>"], "limit": 1}
```

`limit` defaults to 5, range 1–100, and applies to changed valid products.
Response: `examined`, `indexed`, `unchanged`, `invalid`, `failed`, `remaining`,
`errors`, `warnings`, `seconds`. HTTP 200 is a report, not proof every item succeeded:
check `failed`, `invalid`, and issues. Batch failures use `BATCH_FAILED` without
provider text/secrets. `remaining` counts unselected changed products and products
changed/deleted during inference; failed products are counted separately.

Indexing uses paid OpenRouter calls. Repeating unchanged data does not call provider.
The canonical input excludes price, availability and image/source URLs; structured
attributes are sorted and URL/image/credential fields are excluded. Database product
claims remain the source of truth for later retrieval.

Each batch commits atomically; failed batch rolls back while earlier committed batches
remain. A dedicated PostgreSQL advisory lock serializes text indexing. Product row
locks are taken only after the provider returns. Existing rows for other models remain.
Fixed database dimension is 1024; other configured dimensions are rejected.

## Next milestone

Semantic/hybrid search, answer adapter and guardrails are not connected yet.
Chat still uses `catalog_template`. Image embedding is unchanged.

## Verification — 2026-10-11
Live OpenRouter smoke on disposable PostgreSQL at port 55439: validate 1 valid product, indexed 1, failed 0, stored 1024 dimensions. Replay returned unchanged=1; provider called once total. Uses configured backend key; key rotation was not verified. Test products were not inserted into the main database.

Verification 2026-10-11: Backend regression 188 passed / 53 skipped. Text indexing suite 10 passed, including 8 disposable PostgreSQL cases (insert/upsert/replay/UUIDv7, batch rollback, partial success, changed/deleted products, lock contention, guards). Existing auth PostgreSQL and real-model suites were not verified by this regression run. Live indexing smoke passed separately. git diff --check passed.
