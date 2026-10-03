# Ink Buddy — สถานะปัจจุบัน2026-10-03

## Authentication / Guest

- 23operationsบน18paths:11implementedและ12scaffoldหลังตรวจสิทธิ์
- UserJWT15นาที,refreshsessionสูงสุด7วัน,rotation/reuse revokeและLogoutมีผลทันที
- Guest24ชั่วโมง,3รูปต่อsession,Origincheck,ownership,atomicquotaและclaim
- ทุกrouteประกาศpolicyและstartupปฏิเสธrouteที่ไม่ประกาศ; Adminindexตรวจrole+flag
- ProfileGETทำแล้ว PATCH/Chat/Product/ImageDetailDelete/Readinessยังscaffold
- มีscriptsสร้างuser/admin,cleanupGuestหลังexpiryอีก24ชั่วโมงและPostgreSQLintegrationtests

## Database / Runtime

Podmanพร้อมและPostgreSQL16+pgvectorรันผ่านdocker/compose.yaml SQLinit13ตาราง ฐานlocalapplymigration003แล้วพร้อมbackup .local/backups สร้างbackend/.envที่ignoredพร้อมsecretสุ่ม ไม่สร้างบัญชี/passwordเริ่มต้น

ฐานใหม่ใช้init ฐานเดิมดูmigration001–003และbackupก่อน ไม่reruninitบนvolumeเดิม Authtablesใช้rawSQLตามDDL ImageembeddingmodelยังSQLAlchemy

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
