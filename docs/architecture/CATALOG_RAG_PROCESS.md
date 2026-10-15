# การเตรียม Catalog เพื่อทำ Text RAG — 13 ตุลาคม 2026

## จุดประสงค์สำหรับนำเสนอ

Ink Buddy ตอบเรื่องเครื่องเขียนโดยอ้างข้อมูลสินค้าที่ระบบควบคุมได้ ขั้นนี้เตรียมข้อมูลและเวกเตอร์ให้พร้อมค้นหา ยังไม่ได้ให้ LLM ตอบผ่านหน้าแชต

## Process 1 — ตรวจและรวมข้อมูล

แหล่งข้อมูลมี catalog เดิม 50 รายการ, OfficeMate 3 รายการ และ Officework 15 รายการ รวมผู้สมัคร 68 รายการ

ตรวจ SKU, ชื่อ, รุ่น, สี, ขนาด, หน่วยขาย, ราคา, VAT, source URL และความอ่านได้ของไฟล์ภาพ ตรวจชื่อซ้ำอัตโนมัติร่วมกับตรวจรุ่น/สีด้วยคน SKU ต่างร้านไม่ใช่หลักฐานว่าสินค้าต่างกัน

ผล: รับ 67 รายการ และพัก STABILO OfficeMate Y013221 เพราะราคากับหน่วยขายไม่ชัดและรายละเอียดเป็นข้อความการตลาดทั่วไป เก็บภาพไว้ในชุดรอตรวจ ไม่ใช่รายการขายที่ยืนยันแล้ว

- Officework แสดงราคาไม่รวม VAT จึงเก็บราคาต้นทางใน attributes แต่ให้ `products.price=NULL` จนตรวจฐานภาษีและหน่วยขายครบ ไม่คำนวณ VAT โดยสมมติเอง
- สินค้าใหม่ OfficeMate 2 รายการยังไม่ยืนยันฐานภาษี จึงพักราคาเช่นเดียวกัน และใช้ข้อมูลจำเพาะจากชื่อแทน SEO marketing description
- สินค้าเดิม b2s_1091933 มีหมายเหตุราคา 590 บาทอาจเป็นต่อกล่อง จึงพักราคา โดยยังเก็บราคาต้นทาง
- คำกล่าวในรายละเอียดเป็นข้อมูลจากร้าน ยังไม่ได้ทดสอบคุณสมบัติเอง เช่น หมึกกันน้ำ
- สิทธิ์ภาพยังไม่ยืนยัน เก็บสถานะไว้ ไม่กล่าวอ้างว่ามีใบอนุญาตเผยแพร่

ไฟล์ `backend/datasets/reviewed_catalog.json` คือ manifest ที่ใช้รวมข้อมูลสำหรับรอบนี้ พร้อมรายการพักและเหตุผล CSV เดิมของ Vision ไม่ถูกเปลี่ยน เพื่อนยังต้องเลือกว่าจะนำภาพชุดใหม่ไปเพิ่ม Vision อย่างไร

## Process 2 — นำเข้า Database

สำรองฐาน local ด้วย pg_dump ก่อนนำเข้า เก็บ backup ใน `.local/backups` ซึ่งไม่ติด Git

Importer ใช้ transaction เดียว upsert ตาม SKU: สินค้าเดิมคง Product ID; สินค้าใหม่ใช้ UUIDv7 จาก DB เพิ่มข้อมูลรูปใน `product_images` โดยผูกกับ Product ID และกำหนดภาพหลักหนึ่งภาพ ข้อมูลบัญชีและแชตไม่ถูกเปลี่ยน

คำสั่งจาก repository root เพื่อสร้าง manifest:

```powershell
.\backend\.venv\Scripts\python.exe backend/scripts/prepare_text_catalog.py
```

หลังสำรองแล้ว รันจาก backend:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_reviewed_catalog
```

Importer ใช้ DATABASE_URL ใน backend/.env จึงต้องตรวจ target ก่อนรัน การรัน seed เดิมในอนาคตอาจนำราคา CSV ที่พักไว้มาทับ ต้องใช้ reviewed importer สำหรับชุดที่ผ่านการตรวจนี้

## Process 3 — Validate ก่อนใช้เครดิต

Admin เรียก POST `/api/v1/admin/text-index/validate` พร้อม `{}` ตรวจชื่อสินค้าและความยาวข้อความ ข้อมูลที่ขาดเป็น warnings; ชื่อว่างหรือข้อความยาวเกินเป็น errors ไม่เรียก OpenRouter

ผลรอบนี้: ตรวจ 67 รายการ, invalid 0, warnings 68 ส่วนมากเกี่ยวกับ description และราคา NULL รายงาน field/Product ID อยู่ใน `docs/report/CATALOG_INDEX_RESULT.json`

## Process 4 — Text indexing

ชื่อ + SKU + หมวด + ยี่ห้อ + description + attributes ที่อนุญาต → ข้อความต้นทางคงที่ → OpenRouter Qwen3 Embedding 4B → vector 1024 มิติ → PostgreSQL product_embeddings

ตัด URL รูป, fields รูป/credential และ price-related attributes ออกจากข้อความ embedding ราคา/availability จะอ่านจาก DB ตอน retrieval ภายหลัง ไม่ใช้ embeddings เป็นข้อมูลราคาสด

จำกัด batch 16 รายการ; เปรียบเทียบ source_text/model เพื่อข้ามข้อมูลเดิม ไม่มี automatic provider retry และไม่สลับโมเดลเอง Advisory lock ป้องกันงาน indexing พร้อมกัน; ไม่ถือ row lock ระหว่างรอ provider เมื่อ provider กลับมาตรวจสินค้าอีกครั้งแล้วบันทึก batch แบบ atomic

## Process 5 — ตรวจผลและอธิบายข้อจำกัด

ตรวจจำนวนสินค้า/รูป/เวกเตอร์, จำนวนมิติ, failed/remaining และรัน index ซ้ำ ผลซ้ำต้อง indexed 0 และ unchanged เท่ากับข้อมูลที่พร้อม index โดยไม่เรียก provider

ผลจริงของรอบนี้บันทึกแยกใน `docs/report/CATALOG_INDEX_RESULT.json` ไม่ถือว่าการสร้างเวกเตอร์สำเร็จพิสูจน์ว่าค้นหาแม่นยำ ต้องทำ retrieval และชุดประเมินต่อ

## ลำดับถัดไป

Hybrid retrieval → API ทดสอบค้นหา → answer adapter → Guardrails → เชื่อมแชต → ประเมิน retrieval/grounded answers และค่าใช้จ่าย

ตอนนี้หน้าแชตยังเป็น keyword search + catalog_template ไม่ใช่ RAG answer ที่เรียบเรียงด้วย LLM
