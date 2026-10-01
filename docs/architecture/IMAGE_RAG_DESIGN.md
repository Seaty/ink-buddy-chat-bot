# Image RAG Design (Ink Buddy)

เอกสารนี้อธิบายส่วน **ค้นสินค้าจากรูป** ของ Ink Buddy: ผู้ใช้แนบรูปเครื่องเขียน → ระบบหาสินค้าใน catalog ที่ตรงหรือใกล้เคียง ส่วนแชตและการค้นด้วยข้อความเป็นของทีม text — เอกสารนี้ระบุเฉพาะจุดเชื่อมต่อ

- Business source of truth: [`../../BUSINESS_REQUIREMENTS.md`](../../BUSINESS_REQUIREMENTS.md)
- API contract: [`../api/IMAGE_SEARCH_API.md`](../api/IMAGE_SEARCH_API.md)
- Schema ของทีม: [`../../database/DATABASE_SCHEMA.md`](../../database/DATABASE_SCHEMA.md)

> สถานะ: implement แล้วใน `backend/app/` (branch `feature/vision`) ตัวเลขทั้งหมดวัดบน RTX 3050 Laptop 6 GB เมื่อ 28 ก.ย.–1 ต.ค. 2569

---

# 0. สถานะ และเรื่องที่ยังต้องตัดสินใจ

| ส่วน | สถานะ |
|---|---|
| `POST /api/v1/images`, `POST /api/v1/product-search/by-image` | ✅ ใช้งานได้ |
| Fast path (image embedding) | ✅ 0.3–1 วินาที |
| Full path (vision model) | ⚠️ ทำงานได้แต่ช้ามาก (`qwen3-vl:latest` > 2 นาทีต่อ call) |
| exact เฉพาะเมื่อยืนยันรุ่นได้ | ✅ (§1.5) |
| Seed `products` / `product_images` จาก CSV | ✅ `database/seed/` |
| ตาราง vector ของส่วนรูป | ⚠️ ชั่วคราว: สร้างด้วย `create_all` และผูกด้วย SKU (§2.5) |
| Auth | ⚠️ `DEV_AUTH_EMAIL` ชั่วคราวจนกว่าจะมี JWT |
| รูป + ข้อความในแชต | ⏳ รอ endpoint แชตของทีม text (§1.6) |
| `/images/{id}/analysis`, `/images/{id}/ocr` | ✅ เก็บผลไว้ใน `image_uploads` (เรียกซ้ำไม่เรียกโมเดลอีก) · ⚠️ OCR กับรูปที่มีข้อความเยอะใช้ไม่ได้กับ `qwen3-vl:latest` (§5) |
| Rate limit | ⏳ ยังไม่ทำ |

**ต้องให้ทีมตัดสิน**

1. **วิธีค้นจากรูป** — Draft v2 วาง MVP เป็น "vision model อธิบายรูป → ค้น catalog ด้วยข้อความ (BGE-M3)" แต่ส่วนนี้ใช้ image embedding เพิ่ม (Qwen3-VL-Embedding-2B) เพราะวัดได้ว่าเร็วกว่ามาก (§4) ถ้าตกลงใช้ ต้องเพิ่มโมเดลตัวที่สองและ migration ของตาราง (§2.5) ข้อเสนอคือใช้ทั้งสองแบบ: image embedding เป็น fast path, vision model → `product_embeddings` ของทีม text เป็น full path
2. **Vision model** — ทุกเอกสารเขียน `Qwen2.5-VL:7b` แต่ระบบใช้ `qwen3-vl:latest` ซึ่งเป็นรุ่น thinking และช้ามาก ควรเลือกรุ่น instruct รุ่นเดียวทั้งทีม
3. **Dataset** — รูปเป็น © B2S/OfficeMate educational use only จะเก็บใน git และย้ายไป `datasets/` ที่ root ตาม `docs/README.md` หรือไม่
4. **ข้อมูลสต็อก** — catalog ไม่มี จึงเป็น `NULL` และบอทตอบว่าไม่มีข้อมูล (ไม่แต่งตาม `AGENTS.md`)

---

# 1. สถาปัตยกรรม

## 1.1 ภาพรวม

```text
POST /images ──► ตรวจไฟล์จากเนื้อหา ─► re-encode (ลบ EXIF) ─► private storage + image_uploads
                                                                    │ image_id
POST /product-search/by-image ◄──────────────────────────────────────┘
      │
      ├─ FAST PATH: embed รูปเต็ม ─► pgvector ─► retrieval level
      │      ├─ similar → ตอบ (0.3–1 วินาที)
      │      └─ none    → ไป full path
      │
      └─ FULL PATH: vision model วิเคราะห์รูป (intent, หมวด, ยี่ห้อ, รุ่น, bbox)
             ─► crop ─► embed รูป + คำอธิบาย ─► hybrid search ─► ยืนยันรุ่น (§1.5)
             ─► exact / similar / none  (+ บันทึก analysis ลง image_uploads)

matches ─► JOIN products (id, ราคา, availability, source_ref) ─► response
```

ข้อมูลสินค้าใน response มาจากตาราง `products` เสมอ ไม่ได้มาจาก vector index หรือจากโมเดล

## 1.2 ไฟล์และหน้าที่

```text
backend/app/
├── main.py                              FastAPI + error handlers + /api/v1 router
├── api/
│   ├── deps.py                          get_current_user_id (DEV_AUTH_EMAIL ชั่วคราว)
│   └── v1/  router.py · images.py (upload, analysis, ocr) · product_search.py · admin.py
├── core/  config.py (.env) · errors.py (ApiError + error format)
├── db/    database.py (engine, session, init_db)
├── models/product.py                    ProductImageEmbedding (ตาราง vector ชั่วคราว)
├── schemas/vision.py                    request/response ของ API
├── repositories/
│   ├── image_repository.py              image_uploads (SQL ตรง; schema เป็นของ DDL)
│   └── product_repository.py            vector search + catalog_by_sku (products)
├── services/
│   ├── vision_service.py                upload_image · analyze_image · ocr_image · search_by_image · index_catalog
│   └── image_storage.py                 private storage, ลบ metadata, กัน path traversal
└── ai/
    ├── llm/        ollama_client.py · qwen_vision.py
    ├── embeddings/ embedding_service.py · qwen3_vl_embedding.py
    ├── rag/        indexing_service.py (โหลด/ตรวจ CSV) · chunker.py · retriever.py
    ├── vision/     image_analyzer.py · vision_pipeline.py · ocr_service.py
    └── prompts/    vision_prompt.py
database/seed/  generate_catalog_seed.py · 001_catalog_products.sql
```

ส่วน `ai/` ไม่รู้จัก settings, DB หรือ HTTP: `services/` เป็นจุดที่ประกอบทุกอย่างเข้าด้วยกัน ส่วน retriever คุยกับ pgvector ผ่าน Protocol `ImageVectorIndex` ไม่ import `repositories/` ตรง

## 1.3 Full path

1. **วิเคราะห์รูป** (`image_analyzer` → `qwen_vision.analyze`) ได้ JSON ตาม schema `ImageAnalysis`: `is_stationery`, `intent`, `category_guess`, `brand_text`, `model_text`, `colors`, `attributes`, `description`, `bbox` (0–1000), `constraints`
2. ไม่ใช่เครื่องเขียน → ตอบข้อความปฏิเสธสำเร็จรูป ไม่ค้นต่อ
3. **Crop** ตาม bbox ถ้ากรอบใหญ่อย่างน้อย 10% ของรูป เพื่อลดพื้นหลังให้ใกล้รูป catalog ที่เป็นพื้นขาว
4. **Hybrid search** (`ImageRetriever`):
   `score = 0.6·sim(รูป) + 0.4·sim(คำอธิบาย ↔ caption) + 0.05 ถ้าหมวดตรง + 0.10 ถ้ายี่ห้อตรง` น้ำหนักตั้งได้ผ่าน `.env` และต้องจูนจากชุดทดสอบ (§4)
5. **ยืนยันรุ่น** (§1.5) → `exact` / `similar` / `none`
6. ถ้าผู้เรียกต้องการคำตอบข้อความ (แชตในอนาคต) จะเลือก prompt ตาม intent แล้วให้ vision model ตอบ ส่วน `by-image` ข้ามขั้นนี้ (`with_answer=False`)

## 1.4 Fast path

ใช้เมื่อข้อความว่างหรือตรงกฎ "หาของคล้าย" / "ราคา" / "สต็อก" — embed รูปเต็มแล้วค้นทันที ไม่เรียก vision model

- ไม่มีการ crop และไม่ได้อ่านรุ่นจากรูป จึงได้ **มากสุด `similar`**
- ถ้าไม่พบสินค้าใกล้พอ (`none`) จะส่งต่อไป full path ให้ vision model crop และตรวจว่าเป็นเครื่องเขียนหรือไม่
- ปิดได้ด้วย `IMAGE_FAST_PATH=false`

## 1.5 การตัดสิน exact / similar / none

Spec (Draft v2 §Vision Workflow): *exact เฉพาะเมื่อยืนยัน SKU/รุ่นได้ มิฉะนั้นเป็น similar* — คะแนนความคล้ายอย่างเดียวจึงไม่เคยทำให้เป็น exact

| ระดับ | เงื่อนไข (`verify_exact`, `retrieval_level` ใน `vision_pipeline.py`) |
|---|---|
| `exact` | vision model อ่าน `model_text` ได้ (≥ 3 ตัวอักษรหลังตัดช่องว่าง/เครื่องหมาย) **และ** รหัสนั้นอยู่ในชื่อสินค้า **เพียงตัวเดียว** ในผลค้น **และ** `brand_text` ที่อ่านได้ไม่ขัดกับยี่ห้อ **และ** คะแนน ≥ `IMAGE_TAU_SIMILAR` — สินค้าที่ยืนยันได้ถูกเลื่อนขึ้นอันดับแรก |
| `similar` | คะแนนอันดับแรก ≥ `IMAGE_TAU_SIMILAR` (0.55) แต่ยืนยันรุ่นไม่ได้ |
| `none` | คะแนนต่ำกว่าเกณฑ์ → `matches` ว่าง และเสนอ `suggestions` "หมายถึงสิ่งนี้ไหม" (สินค้าคะแนน ≥ `IMAGE_TAU_SUGGEST` ไม่เกิน 3 รายการ) ด้วย template โดยไม่เรียก LLM รอบสอง; รูปที่ไม่ใช่เครื่องเขียนไม่ได้รับข้อเสนอ |

ตัวอย่างจาก catalog จริง: `1448`, `UMN-S-38`, `BL667`, `H-22` ระบุสินค้าได้ตัวเดียว ส่วน `Precision` (กรรไกร 2 รุ่น) และ `500` (เทปใส 3 ขนาด) ใช้ร่วมกันหลายสินค้า จึงไม่นับเป็นการยืนยัน

ผลต่อการตอบราคา: ถ้าไม่ใช่ `exact` บอทจะถามว่าหมายถึงสินค้าตัวไหน (แสดงตัวเลือก 3 รายการ) แทนการบอกราคาทันที

## 1.6 จุดเชื่อมกับส่วน text / แชต

Spec แนบรูปในแชตผ่าน `POST /chat-sessions/{id}/messages` ด้วย `{"content", "image_id"}` ซึ่งเป็นงานของทีม text ข้อตกลงที่เสนอ:

- แชตเรียก `VisionService` → `VisionPipeline.run(image, message)` ซึ่งรองรับ intent ครบแล้ว (หาของคล้าย, แนะนำ, เปรียบเทียบ, ราคา/สต็อก, ทั่วไป)
- บันทึกสินค้าที่พบใน `chat_messages.product_refs` เป็น `products.id` พร้อม snapshot
- คำถามราคา/สต็อกตอบจากข้อมูลใน `products` ด้วยโค้ด (`price_stock_answer`) ไม่ให้ LLM สร้างตัวเลข
- ไฟล์ที่ใช้ร่วมกัน (`core/config.py`, `main.py`, `api/v1/router.py`, `api/deps.py`, `ai/llm/ollama_client.py`) เพิ่มส่วนของตัวเองได้ แต่ไม่แก้ส่วนของอีกฝ่าย

## 1.7 Config

ค่าทั้งหมดอยู่ใน `backend/.env` และอ่านที่ `app/core/config.py` เท่านั้น (ดูรายการเต็มใน `backend/.env.example`) ค่าที่เกี่ยวกับส่วนนี้:

| Key | ค่าเริ่มต้น | หมายเหตุ |
|---|---|---|
| `VISION_MODEL` | `qwen3-vl:latest` | ควรเปลี่ยนเป็นรุ่น instruct |
| `VISION_NUM_PREDICT` / `VISION_NUM_CTX` | `6144` / ว่าง (= 4096 ของ Ollama) | context ใหญ่ขึ้นใช้ VRAM มากขึ้น |
| `IMAGE_EMBED_MODEL` / `IMAGE_EMBED_DEVICE` | `Qwen/Qwen3-VL-Embedding-2B` / ว่าง (= cuda ถ้ามี) | `cpu`, `cuda`, `gpu` |
| `IMAGE_RETRIEVER` | `mock` | `pgvector` หลัง index แล้ว |
| `IMAGE_TAU_SIMILAR` | `0.55` | เกณฑ์ similar/none |
| `IMAGE_TAU_SUGGEST` / `IMAGE_SUGGEST_COUNT` | `0.47` / `3` | ไม่พบสินค้า → เสนอ "หมายถึงสิ่งนี้ไหม" (รูปสุ่ม/สีพื้นได้ 0.39–0.46; รูปสินค้าบางส่วนได้ 0.47–0.53) |
| `IMAGE_ESCALATE_ON_NO_MATCH` | `true` | fast path ไม่พบ → ใช้ vision model ก่อน (`false` = เสนอทันที ไม่ตรวจว่าเป็นเครื่องเขียน) |
| `IMAGE_W_IMAGE` / `IMAGE_W_CAPTION` | `0.6` / `0.4` | น้ำหนัก hybrid search |
| `IMAGE_FAST_PATH` | `true` | |
| `IMAGE_MAX_BYTES` / `IMAGE_MAX_PIXELS` | 5 MB / 40 ล้าน | |
| `IMAGE_STORAGE_DIR` | `uploads` | private, อยู่ใน `.gitignore` |
| `VISION_ADMIN_ENABLED` | `false` | เปิด `POST /admin/image-index` |
| `DEV_AUTH_EMAIL` | ว่าง | ชั่วคราว: ว่าง = ทุก endpoint ตอบ 401 |

แก้ `.env` แล้วต้อง restart server (`--reload` ไม่ดูไฟล์นี้)

---

# 2. ข้อมูล

## 2.1 Catalog (`backend/datasets/catalog/metadata.csv`)

50 สินค้า, 20 หมวด (หมวดละ 2–3), รูปละ 1 สินค้า (400–1200 px, พื้นขาว) ตรวจด้วย `python -m app.ai.rag.indexing_service`

| คอลัมน์ | บังคับ | หมายเหตุ |
|---|---|---|
| `filename`, `category`, `group`, `sku`, `brand`, `name`, `price_thb`, `price_date`, `source_url`, `image_url`, `license`, `notes` | ✓ (มีแล้ว) | `category` ต้องตรงชื่อโฟลเดอร์; `sku` ไม่ซ้ำ |
| `unit`, `pack_qty`, `brand_norm`, `color`, `size`, `visual_caption`, `is_active` | ไม่บังคับ | เพิ่มได้ภายหลัง; ถ้าไม่มีระบบทำงานต่อโดยแสดงว่าไม่มีข้อมูล |
| `stock_qty` | ไม่บังคับ | **ห้ามใส่ค่าสมมติ** (`AGENTS.md`) — ใส่เฉพาะเมื่อมีแหล่งข้อมูลจริง |

ตัวตรวจจะรายงาน error (ไฟล์หาย, SKU ซ้ำ, ราคา/วันที่ผิด, หมวดไม่ตรงโฟลเดอร์) และ warning (หมายเหตุใน `notes`, ชื่อยี่ห้อหลายแบบ เช่น `Montmarte` → `Mont Marte`)

## 2.2 Seed เข้า `products` / `product_images`

`database/seed/generate_catalog_seed.py` สร้าง `001_catalog_products.sql` (upsert, รันซ้ำได้):

| `products` | มาจาก |
|---|---|
| `sku`, `name`, `category`, `brand` | CSV (`brand` ใช้ชื่อที่ normalize แล้ว) |
| `price`, `currency` | `price_thb`, `THB` |
| `source_ref` | `source_url` |
| `attributes` | `category_th`, `group`, `price_date`, `source_image_url`, `license`, `catalog_note` และ `unit` / `pack_qty` / `color` / `size` เมื่อมี |
| `description`, `availability` | **NULL** — catalog ไม่มีข้อมูลที่ตรวจสอบได้ |

`product_images.storage_key` = `catalog/<category>/<file>` (เทียบกับ `backend/datasets/`), `is_primary = true`

```powershell
backend\.venv\Scripts\python database\seed\generate_catalog_seed.py
Get-Content database\seed\001_catalog_products.sql | docker exec -i docker-postgres-1 psql -v ON_ERROR_STOP=1 -U ink_buddy -d ink_buddy
```

## 2.3 Chunking

| chunk | เนื้อหา | ใช้ทำ |
|---|---|---|
| `image` | รูปสินค้า (RGB, เติมขอบขาวเป็นจัตุรัส, ด้านยาว ≤ 1024) | ค้นรูป ↔ รูป |
| `caption` | ชื่อ + หมวด (ไทย/อังกฤษ) + กลุ่ม + ยี่ห้อ (+ สี/ขนาด/คำอธิบายภาพเมื่อมี) | ค้นคำอธิบาย ↔ ข้อความ |
| `image_aug` | (ยังไม่ใช้) รูปจำลองมุมถ่ายจริง | เปิดเมื่อวัดผลแล้วช่วย |

**ไม่ใส่ราคา สต็อก หรือวันที่ราคาใน chunk** เพราะค่าเหล่านี้เปลี่ยนบ่อยและต้องดึงสดจาก `products` แต่ละ chunk มี `content_hash` ทำให้ index ซ้ำจะ embed เฉพาะส่วนที่เปลี่ยน

## 2.4 Embedding: Qwen3-VL-Embedding-2B

- โหลดผ่าน Hugging Face (`transformers` + `torch` 2.8 cu128) **ไม่ใช่ Ollama** เพราะ `MedAIBase/Qwen3-VL-Embedding:2b` ใน Ollama ไม่มีความสามารถ embedding/vision (`/api/embed` ตอบ 501)
- 2048 มิติ, L2-normalized, รูปและข้อความอยู่ใน vector space เดียวกัน
- instruction ใช้เฉพาะฝั่ง query (`IMAGE_QUERY_INSTRUCTION`)
- VRAM 3.96 GiB (fp16) ใช้ร่วมกับ `qwen3-vl` (~5.7 GiB) บน GPU 6 GB ไม่ได้: ถ้าใส่ทั้งคู่ Ollama จะย้าย VLM ไป CPU บางส่วน

## 2.5 ตาราง vector ของส่วนรูป

ตอนนี้ (ชั่วคราว): `product_image_embeddings` สร้างด้วย `init_db()` / `create_all` ในฐานข้อมูลของทีม

| Column | Type | หมายเหตุ |
|---|---|---|
| `sku`, `chunk_type`, `variant` | unique ร่วมกัน | ผูกกับสินค้าด้วย SKU |
| `content`, `content_hash` | text | path รูปหรือ caption |
| `embedding` | `vector(2048)` | ไม่มี vector index: ~100 แถวค้นแบบเต็มได้ในไม่กี่ ms และ HNSW บน `vector` รองรับไม่เกิน 2000 มิติ |
| `embed_model` | varchar | เปลี่ยนโมเดล → index ใหม่ทั้งหมด |
| `metadata` | jsonb | สำเนาข้อมูลสินค้าสำหรับ caption/กรอง |

ใช้ `product_embeddings` ของทีมไม่ได้ เพราะเป็น `vector(1024)` และบังคับ 1 แถวต่อสินค้าต่อโมเดล (ส่วนนี้มี 2 chunk ต่อสินค้า)

**ข้อเสนอ (รอทีมตัดสิน §0 ข้อ 1):** `database/migrations/002_product_image_embeddings.sql` — อ้าง `products.id` (UUID, `ON DELETE CASCADE`) แทน SKU, ตัด `metadata` ที่ซ้ำกับ `products`, ใช้ `halfvec(2048)` ถ้าต้องมี HNSW index

---

# 3. Intent และ Prompt

ทั้งหมดอยู่ใน `backend/app/ai/prompts/vision_prompt.py`

## 3.1 Intent

| Intent | ตัวอย่าง | ค้น catalog | ตอบด้วย |
|---|---|---|---|
| `find_similar` | (รูปอย่างเดียว), "มีแบบนี้ไหม" | ✓ | template / vision model |
| `recommend` | "แบบที่ถูกกว่านี้", "สีอื่น" | ✓ + กรอง | vision model |
| `compare` | "เทียบกับของในร้าน" | ✓ | vision model + รูปลูกค้า และรูปสินค้า 2 รายการ |
| `price_stock` | "ราคาเท่าไหร่", "มีของไหม" | ✓ | **โค้ด** จากข้อมูลจริง |
| `general` | "อันนี้คืออะไร" | top-1 | vision model |
| `out_of_scope` | รูปที่ไม่ใช่เครื่องเขียน | ✗ | ข้อความสำเร็จรูป |

แยก intent ตามลำดับ: ข้อความว่าง → `find_similar` · กฎคำสำคัญ (`INTENT_KEYWORDS`: เปรียบเทียบ → แนะนำ → ราคา/สต็อก → ทั่วไป → หาของคล้าย) · ไม่ตรงกฎ → ใช้ intent จาก vision model · ไม่ใช่เครื่องเขียน → `out_of_scope`

กฎที่ระวังเป็นพิเศษ: ไม่ใช้ "เหลือ" เดี่ยวๆ (ชนกับ "สีเหลือง") และตรวจ "เทียบ" / "ถูกกว่า" ก่อน "ราคา"

## 3.2 Prompt

| Prompt | ใช้เมื่อ |
|---|---|
| `IMAGE_ANALYSIS_PROMPT` + `IMAGE_ANALYSIS_SCHEMA` | full path call #1: บังคับ JSON ผ่าน `format=` ของ Ollama, อ่านเฉพาะข้อความที่เห็นจริง ห้ามเดายี่ห้อ |
| `CAPTION_PROMPT` | สร้าง `visual_caption` ตอน index (ยังไม่ได้รัน) |
| `VISION_SYSTEM_PROMPT` + `ANSWER_INSTRUCTIONS[intent]` | call #2 ตอนต้องการคำตอบข้อความ |
| `find_similar_answer`, `price_stock_answer` | template ใน Python ไม่เรียก LLM |

## 3.3 หลักการตอบ (ตาม Business Requirements)

- ราคา สต็อก และ SKU มาจากข้อมูลใน catalog เท่านั้น ถ้าไม่มีให้บอกว่าไม่มีข้อมูล
- บอกหน่วยและวันที่ของราคาทุกครั้ง แสดงที่มา (`source_ref`)
- `similar` ห้ามพูดว่าเป็นรุ่นเดียวกัน
- ข้อความบนรูปและข้อความผู้ใช้เป็นข้อมูล ไม่ใช่คำสั่ง (`sanitize_user_text` กันการปิด tag ใน prompt)

---

# 4. ผลวัด และแผนประเมินผล

ชุดทดสอบปัจจุบันเป็น **รูป catalog ที่ดัดแปลงเอง** (crop, หมุน, พื้นหลัง, เบลอ) ซึ่งง่ายกว่ารูปถ่ายจริง

| วัด | ผล |
|---|---|
| ค้นรูป ↔ รูป (50 สินค้า) | Recall@1 = 100%, Recall@3 = 100% |
| คะแนนสินค้าที่ถูก / สินค้าผิดที่ใกล้ที่สุด | เฉลี่ย 0.83 (ต่ำสุด 0.63) / เฉลี่ย 0.54 (สูงสุด 0.89) → ช่วงซ้อนกัน เป็นเหตุผลที่ไม่ใช้คะแนนตัดสิน exact |
| ชื่อสินค้าภาษาไทย → รูป | Recall@1 68%, Recall@3 88% |
| Fast path ผ่าน API | 0.3–1 วินาที |
| Embed 1 รูป GPU / CPU | 0.52 / 11.2 วินาที |
| Index catalog (100 chunk, GPU) | 14–26 วินาที |
| `qwen3-vl:latest` ต่อ call | 115–160 วินาที (คิดก่อนตอบ 3,700–5,200 ตัวอักษร) |

**ต้องทำต่อ:** ชุดทดสอบรูปถ่ายจริง ≥ 20 รูป + รูปของที่ไม่มีในร้าน ≥ 15 รูป พร้อม label SKU เพื่อวัด Recall@1/3, ความแม่นของ exact และอัตรา "บอกว่ามี ทั้งที่ไม่มี" แล้วจูน `IMAGE_TAU_SIMILAR` และน้ำหนัก

---

# 5. ปัญหาที่เจอ

| ปัญหา | วิธีแก้ |
|---|---|
| Ollama embed รูปด้วย Qwen3-VL-Embedding ไม่ได้ | โหลดผ่าน Hugging Face |
| `qwen3-vl:latest` ไม่สน `think: false` และช้ามาก | fast path; ตั้ง `num_predict` สูงพอไม่ให้ JSON ถูกตัด; ควรเปลี่ยนเป็นรุ่น instruct |
| `localhost` บน Windows ลอง IPv6 ก่อน (รอ 5 วินาทีทุก connection) | ใช้ `127.0.0.1` |
| `curl` ใน Git Bash ส่งภาษาไทยเพี้ยน | ทดสอบด้วย Postman / Swagger |
| `from __future__ import annotations` ทำให้ transformers 5 โหลดโมเดลไม่ได้ | ตั้ง `config_class` ตรงๆ |
| DB test เขียนลงตารางจริงเมื่อใช้แค่ `search_path` | `schema_translate_map` และ transaction ที่ rollback |
| Container ฐานข้อมูลหยุดหลังเครื่อง sleep แล้ว test ค้าง | `docker compose -f docker/compose.yaml up -d` ก่อนทดสอบ |
| OCR รูปที่มีข้อความเยอะ (เช่น แพ็คเทป Scotch) ได้คำตอบว่าง: `qwen3-vl:latest` คิดยาวจน context 4096 เต็มก่อนตอบ (296 วินาที, `done_reason=length`) · ตั้ง `num_ctx` 16384 แล้วโมเดลโตเป็น 8.1 GB รันบน CPU 57% เกิน 30 นาทีไม่ได้คำตอบ · รูปที่ไม่มีข้อความตอบถูก (`[]`, 10 วินาที) | ยังไม่แก้: เปลี่ยนเป็น VLM รุ่น instruct หรือใช้ EasyOCR / Tesseract ผ่าน `OcrService` (ออกแบบให้เปลี่ยน engine ได้) |
