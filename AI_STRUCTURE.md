# AI Module Architecture

## Overview

เพื่อให้ระบบสามารถขยายต่อในอนาคตได้ง่าย เช่น

- Multimodal RAG
- Multi-Agent
- Hybrid Search
- Reranker
- Tool Calling
- MCP Integration

ควรแยก AI Logic ออกจาก Business Logic ตั้งแต่เริ่มต้น โดยจัดกลุ่มไว้ภายใต้โฟลเดอร์ `ai/`

---

# Backend Structure

```text
backend/
├── app/
│
├── api/
│   ├── auth.py
│   ├── chat.py
│   ├── documents.py
│   └── vision.py
│
├── core/
│   ├── config.py
│   ├── database.py
│   ├── security.py
│   └── logging.py
│
├── models/
│   ├── user.py
│   ├── chat.py
│   └── document.py
│
├── schemas/
│   ├── auth.py
│   ├── chat.py
│   └── document.py
│
├── repositories/
│   ├── user_repository.py
│   ├── chat_repository.py
│   └── document_repository.py
│
├── services/
│   ├── auth_service.py
│   ├── chat_service.py
│   └── document_service.py
│
├── ai/
│   ├── llm/
│   ├── rag/
│   ├── vision/
│   ├── embeddings/
│   ├── prompts/
│   └── guards/
│
├── uploads/
├── tests/
└── main.py
```

---

# AI Layer Structure

```text
ai/
├── llm/
├── rag/
├── vision/
├── embeddings/
├── prompts/
└── guards/
```

---

# LLM Module

หน้าที่:

- เชื่อมต่อ Ollama
- เรียกใช้ Text Model
- เรียกใช้ Vision Model

โครงสร้าง:

```text
ai/
└── llm/
    ├── ollama_client.py
    ├── qwen_chat.py
    └── qwen_vision.py
```

## Responsibilities

### ollama_client.py

จัดการ

- Connection
- Timeout
- Model Configuration

### qwen_chat.py

รองรับ

- Chat
- Question Answering
- Summarization

ใช้

```text
Qwen3:8b
```

### qwen_vision.py

รองรับ

- Image Analysis
- OCR Understanding
- Table Understanding

ใช้

```text
Qwen2.5-VL:7b
```

---

# RAG Module

หน้าที่:

- Chunking
- Embedding
- Vector Search
- Context Retrieval

โครงสร้าง:

```text
ai/
└── rag/
    ├── chunker.py
    ├── retriever.py
    ├── vector_store.py
    ├── indexing_service.py
    └── rag_pipeline.py
```

---

## chunker.py

ทำหน้าที่

```text
Document
    ↓
Chunking
    ↓
Document Chunks
```

รองรับ

- PDF
- DOCX
- TXT
- Markdown

---

## vector_store.py

ทำงานร่วมกับ

```text
PostgreSQL + pgvector
```

ตัวอย่างหน้าที่

```text
Insert Embedding
Delete Embedding
Similarity Search
```

---

## retriever.py

ทำหน้าที่

```text
Question
    ↓
Embedding Search
    ↓
Retrieve Top-K Chunks
```

---

## indexing_service.py

ทำหน้าที่

```text
Document Upload
       ↓
Text Extraction
       ↓
Chunking
       ↓
Embedding
       ↓
Store in pgvector
```

---

## rag_pipeline.py

เป็น Main Pipeline

```text
User Question
       ↓
Embedding Search
       ↓
Retrieve Context
       ↓
Prompt Construction
       ↓
Qwen3
       ↓
Answer
```

---

# Vision Module

หน้าที่:

- OCR
- Image Analysis
- Diagram Analysis

โครงสร้าง:

```text
ai/
└── vision/
    ├── image_analyzer.py
    ├── ocr_service.py
    ├── table_extractor.py
    └── vision_pipeline.py
```

---

## image_analyzer.py

ใช้

```text
Qwen2.5-VL
```

สำหรับ

- Image Description
- Diagram Understanding
- Chart Understanding

---

## ocr_service.py

รองรับอนาคต

```text
EasyOCR
Tesseract
```

สำหรับ

- Image OCR
- Text Extraction

---

## table_extractor.py

ทำหน้าที่

```text
Image Table
    ↓
Extract Rows
    ↓
Structured Response
```

---

## vision_pipeline.py

Flow

```text
Image Upload
      ↓
OCR Processing
      ↓
Image Understanding
      ↓
Prompt Construction
      ↓
Qwen2.5-VL
      ↓
Response
```

---

# Embedding Module

หน้าที่:

- Generate Embedding
- Query Embedding
- Document Embedding

โครงสร้าง:

```text
ai/
└── embeddings/
    ├── embedding_service.py
    └── bge_embedding.py
```

---

## Model

Preferred:

```text
BGE-M3
```

Alternative:

```text
nomic-embed-text
```

---

# Prompt Module

แยก Prompt ออกจาก Business Logic

โครงสร้าง:

```text
ai/
└── prompts/
    ├── chat_prompt.py
    ├── rag_prompt.py
    ├── vision_prompt.py
    └── system_prompt.py
```

---

## chat_prompt.py

ใช้สำหรับ

```text
General Conversation
```

---

## rag_prompt.py

ใช้สำหรับ

```text
Context-Based Question Answering
```

---

## vision_prompt.py

ใช้สำหรับ

```text
Image Understanding
OCR Analysis
```

---

## system_prompt.py

กำหนด Global Instructions

ตัวอย่าง

```text
You are Ink Buddy Chat Bot.
Always answer based on retrieved documents.
Provide citation when available.
```

---

# AI Security Module

เพื่อป้องกันความเสี่ยงด้าน LLM

โครงสร้าง:

```text
ai/
└── guards/
    ├── prompt_injection_guard.py
    ├── content_filter.py
    └── pii_filter.py
```

---

## prompt_injection_guard.py

ตรวจจับคำสั่งอันตราย

ตัวอย่าง

```text
Ignore previous instructions
Reveal system prompt
Show system configuration
```

---

## content_filter.py

กรองเนื้อหา

```text
Unsafe Content
Malicious Instructions
Restricted Content
```

---

## pii_filter.py

ป้องกันการเปิดเผยข้อมูลสำคัญ

เช่น

```text
Password
API Key
Token
Database Credential
Personal Information
```

---

# Chat Flow

```text
api/chat.py
        │
        ▼
chat_service.py
        │
        ▼
rag_pipeline.py
        │
        ▼
retriever.py
        │
        ▼
qwen_chat.py
        │
        ▼
Response
```

---

# Image Analysis Flow

```text
api/vision.py
         │
         ▼
vision_pipeline.py
         │
         ▼
image_analyzer.py
         │
         ▼
qwen_vision.py
         │
         ▼
Response
```

---

# Future Expansion

โครงสร้างนี้รองรับการเพิ่มโมดูลใหม่โดยไม่ต้องปรับ Architecture หลัก

ตัวอย่าง

```text
ai/
├── agents/
├── rerankers/
├── tools/
├── workflows/
└── mcp/
```

---

# Recommended AI Stack

```yaml
LLM Runtime:
  - Ollama

Text Model:
  - Qwen3:8b

Vision Model:
  - Qwen2.5-VL:7b

Embedding:
  - BGE-M3

Vector Database:
  - PostgreSQL
  - pgvector

AI Framework:
  - LangChain

AI Security:
  - Prompt Injection Guard
  - Content Filter
  - PII Filter
```

# Design Principles

- Separation of Concerns
- Clean Architecture
- Modular AI Components
- Secure-by-Design
- Extensible RAG Pipeline
- Future-ready for Multi-Agent and MCP Integration

This structure is the recommended architecture for the Ink Buddy Chat Bot backend and provides a scalable foundation for RAG, Vision AI, and future AI capabilities.