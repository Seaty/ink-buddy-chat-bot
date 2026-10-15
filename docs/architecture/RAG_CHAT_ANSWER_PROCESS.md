# Process 8 — RAG Chat, AI Selection และ Output Guardrails

## เป้าหมายและบทบาทของ AI

Guest/User ถามเครื่องเขียน → Hybrid retrieval จาก catalog → Qwen3 14B เลือกสินค้าและหลักฐาน
→ ระบบตรวจ IDs → ประกอบคำตอบไทยจาก snapshot → บันทึกคู่ข้อความ

AI เป็นผู้เลือกและจัดลำดับสินค้า/หลักฐาน ไม่ได้สร้างราคาหรือคำบรรยายอิสระ
การตอบแบบควบคุมนี้ลดความเสี่ยงแต่งข้อมูล แต่ไม่ได้รับประกันว่าสินค้าที่เลือกเหมาะสมที่สุด

## Process A — Snapshot และ Evidence

Application อ่านผลค้นหาสูงสุด 5 สินค้า เก็บ snapshot ภายในที่ไม่ส่งออกใน Text Search API
สร้าง Evidence ID เช่น p0_brand, p0_description, p0_price ผูกกับ Product ID เดียวกัน
ใช้ชื่อ ยี่ห้อ หมวด description และ attributes ที่อนุญาต; ราคาใช้ products.price ที่ตรวจแล้วเท่านั้น
source URL และข้อมูลบัญชีไม่ถูกส่งให้ LLM รูปและ raw prices ที่พักตรวจไม่เป็นหลักฐานราคา

ข้อเท็จจริงเป็นข้อมูลตาม retailer/catalog ไม่ใช่ผลทดสอบคุณสมบัติหรือข้อมูลสต็อกสด
known injection patterns ถูกตัดออกจาก history/fields ที่ส่งให้โมเดล ชื่อสินค้าที่มี patterns ดังกล่าว
ไม่ถูกส่งเป็นตัวเลือก การตรวจนี้เป็น heuristic ไม่ใช่การ sanitize ที่ครอบคลุมทุกแบบ

## Process B — เรียก OpenRouter

System message ประกาศ selection contract; user message เป็น JSON ข้อมูลคำถาม ประวัติ และหลักฐาน
ข้อมูลทุกส่วนถูกถือว่าไม่ใช่คำสั่ง system ไม่เปิด tools ไม่ส่ง token/password/user IDs
ประวัติสูงสุด 10 ข้อความ รวม 8000 ตัวอักษร เก็บข้อความล่าสุดก่อน; ไม่ตัดข้อความกลางประโยค
เมื่อเกินขอบเขตจะหยุดเติมข้อความเก่า ไม่ทำ summary หรือ query rewriting

โมเดลคืนรูปแบบนี้เท่านั้น:

```json
{"recommendations":[{"product_id":"<UUID from candidates>","evidence_ids":["p0_brand"]}]}
```

ใช้ Qwen3 14B, temperature 0, output cap 512, structured response schema
ไม่มี provider retry หรือ model fallback ชื่อโมเดลที่บันทึกใช้ชื่อจริงจาก response

## Process C — Output Guardrails

- JSON/schema ถูกต้องและไม่รับ field เพิ่ม เช่น reason, price, URL
- มีสินค้า 1–5 รายการเมื่อมี candidates
- Product IDs ไม่ซ้ำและอยู่ในผลค้นหา
- Evidence IDs ไม่ซ้ำและเป็นหลักฐานของสินค้านั้นจริง
- finish reason ต้อง stop; empty/malformed/truncated response ถูกปฏิเสธ
- ประกอบข้อความด้วย facts ที่เลือกและเหตุผลแบบกฎจาก snapshot เดิม แล้วตรวจ contract เดิมรวมความยาว <=16000
- ประกอบ product_refs จาก snapshot ฝั่งระบบ ไม่ใช้ URL/ราคา generated จากโมเดล

INVALID_ANSWER ตอบ 502 ไม่บันทึกประวัติ ไม่ fallback
หลักฐาน IDs ใช้ภายใน runtime; DB เก็บข้อความที่ประกอบแล้ว product_refs และ model_name
ไม่มีตารางใหม่หรือ migration

## Process D — Guardrail/No-match และ Failure

blocked/needs_clarification/no_match จาก retrieval คืนคำตอบกำหนดโดยกฎ ไม่เรียก Text LLM
source label catalog_policy ส่วน unknown follow-up เช่น “มีสีอื่นไหม” ยังถามเพิ่ม
คำตอบกฎที่สำเร็จบันทึก User/Assistant ตามปกติ

OpenRouter policy rejection: 403 OPENROUTER_POLICY_REJECTED (ไม่ใช่ Auth401)
Provider failure: 502 ANSWER_FAILED; timeout: 504 ANSWER_TIMEOUT
failure ทุกแบบคงร่างไว้ ไม่มีคู่ข้อความค้างครึ่งหนึ่งและไม่มี automatic mutation retry

## Process E — Deadline และ Transaction

Message API ใช้ deadline 60 วินาทีครอบ retrieval+LLM ใน bounded executor 4 slots
network timeouts จำกัดตามเวลาที่เหลือ และ connection timeout ไม่เกินเวลานั้น
query retrieval มี PostgreSQL statement timeout; ไม่ถือ row locks ขณะ inference
ก่อนบันทึกตรวจ credential/ownership/sequence อีกครั้ง: logout/claim/delete/expiry
ไม่ทำให้คำตอบถูกย้ายข้ามเจ้าของ; concurrent history change ตอบ 409
User/Assistant commit พร้อมกัน และ replay ที่สำเร็จแล้วไม่ค้น/เรียก AI ซ้ำ
Python หยุด thread ที่ทำงานอยู่ไม่ได้; slot คืนเมื่อ worker เสร็จ จึงต้องมี timeout ภายในด้วย

## Process F — UI และ Configuration

ป้าย source: AI, Catalog Template, กฎระบบ; ข้อมูลเก่าที่ไม่มี model_name แสดง Catalog Template
Frontend ใช้ React text rendering และ reference cards เดิม ไม่ render HTML ของ model

```dotenv
CHAT_ADAPTER=openrouter_catalog
TEXT_CHAT_MODEL=qwen/qwen3-14b
TEXT_CHAT_MAX_TOKENS=512
CHAT_TIMEOUT_SECONDS=60
```

ค่า default ใน code/.env.example ยังคง catalog_template; local เปิด RAG หลังทดสอบ
TEXT_SEARCH_ENABLED เปิดเฉพาะ standalone search API ไม่ใช่สวิตช์การส่งข้อความ RAG
AUTH และ OpenRouter key ยังใช้ backend/.env; restart Backend หลังเปลี่ยนค่า

## หลักฐานรอบ 13 ตุลาคม 2026

- Backend unit/focused 64 passed สำหรับ adapter/client/policy/search
- PostgreSQL disposable transaction suite 54 passed รวมทั้ง template และ RAG branch
- Frontend 23 passed และ TypeScript passed
- Browser regression แบบ API mocks 15 passed บน mobile/tablet/desktop
- Live adapter smoke: Qwen3 14B, refs 1, nonempty answer; input247/output72 tokens
- Real browser → HTTP API → disposable PostgreSQL → OpenRouter RAG ผ่านแยกจาก mocks
- ไม่ใช่ผลทดสอบโมเดล Vision และไม่ได้วัดคุณภาพคำตอบบนชุดอิสระครบทุกสถานการณ์

คำสั่ง browser smoke จาก backend: `.venv/Scripts/python.exe -m scripts.test_chat_browser --rag`
สร้าง DB ชื่อ ink_buddy_test_<UUID> และลบทิ้งใน finally; ไม่ seed ลงฐานหลัก

## ลำดับถัดไป

เพิ่มชุดประเมินคุณภาพคำแนะนำ/หลักฐานและ false positives, ปรับ retrieval thresholds จากข้อมูลจริง
แล้วเตรียม PR ของ feature/rag งาน Vision/streaming/summary ยังเป็นงานแยก

## Technical completion update — 2026-10-13

ขั้น quality/tuning/robustness/acceptance และ audit ทำแล้วตาม Process 1–5 ล่าสุด Process 6 ปรับ description เป็น source spans ที่ครบและยาวไม่เกิน 180 ตัว สูงสุด 6 spans ต่อสินค้า; span ที่ยาวเกินถูกละไว้ในชุดหลักฐานคำตอบ ไม่ตัดข้อความครึ่งข้อกล่าวอ้าง ข้อมูลที่ใช้สร้าง embedding ไม่เปลี่ยนและไม่ต้อง reindex

Generation เลือกหนึ่ง Evidence ID ต่อสินค้า Prefer facts ที่เกี่ยวกับคำถาม มากกว่าชื่อ/หมวดซ้ำ ระบบเพิ่มเหตุผลจากยี่ห้อ งบ และคำค้นสี/วัสดุที่มีใน snapshot และแสดงได้ไม่เกิน 3 bullets ต่อสินค้า พร้อมแจ้งราคาขาดและ attribution ตามเดิม ไม่ได้ให้ LLM เขียนข้อความอิสระ

งบไม่พบสินค้า → ขอปรับช่วงงบหรือระบุเงื่อนไขที่ยืดหยุ่น ไม่เสนอเกินงบเอง; คำถามไม่ระบุสินค้า → ขอชื่อ/รุ่นอีกครั้ง ไม่มี query rewriting

ดู [Technical completion process](RAG_TECHNICAL_COMPLETION_PROCESS.md) สำหรับการทดลองใหม่ 39/39 และ container Browser ทั้งสามขนาด รอบผลเก่าด้านบนเป็นหลักฐานตามเวอร์ชันเดิม ยังไม่ใช่คะแนน human evaluation
