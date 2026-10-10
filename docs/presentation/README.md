# Ink Buddy project update presentation

Editable presentation: https://canva.link/ce95wejbnfhpa94

Updated 2026-10-10. The 13-slide deck distinguishes implemented application behavior, existing Vision modules and planned Text RAG/LLM integration. Historical testing evidence refers to 2026-10-05, not a new model evaluation.

## Current diagrams

- `system-architecture.svg` / `.png`: slide 6, current HTTP/service/repository/database flow and separate image storage, Vision runtime and planned Text RAG branches. Regenerate SVG with `python docs/presentation/build_architecture.py`.
- `erd-accounts.svg` / `.png`: slide 9, account/role/Guest/token/audit tables.
- `erd-chat-catalog.svg` / `.png`: slide 10, chat/catalog/image tables. Regenerate both SVGs with `python docs/presentation/build_split_erd.py`.
- `ink-buddy-erd.svg` and `build_erd.py`: earlier single-page ERD, retained as a source alternative; the deck uses the two-page version.

SVG diagrams are vector assets. Their constituent tables/arrows are not independent Canva elements; edit the source and replace the entire asset. PNG files are local preview copies. Canva design edits must be saved and verified against the actual persisted assets.

Course PDF page previews under `tmp/pdfs/week12/` are temporary and are not part of the presentation source or PR.
