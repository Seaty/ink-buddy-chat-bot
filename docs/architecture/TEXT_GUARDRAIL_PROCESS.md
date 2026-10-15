# Process 7 — Input และ Retrieval Guardrails

## ความสัมพันธ์กับ OpenRouter policy

ใช้ policy ที่ทีมตั้งใน OpenRouter ต่อไป ไม่สร้างหรือแก้ policy ภายนอกในรอบนี้
OpenRouter ควบคุม model/provider/budget/privacy และ security ของคำขอที่ส่งถึงบริการ
Ink Buddy เพิ่มกติกาธุรกิจเฉพาะ catalog ก่อนค้นและหลังค้น

หลักฐานรอบ 13 ตุลาคม 2026:

- Benign embedding: Qwen3 Embedding 4B ใช้งานได้และคืน 1024 มิติ
- Benign chat: Qwen3 14B ตอบข้อความได้
- Prompt-injection ตัวอย่างภาษาอังกฤษ: Chat ได้ HTTP 403 แต่ Embeddings ได้ HTTP 200
- HTTP 403 อาจมาจาก security/model/budget policy; ไม่ได้อ่าน settings ของบัญชีหรือยืนยันชื่อ detector
- ไม่เก็บคำตอบโจมตีที่โมเดลสร้าง; รายงานมีเฉพาะ status และ endpoint

ดู ../report/OPENROUTER_POLICY_CHECK.json จึงไม่ถือว่า policy ฝั่ง Chat ครอบคลุม Embeddings

## Input flow

ตรวจ credential/Origin/feature flag/rate limit เดิม → normalize Unicode/zero-width
→ ตรวจคำสั่งโจมตีที่มีรูปแบบชัดเจน → ตรวจขอบเขตเครื่องเขียน → ตรวจความกำกวมของงบ
→ จึงสร้าง query embedding

กติกา `catalog-scope-v1`:

| กรณี | ผล |
|---|---|
| หมวดเครื่องเขียน/แบรนด์หรือรุ่นที่มีใน catalog | allowed |
| คอมพิวเตอร์ มือถือ สุขภาพที่ไม่มีเครื่องเขียนประกอบ | blocked / OUT_OF_SCOPE |
| เครื่องเขียนผสมคำถามนอกหมวด | needs_clarification / MIXED_SCOPE |
| คำถามกว้างหรือคำถามต่อเนื่องไม่มีบริบท เช่น “มีสีอื่นไหม” | needs_clarification / INSUFFICIENT_CONTEXT |
| งบกำกวมหรือช่วงกลับด้าน | needs_clarification / AMBIGUOUS_BUDGET |
| คำสั่ง ignore previous instructions / reveal system prompt และรูปแบบไทยที่ระบุไว้ | blocked / UNSAFE_QUERY |

คำถามนอกหมวดไม่ผ่านด้วยการส่ง category=notebook มาหลอก filter
รายการ aliases เช่น ไฮไลต์/ไฮไลท์ และ gel pen แปลงเป็น catalog category เดียวกัน
การปฏิเสธหรือถามเพิ่มไม่สร้างข้อความและไม่เรียก OpenRouter embedding

## Retrieval flow

keyword + semantic พร้อม filters เดิม → ตรวจ source_text ของ vector → ตรวจหลักฐานสีและรุ่น
ในข้อมูลสินค้าจริง → ทิ้งรายการที่ไม่ตรง → RRF → คืนผล

หากระบุสีแดงแต่สินค้าไม่มีข้อมูลสีแดง จะไม่แนะนำผ่าน API นี้ รุ่น BL999 ที่ไม่มีข้อมูล
ไม่ถูกแทนด้วย BL77 แม้คะแนนเวกเตอร์ใกล้กัน URL รูปไม่ถูกใช้เป็นหลักฐานรุ่น/สี
หากไม่มีผลที่ผ่านกติกา ให้ no_match / NO_GROUNDED_MATCH ไม่เติมสินค้าใหม่

Response เพิ่ม guardrail_status, guardrail_reason, policy_version, relevance_rejected
index_status=not_checked สำหรับคำขอที่หยุดก่อนตรวจ coverage ของ index
OpenRouter embedding 403 ถูกแปลงเป็น API 403 OPENROUTER_POLICY_REJECTED ไม่ retry/fallback
403 นี้ไม่ถูกกล่าวอ้างว่าเป็น prompt injection เสมอไป ส่วน provider failure อื่นยังเป็น 503

## ชุดประเมินและวิธีรัน

ไฟล์ backend/datasets/evaluation/text_guardrails.json เป็นคำถามสาธารณะคงที่ 21 เคส
ครอบคลุม scope, mixed scope, follow-up ไม่มี context, งบ, aliases, สี, รุ่นไม่พบ,
แบรนด์ไม่พบ, SQL special characters และคำสั่งโจมตีชัดเจน

รันจาก backend:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval_guardrails --live
```

ใช้ฐาน DATABASE_URL และเครดิต OpenRouter สำหรับคำถามที่ผ่าน Input Guardrail เท่านั้น
ผลพร้อม assertions ดู ../report/TEXT_GUARDRAIL_EVAL.json นี่เป็นการวัดพฤติกรรม policy
และ filters ไม่ใช่ Recall@K หรือการรับประกันคุณภาพ RAG ทุกคำถาม

## ข้อจำกัดที่ต้องนำเสนอ

### Verification status — latest confirmed 2026-10-13

- Focused regression: **51 passed** รวม policy/retrieval/embedding/search/scaffold และ PostgreSQL disposable
- Live evaluation หลังแก้ Unicode/identifier boundaries: **21/21 passed** กับ OpenRouter และ catalog local
- เคสคำสั่งโจมตีภาษาอังกฤษและไทยถูกบล็อกก่อน query embedding; เคสนอกหมวด/mixed/บริบทไม่พอผ่านตาม expected decision
- Offline input policy ก่อนหน้า: 11/11 passed; retrieval 10 เคสไม่ได้ทดสอบใน offline mode
- ผล OpenRouter probe ยังคงแยกไว้: benign model calls ผ่าน, attack Chat403 แต่ Embeddings200
- รอบก่อนเคยได้ 20/21 และพบกฎไทยหลุด ปัจจุบันแก้และรันทวนจริงผ่านแล้ว
- ไม่ได้ทดสอบ LLM answer grounding หรือ browser E2E ในรอบนี้ และไม่ใช่หลักฐานป้องกันการโจมตีทุกแบบ
- รายงาน TEXT_GUARDRAIL_EVAL.json อัปเดตเป็นผลล่าสุด 21/21 แล้ว

รันทวนหลังอนุญาตเครือข่าย:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval_guardrails --live
```

ผล offline ล่าสุดอยู่ ../report/TEXT_GUARDRAIL_INPUT_EVAL.json

- Rules เป็น heuristic ที่ตรวจได้เฉพาะรูปแบบที่ระบุไว้ อาจมี false positive/negative
- ไม่ป้องกันทุกภาษา การโจมตีที่เข้ารหัส หรือ indirect injection ใน catalog ครบทุกแบบ
- สีที่ตรวจเป็นชุดภาษาไทย และ identifiers ต้องมีตัวอักษรกับตัวเลข ไม่ใช่ทุกชื่อรุ่น
- ข้อความต่อเนื่องยังถามเพิ่ม เพราะ search endpoint ยังไม่มี conversation context
- cosine threshold เดิม 0.35 ยังไม่ผ่านการ calibration ห้ามเรียก score ว่า confidence
- ยังไม่มี Output Guardrails, LLM answer adapter หรือการเชื่อมหน้าแชต

## สรุปสำหรับอาจารย์

“OpenRouter ช่วยควบคุมการใช้โมเดลและ policy ส่วนแอปตรวจขอบเขตเครื่องเขียนก่อนใช้เครดิต
และตรวจว่าสินค้าที่ค้นได้มีหลักฐานตรงสี/รุ่นหรือไม่ พบว่าคำถามคอมพิวเตอร์ที่เคยคืนเครื่องเขียน
ถูกปฏิเสธก่อนค้นแล้ว เราบันทึกผลผ่าน/ไม่ผ่านด้วยชุดประเมิน ไม่อ้างว่าทุก guardrail สมบูรณ์”
