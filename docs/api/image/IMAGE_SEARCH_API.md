# Image Search API

API สำหรับแนบรูปเครื่องเขียนและค้นสินค้าใน catalog จากรูป ตาม [`../../architecture/INK_BUDDY_DESIGN_DRAFT.md`](../../architecture/INK_BUDDY_DESIGN_DRAFT.md) §3 · เอกสารหลักร่วมของทีมคือ [`../API_SPEC.md`](../API_SPEC.md); ไฟล์นี้ลงรายละเอียดพฤติกรรมของ image search

> สถานะ: implement แล้วใน `backend/app/api/v1/` (branch `feature/vision`) · ข้อมูลสินค้าและคะแนนในตัวอย่างมาจากการเรียกจริงกับ catalog seed; ค่า `timings_s` เป็นค่าประมาณ
> ยังไม่มี: JWT จริง, rate limit, การแนบรูปในแชต (`/chat-sessions/{id}/messages`)

## ภาพรวม

ค้นจากรูปมี 2 ขั้น:

```text
1. POST /api/v1/images                       (multipart: file)       → { id }
2. POST /api/v1/product-search/by-image      (JSON: image_id, limit) → { matches[] }
```

แยกสองขั้นเพื่อให้รูปเดียวกันถูกใช้ซ้ำได้ เช่น ค้นใหม่ หรือแนบในข้อความแชตภายหลัง

## Conventions

| เรื่อง | ค่า |
|---|---|
| Base path | `/api/v1` |
| รูปแบบข้อมูล | JSON `snake_case`; ID เป็น UUID |
| Authentication | `Authorization: Bearer <access_token>` ทุก endpoint ยกเว้น `/health` |
| Error | `{"error": {"code": "...", "message": "...", "details": {}}}` ทุก status ที่ไม่ใช่ 2xx |

**Auth ชั่วคราว (dev เท่านั้น):** ระหว่างที่ยังไม่มี JWT ถ้า backend ตั้ง `DEV_AUTH_EMAIL` ไว้ ทุก request จะทำงานในนามผู้ใช้นั้นโดยไม่ต้องส่ง token ถ้าไม่ได้ตั้ง ทุก endpoint ตอบ `401 UNAUTHORIZED`

### Error codes

| Status | `code` | เกิดเมื่อ |
|---|---|---|
| 401 | `UNAUTHORIZED` | ไม่มีการยืนยันตัวตน |
| 404 | `NOT_FOUND` | path ไม่มีอยู่ |
| 404 | `IMAGE_NOT_FOUND` | รูปไม่มีอยู่ ถูกลบ หรือเป็นของผู้ใช้อื่น (ไม่บอกว่าเป็นกรณีไหน) |
| 413 | `IMAGE_TOO_LARGE` | ไฟล์เกิน `IMAGE_MAX_BYTES` (5 MB) หรือเกิน `IMAGE_MAX_PIXELS` (40 ล้าน pixel) |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | ไม่ใช่รูป หรือไม่ใช่ JPEG / PNG / WEBP (ตรวจจากเนื้อไฟล์ ไม่ใช่นามสกุล) |
| 422 | `VALIDATION_ERROR` | request ผิดรูปแบบ; `details.errors[]` บอก field ที่ผิด |
| 422 | `EMPTY_FILE` / `IMAGE_TOO_SMALL` | ไฟล์ว่าง / ด้านสั้นของรูปน้อยกว่า 32 px |
| 422 | `IMAGE_NOT_READY` | รูปยังไม่อยู่ในสถานะ `ready` |
| 503 | `VISION_UNAVAILABLE` | vision model ไม่ตอบหรือเกินเวลา `OLLAMA_TIMEOUT_S` |
| 500 | `INTERNAL_ERROR` | ข้อผิดพลาดภายใน (ไม่เปิดเผยรายละเอียด) |

ตัวอย่าง:

```json
{"error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": "file is not a readable image", "details": {}}}
```

```json
{"error": {"code": "VALIDATION_ERROR", "message": "request validation failed",
           "details": {"errors": [{"loc": ["body", "limit"], "msg": "Input should be greater than or equal to 1", "type": "greater_than_equal"}]}}}
```

---

## POST `/api/v1/images` — แนบรูป

| | |
|---|---|
| Content-Type | `multipart/form-data` |
| Field | `file` (บังคับ) — JPEG / PNG / WEBP, ≤ 5 MB, ≤ 40 ล้าน pixel, ด้านสั้น ≥ 32 px |
| Success | `201 Created` |
| Errors | 401, 413, 415, 422 |

ระบบบันทึกรูปใน private storage (ไม่มี URL สาธารณะ) โดย re-encode และลบ metadata ทั้งหมด เช่น ตำแหน่ง GPS และข้อมูลกล้อง การแนบรูปยังไม่ได้ระบุว่าเป็นสินค้าอะไร

**Response**

```json
{"id": "104f44d0-fbb7-4b1e-96e5-1fd568e111aa", "status": "ready"}
```

**ตัวอย่าง**

```bash
curl -X POST http://127.0.0.1:8001/api/v1/images -F "file=@scissors.jpg"
```

---

## POST `/api/v1/images/{image_id}/analysis` — อธิบายรูป

ไม่มี body (หรือส่ง `{}`) · Errors: 401, 404 `IMAGE_NOT_FOUND`, 422 (UUID ผิดรูปแบบ / `IMAGE_NOT_READY`), 503 `VISION_UNAVAILABLE`

ผลเป็น **การตีความรูป ไม่ใช่การยืนยันว่าเป็นสินค้าใด** ครั้งแรกเรียก vision model (ช้า) แล้วเก็บผลไว้ใน `image_uploads.analysis` ครั้งต่อไปตอบจากที่เก็บไว้ (`cached: true`) ถ้ารูปเคยผ่าน full path ของ `by-image` มาแล้ว ก็ใช้ผลนั้นได้ทันที

```json
{
  "image_id": "104f44d0-fbb7-4b1e-96e5-1fd568e111aa",
  "description": "ปากกาเจลด้ามหกเหลี่ยมสีน้ำเงิน",
  "attributes": {
    "is_stationery": true,
    "category": "gel_pen",
    "brand_text": "Pentel",
    "model_text": "BL667",
    "colors": ["น้ำเงิน"],
    "features": ["0.7 มม."]
  },
  "cached": false
}
```

| Field | ความหมาย |
|---|---|
| `attributes.category` | หมวดที่ใกล้ที่สุดใน catalog หรือ `other` |
| `attributes.brand_text` / `model_text` | ข้อความที่อ่านได้จริงบนสินค้าเท่านั้น (ว่างถ้าอ่านไม่ได้; ไม่เดา) |
| `cached` | `true` = ผลที่เก็บไว้จากครั้งก่อน |

## POST `/api/v1/images/{image_id}/ocr` — อ่านข้อความบนสินค้า

ไม่มี body · Errors เหมือน `/analysis`

ถอดข้อความที่พิมพ์อยู่บนสินค้า เช่น ยี่ห้อ, รหัสรุ่น, ขนาดหัว และตัวเลขบาร์โค้ด เรียงตามลำดับการอ่าน **ผลเป็นค่าประมาณ ต้องตรวจซ้ำก่อนอ้างรุ่นหรือ SKU** และเก็บไว้ใน `image_uploads.ocr_text` เช่นเดียวกับ `/analysis` ถ้ารูปไม่มีข้อความจะได้ `text: ""` และไม่เรียกโมเดลซ้ำ

```json
{
  "image_id": "104f44d0-fbb7-4b1e-96e5-1fd568e111aa",
  "text": "Pentel\nEnerGel\nBL667",
  "segments": [{"text": "Pentel"}, {"text": "EnerGel"}, {"text": "BL667"}],
  "cached": false
}
```

ตัวอย่าง response ของ `/analysis` และ `/ocr` เป็นรูปแบบข้อมูล ไม่ใช่ผลจริงจากรูปใดรูปหนึ่ง

> ⚠️ ข้อจำกัดปัจจุบัน: กับ `qwen3-vl:latest` บน GPU 6 GB, `/ocr` ของรูปที่มีข้อความเยอะจะตอบ `503 VISION_UNAVAILABLE` เพราะโมเดลคิดจนเต็ม context ก่อนตอบ ส่วนรูปที่ไม่มีข้อความตอบ `text: ""` ได้ถูกต้อง จะใช้งานได้จริงเมื่อเปลี่ยนเป็น VLM รุ่น instruct หรือ OCR engine อื่น

---

## POST `/api/v1/product-search/by-image` — ค้นสินค้าจากรูป

**Request**

```json
{"image_id": "104f44d0-fbb7-4b1e-96e5-1fd568e111aa", "limit": 3}
```

| Field | Type | บังคับ | รายละเอียด |
|---|---|---|---|
| `image_id` | UUID | ✓ | id จาก `POST /images` ต้องเป็นรูปของผู้ใช้คนเดียวกัน |
| `limit` | int | | 1–10, ค่าเริ่มต้น 5 |

**Response `200`**

```json
{
  "image_id": "104f44d0-fbb7-4b1e-96e5-1fd568e111aa",
  "description": null,
  "match_level": "similar",
  "matches": [
    {
      "product_id": "9a37fc17-7bee-4522-949e-d2a6849191f0",
      "sku": "b2s_2071790",
      "name": "SCOTCH กรรไกร รุ่น Precision 1448 สีแดง-เทา 8 นิ้ว",
      "category": "scissors",
      "brand": "Scotch",
      "price": 235.0,
      "currency": "THB",
      "availability": null,
      "source_ref": "https://www.b2s.co.th/product/scotch-กรรไกร-รุ่น-precision-1448-สีแดง-เทา-8-นิ้ว-p.2071790",
      "image_url": "https://pim-cdn0.ofm.co.th/products/large/2071790.jpg",
      "match_type": "similar",
      "score": 0.927
    },
    {
      "product_id": "84b5a5c9-c589-4c46-8a0a-df7713747427",
      "sku": "b2s_2072020",
      "name": "กรรไกร 8 นิ้ว สก๊อตช์ Precision Ultra Edge 1468TUNS",
      "category": "scissors",
      "brand": "Scotch",
      "price": 295.0,
      "currency": "THB",
      "availability": null,
      "source_ref": "https://www.b2s.co.th/product/กรรไกร-8-นิ้ว-สก๊อตช์-precision-ultra-edge-1468tuns-p.2072020",
      "image_url": "https://pim-cdn0.ofm.co.th/products/large/2072020.jpg",
      "match_type": "similar",
      "score": 0.818
    }
  ],
  "path": "fast",
  "timings_s": {"retrieve_fast": 0.31, "total": 0.33}
}
```

| Field | ความหมาย |
|---|---|
| `match_level` | `exact` = ยืนยันรุ่นจากรูปได้ · `similar` = มีสินค้าใกล้เคียง · `none` = ไม่พบสินค้าที่ใกล้พอ |
| `matches[].match_type` | `exact` ได้เฉพาะรายการแรกเมื่อ `match_level` เป็น `exact`; รายการอื่นเป็น `similar` เสมอ |
| `suggestions[]` | มีเฉพาะเมื่อ `match_level` เป็น `none`: สินค้าที่ใกล้ที่สุดไม่เกิน 3 รายการ (`match_type: "suggestion"`) สำหรับถามลูกค้าว่า "หมายถึงสิ่งนี้ไหม" — ว่างถ้าไม่มีสินค้าใดใกล้พอ |
| `message` | ข้อความสำหรับลูกค้าเมื่อไม่พบสินค้า (`match_level: none`) เป็น `null` ในกรณีอื่น |
| `matches[].score` | คะแนนความคล้าย 0–1 ใช้เรียงลำดับ ไม่ใช่ความน่าจะเป็น |
| `price`, `availability`, `source_ref` | มาจากตาราง `products` เท่านั้น เป็น `null` เมื่อ catalog ไม่มีข้อมูล ระบบไม่เดา |
| `description` | สิ่งที่ vision model อ่านได้จากรูป เป็น `null` เมื่อค้นด้วย fast path |
| `path` | `fast` = ค้นด้วย image embedding อย่างเดียว · `full` = ใช้ vision model วิเคราะห์รูป |
| `timings_s` | เวลาแต่ละขั้น ใช้ debug |

**Errors:** 401, 404 `IMAGE_NOT_FOUND`, 422, 503 `VISION_UNAVAILABLE`

### เมื่อไม่พบสินค้า: "หมายถึงสิ่งนี้ไหม"

ตาม Business Requirements "หากไม่พบสินค้าที่ตรงกัน ให้บอกตามจริงและเสนอทางเลือกที่ใกล้เคียงเมื่อมีข้อมูลรองรับ" เมื่อ `match_level` เป็น `none`, `matches` จะว่าง และระบบเสนอสินค้าที่ใกล้ที่สุดใน `suggestions`:

```json
{
  "image_id": "…",
  "description": null,
  "match_level": "none",
  "matches": [],
  "suggestions": [
    {"product_id": "…", "sku": "b2s_3090256", "name": "SCOTCH เทปใส รุ่น 500 แกน 1 นิ้ว ขนาด 1\" x 36 หลา แพ็ค 7 ม้วน",
     "price": 266.0, "currency": "THB", "availability": null, "match_type": "suggestion", "score": 0.525, "…": "…"},
    {"product_id": "…", "sku": "b2s_3101210", "match_type": "suggestion", "score": 0.523, "…": "…"},
    {"product_id": "…", "sku": "b2s_3101160", "match_type": "suggestion", "score": 0.473, "…": "…"}
  ],
  "message": "ไม่พบสินค้าที่ตรงกับในรูปค่ะ หมายถึงสินค้าเหล่านี้หรือเปล่าคะ?
1. SCOTCH เทปใส รุ่น 500 …",
  "path": "fast"
}
```

- เสนอเฉพาะสินค้าที่คะแนนอย่างน้อย `IMAGE_TAU_SUGGEST` (0.47) และไม่เกิน `IMAGE_SUGGEST_COUNT` (3) รายการ ถ้าไม่มีสินค้าใกล้พอ `suggestions` จะว่าง และ `message` เป็น "ขออภัยค่ะ ไม่พบสินค้าที่คล้ายกับในรูปในร้าน"
- 0.47 มาจากการวัด: รูปสุ่มหรือรูปสีพื้นได้ 0.39–0.46 ส่วนรูปสินค้าจริงที่ถ่ายบางส่วนได้ 0.47–0.53 (3 ตัวอย่าง ต้องจูนกับรูปถ่ายจริง)
- รูปที่ vision model ระบุว่าไม่ใช่เครื่องเขียน: ไม่เสนออะไร
- ค่าเริ่มต้น `IMAGE_ESCALATE_ON_NO_MATCH=true`: ถ้า fast path ไม่พบ ระบบให้ vision model crop และตรวจรูปก่อน (ช้า) ถ้าตั้งเป็น `false` จะเสนอทันทีจากผล embedding (~1 วินาที) แต่ไม่ได้ตรวจว่าเป็นเครื่องเขียน
- ฝั่ง frontend: แสดง `suggestions` เป็นปุ่มหรือการ์ดให้ลูกค้าเลือก อย่าแสดงเป็น "สินค้าที่ตรงกัน"

### เมื่อไหร่ถึงได้ `exact`

ตาม spec "exact เฉพาะเมื่อยืนยัน SKU/รุ่นได้" ระบบให้ `exact` เมื่อครบทุกข้อ:

1. vision model อ่านรหัสรุ่นจากตัวสินค้าได้ (เช่น `1448`, `BL667`) ยาวอย่างน้อย 3 ตัวอักษร
2. รหัสนั้นอยู่ในชื่อสินค้า **เพียงตัวเดียว** ในผลค้น ชื่อรุ่นที่ใช้ร่วมกันหลายสินค้า เช่น `Precision` หรือ `500` จะไม่นับ
3. ยี่ห้อที่อ่านได้ (ถ้ามี) ไม่ขัดกับยี่ห้อสินค้า
4. คะแนนความคล้ายผ่านเกณฑ์ `IMAGE_TAU_SIMILAR`

คะแนนสูงอย่างเดียวไม่ทำให้เป็น `exact` ดังนั้น **fast path ได้มากสุด `similar`** เพราะไม่ได้อ่านรุ่นจากรูป

### เวลาตอบ

| กรณี | `path` | เวลาโดยประมาณ (RTX 3050 6 GB) |
|---|---|---|
| พบสินค้าใกล้เคียง | `fast` | 0.3–1 วินาที (request แรกหลังเปิด server ~10 วินาที เพื่อโหลดโมเดล) |
| ไม่พบสินค้าใกล้พอ → ใช้ vision model | `full` | **หลายนาที** กับ `qwen3-vl:latest` |

ฝั่ง client ควรตั้ง timeout ให้ยาวพอสำหรับ `full` (backend ตั้ง `OLLAMA_TIMEOUT_S`) และแสดงสถานะกำลังวิเคราะห์

---

## POST `/api/v1/admin/image-index` — สร้าง image index ใหม่

สำหรับผู้ดูแลระบบ: embed รูปและคำอธิบายสินค้าจาก `backend/datasets/catalog` ลง pgvector ข้ามรายการที่ไม่เปลี่ยน ปิดไว้ (ตอบ `404 NOT_FOUND`) จนกว่าจะตั้ง `VISION_ADMIN_ENABLED=true` เพราะยังไม่มีสิทธิ์ admin

```json
{"products": 50, "chunks_embedded": 0, "chunks_unchanged": 100, "chunks_deleted": 0, "warnings": ["..."], "seconds": 0.09}
```

Errors: 404 (ปิดอยู่), 422 `CATALOG_INVALID` (metadata.csv มี error; `details.report`)

## GET `/api/v1/health`

ไม่ต้องยืนยันตัวตน → `{"status": "ok"}`

---

## ข้อแนะนำสำหรับ frontend

- แสดง `match_type` เป็นป้าย: `exact` → "ตรงรุ่น", `similar` → "ใกล้เคียง" และเมื่อ `match_level` เป็น `none` ให้บอกว่าไม่พบสินค้าในร้าน
- ค่า `null` ของราคาหรือ `availability` ให้แสดง "ไม่มีข้อมูล" อย่าแสดงเป็น 0 หรือ "มีสินค้า"
- แสดง `source_ref` เป็นลิงก์ที่มาของข้อมูลสินค้า ตาม Business Requirements
- `image_url` ชี้ไปยังรูปบน CDN ของแหล่งข้อมูล (© B2S/OfficeMate, educational use only) ควรตกลงกับทีมก่อนแสดงรูปจากแหล่งภายนอกโดยตรง
- อย่าทดสอบข้อความภาษาไทยด้วย `curl` ใน Git Bash บน Windows เพราะตัวอักษรจะเพี้ยน ให้ใช้ Postman หรือ Swagger UI (`/docs`)
