# Ink Buddy Chat Bot

ตรวจเอกสารล่าสุด: 2026-10-03

เว็บแชตบอตสำหรับคำถามเครื่องเขียน ค้นหาและแนะนำสินค้า รวมถึงค้นสินค้าจากภาพ ผู้ใช้แนบ **รูปภาพเท่านั้น** ไม่มีการแนบ PDF/DOCX รายละเอียดธุรกิจอยู่ใน [Business Requirements](BUSINESS_REQUIREMENTS.md)

## สถานะปัจจุบัน

- Backend FastAPI: 23 operations บน 18 paths; ทำงานแล้ว 11 operations และเป็น scaffold 12 operations ที่ตรวจสิทธิ์ก่อนตอบ 501
- Authentication: User JWT, refresh rotation, logout, Guest session, claim และ profile GET ทำแล้ว
- Guest ใช้งาน 24 ชั่วโมง อัปโหลดสำเร็จได้ 3 รูปรวมทุกแชต การลบไม่คืนโควตา
- Image upload/search และ admin indexing มี implementation; retrieval เริ่มต้นเป็น mock ต้องตั้งค่าและ index ก่อนค้น catalog จริง
- Chat, Product list/detail, Profile PATCH, Image detail/delete และ Readiness ยังไม่มี business logic
- Frontend Next.js/TypeScript/Tailwind ยังเป็นโครงและแผน ยังไม่มี Auth UI ที่พร้อมใช้งาน

## Technology และฐานข้อมูล

FastAPI, SQLAlchemy, PostgreSQL 16 และ pgvector ใช้จริงใน backend โดย Auth ใช้ raw SQL ตาม DDL ฐานข้อมูลมี 13 ตาราง ไม่มี document tables

Image pipeline ใช้ Ollama Qwen3-VL (ค่าเริ่มต้น `qwen3-vl:latest`) และ `Qwen/Qwen3-VL-Embedding-2B` เวกเตอร์ 2048 มิติ ส่วน Qwen3:8b, BGE-M3 และ text/chat RAG ยังเป็นแผนที่ต้องเชื่อมต่อเพิ่มเติม การทดสอบ Auth ไม่ได้ยืนยันโมเดล AI จริง

## เริ่มใช้งานและเอกสาร

1. รัน PostgreSQL ตาม [Podman setup](docker/README.md) ผ่าน `docker/compose.yaml` พอร์ตเฉพาะ `127.0.0.1:5432` และเก็บข้อมูลใน volume
2. ตั้งค่า backend environment, สร้างบัญชีผ่าน local script และรัน backend ตาม [Auth setup](docs/api/auth/README.md) ไม่มีบัญชีหรือ signing secret เริ่มต้น
3. ดู [API Spec](docs/api/API_SPEC.md), [Database Schema](database/DATABASE_SCHEMA.md), [Token flow](docs/architecture/TOKEN_AUTH_FLOW.md) และ [คู่มือโฟลเดอร์](docs/README.md)

[สถานะโปรเจกต์](docs/architecture/PROJECT_STATUS.md) รวมผลทดสอบล่าสุด [Auth review](docs/api/auth/AUTH_REVIEW.md) ระบุเคสและสองประเด็น P2 ที่ยังเปิดอยู่ [ผลตรวจเอกสาร](docs/report/DOCUMENTATION_AUDIT.md) แยกเอกสารปัจจุบันออกจากร่างเก่า


## UUIDv7 update — 2026-10-03

UUID ที่สร้างใหม่ใช้ v7 ทั้ง database defaults, Python storage keys และ scripts ฐาน local สำรองแล้วและ apply migration 004 เรียบร้อย ID เดิมและ FK ไม่เปลี่ยน API ยังรับ UUID เดิมได้ ดู [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) สำหรับรูปแบบ

ผลทดสอบหลังเปลี่ยน: regression 113 passed / 23 skipped; PostgreSQL integration 19 passed แยกผ่าน Podman (รวม migration repeat-safe, defaults ทั้ง 12 UUID tables, timestamp/version และ uniqueness) ค่า integer ID คงชนิดเดิม
