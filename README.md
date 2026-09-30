# Ink Buddy Chat Bot

See [the project folder guide](docs/README.md) for repository layout and where to keep architecture, API, database, and seed files.

## Local PostgreSQL with Podman

The [Podman setup guide](docker/README.md) explains how to start PostgreSQL 16 with pgvector from `docker/`. The database is available only on `127.0.0.1:5432` by default. The schema in `database/ddl/001_init.sql` runs automatically when the data volume is created for the first time.

A Multimodal Retrieval-Augmented Generation (RAG) Chatbot that provides intelligent question answering from documents and images using local LLMs powered by Ollama.

## Features

- Chat with AI using Qwen3 8B
- Document-based Question Answering (RAG)
- ~~PDF and DOCX Processing~~
- Image Analysis with Qwen2.5-VL
- Local AI Inference using Ollama
- Vector Search using PostgreSQL pgvector
- Citation-based Responses
- JWT Authentication
- Chat History Management

## Tech Stack

### Frontend
- Next.js 15
- TypeScript
- Tailwind CSS
- shadcn/ui
- Zustand

### Backend
- FastAPI
- LangChain
- SQLAlchemy
- Pydantic

### Database
- PostgreSQL
- pgvector

### AI Models
- Qwen3:8b
- Qwen2.5-VL:7b
- BGE-M3

### Infrastructure
- Podman Compose
