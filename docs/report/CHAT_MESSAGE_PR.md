# PR: catalog-backed text chat messages

Suggested title: feat: add catalog-backed chat messages and atomic history

Base: feature/chat-sessions; head: feature/chat-message-response. Stacked PR: main currently lacks the preceding Chat Session changes. Retarget after that branch merges; do not merge automatically.

## Changes

- Implement POST /chat-sessions/{id}/messages for Guest/User, text-only, trim1–4000, required UUIDv7 client_request_id
- DB product keyword/category/brand/budget search (THB), deterministic top5 and clarification/no-match responses
- Pure AnswerInput/AnswerOutput adapter contract; default catalog_template, no LLM invocation
- Atomic user/assistant history, reference snapshots, replay lookup, request conflict and concurrent-history detection
- Recheck Guest/User credentials/ownership after answer; release DB locks before retrieval/answer; bounded timeout/executor
- Frontend send/Enter/IME, pending/error/retry, draft preservation, catalog refs and history reload
- Migration006 and updated fresh DDL/schema/API/OpenAPI/setup docs
- Project presentation source scripts and SVG/PNG diagrams: architecture and two-page ERD, with Canva presentation link in docs/presentation/README.md

## Historical verification — 2026-10-05

- Backend regression134passed /45skipped (PG41 ran separately;4 real-model tests not run)
- PostgreSQL41passed: replay/concurrency/claim/delete/expiry/logout/rollback/migration
- Frontend19passed; browser15passed with API mocks; TypeScript and container build passed
- Real browser smoke with real HTTP backend + disposable PG + template: Guest/User/claim/history/no-match passed; no seeded data in application DB
- Local DB backed up before applying006; catalog unchanged; container healthy

## Branch cutoff — 2026-10-10

This PR closes the current application/template milestone. Text RAG, OpenRouter, LLM guardrails and Vision integration belong to subsequent work. Base is feature/chat-sessions while PR #4 remains open; retarget after #4 merges.

Current verification: Backend regression 134 passed / 45 skipped (PostgreSQL 41 and real-model 4 not run in this set); focused chat/scaffold 19 passed; Frontend 19 passed; TypeScript passed; staged diff check passed. PostgreSQL integration, browser E2E and container build were not rerun. Podman machine started successfully, but no PostgreSQL container was running. Historical integration/browser/model boundaries above remain separate evidence.

## Local files excluded from Git / PR

Only temporary PDF page renders are deliberately left untracked. They are images extracted from the course attachment, not application assets:

- tmp/pdfs/week12/page-04.png
- tmp/pdfs/week12/page-05.png
- tmp/pdfs/week12/page-06.png
- tmp/pdfs/week12/page-07.png
- tmp/pdfs/week12/page-08.png
- tmp/pdfs/week12/page-09.png
- tmp/pdfs/week12/page-10.png

Existing ignored local environments, secrets, dependencies, backups and test artifacts remain excluded. The attached course PDF and private Canva credentials are not included.

## Boundaries

No streaming, image messages/upload UI, embeddings/semantic RAG, summary or purchase flow. Teammate LLM adapter integration remains separate. Substring search targets small catalog; no claim of production-scale index performance. Timeout cannot forcibly terminate adapter threads, so future network adapters need their own timeouts. Existing limiter/partial image write findings unchanged.

## Rollout

Apply006 after005 on existing DB; fresh DB uses init. Defaults CHAT_ADAPTER=catalog_template and CHAT_TIMEOUT_SECONDS=60. Rebuild frontend container; restart backend if not using reload. Do not auto-seed catalog; empty catalog yields honest no-match response.
