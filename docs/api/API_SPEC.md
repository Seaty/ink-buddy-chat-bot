# Ink Buddy — Current API Specification และประเด็นตัดสินใจ

ตรวจเมื่อ: 2026-10-03 · อ้างอิงโค้ดปัจจุบันและ `openapi.current.json`

เอกสารนี้บันทึก **สิ่งที่ implement แล้ว** และแยกข้อเสนอสำหรับขั้นถัดไปไว้ท้ายไฟล์ ขอบเขตธุรกิจคือแชตบอตเครื่องเขียน ค้น/แนะนำสินค้า และแนบรูปเท่านั้น ไม่มี API อัปโหลดเอกสาร

## 1. สถานะปัจจุบัน

| Method | Endpoint | หน้าที่ | ความพร้อม/ข้อจำกัด |
|---|---|---|---|
| GET | `/api/v1/health` | ตรวจว่า API ตอบสนอง | ไม่ตรวจ DB, Ollama หรือ embedding |
| POST | `/api/v1/images` | อัปโหลดรูปส่วนตัว | มี validation และบันทึก DB; auth เป็น dev user |
| POST | `/api/v1/product-search/by-image` | ค้นสินค้าโดยอ้างรูปที่อัปโหลด | ค่าเริ่มต้นใช้ mock; ไม่ใช่ API สนทนา |
| POST | `/api/v1/admin/image-index` | สร้าง/อัปเดต image catalog index | ปิดตามค่าเริ่มต้น; เมื่อเปิดยังไม่มี admin authentication |

มี Swagger `/docs`, ReDoc `/redoc` และ `/openapi.json` ตามค่าเริ่มต้น FastAPI แต่ไม่มี security scheme ของ JWT ใน OpenAPI

เพิ่มโครง Authentication, Guest, User, Chat Session/Message, Product List/Detail, Image Get/Delete และ Readiness แล้ว รวม **23 operations บน 18 paths: ทำงานเดิม 4 และ scaffold 19** โครงใหม่ตอบ 501 สำหรับ input ที่ถูกต้อง และ 422 เมื่อ input ไม่ผ่าน validation ยังไม่มี business logic, JWT, Guest quota หรือข้อมูลสำเร็จจริง ส่วน standalone Text RAG/Analyze/OCR/Model Status ยังไม่มี routes

### 1.1 Path registry สำหรับโครงตั้งต้น

ทุก path ด้านล่างมี prefix `/api/v1` และมีอยู่ใน Swagger แล้ว **ทุกแถวในตารางนี้เป็น scaffold** Request/Success schema เป็นสัญญาที่เสนอเพื่อวางโครงเท่านั้น Actual response สำหรับ valid request คือ 501 NOT_IMPLEMENTED ไม่มีการอ่าน/เขียน DB ออก token หรือเรียก AI

| Module | Method | Path | Request | Planned success |
|---|---|---|---|---|
| auth | POST | /auth/login | LoginRequest | 200 TokenResponse |
| auth | POST | /auth/refresh | ไม่มี JSON; เสนอ refresh cookie | 200 TokenResponse |
| auth | POST | /auth/logout | ไม่มี JSON; เสนอ refresh cookie | 204 |
| auth/guest | POST | /auth/guest-sessions | ไม่มี body | 201 GuestSessionResponse + cookie |
| auth/guest | GET | /auth/guest-sessions/current | Guest cookie | 200 GuestSessionResponse |
| auth/guest | POST | /auth/guest-sessions/current/claim | Guest cookie + user access token | 200 GuestClaimResponse |
| user | GET | /users/me | user access token | 200 UserProfileResponse |
| user | PATCH | /users/me | UpdateProfileRequest | 200 UserProfileResponse |
| session | POST | /chat-sessions | CreateSessionRequest | 201 SessionResponse |
| session | GET | /chat-sessions | limit, cursor | 200 SessionListResponse |
| session | GET | /chat-sessions/{session_id} | UUID path | 200 SessionResponse |
| session | DELETE | /chat-sessions/{session_id} | UUID path | 204; เสนอ soft delete |
| session | GET | /chat-sessions/{session_id}/messages | UUID path, limit, cursor | 200 MessageListResponse |
| session | POST | /chat-sessions/{session_id}/messages | UUID path, SendMessageRequest | 201 SendMessageResponse |
| image | GET | /images/{image_id} | UUID path | 200 ImageDetailResponse; metadata เท่านั้น |
| image | DELETE | /images/{image_id} | UUID path | 204; เสนอ soft delete |
| product | GET | /products | q, category, brand, limit, cursor | 200 ProductListResponse |
| product | GET | /products/{product_id} | UUID path | 200 ProductResponse |
| system | GET | /ready | ไม่มี input | 200 ReadinessResponse หรือ 503 เมื่อ dependency ไม่พร้อม |

#### Request/response schemas ของ scaffold

| Schema | Fields / Validation |
|---|---|
| LoginRequest | email string 3–320 chars; password 1–1024 chars; email format/password policy ยังต้องลงรายละเอียด |
| TokenResponse | access_token, token_type=bearer, expires_in positive seconds; refresh token ผ่าน HttpOnly cookie เป็นข้อเสนอ |
| GuestSessionResponse | id UUID, expires_at datetime, image_upload_limit=3, image_uploads_used/remaining 0–3; service ต้องคำนวณ remaining ให้ตรงกัน |
| GuestClaimResponse | guest_session_id, user_id, chat_sessions_claimed, images_claimed |
| UserProfileResponse | id, email, display_name nullable, role; ไม่ส่ง password_hash |
| UpdateProfileRequest | display_name optional/null; string 1–120 chars; null เสนอให้ล้างชื่อ; ไม่ส่ง field เสนอให้คงเดิม |
| CreateSessionRequest | title optional/null; string 1–200 chars |
| SessionResponse | id, title, summary nullable, created_at, updated_at |
| SendMessageRequest | content default empty, max 4000 chars เป็น limit ที่เสนอสำหรับ MVP; image_id UUID optional; ต้องมีข้อความที่ไม่เป็นช่องว่างหรือรูป |
| MessageResponse | id, session_id, sequence_number positive, role user/assistant/system, content, image_id nullable, product_refs nullable, created_at |
| SendMessageResponse | user_message และ assistant_message; เริ่มด้วย JSON synchronous; streaming ยังไม่กำหนด |
| ImageDetailResponse | id, status, mime_type, size_bytes, created_at; ไม่มี public storage path |
| ProductResponse | id, name; sku/category/brand/description/price/currency/availability/source_ref nullable |
| List responses | items ของ resource และ next_cursor nullable; cursor format ยังไม่ implement |
| ReadinessResponse | status ready/not_ready, dependencies mapping ชื่อ dependency → สถานะ; ห้ามใส่ secrets |

List query `limit` default 20 ช่วง 1–100, `cursor` optional; product q ยาวไม่เกิน 200, category/brand ไม่เกิน 100 chars UUID path validation เป็น 422 เมื่อไม่ถูกต้อง JSON requests ใช้ Content-Type application/json ส่วน credentials/cookies ยังไม่ตรวจใน scaffold

ข้อความใช้ **image_id เดียว** ให้ตรง `chat_messages.image_id` ใน DDL ปัจจุบัน Guest ส่งรูปสะสม 3 รูปได้ในหลายข้อความ หากต้องการหลายรูปต่อข้อความ ต้องเพิ่ม message_images relation ก่อนเปลี่ยนเป็น image_ids

#### Authentication / Business / Security ที่ต้อง implement

- Login และสร้าง Guest เป็น public แต่ต้อง rate limit; refresh/logout ใช้ refresh credential; claim ต้องยืนยันทั้ง Guest และบัญชี
- User profile ใช้ user principal; session/image routes ใช้ user หรือ Guest พร้อม ownership checks; product read/search เสนอให้ใช้ principal ทั้งสองชนิดเพื่อควบคุม abuse
- Public health เป็น liveness; readiness ควรจำกัดข้อมูลและกำหนดว่าจะเปิดให้ใครเข้าถึงก่อน deploy
- คง /images และ /product-search/by-image เดิม แต่ Guest ยังใช้งานไม่ได้จนเพิ่ม principal + quota transaction; admin indexing ยังขาด role guard
- Cookie proposals ใช้ HttpOnly, SameSite, Secure ใน production และ CSRF/Origin protection สำหรับ mutation; ไม่มีการตั้ง cookie จริงใน scaffold
- Error ที่จะเพิ่มเมื่อ implementation พร้อม: 401 auth, 404 missing/not-owned, 403 Guest quota exceeded, 429 rate limit, 503 dependency unavailable
- Success schema ที่ Swagger แสดงไม่ได้หมายความว่า route ใช้งานได้ ตรวจ `x-implementation-status=scaffold` และ summary `[Scaffold]` ก่อนเชื่อม frontend

#### Example scaffold request/response

```http
POST /api/v1/chat-sessions HTTP/1.1
Content-Type: application/json

{"title":"เลือกปากกาจดโน้ต"}
```

Actual response **501**:

```json
{"error":{"code":"NOT_IMPLEMENTED","message":"This endpoint is a scaffold; implementation is pending","details":{"feature":"create_chat_session"}}}
```

## 2. Contract กลาง

- Base URL ตัวอย่าง local: `http://localhost:8000` (ขึ้นอยู่กับพอร์ตที่ใช้รัน)
- Prefix: `/api/v1`; JSON ใช้ `snake_case`; identifiers ใช้ UUID
- Auth ปัจจุบัน: ตั้ง `DEV_AUTH_EMAIL` ที่ backend แล้วทุกคำขอใน routes ที่ใช้ auth dependency จะเป็นผู้ใช้คนเดียวกัน หากไม่ตั้งจะได้ 401 **ยังไม่ตรวจ Bearer token**
- CORS ค่าเริ่มต้นอนุญาต `http://localhost:3000`; เปลี่ยนได้ผ่าน settings
- Error รูปแบบเดียวกัน:

```json
{"error":{"code":"VALIDATION_ERROR","message":"request validation failed","details":{}}}
```

Validation error ใส่ `details.errors` เป็นรายการ `loc`, `msg`, `type`; unexpected error ใช้ 500 `INTERNAL_ERROR` และไม่ส่ง exception ภายในกลับไปให้ client

ไม่มี pagination ที่ routes ปัจจุบัน, rate limiter, idempotency key หรือ background job API การ inference/indexing รอจนงานจบในคำขอเดียว แม้รันงาน blocking ผ่าน worker thread

## 3. GET Health

### Purpose

ตรวจว่าแอปตอบ HTTP ได้

### Endpoint / Method / Authentication Required

`GET /api/v1/health` · Public

### Request Headers

`Accept: application/json`

### Path Parameters / Query Parameters / Request Body

ไม่มี

### Success Response

200: `{"status":"ok"}`

### Error Responses

ไม่มี dependency error ที่ตรวจเอง; infrastructure อาจทำให้คำขอไม่สำเร็จ

### Validation Rules / Business Rules

ไม่มี input; เป็น liveness เท่านั้น

### Security Considerations

ไม่เปิดเผยข้อมูล config แต่ห้ามใช้ผลนี้สรุปว่าฐานข้อมูลและ AI พร้อม

### Example Request

```http
GET /api/v1/health HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Example Response

```json
{"status":"ok"}
```

## 4. POST Upload Image

### Purpose

รับรูป เก็บใน private storage และสร้างแถว `image_uploads` เพื่อใช้ค้นสินค้า

### Endpoint / Method / Authentication Required

`POST /api/v1/images` · Required (dev auth ปัจจุบัน)

### Request Headers

`Content-Type: multipart/form-data; boundary=...`; ให้ HTTP client สร้าง boundary

### Path Parameters / Query Parameters

ไม่มี

### Request Body

| Field | Type | Required | Validation |
|---|---|---|---|
| file | binary multipart part | Yes | ตรวจเนื้อหารูปจริง JPEG/PNG/WEBP |

### Success Response

201:

| Field | Type | Meaning |
|---|---|---|
| id | UUID | ID รูปที่ใช้ส่งไปค้นสินค้า |
| status | string | สถานะรูป; schema อธิบาย ready/processing/failed แต่ไม่ได้บังคับ enum |

### Error Responses

| HTTP | Code | Cause |
|---|---|---|
| 401 | UNAUTHORIZED | ไม่ตั้ง dev user |
| 413 | IMAGE_TOO_LARGE | เกินขนาดที่กำหนด |
| 415 | UNSUPPORTED_MEDIA_TYPE | decode ไม่ได้หรือ format ไม่รองรับ |
| 422 | EMPTY_FILE / IMAGE_TOO_SMALL / validation code | รูปว่าง รูปเล็กเกิน หรือภาพไม่ผ่านข้อจำกัด |
| 422 | VALIDATION_ERROR | ไม่มี file part |
| 500 | INTERNAL_ERROR | เช่น storage/DB ไม่พร้อม |

### Validation Rules

ค่าเริ่มต้น: ไม่เกิน 5 MiB (5,242,880 bytes), ไม่เกิน 40 ล้าน pixels, แต่ละด้านอย่างน้อย 32 pixels; ขนาดสูงสุดปรับได้ใน settings รูปที่ decode ไม่ได้ถูกปฏิเสธ ไม่เชื่อเพียงนามสกุลหรือ MIME จาก client

### Business Rules

ผูกกับ user ปัจจุบัน; re-encode รูปและไม่เก็บ metadata เดิม ถ้าบันทึก DB ล้มเหลวจะ rollback และลบไฟล์ที่เพิ่งเก็บ ไม่มี chat_session_id ใน request

### Security Considerations

ไฟล์ไม่ได้เสิร์ฟตรงผ่าน public API; ยังต้องกำหนดนโยบาย retention/deletion และ auth จริงก่อนใช้หลายผู้ใช้

### Example Request

```shell
curl.exe -X POST http://localhost:8000/api/v1/images -F "file=@sample.jpg"
```

### Example Response

```json
{"id":"123e4567-e89b-42d3-a456-426614174000","status":"ready"}
```

## 5. POST Search Products by Image

### Purpose

ค้นสินค้าจากรูปของผู้ใช้ แล้วเติมข้อมูลสินค้าจากตาราง products

### Endpoint / Method / Authentication Required

`POST /api/v1/product-search/by-image` · Required (dev auth ปัจจุบัน)

### Request Headers

`Content-Type: application/json`, `Accept: application/json`

### Path Parameters / Query Parameters

ไม่มี

### Request Body

| Field | Type | Required | Validation |
|---|---|---|---|
| image_id | UUID | Yes | ต้องเป็นรูปของ user และยังไม่ถูกลบ |
| limit | integer | No | 1–10; default 5 |

ไม่มี `message`, `session_id` หรือคำถามใน contract นี้

### Success Response

200:

| Field | Type | Meaning |
|---|---|---|
| image_id | UUID | รูปต้นทาง |
| description | string/null | คำอธิบายจาก vision; fast path อาจเป็น null |
| match_level | exact/similar/none | ระดับที่ pipeline จัดให้ |
| matches | ProductMatch[] | รายการสินค้า ไม่รับประกันว่าจะครบ limit |
| path | fast/full | เส้นทางประมวลผล |
| timings_s | object<string,number> | เวลาขั้นตอนเป็นวินาที; keys ขึ้นกับ pipeline |

ProductMatch:

| Field | Type | Meaning |
|---|---|---|
| product_id | UUID | ID จาก products |
| sku | string/null | รหัสสินค้า |
| name | string | ชื่อสินค้า |
| category, brand | string/null | ข้อมูล catalog |
| price | number/null | ราคาใน DB; ไม่ได้ตรวจราคาปัจจุบันจากร้าน |
| currency, availability | string/null | ข้อมูล DB; ไม่รับประกัน stock แบบ realtime |
| source_ref | string/null | ที่มาข้อมูลสินค้า |
| image_url | string/null | URL จาก metadata สินค้า; ไม่มี route เสิร์ฟรูป catalog ใน API นี้ |
| match_type | exact/similar | ป้ายกำกับแต่ละรายการ |
| score | number | similarity score; ไม่ใช่ probability/ความมั่นใจที่สอบเทียบแล้ว |

### Error Responses

| HTTP | Code | Cause |
|---|---|---|
| 401 | UNAUTHORIZED | ไม่ตั้ง dev user |
| 404 | IMAGE_NOT_FOUND | ไม่มีรูป/ไม่ใช่เจ้าของ/ถูกลบ/ไฟล์หาย |
| 422 | IMAGE_NOT_READY | รูปยังไม่พร้อม |
| 422 | VALIDATION_ERROR | UUID หรือ limit ไม่ถูกต้อง |
| 503 | VISION_UNAVAILABLE | Ollama/vision model error ที่ service จัดการไว้ |
| 500 | INTERNAL_ERROR | เช่น DB หรือ embedding failure ที่ยังไม่ได้ map เป็น 503 |

### Validation Rules

บังคับรูปแบบ UUID และช่วง limit; response score มีคำอธิบาย 0–1 แต่ schema ไม่ได้บังคับช่วงด้วย validator

### Business Rules

- ค่าเริ่มต้น `IMAGE_RETRIEVER=mock`; ต้องเปลี่ยนเป็น pgvector และเตรียม index จึงใช้ vector retrieval จริง
- fast path อาจค้นด้วย embedding โดยไม่เรียก vision; full path วิเคราะห์ภาพและค้นเพิ่ม
- thresholds ค่าเริ่มต้น exact ≥ 0.80, similar ≥ 0.55; ต้องประเมินด้วยชุดรูปจริงก่อนใช้คำว่า “ตรงรุ่น” ใน UI
- ผล retrieval ที่ไม่มี SKU ใน products จะถูกตัดออก ไม่สร้างสินค้า/ราคาขึ้นเอง
- `match_level=none` อาจยังมีรายการทางเลือกจาก pipeline จึงไม่ควรตีความว่าต้องได้ matches ว่างเสมอ
- เมื่อเป็น exact โค้ดติดป้าย exact ให้รายการแรกที่ส่งคืน หาก candidate แรกไม่มีใน products รายการถัดไปอาจรับป้ายนี้แทน: ควรแก้ก่อนนำป้ายไปยืนยันรุ่นสินค้า
- endpoint เรียก pipeline โดยไม่ส่งข้อความและปิดการสร้างคำตอบ (`with_answer=False`); ไม่บันทึก chat history
- ถ้ามี analysis จะบันทึกลงรูป; OCR ที่ service เก็บประกอบจาก brand/model text ไม่ใช่ endpoint OCR แบบอ่านข้อความทั้งภาพ

### Security Considerations

ตรวจ ownership แล้ว แต่ dev auth ไม่แยกผู้ใช้จริง ต้องเพิ่ม JWT, rate limit และการควบคุมทรัพยากร AI

### Example Request

```http
POST /api/v1/product-search/by-image HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{"image_id":"123e4567-e89b-42d3-a456-426614174000","limit":5}
```

### Example Response

ตัวอย่าง contract เท่านั้น ไม่ใช่ผลทดสอบจริงหรือรายการสินค้าที่รับรอง:

```json
{
  "image_id":"123e4567-e89b-42d3-a456-426614174000",
  "description":null,
  "match_level":"none",
  "matches":[],
  "path":"fast",
  "timings_s":{}
}
```

## 6. POST Index Image Catalog

### Purpose

อ่าน catalog ที่ server กำหนด สร้าง embedding ของรูปและ caption พร้อมปรับ index ตามข้อมูลต้นทาง

### Endpoint / Method / Authentication Required

`POST /api/v1/admin/image-index` · **ไม่มี auth dependency ในโค้ดปัจจุบัน**; เปิดได้เมื่อ `VISION_ADMIN_ENABLED=true`

### Request Headers

`Accept: application/json`

### Path Parameters / Query Parameters / Request Body

ไม่มี; catalog/model อ่านจาก settings

### Success Response

200:

| Field | Type | Meaning |
|---|---|---|
| products | integer | จำนวนสินค้าใน catalog ที่อ่าน |
| chunks_embedded | integer | chunks ใหม่/เปลี่ยนที่สร้าง vector |
| chunks_unchanged | integer | chunks เดิมที่ hash ไม่เปลี่ยน |
| chunks_deleted | integer | chunks ที่ตัดออกจาก index |
| warnings | string[] | คำเตือน catalog |
| seconds | number | ระยะเวลารวม |

### Error Responses

| HTTP | Code | Cause |
|---|---|---|
| 404 | NOT_FOUND | ปิด admin feature |
| 422 | CATALOG_INVALID | catalog ไม่ผ่าน strict validation; details มีรายงาน |
| 500 | INTERNAL_ERROR | เช่น model/embedding/DB failure |

### Validation Rules

ตรวจ catalog ฝั่ง server แบบ strict ไม่มี catalog path ที่ client ส่งได้

### Business Rules

เทียบ content hash และ model เพื่อ embed เฉพาะข้อมูลเปลี่ยน; refresh metadata ของข้อมูลเดิม และลบ index entries ที่ไม่อยู่ในชุดใหม่ ไม่ใช่ endpoint seed/upsert ข้อมูล products ต้อง seed products แยก

### Security Considerations

Feature flag ไม่ใช่สิทธิ์ admin เมื่อเปิดใครเข้าถึง route ได้ก็เรียกงานหนักและปรับ index ได้ ควรคงปิดและใช้ script ภายในจนมี JWT + role guard; ยังไม่มี job locking ป้องกันการ index พร้อมกัน

### Example Request

```http
POST /api/v1/admin/image-index HTTP/1.1
Host: localhost:8000
Accept: application/json
```

### Example Response

ตัวเลขสมมติสำหรับอธิบายรูปแบบ:

```json
{"products":2,"chunks_embedded":4,"chunks_unchanged":0,"chunks_deleted":0,"warnings":[],"seconds":12.5}
```

## 7. ความพร้อมด้านข้อมูลและการรัน

1. เริ่ม PostgreSQL + pgvector และ schema หลัก พร้อม seed products
2. ตรวจ schema `product_image_embeddings`: SQL init ปัจจุบันเพิ่ม vector 2048 มิติแล้ว; ฐานเดิมใช้ migration 002 ตาม Database Schema; startup แอปไม่ได้ migrate ให้อัตโนมัติ
3. ตั้ง DB connection และ dev user สำหรับ local; ไม่เผยแพร่ระบบแบบ dev auth
4. สำหรับค้นจริง เตรียม Qwen/Qwen3-VL-Embedding-2B, index catalog แล้วตั้ง `IMAGE_RETRIEVER=pgvector`
5. เตรียม Ollama model `qwen3-vl:latest` สำหรับ full path; ค่าเริ่มต้นนี้ต่างจากโมเดลใน design draft เก่า

Text embedding BGE-M3/vector1024 ในแผนเดิมเป็นคนละ index กับ image embedding/vector2048 ห้ามใช้แทนกันโดยไม่ออกแบบและ migrate

## 8. ประเด็นที่แนะนำให้ตัดสินใจ

| เรื่อง | ข้อเสนอ | Trade-off / ผลต่อ scope |
|---|---|---|
| ลำดับ MVP | ทำ upload → image search → แสดง product cards ก่อน แล้วเชื่อม chat | ทดลอง image flow ได้เร็ว แต่ยังไม่ครบ chatbot business requirement |
| Conversation contract | เพิ่ม sessions/messages API และให้ข้อความแนบ image_ids ที่ผู้ใช้เป็นเจ้าของ; ใช้ search endpoint เดิมเป็น capability | แยก lifecycle ของ chat ชัดเจน แต่เพิ่ม orchestration และการเก็บ history |
| ป้าย exact | เริ่มแสดง “สินค้าที่คล้ายกัน”; เปิด exact เมื่อมี SKU/brand/model verification และประเมิน precision | ลดการยืนยันผิด แต่ต้องเพิ่มข้อมูลและ evaluation เพื่อรองรับตรงรุ่น |
| Auth/admin | JWT + refresh token rotation + role guard; indexing ผ่าน script ภายในก่อน | งาน auth เพิ่ม แต่จำเป็นก่อนใช้หลายผู้ใช้/เปิด network |
| งาน AI ที่ช้า | sync สำหรับ local prototype; production เปลี่ยน indexing เป็น job ตอบ 202 และ polling | queue/worker เพิ่ม แต่รองรับ retry, timeout และติดตามงานได้ |
| Catalog | ให้ DB เป็นแหล่ง metadata หลัก พร้อมกำหนด sync กับ CSV/index | ลด SKU/index ไม่ตรงกัน แต่ต้องมีขั้นตอน ingest และ versioning |
| รูปผู้ใช้ | เพิ่ม delete และ retention; ตัดสินใจว่าจะผูกกับ session หรือ reuse ข้าม session | กระทบ privacy, storage และ UX |
| Observability | เพิ่ม readiness ตรวจ dependency และ model status ที่ป้องกันสิทธิ์ | ตรวจ readiness ลึกเกินไปอาจช้า; ไม่ควรโหลดโมเดลทุก health request |

## 9. ขั้นถัดไปหลังสร้างโครง

ข้อกำหนด Guest ทดลองก่อน Login และอัปโหลด 3 รูปต่อ free session รวมไว้ในหัวข้อ 10 ของไฟล์นี้; routes ปัจจุบันยังไม่รองรับ Guest

| Module | Proposed endpoints | จุดที่ต้องกำหนด |
|---|---|---|
| Authentication | POST `/api/v1/auth/login`, POST `/auth/refresh`, POST `/auth/logout`, GET `/users/me` | สมัครเองหรือสร้าง user โดย admin; token lifetime/rotation |
| Chat | POST/GET `/api/v1/chat-sessions`, GET/DELETE `/chat-sessions/{session_id}`, POST `/chat-sessions/{session_id}/messages` | message + image_ids, pagination, streaming, summary policy |
| Products | GET `/api/v1/products`, GET `/products/{product_id}` | filter/search/pagination และเจ้าของข้อมูลราคา/stock |
| Images | GET/DELETE `/api/v1/images/{image_id}` | ownership, retention, private preview |
| Operations | GET `/api/v1/ready`, GET `/admin/models`, GET `/admin/jobs/{job_id}` | roles และขอบเขต dependency checks |

Paths ย่อในแถวเดียวกันใช้ prefix `/api/v1` เช่นกัน รายละเอียดการทำงานยังเป็น proposal; ส่วน paths ที่ลงทะเบียนแล้วให้ดูหัวข้อ 1.1 และ openapi.current.json ควรเลือก scope ก่อนเขียน request/response แบบละเอียด Multi-Agent/MCP สามารถเชื่อมผ่าน service adapters ได้ภายหลัง โดยไม่ต้องเปิด agent internals เป็น public API

## 10. Guest session และโควตารูป (มี DDL และ route scaffold; logic ยังไม่ implement)

สถานะ: ข้อกำหนดธุรกิจยืนยัน Guest และ 3 รูปต่อ free session แล้ว; Guest API ด้านล่างยังเป็นข้อเสนอ; DDL และ migration รองรับ schema นี้แล้ว แต่ยังไม่ได้ apply ฐานจริง

### ขอบเขต

Guest ถาม ค้น และรับคำแนะนำเครื่องเขียนได้ก่อน Login แนบได้เฉพาะรูป สูงสุด 3 รูปต่อ free session ไม่ใช้ dev user ร่วมกันสำหรับลูกค้าทุกคน

สมมติฐานเพื่อออกแบบ: free session เป็น Guest access session ที่ server ออกให้และครอบคลุมหลาย chat threads การเปิดแชตใหม่ไม่คืนโควตา ยังต้องยืนยันอายุ session และโควตาของผู้ Login

### Database ต้องเปลี่ยนอะไร

Schema ปัจจุบัน `chat_sessions.user_id` และ `image_uploads.user_id` เป็น NOT NULL จึงยังรับ Guest ไม่ได้ ไม่แนะนำสร้าง email/password ปลอมใน users ให้ Guest

#### เพิ่ม guest_sessions

| Column | Type | Nullable | หน้าที่ |
|---|---|---|---|
| id | uuid PK | No | Guest access session |
| token_hash | text UNIQUE | No | Hash ของ random session token; ไม่เก็บ token ดิบ |
| image_upload_limit | smallint | No | Default 3; จำกัด policy Guest นี้ไว้ที่ 3 |
| image_uploads_used | smallint | No | Default 0; จำนวนรูปที่รับสำเร็จ |
| created_at | timestamptz | No | เวลาสร้าง |
| expires_at | timestamptz | No | เวลาหมดอายุ; ระยะเวลายังไม่กำหนด |
| revoked_at | timestamptz | Yes | เวลายกเลิก token |
| claimed_by_user_id | uuid FK users | Yes | บัญชีที่รับข้อมูล Guest หลัง Login |
| claimed_at | timestamptz | Yes | เวลาย้ายข้อมูลเข้าบัญชี |

Constraints ที่เสนอ: `image_upload_limit = 3`, `0 <= image_uploads_used <= image_upload_limit`, expiry หลัง created_at และ claimed user/time ต้องมีคู่กัน Index: unique token_hash สำหรับ lookup; expires_at สำหรับ cleanup; index claimed_by_user_id เฉพาะแถวไม่ null

#### ปรับตารางเดิม

| Table | Change | Rules |
|---|---|---|
| chat_sessions | user_id nullable; เพิ่ม guest_session_id UUID FK | เจ้าของต้องมีหนึ่งอย่างเท่านั้นด้วย CHECK XOR |
| image_uploads | user_id nullable; เพิ่ม guest_session_id UUID FK | เจ้าของต้องมีหนึ่งอย่างเท่านั้นด้วย CHECK XOR |

แถวผู้ใช้เดิมยังเก็บ user_id และ guest_session_id=null ได้ เพิ่ม partial indexes `(guest_session_id, updated_at DESC, id DESC)` สำหรับแชต และ `(guest_session_id, created_at DESC, id DESC)` สำหรับรูป โดยกรอง deleted_at IS NULL และ guest_session_id IS NOT NULL

ไม่จำเป็นต้องเปลี่ยน products หรือ embedding เพื่อรองรับ Guest; guest_session_id ไม่ใช่ chat_sessions.id ปัจจุบัน chat_messages อ้างรูปหนึ่งรูปต่อข้อความ ซึ่งแยกจากโควตา 3 รูปสะสมต่อ free session

ควรใช้ FK แบบ RESTRICT และ cleanup ตามลำดับอย่างชัดเจน เพื่อไม่ให้ลบ Guest session แล้วเหลือไฟล์หรือข้อความอ้างรูปที่ถูกลบ สคริปต์ cleanup ต้องลบ private files ด้วย ไม่ใช่ลบแค่แถว DB

### การนับโควตา

ข้อเสนอ: นับเฉพาะรูปที่ผ่าน validation และบันทึกสำเร็จ การค้นด้วยรูปเดิมไม่เสียโควตาเพิ่ม การลบรูปไม่คืนโควตา หากอัปโหลดรูปเดิมอีกเป็นคำขอใหม่ให้นับใหม่; อาจเพิ่ม idempotency key เพื่อกัน retry ซ้ำ

ใช้ transaction และ lock แถว Guest session ก่อนตรวจโควตา เพิ่ม counter และ insert image ใน transaction เดียวกัน ห้ามใช้ count แล้ว insert โดยไม่มี lock เพราะคำขอพร้อมกันอาจเกิน 3 รูป ตรวจ expiry/revocation/claimed state ภายใต้ lock เดียวกัน หาก DB fail rollback counter และลบไฟล์ที่เพิ่งบันทึก

DB CHECK ของ counter เพียงอย่างเดียวไม่บังคับจำนวน image rows ทุกช่องทาง ต้องให้ทุก upload path ผ่าน transaction นี้ หรือเพิ่มกลไก DB หากมีผู้เขียนข้อมูลหลายระบบ

### API ที่เสนอ

| Method | Path | Purpose |
|---|---|---|
| POST | /api/v1/auth/guest-sessions | สร้าง Guest access session และออก token |
| GET | /api/v1/auth/guest-sessions/current | สถานะ expiry และโควตา used/remaining |
| POST | /api/v1/auth/guest-sessions/current/claim | ย้ายข้อมูลเข้าบัญชี; ต้องมีทั้งบัญชีที่ Login และหลักฐาน Guest |
| POST | /api/v1/images | ขยาย endpoint เดิมให้รับ Guest หรือ user principal |

แนวทาง token ที่เสนอสำหรับเว็บ: HttpOnly cookie, Secure ใน production พร้อม CSRF/Origin protection สำหรับ mutation; frontend ไม่ส่ง guest_session_id มาเป็นหลักฐานสิทธิ์เพียงอย่างเดียว

เมื่อครบโควตา เสนอ 403 `GUEST_IMAGE_QUOTA_EXCEEDED` พร้อม details `{limit:3,used:3,remaining:0}`; 429 ใช้สำหรับ rate limit และควรมี Retry-After ไม่ใช้กับโควตาที่รอเฉย ๆ แล้วไม่คืน

ทุก route ที่อ่านแชต/รูป/ค้นรูปต้องตรวจ ownership ตาม principal ที่ server ตรวจสอบแล้ว ใช้ 404 สำหรับทรัพยากรที่ไม่ใช่เจ้าของ

Claim ต้องทำใน transaction เดียว เปลี่ยนเจ้าของแชตและรูปทั้งหมดเป็น user เดียวกัน ตั้ง claimed fields และ revoke Guest token; คำขอ claim ซ้ำต้องไม่ย้ายไปบัญชีอื่น รูปไม่ได้กลายเป็น public หลัง Login

### ประเด็นต้องตัดสินใจ

- free session ใช้นิยาม Guest access session ตามข้อเสนอหรือไม่
- อายุ session/ข้อมูลชั่วคราว และหลัง Login เก็บข้อมูลนานเท่าไร
- โควตาข้อความและรูปสำหรับผู้ Login
- การควบคุมการสร้าง Guest ใหม่: 3 รูปต่อ session ไม่ได้ป้องกันการล้าง cookie แล้วสร้าง session ใหม่ ต้องมี rate limit ฝั่ง server และนโยบาย abuse ที่เหมาะสม

### ลำดับ implementation

Migration เพิ่ม guest_sessions และ owner fields → SQLAlchemy models → auth principal รองรับ Guest/user → upload quota transaction → ownership checks → claim/cleanup → tests concurrency, expiry, cross-owner และ quota

อัปเดต `001_init.sql` สำหรับฐานใหม่และเพิ่ม migration 001 สำหรับ Guest ในฐานเดิมแล้ว ดู `database/DATABASE_SCHEMA.md`; ยังไม่ได้ apply ฐานจริง และยังไม่เปิด Guest ใน API จริง

## 11. หลักฐานและขอบเขตการตรวจ

- สร้าง `openapi.current.json` ด้วย `app.openapi()` จากแอปจริง: พบ 18 paths / 23 operations (4 implemented, 19 scaffold) และไม่มี JWT security scheme
- หลังสร้างโครง รัน backend tests ทั้งชุดเมื่อ 2026-10-03: **113 passed, 4 skipped**; API เดิม 20 tests ผ่าน และ scaffold 21 tests ผ่าน
- API tests ใช้ fake service/override dependencies: ยืนยัน routing, validation และ error contract ไม่ใช่การทดสอบ end-to-end กับ PostgreSQL, Ollama หรือ embedding จริง
- จุดอ้างอิง: `backend/app/api/v1/`, `backend/app/schemas/vision.py`, `backend/app/services/vision_service.py`, `backend/app/core/config.py`, `backend/app/core/errors.py`, `backend/app/api/deps.py`
- Snapshot ไม่อัปเดตอัตโนมัติ ต้อง generate ใหม่เมื่อ routes/schemas เปลี่ยน Swagger ของแอปที่รันคือข้อมูลล่าสุด
