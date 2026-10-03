# Backend structure — โครงตั้งต้น API

## Folder structure

```text
backend/app/
├── main.py                 # FastAPI setup, CORS, error handlers
├── api/
│   ├── deps.py             # Shared dependencies; dev user ปัจจุบัน
│   ├── scaffold.py         # 501 helper + OpenAPI status; ลบเมื่อ modules พร้อม
│   └── v1/
│       ├── router.py       # รวม routers และกำหนด /api/v1
│       ├── auth/routes.py  # Login, tokens, Guest access session
│       ├── user/routes.py  # Profile
│       ├── session/routes.py # Chat sessions/messages
│       ├── image/routes.py # Upload/detail/delete
│       ├── product/
│       │   ├── routes.py   # Product list/detail + รวม search router
│       │   └── search.py   # Image search เดิม
│       ├── admin/routes.py # Index catalog เดิม
│       └── system/routes.py # Health/readiness
├── schemas/                # auth/user/session/image/product/admin/system.py
│   └── vision.py           # Compatibility exports สำหรับ imports เดิม
├── services/
│   ├── auth/               # เตรียม boundary; ยังไม่มี implementation
│   ├── user/
│   ├── session/
│   ├── product/
│   ├── vision_service.py   # Image upload/search/index orchestration เดิม
│   └── image_storage.py    # Private file storage เดิม
├── repositories/
│   ├── auth/               # เตรียม boundary; ยังไม่มี implementation
│   ├── user/
│   ├── session/
│   ├── product_repository.py # Catalog/index data access เดิม
│   └── image_repository.py # Image data access เดิม
├── models/                 # SQLAlchemy mappings; Guest mappings ยังต้องเพิ่ม
├── db/                     # Engine/session management
├── core/                   # Settings และ errors
└── ai/                     # Model adapters, retrieval และ pipelines เดิม
```

## หลักการต่อยอด

1. Routes รับ HTTP input/dependencies และเรียก service ไม่ใส่ SQL หรือ prompt orchestration ใน route
2. Schemas เป็น API contract แยกจาก SQLAlchemy models ไม่ส่ง password/token hash หรือ storage key ให้ client
3. Services ดูแล business rules, ownership และ transaction; repositories อ่าน/เขียนโดยไม่ commit เอง
4. Auth service ต่อไปต้องสร้าง principal แบบ User/Guest แทน dev user และตรวจ role สำหรับ admin
5. Guest quota ต้อง lock แถวและบันทึก counter/รูปใน transaction เดียว; การย้ายข้อมูลหลัง Login ต้อง atomic
6. AI adapters ยังคงอยู่ ai/ เพื่อให้เปลี่ยนโมเดล เพิ่ม Multi-Agent/MCP ผ่าน service ได้โดยไม่เปลี่ยน public contracts ตาม implementation ภายใน
7. เมื่อ implement endpoint ให้แทน not_implemented ด้วย service dependency, เพิ่ม error/ownership behavior, เอา scaffold metadata ออก และ regenerate OpenAPI
8. เก็บ module tests ใน backend/tests ตามชื่อฟีเจอร์; ทดสอบ ownership, token lifecycle, quota concurrency และ DB integration เมื่อเริ่ม logic

## สถานะและข้อจำกัด

- 4 endpoints เดิมยังทำงาน; 19 endpoints ใหม่ตอบ 501 ไม่คืนข้อมูลปลอม ไม่มี DB/model calls จาก scaffold
- Swagger ลง success schema เป็น proposed contract พร้อม 501 และ x-implementation-status=scaffold
- Auth/Guest logic และ DB models ใหม่ยังไม่ได้ทำ DDL พร้อมไม่ได้แปลว่า backend ใช้ Guest ได้แล้ว
- API message ใช้ image_id เดียวให้ตรง DDL; 3 รูปต่อ Guest session ไม่ใช่ 3 รูปต่อข้อความ
- อายุ Guest/retention และโควตาบัญชี Login ยังไม่กำหนด; cursor และ refresh cookie policy ยังต้องลงรายละเอียด
- Service/repository เดิมยังคงไว้ในชื่อเดิมเพื่อให้ตรวจการเปลี่ยนครั้งนี้ได้ชัดเจน โฟลเดอร์ module ใหม่เป็นจุดเริ่มสำหรับ implementation ถัดไป

## ดูและรัน

จาก backend ใช้ local .venv แล้วรัน `python -m uvicorn app.main:app --reload` เปิด `http://localhost:8000/docs` เพื่อดู routes โครงใหม่ไม่ต้องมีฐานข้อมูลเพื่อดู schema หรือลอง 501; routes เดิมที่ใช้งานจริงยังต้อง config DB/AI
