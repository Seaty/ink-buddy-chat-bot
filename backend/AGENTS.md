# Ink Buddy backend guidance

Applies to this backend directory in addition to the repository root guidance.

## Access and credentials

- Every API operation must declare an explicit policy through `app/api/policy.py`. Preserve default-deny enforcement and the startup policy audit; do not add broad prefix exemptions or a development user bypass.
- When a Bearer credential is supplied, invalid credentials must return 401 without falling back to Guest. Derive principal and role from validated credentials and DB state.
- Check resource ownership in implemented handlers/services. Return 404 for another principal's image; a scaffold returning 501 does not establish ownership behavior.
- Preserve immediate Login-session revocation on logout and refresh-token reuse, refresh rotation in one transaction, and the absolute session expiry. Read the token flow before changing these behaviors.
- Cookie-authenticated mutations must retain the allowed-Origin check. Never log passwords, raw tokens, token/password hashes, signing secrets, or credential-bearing database URLs.

## Data and verification

- Guest successful-upload quota and claim must lock the Guest row and update ownership/counters in one database transaction. Failed validation or rolled-back inserts must not consume quota. File storage needs separate failure cleanup because files are outside the DB transaction.
- Generate new UUIDs with `app.core.identifiers.uuid7()` in Python or `public.ink_buddy_uuid_v7()` in SQL. Keep API parsing compatible with existing UUIDs and preserve stored IDs/FKs. Integer IDs remain integers.
- Schema changes need an existing-database migration as well as a current fresh-install DDL snapshot. Keep historical applied migrations unchanged and update `database/DATABASE_SCHEMA.md`.
- For Auth/Guest transaction or concurrency changes, verify against isolated PostgreSQL using `scripts.test_auth_postgres`. Unit-test success or skipped DB tests do not prove integration behavior. Never point the integration runner at the application database.
- Use the project-local Python environment. Update API Spec and regenerate OpenAPI when routes/contracts/policies change; distinguish implemented operations from scaffolds.

## References

- [Token flow](../docs/architecture/TOKEN_AUTH_FLOW.md)
- [API Spec](../docs/api/API_SPEC.md)
- [Auth setup and test commands](../docs/api/auth/README.md)
- [Auth review and open findings](../docs/api/auth/AUTH_REVIEW.md)
- For Auth/Guest implementation or review, use the repository-local [ink-buddy-auth skill](../.agents/skills/ink-buddy-auth/SKILL.md).
