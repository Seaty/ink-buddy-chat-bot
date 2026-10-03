# Ink Buddy — สถานะปัจจุบัน2026-10-03

## Authentication / Guest

- 23operationsบน18paths:11implementedและ12scaffoldหลังตรวจสิทธิ์
- UserJWT15นาที,refreshsessionสูงสุด7วัน,rotation/reuse revokeและLogoutมีผลทันที
- Guest24ชั่วโมง,3รูปต่อsession,Origincheck,ownership,atomicquotaและclaim
- ทุกrouteประกาศpolicyและstartupปฏิเสธrouteที่ไม่ประกาศ; Adminindexตรวจrole+flag
- ProfileGETทำแล้ว PATCH/Chat/Product/ImageDetailDelete/Readinessยังscaffold
- มีscriptsสร้างuser/admin,cleanupGuestหลังexpiryอีก24ชั่วโมงและPostgreSQLintegrationtests

## Database / Runtime

Podmanพร้อมและPostgreSQL16+pgvectorรันผ่านdocker/compose.yaml SQLinit13ตาราง ฐานlocalapplymigration004แล้วพร้อมbackup .local/backups สร้างbackend/.envที่ignoredพร้อมsecretสุ่ม ไม่สร้างบัญชี/passwordเริ่มต้น

ฐานใหม่ใช้init ฐานเดิมดูmigration001–004และbackupก่อน ไม่reruninitบนvolumeเดิม Authtablesใช้rawSQLตามDDL ImageembeddingmodelยังSQLAlchemy

## AI

ImageRAGของทีมคงเดิม:Qwen3-VLผ่านOllamaและQwen3-VL-Embedding-2B/vector2048 ค่าเริ่มต้นretrievalmock ต้องindexและตั้งpgvectorก่อนค้นจริง TextBGE-M3/vector1024แยกspace ยังไม่ครบtextchatRAG

Authintegrationtestsใช้fakeVisionpipeline ไม่ได้ยืนยันOllama/embeddingจริงหรือprecisionของexactlabel

## งานถัดไป

FrontendAuthbootstrap/single-flightrefresh,Chatbusinesslogic,ProductAPI,ImageDetailDelete,Readinessimplementation,accountregister/reset,emailverification และproductionsharedlimiter/cleanup scheduler ยังไม่ได้ทำ

ดู [API_SPEC](../api/API_SPEC.md), [Auth setup](../api/auth/README.md), [Token flow](TOKEN_AUTH_FLOW.md), [Database Schema](../../database/DATABASE_SCHEMA.md)

## ผลตรวจหลัง implementation

2026-10-03: regression111passed;22skippedประกอบด้วยPostgreSQLtests18ที่รันแยกและmodel-dependent4 PostgreSQLintegrationรันแยกผ่าน18testsบนPodman dependencycheckผ่าน Localhealth200,profileไม่มีtoken401 ไม่มีการรันโมเดลAIจริงในAuthtests

## ประเด็นจากรีวิวที่ยังเปิดอยู่

ดู [Auth review](../api/auth/AUTH_REVIEW.md): custom app configuration ยังอาจไม่ถูกใช้โดย global limiter และการเขียนไฟล์ภาพล้มเหลวระหว่างทางอาจเหลือไฟล์บางส่วน โค้ดยังไม่ได้แก้สองประเด็นนี้ ผลทดสอบเดิมไม่ครอบคลุมการยืนยันว่าแก้แล้ว


## UUIDv7 (2026-10-03)

ID ใหม่ที่เป็น UUID ใช้ UUIDv7: database defaults เรียก `public.ink_buddy_uuid_v7()` และ Python ใช้ `app.core.identifiers.uuid7()` ชนิด column/API ยังคง UUID เพื่อรองรับ ID เดิม ไม่มีการเปลี่ยน primary/foreign keys ที่มีอยู่ ฐานเดิมต้อง apply `database/migrations/004_uuid_v7.sql` หลัง 003; ฐานใหม่ใช้ init ปัจจุบัน migrations 001–003 เก็บเป็นประวัติเดิม

UUIDv7 มี Unix timestamp ระดับ millisecond และ random bits ตาม [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) ไม่รับประกันลำดับภายใน millisecond หรือเมื่อ clock ย้อนกลับ ไม่ใช้ ID เป็น credential และยังตรวจ ownership ตามเดิม PostgreSQL 16 ใช้ compatibility function เพราะ built-in generator เป็น UUIDv4; ไม่มีการเปลี่ยนคอลัมน์ integer เช่น product_image_embeddings.id

ผล UUIDv7 verification: regression 113 passed / 23 skipped; PostgreSQL integration 19 passed ฐาน local apply 004 แล้วพร้อม backup ก่อนเปลี่ยน
