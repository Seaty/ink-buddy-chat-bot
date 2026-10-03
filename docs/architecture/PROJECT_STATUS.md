# Ink Buddy — สถานะโปรเจค 2026-10-03

อ้างอิงโค้ด `main` commit `b90df77` หลัง merge งาน `feature/vision` และอัปเดต checkout ในเครื่องแบบ fast-forward

## สิ่งที่เพิ่มจริง

- FastAPI entry point: `backend/app/main.py`
- API `POST /api/v1/images` รับ JPEG/PNG/WEBP, ตรวจชนิดจากเนื้อหา, จำกัดขนาด, เก็บภาพส่วนตัวและข้อมูลใน `image_uploads`
- API `POST /api/v1/product-search/by-image` ตรวจเจ้าของภาพและคืนสินค้าที่ค้นได้จาก catalog
- API `POST /api/v1/admin/image-index` สร้าง/ปรับปรุง image index; ปิดเป็นค่าเริ่มต้น ยังไม่มี admin authentication
- API `GET /api/v1/health` ตรวจสถานะพื้นฐาน
- Vision pipeline สำหรับอ่านภาพ/ข้อความ ระบุความต้องการ ค้นสินค้า แนะนำ เปรียบเทียบ และตอบจากข้อมูล catalog บางเส้นทางคืนคำตอบโดยไม่เรียก VLM เพื่อลดเวลา
- Catalog CSV 50 รายการพร้อมภาพใน `backend/datasets/catalog/`; SQL seed ใน `database/seed/001_catalog_products.sql` และ script สร้าง seed
- Tests ของ catalog, prompts, pipeline, storage, API และ database integrations

## โมเดลและการตั้งค่าที่โค้ดใช้

| ส่วน | ค่าเริ่มต้นในโค้ด | สถานะ |
|---|---|---|
| Vision | `qwen3-vl:latest` ผ่าน Ollama | เปลี่ยนจากแผน Qwen2.5-VL เดิม |
| Image/caption embedding | `Qwen/Qwen3-VL-Embedding-2B`, 2048 มิติ ผ่าน Transformers/PyTorch | แยกจาก BGE-M3 text embedding |
| Retrieval | `IMAGE_RETRIEVER=mock` | เป็น metadata-based stand-in; ต้องเปลี่ยนเป็น `pgvector` หลัง indexing เพื่อทดสอบความแม่นยำจริง |
| Configuration | `backend/.env` | ดูค่าตัวอย่างใน `backend/.env.example`; ไม่ควร commit ค่าจริง |

## จุดเชื่อมฐานข้อมูล

SQL init เดิมสร้าง `products`, `product_images`, `product_embeddings` (1024 มิติ) และ `image_uploads` งาน AI เพิ่ม SQLAlchemy model `product_image_embeddings` (2048 มิติ) ซึ่งยังไม่อยู่ใน `database/ddl/001_init.sql`

ฟังก์ชัน `app.db.database.init_db()` สามารถสร้างตารางจาก models ได้ แต่ไม่ได้ถูกเรียกอัตโนมัติเมื่อเริ่ม FastAPI การเริ่มฐานข้อมูลผ่าน Compose เพียงอย่างเดียวจึงยังไม่สร้าง image embedding table ควรเพิ่ม migration สำหรับตารางใหม่ก่อนเปิด pgvector retrieval

Image API อ่านชื่อ ราคาและ availability จาก `products`; image index เก็บ metadata จาก CSV ด้วย ต้องวางกระบวนการ sync ทั้งสองแหล่งให้สอดคล้องกัน ราคาและสต็อกใน catalog ชุดนี้ควรถือเป็นข้อมูลทดลองจนกว่าทีมจะยืนยันแหล่งจริง

## สิ่งที่ยังไม่เสร็จ

- JWT login/refresh/logout ยังไม่มี; `DEV_AUTH_EMAIL` ใช้จำลองผู้ใช้สำหรับ local development เท่านั้น เมื่อเว้นว่าง protected endpoints จะตอบ 401
- Admin index ไม่มีการตรวจ role; คง `VISION_ADMIN_ENABLED=false` จนมี admin auth
- ยังไม่มี frontend app ที่ทำงาน, chat session/history APIs, text-only product search API และ conversation summary ที่เชื่อมใช้งาน
- `POST /images/{image_id}/analysis` และ `/ocr` มีแล้ว (เก็บผลใน `image_uploads`); OCR กับรูปที่มีข้อความเยอะยังใช้ไม่ได้กับ `qwen3-vl:latest` เพราะ context เต็มก่อนตอบ
- ค่า similarity threshold ใช้แยก `exact`/`similar` แต่ยังไม่ใช่หลักฐานยืนยัน SKU ต้องประเมินกับชุดภาพทดสอบก่อนใช้จริง
- Text embeddings BGE-M3 และ text RAG เดิมยังเป็นแผน; ไม่ควรสรุปว่าระบบเหล่านี้ทำงานครบแล้ว

## การตรวจครั้งนี้

- Tests ที่ไม่ต้องใช้ API/ฐานข้อมูลจริง: **71 passed, 1 skipped**
- ทั้งชุดหยุดระหว่าง collection เพราะ Python ของเครื่องยังไม่มี `fastapi`; ยังไม่ได้ติดตั้ง dependencies เพิ่ม
- ยังไม่ได้ทดสอบ Ollama, embedding model จริง, PostgreSQL integration หรือความแม่นยำของการค้นภาพจริง

## ลำดับงานต่อที่แนะนำ

1. เพิ่ม migration `product_image_embeddings` ให้ตรงกับ model ของทีม
2. เตรียม backend environment, database seed และ model/index แล้วทดสอบ image flow จริง
3. ทำ JWT/admin authorization ก่อนเปิดใช้นอก local development
4. เชื่อม frontend แนบรูป → upload API → search API และแสดงสินค้าจาก response
5. ทดสอบภาพที่ตรงสินค้า ภาพคล้าย ภาพไม่ใช่เครื่องเขียน และภาพที่ไม่มีใน catalog เพื่อปรับ threshold

เอกสารร่างก่อนหน้าให้ใช้เทียบกับสถานะนี้ เพราะ model และวิธี image retrieval เปลี่ยนจากร่างแรกแล้ว ดูแนวคิดรายละเอียดของทีมใน [`IMAGE_RAG_DESIGN.md`](IMAGE_RAG_DESIGN.md)

## API scaffold update (2026-10-03)

เพิ่มโครง routes 7 หมวด รวม 25 operations บน 20 paths: ทำงานจริง 6 (รวม image analysis/OCR จาก `feature/vision`) และ scaffold 19 ตอบ 501 สำหรับ valid requests ดู [API_SPEC.md](../api/API_SPEC.md) และ [BACKEND_STRUCTURE.md](BACKEND_STRUCTURE.md) เป็นสถานะล่าสุด โครง Auth/Guest/Chat ยังไม่มี business logic; backend tests 113 passed, 4 skipped
