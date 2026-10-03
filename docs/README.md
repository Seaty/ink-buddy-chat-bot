# คู่มือโครงสร้างโฟลเดอร์ Ink Buddy

ไฟล์นี้อธิบายหน้าที่ของโฟลเดอร์ใน repository เพื่อให้รู้ว่าควรเก็บโค้ด สคริปต์ฐานข้อมูล และเอกสารไว้ที่ไหน โฟลเดอร์หลายส่วนยังเป็นโครงที่เตรียมไว้ ไม่ได้หมายความว่ามีฟีเจอร์นั้นทำงานแล้ว

## โฟลเดอร์ระดับบน

| โฟลเดอร์ | หน้าที่ | ตัวอย่างสิ่งที่ควรเก็บ |
|---|---|---|
| `.agents/skills/` | Skill เฉพาะโปรเจคสำหรับผู้ช่วยพัฒนา | `ink-buddy-context/SKILL.md` |
| `.github/workflows/` | งานอัตโนมัติบน GitHub | CI ตรวจโค้ดและทดสอบ |
| `frontend/` | เว็บที่ผู้ใช้เห็นและใช้งาน | หน้าแชต ค้นสินค้า แนบรูป และแสดงสินค้า |
| `backend/` | API, กฎธุรกิจ และการเชื่อมต่อ AI | FastAPI, services, models, AI adapters |
| `database/` | สคริปต์ฐานข้อมูลและคำอธิบาย schema | DDL, migrations, seed, `DATABASE_SCHEMA.md` |
| `datasets/` | ชุดข้อมูลสำหรับพัฒนา/ทดลองที่อนุญาตให้เก็บใน repo | ตัวอย่างข้อมูลสินค้าแบบไม่เป็นความลับ |
| `docker/` | ไฟล์สำหรับรัน services ด้วย Podman Compose | `compose.yaml`, `.env.example` และคู่มือเริ่มต้น |
| `docs/` | เอกสารของโปรเจค | โครงสร้างระบบ, API, diagram, รายงาน |

ไฟล์สำคัญที่ root:

- `BUSINESS_REQUIREMENTS.md` — เป้าหมายธุรกิจปัจจุบัน: แชตบอตเครื่องเขียน ค้น/แนะนำสินค้า และแนบ **รูปภาพเท่านั้น**
- `FIRST_DRAFT_SUMMARY.md` — ร่างแนวคิดเทคนิคช่วงแรก มีบางส่วนที่ยังไม่ตรงกับข้อกำหนดปัจจุบัน เช่น การอัปโหลดเอกสาร
- `AGENTS.md` — แนวทางสำหรับ agent ที่ทำงานใน repository นี้
- `README.md` — ภาพรวมโปรเจค

## Frontend

| โฟลเดอร์ | หน้าที่ |
|---|---|
| `frontend/src/app/` | Pages, layouts และ routing ของ Next.js |
| `frontend/src/components/` | UI components ที่ใช้ในหน้าต่าง ๆ |
| `frontend/src/components/ui/` | UI primitives ที่ใช้ซ้ำ |
| `frontend/src/lib/` | API client และ utility functions |
| `frontend/src/stores/` | State ที่ใช้ข้าม component |
| `frontend/src/types/` | TypeScript types/interfaces |

`frontend/library-guide.md` เป็นบันทึกไลบรารีที่เคยวางแผนใช้ ไม่ใช่รายการ dependencies ที่ติดตั้งแล้ว

## Backend

| โฟลเดอร์ | หน้าที่ |
|---|---|
| `backend/app/api/` และ `api/v1/` | FastAPI routes และ API versioning |
| `backend/app/core/` | Configuration, security, logging และส่วนกลาง |
| `backend/app/db/` | การเชื่อมต่อฐานข้อมูลและ session setup |
| `backend/app/models/` | SQLAlchemy mappings ของ Image RAG; Auth/Guest ใช้ raw SQL ตาม DDL |
| `backend/app/schemas/` | Pydantic request/response schemas |
| `backend/app/repositories/` | การอ่าน/เขียนข้อมูล |
| `backend/app/services/` | กฎธุรกิจของสินค้า แชต และผู้ใช้ |
| `backend/app/ai/llm/` | การเชื่อมต่อ Ollama และโมเดลภาษา/ภาพ |
| `backend/app/ai/embeddings/` | Image/caption embedding ของสินค้า; text BGE-M3 ยังเป็นแผน |
| `backend/app/ai/rag/` | ดึงข้อมูลจาก catalog เพื่อประกอบคำตอบ |
| `backend/app/ai/vision/` | วิเคราะห์ภาพและ OCR |
| `backend/app/ai/prompts/` | Prompt templates |
| `backend/app/ai/guards/` | การตรวจข้อมูลและขอบเขตคำสั่งที่ส่งให้ AI |
| `backend/tests/` | การทดสอบ backend |
| `backend/uploads/` | private storage ของภาพที่อัปโหลดตาม configuration; ไม่ใช่ไฟล์ชั่วคราวที่ลบหลัง request |

`backend/app/services/document_processing/` และ `backend/app/services/rag/` เป็นโฟลเดอร์ที่เตรียมไว้ตามแผนเก่า หากเริ่มพัฒนาให้ทบทวนกับขอบเขตล่าสุดก่อนใช้: ผู้ใช้ไม่มีการแนบเอกสาร และ RAG ปัจจุบันอ้างข้อมูลสินค้าใน catalog

## Database

| โฟลเดอร์/ไฟล์ | หน้าที่ |
|---|---|
| `database/ddl/` | SQL สร้าง schema เริ่มต้น เช่น `001_init.sql` |
| `database/migrations/` | สคริปต์เปลี่ยน schema หลังเริ่มใช้ฐานข้อมูลแล้ว; ไม่แก้ init เดิมเพื่อเปลี่ยนระบบที่รันอยู่ |
| `database/seed/` | สคริปต์ `INSERT`/`UPSERT` ข้อมูลตั้งต้นหรือข้อมูลตัวอย่าง เช่น สินค้าทดลอง; แยกจากคำสั่งสร้างตาราง |
| `database/DATABASE_SCHEMA.md` | คำอธิบายตาราง ความสัมพันธ์ indexes และวิธีเริ่มต้นฐานข้อมูล |

ข้อมูลจริงที่มีความลับหรือข้อมูลส่วนบุคคลไม่ควรใส่ใน seed หรือ datasets ที่ commit ขึ้น repository

## เอกสารและตำแหน่งที่จัดเก็บ

| โฟลเดอร์ | เก็บเอกสารประเภทใด |
|---|---|
| `docs/architecture/` | โครงสร้างระบบ, AI modules, database/API design drafts และการตัดสินใจด้านสถาปัตยกรรม |
| `docs/api/` | API contracts, ตัวอย่าง request/response และ OpenAPI notes |
| `docs/diagrams/` | แผนภาพที่เป็นไฟล์แยก เช่น Mermaid source หรือ export |
| `docs/report/` | รายงานโปรเจคและเอกสารประกอบการศึกษา |

เอกสารโครงสร้างที่มีตอนนี้:

- [`architecture/TOKEN_AUTH_FLOW.md`](architecture/TOKEN_AUTH_FLOW.md) — วิธีทำงาน User/Guest token, whitelist, โควตารูป และการย้ายข้อมูลหลัง Login

- [`architecture/BACKEND_STRUCTURE.md`](architecture/BACKEND_STRUCTURE.md) — โครง code API ตาม module และขอบเขต routes/services/repositories
- [`api/README.md`](api/README.md) — สารบัญ API แยกตามหมวด

- ข้อกำหนด Guest, โควตา 3 รูป และข้อเสนอปรับ database/API รวมอยู่ใน [`api/API_SPEC.md`](api/API_SPEC.md) หัวข้อ 10

- [`api/API_SPEC.md`](api/API_SPEC.md) — API ที่ implement แล้ว สถานะ ข้อจำกัด และประเด็นตัดสินใจ; [`api/openapi.current.json`](api/openapi.current.json) เป็น snapshot จากแอปจริง

- [`architecture/PROJECT_STATUS.md`](architecture/PROJECT_STATUS.md) — สถานะโค้ดหลังทีมเพิ่ม Image RAG, ผลทดสอบ และจุดที่ยังต้องเชื่อมต่อ

- [`architecture/AI_STRUCTURE.md`](architecture/AI_STRUCTURE.md) — ร่างการแบ่ง AI modules จากช่วงแรก; ตรวจเทียบ Business Requirements ล่าสุดก่อนนำไปทำจริง
- [`architecture/INK_BUDDY_DESIGN_DRAFT.md`](architecture/INK_BUDDY_DESIGN_DRAFT.md) — ร่าง architecture, database และ API ที่ปรับให้ใช้ catalog สินค้าและการแนบรูป
- [`../database/DATABASE_SCHEMA.md`](../database/DATABASE_SCHEMA.md) — โครงสร้างฐานข้อมูลตาม SQL init

## หลักการเลือกที่เก็บไฟล์ใหม่

- เปลี่ยนพฤติกรรมผลิตภัณฑ์หรือขอบเขตงาน → อัปเดต `BUSINESS_REQUIREMENTS.md` ก่อน
- อธิบายภาพรวมระบบหรือการแบ่ง module → `docs/architecture/`
- อธิบาย endpoint ที่ implement แล้ว → `docs/api/`
- สร้างตารางครั้งแรก → `database/ddl/`; เปลี่ยนตารางหลังใช้งาน → `database/migrations/`
- เพิ่มข้อมูลเริ่มต้น/ทดลองด้วย SQL → `database/seed/`; เก็บชุดข้อมูลต้นทางสำหรับทดลอง → `datasets/`

## ผลตรวจล่าสุด 2026-10-03

- [ผลตรวจเอกสารทั้งหมด](report/DOCUMENTATION_AUDIT.md)
- [รีวิว Auth และรายละเอียดเคส](api/auth/AUTH_REVIEW.md) — สองประเด็น P2 ยังไม่ได้แก้โค้ด
- `backend/scripts/` เก็บสคริปต์สร้างบัญชี, cleanup Guest และทดสอบ PostgreSQL
- Auth service/repository ใช้งานแล้ว; user/session/product module folders บางส่วนยังเป็น placeholder

## แนวทางสำหรับผู้ช่วยพัฒนา backend

- [backend/AGENTS.md](../backend/AGENTS.md) — กฎสิทธิ์, token, transaction, UUIDv7 และการทดสอบ
- [ink-buddy-auth skill](../.agents/skills/ink-buddy-auth/SKILL.md) — ขั้นตอนพัฒนาและรีวิว Auth/Guest ที่ใช้ซ้ำ เก็บใน repository เท่านั้น
