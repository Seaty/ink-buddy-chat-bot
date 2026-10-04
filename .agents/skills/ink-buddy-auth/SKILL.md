---
name: ink-buddy-auth
description: Implement or review Ink Buddy authentication, route access policies, Guest ownership, upload quota, claim, and their database transactions. Use for changes involving these behaviors in this repository.
---

# Ink Buddy Auth workflow

Support the requested Auth/Guest change or review without expanding it into unrelated hardening. Repository and backend AGENTS.md guidance applies. Keep project-specific resources local.

## Read the maintained context

Resolve paths below relative to this skill directory:

- Read [Token flow](../../../docs/architecture/TOKEN_AUTH_FLOW.md) and the relevant sections of [API Spec](../../../docs/api/API_SPEC.md) for current policies, credentials, expiry, and error contracts.
- Read [Auth review](../../../docs/api/auth/AUTH_REVIEW.md) for open findings. Verify their status against current code before repeating them or claiming they are fixed; review notes are not authorization to implement unrelated fixes.
- For setup and verification, use [Auth README](../../../docs/api/auth/README.md). For schema changes, read [Database Schema](../../../database/DATABASE_SCHEMA.md) and pending migrations.

## Trace the behavior

Inspect `backend/app/api/deps.py`, `api/policy.py`, and the relevant route, Auth service/repository or Vision service. Use code to establish what is implemented; documented scaffold contracts are proposals.

For the touched behavior, cover the relevant success, refusal, and race cases:

- User credentials: wrong/inactive account, invalid or expired JWT, revoked Login session, refresh rotation/reuse, concurrent refresh, immediate logout, and absolute expiry.
- Access policy: missing credentials, invalid Bearer with a valid Guest cookie, Guest versus User/Admin, ownership, allowed Origin, cookie attributes, and route policy declaration.
- Guest: existing cookie reuse without resetting expiry/quota, expired/revoked cookie, upload quota under concurrent requests, failed validation/DB writes, claim versus upload/search, and complete ownership transfer.
- Storage/operations when touched: partial file-write failure, safe cleanup paths and retry, claimed-data exclusion, and actual limiter storage matching app configuration.

Read TTLs and rate limits from maintained documents/settings; do not copy them into new permanent instruction files. Keep a clear distinction between DB transaction guarantees and filesystem behavior. UUIDs identify resources; they are not authentication credentials.

## Verify proportionately

From `backend/`, use `.\.venv\Scripts\python.exe` with focused tests for affected behavior. For Auth/Guest transaction, migration, or concurrency changes, run `-m scripts.test_auth_postgres` against its uniquely named disposable database after checking local Podman/PostgreSQL availability. The runner manages creation and removal of that test DB.

Do not use the application DB as a test database or restart/init its persistent volume for verification. If integration cannot run, report the concrete blocker and separate passed, failed, and skipped checks. Use fake Vision fixtures for Auth tests; do not imply they verify real Ollama/embedding behavior. Broaden regression only for a relevant risk or required gate.

## Deliver

Update DDL plus migration and schema docs for schema changes; update API Spec/OpenAPI for contract/policy changes and Token Flow for lifecycle changes. Update Auth review when a finding has actually been fixed and verified.

Report what changed, affected API cases, verification evidence, and remaining limitations. Preserve scaffolds as scaffolds unless implementing them is part of the user's request.
