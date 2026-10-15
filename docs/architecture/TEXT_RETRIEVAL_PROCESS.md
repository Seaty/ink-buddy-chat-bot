# Process 6 — Hybrid retrieval สำหรับนำเสนออาจารย์

## เป้าหมาย

ค้นสินค้าใน catalog ด้วยทั้งคำที่ตรงกันและความหมาย ก่อนนำผลไปสร้างคำตอบ LLM
ขั้นนี้มี API ทดลองค้นหาและ Postman แต่ยังไม่เชื่อมเข้าการส่งข้อความ

## Flow

Guest/User credential → ตรวจ request/งบ → อ่าน keyword candidates จาก products
→ จบ transaction → query embedding ผ่าน OpenRouter → cosine search ใน pgvector
→ กรองหมวด/ยี่ห้อ/งบและตรวจ source_text ว่ายังตรงสินค้า → RRF fusion → คืนข้อมูล DB และ source_ref

keyword ใช้น้ำหนักเดิมของชื่อ หมวด ยี่ห้อ รายละเอียด เพิ่ม candidate pool เป็น 20
โดยไม่เปลี่ยนค่า default 5 ของแชตเดิม semantic ใช้โมเดล/มิติเดียวกับ catalog index
รับ candidate สูงสุด 100 ตรวจ freshness และ similarity แล้วเลือก semantic 20 รายการ

รวมสองลำดับด้วย Reciprocal Rank Fusion: score = ผลรวม 1/(60+rank) ของแต่ละช่องทาง
สินค้าที่พบทั้งสองช่องทางมีคะแนนเพิ่ม ผูกผลด้วย Product ID จึงไม่ซ้ำ
หาก score เท่ากันใช้ Product ID เป็นลำดับคงที่ คืนสูงสุด 10 (default 5)

ราคาที่ไม่ทราบหรือพัก VAT/หน่วยขายไม่เข้า budget search ไม่ตีความเป็นราคา 0
query embedding ใช้เครดิตจริง ไม่อ่าน CSV ทุกคำขอ ไม่สร้างหรือบันทึกข้อความสนทนา

## Failure และความปลอดภัย

API ต้องมี credential; Guest ใช้ cookie+Origin, User ใช้ Bearer; rate limit 20/minute
feature flag ปิดเริ่มต้น Provider ล้มเหลวตอบ 503 โดยไม่เผย response body/key
ถ้าไม่มี index แจ้ง missing พร้อม keyword results ถ้า vector เก่าไม่ใช้ช่อง semantic
ไม่มี row locks ระหว่างรอ API ทุก SQL values ใช้ parameters

## หลักฐานจริงและสิ่งที่ยังไม่ผ่าน

ลอง OpenRouter กับ catalog 67 สินค้า:

- “ปากกาเจล ไม่เกิน 100 บาท”: พบ Uni UMN-S-38 ราคา catalog 42 บาท 1 รายการ
- “สมุดสำหรับจดเลกเชอร์” + notebook: คืน 5 สินค้า รวมสมุดชุดใหม่ที่ price=NULL
- “คอมพิวเตอร์เล่นเกม”: ยังคืนเครื่องเขียน 5 รายการที่ไม่เกี่ยวข้อง

เคสสุดท้ายแสดงว่า embeddings เป็นการวัดความใกล้ ไม่ใช่การตรวจขอบเขตคำถาม
threshold 0.35 เป็นค่าเริ่มต้น ไม่ควรปรับจากตัวอย่างเพียงสามคำถาม ต้องมี eval set
และ domain/grounding guardrails ก่อนให้ LLM แนะนำผ่านหน้าแชต

ผล response จริงอยู่ ../report/TEXT_RETRIEVAL_SMOKE.json ไม่มี credentials
API/Postman guide อยู่ ../api/product/TEXT_SEARCH_API.md

Tests รอบนี้: 39 passed (focused regression) รวม disposable PostgreSQL สำหรับ retrieval/indexing,
Guest cookie + Origin, invalid Bearer ไม่ fallback, feature flag, request validation และ rate limit.
Live smoke 3 query เป็น service → OpenRouter → local PostgreSQL แยกจาก HTTP tests ที่ใช้ fake embedding.
ไม่ได้รัน backend ทั้งชุดหรือ browser E2E ใหม่ใน milestone นี้

## ขั้นต่อไป

ชุดประเมิน retrieval → scope/grounding guardrails → OpenRouter answer adapter
→ เชื่อม message API โดยรักษา atomic history และ request replay
