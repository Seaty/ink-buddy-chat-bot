# Ink Buddy — สถานะปัจจุบัน 2026-10-04

## ทำงานแล้ว

- 27 operations บน 21 paths: 20 implemented และ 7 scaffold
- Auth: User access JWT 15 นาที, refresh session สูงสุด 7 วัน, rotation/reuse revocation และ Logout ทันที
- Guest: อายุ 24 ชั่วโมง, โควตารูป 3 รูปรวมทุกแชต, Origin/ownership guards และ atomic claim
- Chat Session: สร้าง/รายการ/รายละเอียด/เปลี่ยนชื่อ/soft delete และอ่านประวัติ พร้อม cursor pagination และ Guest-before-chat lock
- Frontend: Next.js/TypeScript/Tailwind, Guest/Login/Logout/claim, Chat UI, prompt 3 รายการ และร่างข้อความใน memory
- Mobile แสดงรายการกับแชตทีละหน้า; Tablet ใช้ drawer; Desktop มี sidebar; theme tokens แยกจาก components
- Image upload/search และ admin indexing มี implementation; retrieval เริ่มต้น mock
- PostgreSQL 16 + pgvector ผ่าน docker/compose.yaml, 14 ตาราง, UUIDv7 defaults และ migration 005
- Scripts สร้าง User/Admin, cleanup Guest และ isolated PostgreSQL tests

## ยังไม่ทำ

การส่งข้อความ/AI response (POST messages ยัง501), text product search/recommendations, citations/summary, upload UI, Product list/detail, Profile PATCH, Image detail/delete และ Readiness

ยังไม่มี Email Verification และ cleanup scheduler production Shared limiter และ partial image write ยังมีประเด็น P2 ดู Auth Review

## หลักฐานตรวจ

2026-10-04: backend regression 108 passed / 27 skipped (PostgreSQL 23 รันแยก + model-dependent 4), PostgreSQL integration 23 passed บนฐาน disposable ผ่าน Podman; frontend unit/component 7 passed, browser 6 passed บน Mobile/Tablet/Desktop และ TypeScript/production build ผ่าน

Browser tests ใช้ API mock; DB transaction tests ใช้ PostgreSQL จริงแยกจาก browser Auth/Vision tests ไม่ยืนยันโมเดล AI จริง ไม่มีการส่งข้อความจาก draft

ดู [API Spec](../api/API_SPEC.md), [Frontend setup](../../frontend/README.md), [Database Schema](../../database/DATABASE_SCHEMA.md), [Auth Review](../api/auth/AUTH_REVIEW.md)

## Register / Reset Password — 2026-10-04

ทำแล้ว: Register user active ไม่บังคับ email verification; Forgot/Reset single-use token พร้อม revoke ทุก Login session; หน้า register/forgot/reset; Mailpit local + configurable SMTP; migration 005 และ schema 14 ตาราง Main local DB apply แล้วหลัง backup

ตรวจแล้ว: backend 109 passed; PG 27 passed; frontend 11 passed; browser 9 passed (API mocks); typecheck/build และ Mailpit transport ผ่าน Node 24.19.0 ตรวจแล้ว

ยังเหลือ Email Verification, durable mail outbox/retry, AI/message sending และ upload UI ดูขอบเขต API scaffold ใน API_SPEC.md

## Frontend container — 2026-10-04

เพิ่ม docker/frontend.Containerfile แบบ multi-stage, Next standalone, Node 24.19.0, non-root runtime และ healthcheck พร้อม service frontend ใน Podman Compose Bind loopback port 3000; backend ยังรันบน host API URL ฝังตอน build ดู docker/README.md

## Password policy — 2026-10-05

Register/Reset/local account script: 12–24 ตัว, a–z/A–Z/0–9/ASCII punctuation, ห้าม whitespace ตรวจทั้ง UI และ Backend; Login บัญชีเดิมยังรองรับ ไม่ต้อง migration ตรวจ policy 15 เคส, PG 27, frontend 18, browser 9 ผ่าน
