# ผลแก้ RAG จาก UAT — 2026-10-14

## สิ่งที่ปรับ

1. ใช้บริบทจากแชตเดียวกันและ product_refs ของคำตอบล่าสุด ก่อน retrieval; ขอประเภทเมื่อแชตใหม่ไม่มีบริบท
2. คำถามราคา/งบเลือกเฉพาะข้อมูลราคา THB ที่ไม่เป็น NULL ก่อนคัด candidates; ranking ใช้ PostgreSQL price/id และจำนวน 1–5
3. แยกหมึก/ด้าม; สีในชื่ออย่างเดียวไม่ถูกยกระดับเป็นสีหมึก; ไม่รับ notes/URL เป็นหลักฐานสี
4. “ตัวที่สอง” อ้างลำดับที่แสดง; รุ่นนี้เมื่อกำกวมถามเพิ่ม; เปลี่ยนประเภทใหม่ไม่สืบสี/brand ของประเภทเดิม
5. สีอื่นตรวจ model family/brand/category แล้วแสดงใน variants ใต้รุ่นเดิม ไม่ปะปนกับรายการหลัก
6. ไม่เปรียบเทียบแพ็ค/หน่วยที่ไม่ชัดกับต่อชิ้นโดยเงียบ ๆ; หน่วยเดิมไม่ยืนยันระบุเป็น catalog listing; ถ้าขอราคาต่อชิ้นต้องมีหน่วยที่ยืนยัน
7. พบไม่ครบจำนวนแจ้งตามจริง; ไม่มีผลราคาใช้ catalog_policy ไม่เรียก Text LLM
8. LLM ให้หลักฐานครบชุดที่ระบบจัดอันดับ; server คุมลำดับ/ราคาจริง ไม่มีคำตอบสมมติ ไม่มี retry/fallback
9. UI แยกแหล่งสินค้า/แหล่งราคา แสดงหน่วย ภาษี demo และสีอื่น พร้อมเว้นระยะป้าย AI/กฎระบบ
10. อัปเดต API Spec/OpenAPI, adapter contract, database JSON snapshot notes, Project Status, frontend guide, Postman และ Process 7 สำหรับนำเสนอ

ไม่มี migration/ตารางใหม่ ไม่เปลี่ยน Image Embedding หรือ Vision ในรอบนี้

## หลักฐานทดสอบ

| กลุ่ม | ผล | ขอบเขต |
|---|---|---|
| Unit | 51 ผ่าน | intent, color relevance, units/family, adapter ID/evidence, search, answer rendering |
| PostgreSQL ใน Podman | 68 ผ่าน | ฐาน disposable: atomic/replay/rollback, concurrent send, claim/delete/logout/expiry, priced-only hybrid search, ascending/descending, shortage, variants/ordinal/pack |
| Frontend | 25 ผ่าน | component/client/account/composer/source/reference; TypeScript ผ่าน |
| Browser mocks | 15 ผ่าน | Mobile/Tablet/Desktop: lifecycle/auth/claim/draft/error/retry/history |
| Browser → container → API → PG → OpenRouter จริง | ผ่าน 3 viewports | ราคา 3 รุ่น, NULL/สีม่วง/แพ็คไม่ปะปน, ordinal, สีแดงตระกูลเดียว, price source, replay, reload nested refs, ไม่ล้นแนวนอน |
| Main catalog + OpenRouter จริง | 3 paid questions + 1 policy ผ่าน | read-only หลังตรวจ 67 products ตรง reviewed public manifest; history ทดสอบใน memory ไม่ส่งบัญชีหรือแชตจริง |
| Real browser auth regression | ผ่าน Mobile | Guest/User/register/login/claim/replay/history/no-match; เป็นข้อมูลสังเคราะห์บน disposable PG |
| Container build | ผ่าน | Next.js standalone/TypeScript ใน Podman image ink-buddy-frontend:rag-uat |
| OpenAPI/diff | ผ่าน | snapshot ตรง runtime, 32 operations/26 paths, ทุก operation มี policy; ไม่พบ secret จาก environment ในไฟล์เปลี่ยนแปลงที่สแกน |

ผล live ของ catalog หลัก: Feel-it หมึกน้ำเงิน 10 บาท → BL77 น้ำเงิน 50 บาท → BL-57 น้ำเงิน 55 บาท; “ตัวที่สองราคาเท่าไร” คืน BL77 50 บาท; ด้ามส้ม/หมึกน้ำเงินคืน Feel-it. หน่วยราคาของ Feel-it ยังเป็น listing ที่ไม่ยืนยันต่อด้ามและฐานภาษีเป็นสมมติฐาน demo ต้องดูหมายเหตุที่ card

ผลเฉพาะรอบนี้: [Browser container](RAG_CONVERSATION_BROWSER.json), [Main catalog live](RAG_CONVERSATION_LIVE.json), [Auth browser](RAG_BROWSER_ACCEPTANCE.json)

## สิ่งที่พบระหว่างทดสอบ

- PostgreSQL ครั้งหนึ่งเกิด Broken pipe/recovery; รอบ disposable integration หลังจากฟื้นตัวผ่าน
- Harness ชุด auth browser เคย timeout proxy 30 วินาที ก่อน server deadline 60; ปรับเป็น 65 วินาทีและไม่ dump request headers แล้วทดลองใหม่ผ่าน เก็บผลที่ล้มเหลวไว้ [รายงานก่อนแก้ harness](RAG_BROWSER_REGRESSION_2026-10-14.json)
- ทดสอบ scaffold เพิ่มเติมรอบหนึ่งค้างในเส้นทางที่มี dependency Vision จึงหยุดเฉพาะ process ทดสอบนั้น; ไม่นับเป็นผ่าน และไม่ใช้แทนชุด RAG/PG ที่ผ่านแล้ว
- ระบบอนุมัติอัตโนมัติปฏิเสธ main-catalog outbound trial ครั้งแรก จึงเพิ่ม fail-closed audit เปรียบเทียบ evidence fields กับ reviewed public manifest ทุกสินค้า ก่อนเรียก provider; audit ผ่านและได้รับอนุมัติให้ทดสอบ
- ลบเฉพาะฐานทดสอบที่ค้างจาก harness และ container ทดสอบพอร์ต 3002; เก็บ main DB และ image ไว้ ไม่มีการ seed/change ราคาหลักในรอบนี้

## วิธีลองด้วยตัวเอง

เปิด [หน้าแชต](http://localhost:3000/chat) แล้วทำตาม [Process 7 / ตาราง 8 เคส](../architecture/RAG_CONVERSATION_PROCESS.md#วิธีทดลองด้วยตัวเอง)

เริ่ม “ปากกาหมึกน้ำเงิน สามรุ่นถูกที่สุด และมีสีอื่นไหม” → “ตัวที่สองราคาเท่าไร” → “รุ่นนี้มีสีแดงไหม” → reload. จากนั้นเปลี่ยนเป็นสมุด และทดลองคำถามสั้นในแชตใหม่เพื่อเช็กว่าไม่ยืมบริบทข้ามแชต

Local backend เปิดที่ http://localhost:8000 และ Swagger http://localhost:8000/docs; frontend local 3000 ใช้ backend นี้. Postman folder Conversational price UAT อยู่ใน [collection](../api/session/rag-chat.postman_collection.json) เริ่ม Guest/create session ก่อน

## ข้อจำกัด

ยังต้อง human evaluation และยืนยันข้อมูลภาษี/หน่วย/สีบางรายการก่อนใช้งานขายจริง; deterministic context rules รองรับรูปแบบที่กำหนด ไม่ใช่การจำบริบทไม่จำกัด ทุกผลราคาคือ snapshot. ไม่แก้คะแนนหรือผล frozen evaluation เดิมให้เป็นผลหลังอัปเดต catalog
