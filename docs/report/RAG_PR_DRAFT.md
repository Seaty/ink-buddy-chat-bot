# Text Catalog RAG with OpenRouter and conversational product answers

Base: main; Head: feature/rag

## Changes

- Admin text validation/indexing: Qwen3 Embedding 4B, 1024 dimensions, unchanged detection, advisory locking and atomic batches
- Hybrid PostgreSQL keyword/pgvector retrieval, category/brand aliases, THB budgets and input/retrieval guardrails
- Qwen3 14B selects permitted Product/Evidence IDs; server validates and renders factual answers, without automatic retry/fallback
- Same-chat context, displayed-order references, SQL price ranking/count, ink/body colors and same-family variants
- Preserve atomic message pair, ownership/credential rechecks, sequence and request replay
- Natural Thai answers, readable prices, concise details; remove repetitive internal labels/freshness disclaimers while retaining source cards
- Frontend source badges and separate product/price sources, unit/tax metadata and nested alternative colors
- Reviewed catalog, import/audit/evaluation tools, Postman examples and presentation process documentation
- Podman frontend service healthcheck and standalone container verification

## Verification

2026-10-15: intent/adapter/rendering 27 passed; disposable PostgreSQL 68 passed. No live provider rerun for wording-only adjustment; provider contract unchanged.

2026-10-14 UAT: focused backend 51 passed; PostgreSQL 68 passed; frontend 25 passed; TypeScript passed; browser API mocks 15 passed. Real frontend Podman container -> local API -> disposable PostgreSQL -> OpenRouter passed Mobile/Tablet/Desktop for ranked prices, variants, ordinal follow-up, replay and reloaded history. Main catalog read-only live trial passed 3 paid questions + fresh-chat clarification. Real browser auth regression passed Mobile. Container build and OpenAPI/policy checks passed: 32 operations, 26 paths.

Earlier live robustness 39/39 is historical evidence on its catalog version, not an independent human benchmark. Failed development trials remain in reports. Optional scaffold verification stalled in a Vision dependency and was stopped, not counted as passed. Environment/proxy issues and corrections are documented in RAG_CONVERSATION_UAT_2026-10-14.md.

## Configuration and scope

OPENROUTER_API_KEY belongs in backend/.env. CHAT_ADAPTER=openrouter_catalog enables RAG; code default remains catalog_template. Index admin/standalone search have separate feature flags. Indexing/query embeddings/answers use credits. Models are server configured.

No new schema migration: references use existing JSONB. Image embedding/Vision flow unchanged. No streaming, image upload UI, conversation summary, checkout or user document uploads.

Local demo catalog: 67 priced products. 15 explicitly exclude VAT; 52 have user-assumed tax basis. Prices are coursework snapshots; verify units/colors/tax details before commercial use.

## Remaining work

- Team human evaluation and independent held-out question set
- Verify product color/unit/tax/source details that remain incomplete
- Broader natural-language follow-ups, long-history summary and larger-catalog query optimization as future work
- Production deployment/shared limiter storage/operations separately

## Intentionally excluded local files

Runtime .env/secrets, .venv/node_modules/.next, .local logs/backups/screenshots and DB contents are not published. Raw candidate images remain local: backend/datasets/officemate_candidates/images/ (3) and backend/datasets/officework_candidates/images/ (15). Text source metadata and reviewed manifest are included; optional raw images are not required for text RAG. Check git status for exact remaining paths.

## Review references

- docs/architecture/RAG_CONVERSATION_PROCESS.md
- docs/architecture/RAG_RESPONSE_TONE.md
- docs/report/RAG_CONVERSATION_UAT_2026-10-14.md
- docs/api/session/RAG_CHAT_API.md and Postman collection
