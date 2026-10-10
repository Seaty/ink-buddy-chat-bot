<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->


# Ink Buddy frontend guidance

- Read root BUSINESS_REQUIREMENTS.md and current API Spec before product behavior changes. Users attach images only; upload UI and sending messages are outside the current session-management feature.
- Access tokens and drafts stay in memory. Use the shared API/Auth modules; retain single-flight refresh, no automatic mutation retry, and draft clearing on identity change.
- Suggested prompts are configured in src/features/chat/prompts.ts; changing a draft must not create a chat or message.
- Preserve Mobile-first layouts, theme tokens, keyboard focus, and confirmation before replacing a draft or deleting a chat.
- Run typecheck and focused frontend tests. Browser tests mock API contracts; PostgreSQL integration is tested separately in backend.
