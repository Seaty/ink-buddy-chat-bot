# Hybrid Text Search API

## Setup and Postman

Set `TEXT_SEARCH_ENABLED=true` in backend/.env and restart Backend. Keep
`TEXT_EMBED_MODEL=qwen/qwen3-embedding-4b`, `TEXT_EMBED_DIM=1024` matching indexed catalog.
Import `text-search.postman_collection.json` and `text-search.postman_environment.json`.
Enter email/password privately and run Login. User/Admin work equally; Guest uses
Create Guest then Guest search with Postman's cookie jar and allowed Origin.

## POST /api/v1/product-search/by-text

Policy: guest_or_user. Bearer supplied but invalid never falls back to Guest.
Guest POST requires allowed Origin, e.g. http://localhost:3000. Limit 20/minute
per authenticated principal. Feature flag defaults off.

```json
{"query":"ปากกาเจล ไม่เกิน 100 บาท","limit":5}
```

Fields: query trimmed 1–4000 characters; limit 1–10 (default 5); optional category
uses catalog key (e.g. gel_pen, notebook); optional brand is exact catalog spelling.
Unknown fields rejected. Category/brand specified explicitly override inferred filters.
Budget comes from query using existing parser: `ไม่เกิน 100 บาท` or `50–100 บาท`.
Ambiguous budget returns 200 with clarification and empty items without query embedding.

Response fields: items, clarification, embedding_model, method=hybrid_rrf,
index_status (ready/partial/missing), stale_skipped, timings_ms. Each item contains
product facts from DB, score, keyword_rank, semantic_rank, semantic_similarity.
No chat session/message writes or answer generation.

No-match responses now include clarification tailored to budget vs other filters;
they do not relax filters automatically. Catalog completeness/index freshness audit
is available through `python -m scripts.audit_text_catalog` (local read-only script,
not a new public API).

Errors: 401 credential invalid/missing; 403 Guest Origin invalid; 404 disabled;
422 request/category/dimensions invalid; 429 limited; 503 query embedding unavailable.
Provider failure does not silently return keyword-only results. Missing index returns
keyword results with index_status=missing without a paid embedding call.
NULL prices or non-THB currency never qualify for THB budget search. No products
matching the filters returns empty items; source_ref may be null if absent in catalog.

`score` is reciprocal rank fusion, not confidence/probability. Price/availability are
catalog snapshots; this API does not fetch fresh retailer prices.

## Limitations

### Retrieval tuning — 2026-10-13

Inferred categories include สีไม้/ดินสอสี (colored_pencil). Thai brand aliases
are mapped to catalog brand spellings. Explicit steel/plastic/watercolor traits
and colors require evidence in product text; missing evidence may exclude a valid
but incompletely described product. Similarity threshold remains 0.35 after
development trials at 0.35/0.45/0.55/0.65 showed equal results.
See [evaluation process](../../architecture/RAG_QUALITY_EVALUATION_PROCESS.md)
for provisional labels, metrics and limitations.

### Catalog policy update

Response now includes `guardrail_status` (allowed/blocked/needs_clarification/no_match),
`guardrail_reason`, `policy_version`, `relevance_rejected`. Business refusals return
HTTP 200 with empty items and a clarification/message. `index_status=not_checked`
means processing stopped before index coverage inspection. Missing credentials remain 401.
Upstream embedding HTTP 403 returns `OPENROUTER_POLICY_REJECTED` with HTTP 403;
it may reflect budget/model/security policy, so no cause is guessed.
Scope and explicit color/model evidence checks are described in
[Guardrail process](../../architecture/TEXT_GUARDRAIL_PROCESS.md).

Similarity cutoff defaults 0.35 and is not calibrated. Rules reduce known scope failures;
they do not guarantee correct relevance for all inputs. Nearest vector results can be
irrelevant, especially for questions outside stationery. Do not treat returned items
as verified recommendations. Domain guardrails/evaluation precede chat integration.
index_status=ready is row-count coverage, not a quality guarantee. Freshness is checked
for semantic candidates retrieved (up to 100); keyword results use current DB facts.

Requests with indexed catalog use paid query embeddings; catalog embeddings are reused.
Image embedding and message answer adapter remain unchanged.
