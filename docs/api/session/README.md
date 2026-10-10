# Chat Session API

อัปเดต 2026-10-04: policy guest_or_user ทุก operation ตรวจ ownership และ live credential; Guest mutation ต้องมี allowed Origin

| Method | Path ใต้ /api/v1 | สถานะ |
|---|---|---|
| POST | /chat-sessions | Implemented |
| GET | /chat-sessions | Implemented |
| GET | /chat-sessions/{session_id} | Implemented |
| PATCH | /chat-sessions/{session_id} | Implemented |
| DELETE | /chat-sessions/{session_id} | Implemented (soft delete) |
| GET | /chat-sessions/{session_id}/messages | Implemented |
| POST | /chat-sessions/{session_id}/messages | Scaffold501 |

รายละเอียด cursor, validation, locking และตัวอย่างอยู่ใน [API_SPEC](../API_SPEC.md) โครง frontend และ prompt draft อยู่ใน [Frontend README](../../../frontend/README.md)

## Text messages

POST messages implement แล้วพร้อม replay/atomic pair/recheck principal. [Adapter contract](ADAPTER_CONTRACT.md) ใช้ส่งต่อทีม AI ค่าเริ่มต้น catalog_template, search products DB ไม่ใช้ LLM/embeddings รายละเอียด API ใน API_SPEC.md และ migration006ใน Database Schema
