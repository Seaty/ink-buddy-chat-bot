# ผลตรวจเอกสาร Ink Buddy

วันที่ตรวจ: 2026-10-03

## สรุป

ตรวจ Markdown ทุกไฟล์ใน repository รวม local skill/instructions โดยไม่รวม dependencies, Git และไฟล์ local ที่ ignored ปรับ README, folder guide, module indexes, Auth review และจุดที่ยังระบุสถานะเก่า ตรวจ OpenAPI snapshot และ DDL ประกอบ ไม่เปลี่ยน implementation ในงานนี้

สถานะอ้างอิง: 13 ตาราง, 23 operations / 18 paths, 11 implemented / 12 scaffold ผู้ใช้แนบรูปเท่านั้น Auth/Guest ทำแล้ว แต่ business logic ของ Chat และหลาย routes ยังไม่ทำ

ร่างเทคนิคเก็บไว้เป็นประวัติแนวคิด มี banner ระบุว่าไม่ใช่ contract ล่าสุด จึงอาจยังมีข้อความเรื่องเอกสาร โมเดลและ endpoint เก่าในเนื้อหาร่าง ให้ใช้ API_SPEC, DATABASE_SCHEMA และ PROJECT_STATUS ตัดสินสถานะปัจจุบัน

สอง P2 จากรีวิว Auth ยังเปิดอยู่ ดู [AUTH_REVIEW](../api/auth/AUTH_REVIEW.md) ผลทดสอบที่บันทึกเป็นผล verification ก่อนงานเอกสารครั้งนี้ ไม่ได้รันทดสอบโค้ดซ้ำ

## รายการเอกสารที่ตรวจ

| เอกสาร | สถานะ |
|---|---|
| [.agents/skills/ink-buddy-context/SKILL.md](../../.agents/skills/ink-buddy-context/SKILL.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [AGENTS.md](../../AGENTS.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [backend/.pytest_cache/README.md](../../backend/.pytest_cache/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [backend/app/repositories/auth/README.md](../../backend/app/repositories/auth/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [backend/app/repositories/session/README.md](../../backend/app/repositories/session/README.md) | placeholder ระบุขอบเขตแล้ว |
| [backend/app/repositories/user/README.md](../../backend/app/repositories/user/README.md) | placeholder ระบุขอบเขตแล้ว |
| [backend/app/services/auth/README.md](../../backend/app/services/auth/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [backend/app/services/product/README.md](../../backend/app/services/product/README.md) | placeholder ระบุขอบเขตแล้ว |
| [backend/app/services/session/README.md](../../backend/app/services/session/README.md) | placeholder ระบุขอบเขตแล้ว |
| [backend/app/services/user/README.md](../../backend/app/services/user/README.md) | placeholder ระบุขอบเขตแล้ว |
| [BUSINESS_REQUIREMENTS.md](../../BUSINESS_REQUIREMENTS.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [database/DATABASE_SCHEMA.md](../../database/DATABASE_SCHEMA.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docker/README.md](../../docker/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/admin/README.md](../../docs/api/admin/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/API_SPEC.md](../../docs/api/API_SPEC.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/auth/AUTH_REVIEW.md](../../docs/api/auth/AUTH_REVIEW.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/auth/README.md](../../docs/api/auth/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/image/README.md](../../docs/api/image/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/product/README.md](../../docs/api/product/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/README.md](../../docs/api/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/session/GUEST_SESSION_DESIGN.md](../../docs/api/session/GUEST_SESSION_DESIGN.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/session/README.md](../../docs/api/session/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/system/README.md](../../docs/api/system/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/api/user/README.md](../../docs/api/user/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/architecture/AI_STRUCTURE.md](../../docs/architecture/AI_STRUCTURE.md) | ร่าง/บันทึกเก่า มีคำเตือนและลิงก์สถานะล่าสุด |
| [docs/architecture/BACKEND_STRUCTURE.md](../../docs/architecture/BACKEND_STRUCTURE.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/architecture/INK_BUDDY_DESIGN_DRAFT.md](../../docs/architecture/INK_BUDDY_DESIGN_DRAFT.md) | ร่าง/บันทึกเก่า มีคำเตือนและลิงก์สถานะล่าสุด |
| [docs/architecture/PROJECT_STATUS.md](../../docs/architecture/PROJECT_STATUS.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/architecture/TOKEN_AUTH_FLOW.md](../../docs/architecture/TOKEN_AUTH_FLOW.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [docs/README.md](../../docs/README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |
| [FIRST_DRAFT_SUMMARY.md](../../FIRST_DRAFT_SUMMARY.md) | ร่าง/บันทึกเก่า มีคำเตือนและลิงก์สถานะล่าสุด |
| [frontend/library-guide.md](../../frontend/library-guide.md) | ร่าง/บันทึกเก่า มีคำเตือนและลิงก์สถานะล่าสุด |
| [IMAGE_RAG_DESIGN.md](../../IMAGE_RAG_DESIGN.md) | ร่าง/บันทึกเก่า มีคำเตือนและลิงก์สถานะล่าสุด |
| [README.md](../../README.md) | ตรวจเทียบสถานะปัจจุบันแล้ว |

รายงานนี้เป็นเอกสารเพิ่มหลังตรวจรายการข้างต้น ตรวจลิงก์ไฟล์ภายใน repository อีกครั้งหลังแก้ไข


## UUIDv7 update — 2026-10-03

UUID ที่สร้างใหม่ใช้ v7 ทั้ง database defaults, Python storage keys และ scripts ฐาน local สำรองแล้วและ apply migration 004 เรียบร้อย ID เดิมและ FK ไม่เปลี่ยน API ยังรับ UUID เดิมได้ ดู [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) สำหรับรูปแบบ

ผลทดสอบหลังเปลี่ยน: regression 113 passed / 23 skipped; PostgreSQL integration 19 passed แยกผ่าน Podman (รวม migration repeat-safe, defaults ทั้ง 12 UUID tables, timestamp/version และ uniqueness) ค่า integer ID คงชนิดเดิม


## หลังเพิ่ม Chat Session — 2026-10-04

API ปัจจุบัน 24 operations / 18 paths: 17 implemented / 7 scaffold Frontend Auth/Session/prompt draft ทำแล้ว API Spec/OpenAPI/Project Status/Frontend README/Session module guides อัปเดตตามโค้ด แผนเก่ายังคงติด banner ประวัติไว้ ไม่ใช่ contractปัจจุบัน
