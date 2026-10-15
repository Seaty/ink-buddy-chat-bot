# Ink Buddy — สถานะปัจจุบัน 2026-10-14

## Chat UI presentation — 2026-10-15 · feature/chat-ui

เพิ่ม loading animation, แสดงคำตอบใหม่ทีละคำภาษาไทย, เลื่อนตามพร้อมพักเมื่อเลื่อนขึ้นอ่าน/ปุ่มกลับล่าสุด, skip และ reduced-motion. ปรับการ์ดสินค้าแยกข้อมูลราคา/สี/variants/source และพับรายละเอียดรอง ใช้สีเดิม เป็น presentation หลัง REST response ไม่ใช่ backend streaming. Frontend unit 29, browser API mocks 24 และ TypeScript ผ่าน ดู [UI process](CHAT_UI_PRESENTATION.md)

## Natural response tone — 2026-10-15

ปรับ Text RAG ให้ตอบตรงคำถามด้วยภาษาสนทนา ลดการทวนรายละเอียดและข้อความภายในระบบ ไม่แปะคำเตือนไม่ใช่ข้อมูลสดทุกคำตอบ ยังคงข้อมูลอ้างอิงและ output guardrails เดิม ทดสอบ intent/adapter/rendering 27 และ PostgreSQL disposable 68 ผ่าน ดู [โทนคำตอบ](RAG_RESPONSE_TONE.md) มีผลกับคำตอบใหม่หลัง restart เท่านั้น

## Conversational RAG UAT — 2026-10-14

แก้บริบทในแชตเดียวกัน, price intent/NULL filtering, SQL price ranking/count, ordinal references, แยกหมึก/ด้าม, same-family color variants และ price source/unit/VAT metadata แล้ว ใช้ Qwen3 14B เลือกหลักฐาน ส่วนระบบจัดอันดับและประกอบราคาเอง ไม่มี retry/fallback

Unit 51 / PostgreSQL disposable 68 / frontend 25 / browser mocks 15 ผ่าน; TypeScript และ Podman frontend build ผ่าน; real container → local API → disposable PostgreSQL → OpenRouter ผ่าน Mobile/Tablet/Desktop; main catalog read-only 3 live questions + fresh-chat policy ผ่าน ดู [Process 7 / วิธีทดสอบ](RAG_CONVERSATION_PROCESS.md)

ยังต้อง human evaluation และยืนยันข้อมูลสี/หน่วย/ภาษีที่ยังเป็น demo; bounded conversation rules ไม่ใช่ความจำระยะยาว ไม่แก้ frozen reports รอบก่อนให้กลายเป็นผลรอบนี้

## Coursework demo prices — 2026-10-14

ผู้ใช้อนุมัติราคาเสนอครบ 18 รายการ: catalog 67 สินค้ามีราคาแล้ว ราคาเดิม 49 ไม่เปลี่ยนจำนวนเงิน ตั้งฐานไม่รวม VAT สำหรับ demo (15 มีหลักฐานต้นทาง อีก 52 เป็นสมมติฐานเพื่อส่งงาน) เก็บข้อจำกัดและแหล่งราคาแยก Backup และ atomic update ผ่าน source_text ไม่เปลี่ยนและ index ไม่ stale ไม่มี provider calls ดู [ผลบันทึก](../report/PRODUCT_PRICE_APPLY_2026-10-14.md) ข้อผิดพลาด UAT เกี่ยวกับบริบท/ranking/สี/หน่วยแก้ใน Process 7 แล้ว โดยยังมีข้อจำกัดข้อมูล ไม่ใช้ผลประเมินก่อนเปลี่ยนราคายืนยัน catalog รอบใหม่นี้

## สถานะ Text RAG ปัจจุบัน

- Guest/User ส่งข้อความจริง → Hybrid PostgreSQL/pgvector retrieval → OpenRouter Qwen3 14B เลือกสินค้า/หลักฐาน → server ประกอบคำตอบ → atomic history พร้อม replay
- Text indexing ใช้ Qwen3 Embedding 4B 1024 มิติ; catalog local 67 สินค้าและ index ไม่ขาด/ไม่ stale จาก audit ล่าสุด
- ปรับข้อความหลักฐานให้กระชับและมีเหตุผลตามเงื่อนไขจริง ไม่สร้างสรรพคุณ/ราคา/สต็อกเพิ่ม ไม่มี retry/fallback อัตโนมัติ
- Live consistency 3 รอบผ่าน 39/39; real Frontend container → local Backend → disposable PostgreSQL → OpenRouter ผ่าน Mobile/Tablet/Desktop
- ทั้ง app มี 32 operations / 26 paths และทุก operation มี policy; OpenAPI snapshot ตรง app ปัจจุบัน
- งานเทคนิคในขอบเขตนี้ครบแล้ว ยังรอ human evaluation และยืนยัน/เติมข้อมูล catalog ที่ขาด ไม่ใช่ผลรับรองคุณภาพคำแนะนำหรือความพร้อม production

ดู [Process 6 / Technical completion](RAG_TECHNICAL_COMPLETION_PROCESS.md) สำหรับผลทดสอบและขอบเขตที่ตรวจจริง รายการย้อนหลังด้านล่างมีสถานะตามวันที่ส่งมอบแต่ละรอบ

## Saved RAG answer audit — 2026-10-13

ตรวจคำตอบ acceptance ที่บันทึกไว้กับ catalog ปัจจุบัน 12/12 ผ่าน ไม่เรียก provider เพิ่ม มีข้อสังเกตเรื่องเหตุผลชื่อ/หมวดซ้ำและคำบรรยายร้านยาว a01/a05/a07; ยังไม่มี human scores เพิ่ม audit script/tests 2 passed ดู [Process 5](RAG_ANSWER_REVIEW_PROCESS.md) ไม่เปลี่ยน adapter/retrieval จากผล review นี้

## Text RAG acceptance / real browser — 2026-10-13

คำถามใหม่ 12 ข้อผ่าน constraints 12/12 โดยไม่ปรับ adapter/policy จากผลชุดนี้; labels ยังเป็น draft/shared catalog ไม่ใช่ independent human benchmark เตรียมคำตอบให้ทีมตรวจคะแนน Browser mobile → real API → disposable PostgreSQL → OpenRouter ผ่าน Guest/User/claim/replay/reload/no-match; focused regression 21 passed ดู [Process 4](RAG_ACCEPTANCE_PROCESS.md) ยังรอคะแนนมนุษย์ก่อนสรุปทุก process

## Text RAG robustness / usage — 2026-10-13

เพิ่ม constraint probes 13 ข้อและเครื่องมือวัดเวลา/token/cost ที่ provider รายงาน แก้สีทอง/เงิน และจำกัด generation ด้วย ID enums + หนึ่งหลักฐานต่อสินค้า Live final 13/13, regression 63 passed และ PostgreSQL disposable 54 passed เก็บรอบที่ไม่ผ่านไว้ด้วย ยังต้องประเมินคุณภาพโดยทีมและชุดอิสระ ดู [Process 3](RAG_ROBUSTNESS_PROCESS.md) ไม่ใช่ผลรับรองความแม่นยำรวม

## Text RAG quality evaluation / tuning — 2026-10-13

เพิ่มชุด relevance ฉบับร่าง 24 ข้อ เครื่องมือวัด Recall/Precision/MRR/nDCG และ query-vector cache ปรับ aliases หมวด/ยี่ห้อ และตรวจสี/วัสดุจาก catalog; คง similarity threshold 0.35 หลังทดลอง development 4 ค่า ผลหลังปรับผ่าน gold ทุกข้อในชุดร่าง และ live Answer Adapter ผ่าน 9/9; ยังต้องให้ทีมตรวจ labels และประเมินชุดอิสระก่อนอ้างความแม่นยำทั่วไป Regression 43 passed และ PostgreSQL disposable 54 passed รายละเอียดเฉพาะ process ดู [RAG Quality Evaluation](RAG_QUALITY_EVALUATION_PROCESS.md)

## สถานะพื้นฐาน 2026-10-05 (ประวัติก่อน Text RAG)

- 27 operations บน 21 paths: 21 implemented และ 6 scaffold
- Auth: User access JWT 15 นาที, refresh session สูงสุด 7 วัน, rotation/reuse revocation และ Logout ทันที
- Guest: อายุ 24 ชั่วโมง, โควตารูป 3 รูปรวมทุกแชต, Origin/ownership guards และ atomic claim
- Chat Session: สร้าง/รายการ/รายละเอียด/เปลี่ยนชื่อ/soft delete และอ่านประวัติ พร้อม cursor pagination และ Guest-before-chat lock
- Frontend: Next.js/TypeScript/Tailwind, Guest/Login/Logout/claim, Chat UI, prompt 3 รายการ และร่างข้อความใน memory
- Mobile แสดงรายการกับแชตทีละหน้า; Tablet ใช้ drawer; Desktop มี sidebar; theme tokens แยกจาก components
- Image upload/search และ admin indexing มี implementation; retrieval เริ่มต้น mock
- PostgreSQL 16 + pgvector ผ่าน docker/compose.yaml, 14 ตาราง, UUIDv7 defaults และ migration 006
- Scripts สร้าง User/Admin, cleanup Guest และ isolated PostgreSQL tests

## งานที่ยังไม่ทำ ณ 2026-10-05 (ประวัติ)

LLM response, semantic text RAG, summary, upload UI, Product list/detail, Profile PATCH, Image detail/delete และ Readiness

ยังไม่มี Email Verification และ cleanup scheduler production Shared limiter และ partial image write ยังมีประเด็น P2 ดู Auth Review

## หลักฐานตรวจ

2026-10-04: backend regression 108 passed / 27 skipped (PostgreSQL 23 รันแยก + model-dependent 4), PostgreSQL integration 23 passed บนฐาน disposable ผ่าน Podman; frontend unit/component 7 passed, browser 6 passed บน Mobile/Tablet/Desktop และ TypeScript/production build ผ่าน

Browser tests ใช้ API mock; DB transaction tests ใช้ PostgreSQL จริงแยกจาก browser Auth/Vision tests ไม่ยืนยันโมเดล AI จริง ส่งข้อความและบันทึกประวัติได้แล้ว

ดู [API Spec](../api/API_SPEC.md), [Frontend setup](../../frontend/README.md), [Database Schema](../../database/DATABASE_SCHEMA.md), [Auth Review](../api/auth/AUTH_REVIEW.md)

## Register / Reset Password — 2026-10-04

ทำแล้ว: Register user active ไม่บังคับ email verification; Forgot/Reset single-use token พร้อม revoke ทุก Login session; หน้า register/forgot/reset; Mailpit local + configurable SMTP; migration 005 และ schema 14 ตาราง Main local DB apply แล้วหลัง backup

ตรวจแล้ว: backend 109 passed; PG 27 passed; frontend 11 passed; browser 9 passed (API mocks); typecheck/build และ Mailpit transport ผ่าน Node 24.19.0 ตรวจแล้ว

ยังเหลือ Email Verification, durable mail outbox/retry, AI/message sending และ upload UI ดูขอบเขต API scaffold ใน API_SPEC.md

## Frontend container — 2026-10-04

เพิ่ม docker/frontend.Containerfile แบบ multi-stage, Next standalone, Node 24.19.0, non-root runtime และ healthcheck พร้อม service frontend ใน Podman Compose Bind loopback port 3000; backend ยังรันบน host API URL ฝังตอน build ดู docker/README.md

## Password policy — 2026-10-05

Register/Reset/local account script: 12–24 ตัว, a–z/A–Z/0–9/ASCII punctuation, ห้าม whitespace ตรวจทั้ง UI และ Backend; Login บัญชีเดิมยังรองรับ ไม่ต้อง migration ตรวจ policy 15 เคส, PG 27, frontend 18, browser 9 ผ่าน

## Message response — 2026-10-05

ทำแล้ว: text send1–4000, UUIDv7 request replay, atomic User/Assistant history, Guest/User ownership recheck after answer, DB keyword/category/brand/THB budget search, template answer with typed catalog references, UI pending/errors/retry/Enter/IME. 27 operations21paths:21implemented6scaffold Migration006appliedlocalafterbackup. Friend AI integration behind adapter pending; no streaming/images/semanticRAG. PG41passed, backend134passed (PG41แยกรัน; AIจริง4เคสไม่รัน), frontend19, browser15 API mocks และ real-browser smokeผ่านแยก

## Text indexing — 2026-10-11

Latest catalog update 2026-10-13: reviewed manifest 67 products, held 1 candidate; imported into local DB after backup. 67 images and 67 Qwen3 Embedding 4B vectors (1024 dimensions). Live indexing: 67 indexed / 0 failed; replay: 0 indexed / 67 unchanged. New uncertain-tax prices and one old ambiguous-unit price are NULL; raw amounts preserved in attributes. See CATALOG_RAG_PROCESS.md and ../report/CATALOG_INDEX_SUMMARY.md. Vision CSV remains 50 products; text catalog manifest is separate.
Implemented Admin catalog validation and OpenRouter Qwen3 Embedding 4B indexing (1024 dimensions), feature flag, batch atomic upsert, advisory lock, changed-product recheck and Postman examples. Text chat remains catalog_template; semantic retrieval/answer guardrails are pending. No migration required.

Verification 2026-10-11: Backend regression 188 passed / 53 skipped. Text indexing suite 10 passed, including 8 disposable PostgreSQL cases (insert/upsert/replay/UUIDv7, batch rollback, partial success, changed/deleted products, lock contention, guards). Existing auth PostgreSQL and real-model suites were not verified by this regression run. Live indexing smoke passed separately. git diff --check passed.

## Hybrid text retrieval — 2026-10-13
Implemented Guest/User POST product-search/by-text with query embedding, cosine retrieval, keyword/RRF fusion, budget/category/brand filters, candidate freshness checks, feature flag and rate limit. Postman and process docs included. Live 3-query smoke: in-domain examples returned products; gaming-computer query returned irrelevant stationery. Domain guardrails and quality calibration are pending; chat remains catalog_template. See TEXT_RETRIEVAL_PROCESS.md.

## Input/Retrieval guardrails — 2026-10-13
Added catalog-scope-v1 for text search: out-of-scope/mixed/ambiguous queries, explicit model/color evidence and known injection forms before embedding. Upstream 403 maps to OPENROUTER_POLICY_REJECTED; OpenRouter guardrail configuration unchanged. Benign Embedding/Chat passed; attack probe Chat403 vs Embeddings200. 21-case evaluation fixture and Postman policy examples added. See TEXT_GUARDRAIL_PROCESS.md for verification and limitations. Message chat/LLM output guardrails remain pending.

Latest guardrail verification 2026-10-13: focused regression 51 passed including disposable PostgreSQL; live 21-case evaluation 21/21 passed after Unicode/identifier fix. Previous automatic approval timeouts resolved. Chat remains template; Output Guardrails and answer adapter pending.

## RAG Chat answer — 2026-10-13
Implemented openrouter_catalog adapter, controlled Product/Evidence selection with Qwen3 14B, Output Guardrails, hybrid retrieval in message pipeline, shared deadline and source labels. Existing message/history APIs add model_name; no migration. Tests: focused64, disposable PostgreSQL54, frontend23+typecheck, API-mock browser15 and real browser→API→disposable PostgreSQL→OpenRouter passed separately. Local RAG activation follows verification; default stays catalog_template. See RAG_CHAT_ANSWER_PROCESS.md.
