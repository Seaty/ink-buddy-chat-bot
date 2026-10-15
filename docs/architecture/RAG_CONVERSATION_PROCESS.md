# Process 7 — Conversational Catalog RAG

อัปเดต 2026-10-14 หลัง UAT เรื่องบริบท สี ราคา และสินค้าอ้างอิง

## จุดประสงค์

ให้ถามต่อในแชตเดิม เช่น “ขอสามรุ่นถูกที่สุด” และ “ตัวที่สองราคาเท่าไร” ได้ โดยใช้ข้อมูล catalog จริง คำถามเกี่ยวกับราคาใช้เฉพาะราคาที่มีค่าและสกุล THB ไม่มีการเติมราคา/สต็อกจากโมเดล

## การทำงาน

```text
ตรวจ credential / ownership / request replay
        ↓
อ่าน 10 ข้อความล่าสุด + product_refs ของคำตอบล่าสุดในแชตนี้
        ↓
ตรวจ scope ของคำถามใหม่ ก่อนรับบริบทเดิม
        ↓
Resolve ประเภท / ยี่ห้อ / สี / งบ / จำนวน / ลำดับสินค้า
        ↓
┌ คำถามทั่วไป → Hybrid keyword + vector retrieval
│ คำถามราคา → กรอง NULL / สกุลเงิน ก่อนคัด candidates
│ จัดอันดับราคา / อ้างรายการเดิม → SQL filter + price,id ordering
└ กำกวม / ไม่พบ / ถูกบล็อก → catalog_policy ไม่เรียก Text LLM
        ↓
ตรวจสีหมึก/สีด้าม + หน่วยราคา + หา variant ตระกูลเดียวกัน
        ↓
Qwen3 14B เลือก Evidence IDs ของสินค้าเท่านั้น
        ↓
ตรวจ output → ระบบประกอบคำตอบ / ราคา / แหล่งอ้างอิง
        ↓
ตรวจสิทธิ์และ history ซ้ำ → บันทึก User/Assistant atomic
```

## กติกาบริบท

- ใช้เฉพาะประวัติที่ MessageService อ่านจาก session ที่ตรวจ ownership แล้ว ไม่มี account data/token ส่งเข้าโมเดล
- “จากที่แนะนำเมื่อกี้” ใช้ Product IDs ตามลำดับที่แสดงในคำตอบล่าสุด
- คำถามสั้นขอจัดอันดับโดยไม่ระบุประเภท ใช้ประเภท/สีเดิมและจัดอันดับเฉพาะชุดล่าสุด พร้อมบอกขอบเขต
- “ทั้งหมดใน catalog” เปลี่ยนไปค้นทั้ง catalog ภายใต้ประเภท/เงื่อนไขที่ตีความได้
- “ตัวที่สอง” อ้างตัวที่สองของ product_refs ที่แสดงจริง ไม่ใช่ retrieval rank
- “รุ่นนี้/รุ่นนั้น” เมื่อมีหลายสินค้า ต้องระบุลำดับหรือชื่อให้ชัด ไม่เลือกแทนผู้ใช้
- ระบุประเภทใหม่ เช่น “เปลี่ยนเป็นสมุด” ไม่สืบสี/ยี่ห้อของปากกามาเอง
- ไม่มีประวัติหรือไม่มีสินค้าปัจจุบันที่อ้างถึง → ขอรายละเอียดเพิ่ม
- ใช้ deterministic intent rules ยังไม่ใช่ query rewriting แบบ LLM ที่เข้าใจทุกประโยค; บริบทสูงสุด 10 ข้อความ ไม่มี summary/long-term memory

## ราคาและจำนวน

- ขอครั้งละ 1–5 รายการ; พบไม่ครบแจ้งจำนวนจริง; จำนวนเกินขอบเขตขอให้ปรับ
- กรอง price IS NOT NULL และ currency=THB ก่อน keyword/semantic candidate limit
- ถูกที่สุด/แพงที่สุดเรียงใน PostgreSQL ด้วย price และ id เป็นตัวตัดสินเมื่อราคาเท่ากัน ไม่ใช้ similarity score เป็นราคาหรือความมั่นใจ
- LLM ต้องให้หลักฐานครบทุกสินค้าที่ระบบจัดอันดับ ถ้าตอบไม่ครบตอบ 502 INVALID_ANSWER ไม่ซ่อมหรือ retry อัตโนมัติ
- ค่าเริ่มต้นเปรียบเทียบราคาต่อรายการ catalog ที่ไม่ใช่แพ็ค ตัดแพ็ค/หน่วยกำกวมออกและแจ้ง ไม่หารราคาด้วยจำนวนชิ้นเอง
- หน่วยเดิมที่ยังไม่ยืนยันแสดง “รายการ catalog (หน่วยขายไม่ได้ยืนยัน)” ไม่กล่าวว่าเป็นราคาต่อด้าม; ถ้าถาม “ต่อด้าม/ต่อชิ้น” ใช้เฉพาะหน่วยเดี่ยวที่ยืนยัน
- ถ้าถาม “ต่อแพ็ค” ใช้แพ็คที่จำนวนชิ้นเท่ากัน; ต่างขนาดหรือไม่รู้จำนวนต้องขอหน่วยเพิ่ม
- ราคา 67 รายการเป็น coursework snapshot ที่ผู้ใช้อนุมัติ ไม่ใช่ราคาสด; 15 รายการยืนยันไม่รวม VAT จากต้นทาง อีก 52 ฐานภาษีเป็นสมมติฐานสำหรับส่งงาน

## สีและ variants

- แยกหมึกและด้ามจาก attributes ที่ระบุหรือข้อความชื่อ/รายละเอียดที่ระบุหมึก/ด้ามชัดเจน
- “สีน้ำเงิน” ในชื่อเพียงอย่างเดียวไม่ยืนยันสีหมึก/ด้าม; ใช้กับคำถามสีกว้างได้ แต่ไม่ผ่านเงื่อนไข “หมึกน้ำเงิน” หากไม่มีหลักฐานหมึก
- ไม่ใช้ source URL หรือ catalog notes เป็นหลักฐานสี
- สีอื่นอยู่หลังคำตอบหลักและใน variants ของสินค้าตัวนั้น ไม่เพิ่มจำนวนรุ่นใน ranking หลัก
- ต้องตรง brand/category และ model_family หรือรหัสรุ่นที่ตรวจขอบเขตคำได้ ไม่ถือว่าสินค้าประเภทเดียวกันเป็น variant
- ถ้าไม่มีหลักฐานสีอื่นแจ้งว่ายืนยันไม่ได้ ไม่อ้างว่าโรงงานไม่มีสีอื่น

## สัญญา API และฐานข้อมูล

POST /api/v1/chat-sessions/{id}/messages ใช้ request เดิม content/client_request_id; response product_refs เพิ่ม optional price_source_ref, price_basis, price_verification, selling_unit, pack_quantity, ink_color, body_color และ variants สูงสุด 5

variants ใช้ ProductFactReference ไม่มีการซ้อน variants หลายชั้น ราคา/URL มาจาก snapshot DB; UI แยกแหล่งสินค้าและแหล่งราคา แสดงเป็น React text และอนุญาตลิงก์ HTTP/HTTPS เท่านั้น

เก็บข้อมูลเพิ่มใน chat_messages.product_refs JSONB เดิม ไม่เพิ่ม migration/ตาราง และประวัติเก่ามี defaults ที่อ่านต่อได้ ไม่เขียนคำตอบเก่าย้อนหลัง

Provider/schema/timeout failure ไม่บันทึกทั้งคู่; replay สำเร็จไม่ค้น/เรียก AI ใหม่; Guest-before-chat lock, claim/logout/delete races และ concurrency 409 คงเดิม

การอ่าน catalog เพื่อ resolve/variants จำกัด 5,000 รายการ; มากกว่านี้ตอบ 503 CATALOG_QUERY_LIMIT ต้องปรับเป็น repository queries สำหรับ catalog ขนาดใหญ่ก่อน production

## ผลทดสอบรอบนี้

- Unit ของ intent/adapter/relevance/search/rendering: 51 ผ่าน
- PostgreSQL disposable ผ่าน Podman: 68 ผ่าน รวม auth/ownership/quota/claim/concurrent history และ Hybrid retrieval ที่ใช้ embedding จำลอง
- Frontend component: 25 ผ่าน; TypeScript ผ่าน; browser API mocks: 15 ผ่าน
- OpenRouter จริง + synthetic PostgreSQL + หน้าเว็บ: Mobile/Tablet/Desktop ผ่านราคา 3 รายการ, ordinal, variants, replay และ reload ดู [ผล browser](../report/RAG_CONVERSATION_BROWSER.json)
- Main catalog อ่านอย่างเดียว: 3 คำถามเรียก Qwen3 14B จริง + fresh-chat clarification 1 เคส ผ่าน หลัง audit ทั้ง 67 รายการตรง reviewed public catalog ดู [ผล live](../report/RAG_CONVERSATION_LIVE.json)
- Frontend standalone Podman image build ผ่าน; ผลทดสอบไม่ใช่ human evaluation หรือการรับรองความพร้อม production

ระหว่างทดสอบ PostgreSQL เคย reconnect/recovery จาก Broken pipe แล้วรอบถัดมาผ่าน; browser regression อีกชุดพบ proxy timeout 30 วินาที จึงปรับ harness เป็น 65 วินาทีตาม server deadline 60 และไม่ dump request headers ไม่ได้เพิ่ม retry ให้แอป

## วิธีทดลองด้วยตัวเอง

เปิด http://localhost:3000/chat แล้วใช้แชตใหม่:

| ขั้น | คำถาม | ตรวจอะไร |
|---|---|---|
| 1 | ปากกาหมึกน้ำเงิน สามรุ่นถูกที่สุด และมีสีอื่นไหม | สูงสุด 3 รุ่น ราคาเรียงขึ้น หมึกน้ำเงิน; สีอื่นแยกใต้รุ่น |
| 2 | ตัวที่สองราคาเท่าไร | ต้องตรงตัวที่สองจากขั้น 1 |
| 3 | รุ่นนี้มีสีแดงไหม | ตระกูลเดียวกับขั้น 2 หรือแจ้งไม่มีข้อมูลยืนยัน |
| 4 | ขอสามรุ่นแพงที่สุดทั้งหมดใน catalog | ใช้ประเภทจากบริบท แต่ขยายชุดค้นและเรียงราคาลง |
| 5 | เปลี่ยนเป็นสมุด ไม่เกิน 50 บาท | ไม่สืบสี/ยี่ห้อปากกา |
| 6 | แชตใหม่: ขอสามรุ่นถูกที่สุด | ขอประเภทสินค้า ไม่ยืมประวัติจากแชตอื่น |
| 7 | ปากกาหมึกน้ำเงิน ด้ามสีส้ม | สีหมึกและด้ามต้องตรงคนละเงื่อนไข |
| 8 | ปากกาหมึกน้ำเงิน ไม่เกิน 1 บาท | แจ้งไม่พบ ไม่เสนอเกินงบหรือเติมราคา |

reload ต้องยังเห็นราคา/สีอื่น/แหล่งราคาในประวัติ ลิงก์ราคาอาจต่างจากแหล่งสินค้าตามข้อมูลที่อนุมัติ ราคาไม่ยืนยันสต็อกสด

## รันทดสอบซ้ำ

จาก backend:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_auth_postgres
.\.venv\Scripts\python.exe -m scripts.test_chat_browser --conversation --viewports all
.\.venv\Scripts\python.exe -m scripts.smoke_conversation_rag --audit-only
# สองคำสั่ง live/browser RAG ใช้เครดิต OpenRouter จริง; smoke ต่อไปเป็น read-only
.\.venv\Scripts\python.exe -m scripts.smoke_conversation_rag
```

จาก frontend:

```powershell
pnpm test -- --maxWorkers=1
pnpm typecheck
pnpm test:e2e
```

หาก pnpm shim พยายามดาวน์โหลดทั้งที่ offline ใช้ Node เรียก local vitest/TypeScript/Playwright CLI ได้ ไม่ต้องติดตั้ง dependencies ใหม่เพื่อทดสอบ

ยังต้องให้ทีมประเมินความเหมาะสมของคำแนะนำด้วยชุดอิสระ และยืนยันข้อมูลสี/หน่วย/ฐานภาษีจากต้นทางก่อนใช้ขายจริง ไม่ปรับ frozen evaluation รอบก่อนให้ดูเหมือนวัดหลังแก้ครั้งนี้
