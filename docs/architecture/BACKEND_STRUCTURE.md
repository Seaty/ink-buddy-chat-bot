# Backend structure — โครงตั้งต้น API

## Folder structure

```text
backend/app/
├── main.py                 # FastAPI setup, CORS, error handlers
├── api/
│   ├── deps.py             # Default-deny authorization และ User/Guest principal
│   ├── policy.py           # ทุก endpoint ประกาศ policy; ตรวจ nested routers ตอน startup
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
│   ├── auth/               # service.py: Auth transactions
│   ├── user/
│   ├── session/
│   ├── product/
│   ├── vision_service.py   # Image upload/search/index orchestration เดิม
│   └── image_storage.py    # Private file storage เดิม
├── repositories/
│   ├── auth/               # repository.py: Auth SQL
│   ├── user/
│   ├── session/
│   ├── product_repository.py # Catalog/index data access เดิม
│   └── image_repository.py # Image data access เดิม
├── models/                 # SQLAlchemy mappings สำหรับ Image RAG; Auth/Guest ใช้ raw SQL ตาม DDL
├── db/                     # Engine/session management
├── core/                   # Settings, errors, security และ rate limiting
└── ai/                     # Model adapters, retrieval และ pipelines เดิม
```

## หลักการต่อยอด

1. Routes รับ HTTP input/dependencies และเรียก service ไม่ใส่ SQL หรือ prompt orchestration ใน route
2. Schemas เป็น API contract แยกจาก SQLAlchemy models ไม่ส่ง password/token hash หรือ storage key ให้ client
3. Services ดูแล business rules, ownership และ transaction; repositories อ่าน/เขียนโดยไม่ commit เอง
4. Auth service สร้าง User/Guest principal และ role จาก DB; API policy ตรวจสิทธิ์ทุก operation
5. Guest quota ต้อง lock แถวและบันทึก counter/รูปใน transaction เดียว; การย้ายข้อมูลหลัง Login ต้อง atomic
6. AI adapters ยังคงอยู่ ai/ เพื่อให้เปลี่ยนโมเดล เพิ่ม Multi-Agent/MCP ผ่าน service ได้โดยไม่เปลี่ยน public contracts ตาม implementation ภายใน
7. เมื่อ implement endpoint ให้แทน not_implemented ด้วย service dependency, เพิ่ม error/ownership behavior, เอา scaffold metadata ออก และ regenerate OpenAPI
8. เก็บ module tests ใน backend/tests ตามชื่อฟีเจอร์; ทดสอบ ownership, token lifecycle, quota concurrency และ DB integration เมื่อเริ่ม logic

## สถานะและข้อจำกัด

- 17 endpoints implement แล้ว; 7 endpoints ยังตอบ 501หลังตรวจสิทธิ์ ไม่คืนข้อมูลปลอม scaffold handler ยังไม่ทำ business/AI logic แต่ authorization guard อาจอ่าน DB
- Swagger ลง success schema เป็น proposed contract พร้อม 501 และ x-implementation-status=scaffold
- Auth/Guest lifecycle,quota/claimและmigration003ทำแล้ว ดูTOKEN_AUTH_FLOWกับauthREADME
- API message ใช้ image_id เดียวให้ตรง DDL; 3 รูปต่อ Guest session ไม่ใช่ 3 รูปต่อข้อความ
- Guest24ชั่วโมง+retention24ชั่วโมง; access15นาที refresh7วัน rotation; โควตาบัญชีLogin/cursorยังต้องลงรายละเอียด
- Service/repository เดิมยังคงไว้ในชื่อเดิมเพื่อให้ตรวจการเปลี่ยนครั้งนี้ได้ชัดเจน โฟลเดอร์ module ใหม่เป็นจุดเริ่มสำหรับ implementation ถัดไป

## ดูและรัน

จาก backend ใช้ local .venv แล้วรัน `python -m uvicorn app.main:app --reload` เปิด `http://localhost:8000/docs` เพื่อดู routes การสร้าง OpenAPI ไม่จำเป็นต้องเชื่อม DB แต่ต้องมี Auth configuration ที่ถูกต้อง; การเรียก protected routes รวม scaffold ต้องมี credential และฐานข้อมูล ส่วน Image pipeline ต้องมี AI configuration ตามโหมดที่ใช้

Scripts ใน backend/scripts: create_user,cleanup_guests,test_auth_postgres; requirements เพิ่มargon2-cffi/email-validator ใช้bcryptโดยตรงเพื่ออ่านhashเดิม; เลิกdev bypassแล้ว


หลักการแยก SQL จาก routes เป็นแนวทางต่อยอด: ปัจจุบัน Profile GET ยังอ่าน DB ใน user/routes.py โดยตรง ส่วน user/product module services ยังเป็น placeholder; session service/repository implement แล้ว ดู [Auth review](../api/auth/AUTH_REVIEW.md) สำหรับข้อจำกัดที่พบ


## UUIDv7 (2026-10-03)

ID ใหม่ที่เป็น UUID ใช้ UUIDv7: database defaults เรียก `public.ink_buddy_uuid_v7()` และ Python ใช้ `app.core.identifiers.uuid7()` ชนิด column/API ยังคง UUID เพื่อรองรับ ID เดิม ไม่มีการเปลี่ยน primary/foreign keys ที่มีอยู่ ฐานเดิมต้อง apply `database/migrations/004_uuid_v7.sql` หลัง 003; ฐานใหม่ใช้ init ปัจจุบัน migrations 001–003 เก็บเป็นประวัติเดิม

UUIDv7 มี Unix timestamp ระดับ millisecond และ random bits ตาม [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) ไม่รับประกันลำดับภายใน millisecond หรือเมื่อ clock ย้อนกลับ ไม่ใช้ ID เป็น credential และยังตรวจ ownership ตามเดิม PostgreSQL 16 ใช้ compatibility function เพราะ built-in generator เป็น UUIDv4; ไม่มีการเปลี่ยนคอลัมน์ integer เช่น product_image_embeddings.id


อัปเดต Chat Session 2026-10-04: CRUD/rename/history ใช้งานแล้ว ส่วน send message ยัง501; Frontend มี Auth/Session UI และ prompt draft 3 รายการ ดู [Frontend setup](../../frontend/README.md)
