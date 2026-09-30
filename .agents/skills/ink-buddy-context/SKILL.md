---
name: ink-buddy-context
description: Apply Ink Buddy's stationery business requirements when planning, implementing, or reviewing product search, recommendations, chat, or image search in this repository.
---

# Ink Buddy context

Use this skill for product-related work in this repository.

1. Read `BUSINESS_REQUIREMENTS.md` as the source of truth for the product goal and confirmed capabilities.
2. Read `FIRST_DRAFT_SUMMARY.md` and `docs/architecture/AI_STRUCTURE.md` only as proposed technical architecture, then inspect the current files before describing what is implemented.
3. Make stationery discovery and useful recommendations the center of the user flow. Users attach images only. Treat catalog-based RAG, OCR, vision models, and vector search as supporting mechanisms; do not add user-facing document upload or document tables.
4. Ground specific product claims in available catalog data. If matching products or details are unavailable, communicate the gap clearly.
5. Keep unresolved decisions from `BUSINESS_REQUIREMENTS.md` explicit in plans; do not silently decide catalog source, stock rules, or checkout scope.

