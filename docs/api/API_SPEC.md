# Ink Buddy API Specification

อัปเดต 2026-10-04 · อ้างอิง code และ openapi.current.json หลัง implementation Chat Session และ Register/Reset Password

## 1. สถานะ

**27 operations บน 21 paths: implement แล้ว 20 และ scaffold 7** Authentication, Guest lifecycle, Profile GET และ Guest image upload/search ใช้งานจริงแล้ว การจัดการแชตและอ่านประวัติ implement แล้ว; ส่งข้อความ/สินค้า/รูป detail-delete/readiness ที่ยังเป็น scaffold ตรวจสิทธิ์ก่อนตอบ 501 ไม่คืนข้อมูลสำเร็จปลอม ไม่มี document upload

## 2. Contract กลางและ Authentication

- Prefix `/api/v1`; JSON snake_case; IDs เป็น UUID
- User: Authorization: Bearer JWT อายุ 15 นาที ตรวจ HS256, issuer/audience/expiry และ auth_sessions ใน DB ทุกคำขอ Logout มีผลทันทีสำหรับ Login session นั้น
- Refresh: opaque random token ใน cookie ink_buddy_refresh อายุสูงสุด 7 วันจาก Login เก็บ hash และ rotate เมื่อ refresh; reuse token เก่าจะ revoke ทั้ง Login session แม้เกิดจาก refresh พร้อมกัน client ต้องทำ refresh แบบ single-flight
- Guest: opaque random token ใน cookie ink_buddy_guest อายุ 24 ชั่วโมงคงที่ ใช้โควตา 3 รูปร่วมกันทุกแชต คืน session เดิมเมื่อ cookie ยังใช้ได้ ไม่สร้างใหม่ทุก API request
- Cookies: HttpOnly, SameSite=Lax, Path=/api/v1, ไม่มี Domain; Secure ใน production
- Register/Forgot Password/Reset Password/Login/Create Guest/Refresh/Logout/Claim และ Guest mutation ต้องส่ง Origin ที่ตรง CORS_ORIGINS หากไม่มีหรือผิดตอบ 403 ORIGIN_NOT_ALLOWED
- Bearer ที่ส่งมาแต่ผิดไม่ fallback เป็น Guest ใน routes ที่รับได้ทั้งสองชนิด User/Admin ไม่มี Bearer ตอบ 401 แม้มี Guest cookie
- ทุก operation มี x-access-policy; startup ล้มเหลวหากมี route ที่ยังไม่ประกาศ policy เอกสาร production ปิด /docs, /redoc และ /openapi.json
- Status: 401 invalid/missing/expired credential, 403 role/Origin/quota denied, 404 resource missing/not-owned, 422 input validation, 429 rate limit, 500 unexpected failure, 501 scaffold
- Error: `{"error":{"code":"...","message":"...","details":{}}}` Validation details.errors มี loc/msg/type โดยไม่ echo password/input
- Rate limits: Login 10/min/IP, Create Guest 5/hour/IP (รวมการเรียกคืน Guest เดิม), Refresh 30/min/IP, Image Search 20/min/verified principal; 429 ส่ง Retry-After ค่าเริ่มต้น memory backend สำหรับหนึ่ง workerเท่านั้น หลาย workers ต้องมี shared limiter URI และตั้ง AUTH_WORKERS ให้ตรง runtime
- Health เป็น public; Readiness ตรวจสิทธิ์ admin แต่ยังเป็น scaffold Admin indexing ต้องมีทั้ง role admin และ VISION_ADMIN_ENABLED=true

## 3. Registry

| Method | Path | Access | Implementation |
|---|---|---|---|
| POST | `/api/v1/auth/register` | public | Implemented |
| POST | `/api/v1/auth/forgot-password` | public | Implemented |
| POST | `/api/v1/auth/reset-password` | public | Implemented |
| POST | `/api/v1/auth/login` | public | Implemented |
| POST | `/api/v1/auth/refresh` | refresh | Implemented |
| POST | `/api/v1/auth/logout` | refresh | Implemented |
| POST | `/api/v1/auth/guest-sessions` | public | Implemented |
| GET | `/api/v1/auth/guest-sessions/current` | guest | Implemented |
| POST | `/api/v1/auth/guest-sessions/current/claim` | claim | Implemented |
| GET | `/api/v1/users/me` | user | Implemented |
| PATCH | `/api/v1/users/me` | user | Scaffold: 501 |
| POST | `/api/v1/chat-sessions` | guest_or_user | Implemented |
| GET | `/api/v1/chat-sessions` | guest_or_user | Implemented |
| GET | `/api/v1/chat-sessions/{session_id}` | guest_or_user | Implemented |
| DELETE | `/api/v1/chat-sessions/{session_id}` | guest_or_user | Implemented |
| GET | `/api/v1/chat-sessions/{session_id}/messages` | guest_or_user | Implemented |
| PATCH | `/api/v1/chat-sessions/{session_id}` | guest_or_user | Implemented |
| POST | `/api/v1/chat-sessions/{session_id}/messages` | guest_or_user | Scaffold: 501 |
| POST | `/api/v1/images` | guest_or_user | Implemented |
| GET | `/api/v1/images/{image_id}` | guest_or_user | Scaffold: 501 |
| DELETE | `/api/v1/images/{image_id}` | guest_or_user | Scaffold: 501 |
| POST | `/api/v1/product-search/by-image` | guest_or_user | Implemented |
| GET | `/api/v1/products` | guest_or_user | Scaffold: 501 |
| GET | `/api/v1/products/{product_id}` | guest_or_user | Scaffold: 501 |
| POST | `/api/v1/admin/image-index` | admin | Implemented |
| GET | `/api/v1/health` | public | Implemented |
| GET | `/api/v1/ready` | admin | Scaffold: 501 |

## 4. กฎธุรกิจสำคัญ

- Login: email validation, password 1–1024 chars; missing user/wrong password/inactive ใช้ 401 error เดียวกัน บัญชีใหม่ใช้ Argon2id; bcrypt เดิม upgrade หลัง Login สำเร็จ
- สร้างบัญชีผ่าน `python -m scripts.create_user --email ... --role user|admin` รับ password แบบซ่อน 12–24 chars ไม่แก้บัญชีเดิม Register API ใช้งานแล้ว
- Create Guest ตอบ 201 สำหรับ session ใหม่ และ 200 สำหรับ session เดิม ไม่คืน token ดิบใน JSON ให้ browser เก็บ cookie
- Guest current ส่ง id/expiry/limit/used/remaining ไม่ใช่โควตาฝั่ง client
- Upload: JPEG/PNG/WEBP ตรวจเนื้อหาจริง สูงสุด 5 MiB / 40 ล้าน pixels / แต่ละด้านอย่างน้อย 32 pixels ตาม config เก็บ private re-encoded image และลบ metadata
- Guest upload lock guest_sessions ตรวจ expiry/revoked/claimed และเพิ่ม counter+insert image ใน transaction เดียว Fail validation/DB ไม่เพิ่ม quota; ลบรูปไม่คืน quota; ค้นรูปเดิมไม่เสีย quota
- รูปที่ 4: 403 GUEST_IMAGE_QUOTA_EXCEEDED details `{limit:3,used:3,remaining:0}` บัญชี Login ยังไม่มีโควตารูปธุรกิจ; ขนาดรูปยังจำกัดเหมือนเดิม
- Search: image_id UUID และ limit default5 ช่วง1–10; ต้องเป็นเจ้าของรูป รายการสินค้ามาจาก products ไม่แต่งราคา/stock ค่าเริ่มต้น retrieval ยังเป็น mock ต้อง index และตั้ง pgvector จึงค้นเวกเตอร์จริง
- exact ในผลค้นยังเป็น threshold similarity ไม่ใช่ยืนยัน SKU/รุ่นที่สอบเทียบแล้ว; description อาจ null บน fast path และ match_level none ไม่รับประกัน matches ว่าง
- Claim: User Bearer และ Guest cookie ต้อง valid ย้ายแชต/รูปทั้งชุดแบบ atomic พร้อม revoke Guest และ clear cookie Claim ซ้ำ/expired Guest ตอบ 401
- Profile GET ไม่ส่ง password hash; PATCH ยังเป็น scaffold ไม่มีการแก้ข้อมูล
- Message contract ยังคง image_id เดียว ไม่ใช่ image_ids; content หรือ image ต้องมีอย่างน้อยหนึ่งอย่าง ข้อจำกัดข้อความ 4000 chars เป็น scaffold validation ที่เสนอ
- Chat lists: limit default20 ช่วง1–100; cursor scoped ตาม owner ใช้ updated_at/id สำหรับแชต และ sequence_number สำหรับข้อความ; cursor ผิดตอบ422 Product lists ยัง scaffold
- Guest data cleanup: ลบเมื่อ expires_at ผ่านไปอีก24ชั่วโมงและยังไม่ได้ claim ใช้ script dry-run/--apply ต้องตั้ง scheduler เอง; ไม่ลบไฟล์ของข้อมูลที่ย้ายเข้าบัญชีแล้ว

## 5. Endpoint contracts

Success ของ scaffold เป็น proposed schema เท่านั้น หลังผ่าน auth และ input validation จะได้ 501 handler ไม่มี business operation แต่ auth guard อาจอ่าน DB

### 5.1. POST /api/v1/auth/login

- Purpose: Login
- Authentication: Public + Origin สำหรับ mutation
- Status: Implemented
- Request Headers: Accept: application/json; Content-Type: application/json; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: {"application/json": {"schema": {"$ref": "#/components/schemas/LoginRequest"}}}
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/TokenResponse"}}}
- Error Responses: 401, 403, 422, 429; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.2. POST /api/v1/auth/refresh

- Purpose: Refresh Token
- Authentication: Refresh cookie + Origin
- Status: Implemented
- Request Headers: Accept: application/json; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/TokenResponse"}}}
- Error Responses: 401, 403, 422, 429; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.3. POST /api/v1/auth/logout

- Purpose: Logout
- Authentication: Refresh cookie + Origin
- Status: Implemented
- Request Headers: Accept: application/json; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 204 {}
- Error Responses: 401, 403, 422, 429; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.4. POST /api/v1/auth/guest-sessions

- Purpose: Create Guest Session
- Authentication: Public + Origin สำหรับ mutation
- Status: Implemented
- Request Headers: Accept: application/json; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 201 {"application/json": {"schema": {"$ref": "#/components/schemas/GuestSessionResponse"}}}; 200 {"application/json": {"schema": {"$ref": "#/components/schemas/GuestSessionResponse"}}}
- Error Responses: 401, 403, 422, 429; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.5. GET /api/v1/auth/guest-sessions/current

- Purpose: Get Guest Session
- Authentication: Guest cookie
- Status: Implemented
- Request Headers: Accept: application/json
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/GuestSessionResponse"}}}
- Error Responses: 401, 403, 422, 429; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.6. POST /api/v1/auth/guest-sessions/current/claim

- Purpose: Claim Guest Session
- Authentication: User Bearer + Guest cookie + Origin
- Status: Implemented
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/GuestClaimResponse"}}}
- Error Responses: 401, 403, 422, 429; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.7. GET /api/v1/users/me

- Purpose: Get Profile
- Authentication: User Bearer
- Status: Implemented
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/UserProfileResponse"}}}
- Error Responses: 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.8. PATCH /api/v1/users/me

- Purpose: [Scaffold] update profile
- Authentication: User Bearer
- Status: Scaffold — authenticated valid requests return 501
- Request Headers: Accept: application/json; Content-Type: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: {"application/json": {"schema": {"$ref": "#/components/schemas/UpdateProfileRequest"}}}
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/UserProfileResponse"}}}
- Error Responses: 501, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.9. POST /api/v1/chat-sessions

- Purpose: create chat session
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Implemented
- Request Headers: Accept: application/json; Content-Type: application/json; Authorization: Bearer <access_token> เมื่อใช้ User; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: {"application/json": {"schema": {"$ref": "#/components/schemas/CreateSessionRequest"}}}
- Success Response: 201 {"application/json": {"schema": {"$ref": "#/components/schemas/SessionResponse"}}}
- Error Responses: 404, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.10. GET /api/v1/chat-sessions

- Purpose: list chat sessions
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Implemented
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: ไม่มี
- Query Parameters: limit {"type": "integer", "maximum": 100, "minimum": 1, "default": 20, "title": "Limit"}; cursor {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Cursor"}
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/SessionListResponse"}}}
- Error Responses: 404, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.11. GET /api/v1/chat-sessions/{session_id}

- Purpose: get chat session
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Implemented
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: session_id {"type": "string", "format": "uuid", "title": "Session Id"}
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/SessionResponse"}}}
- Error Responses: 404, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.12. DELETE /api/v1/chat-sessions/{session_id}

- Purpose: delete chat session
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Implemented
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: session_id {"type": "string", "format": "uuid", "title": "Session Id"}
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 204 {}
- Error Responses: 404, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.13. GET /api/v1/chat-sessions/{session_id}/messages

- Purpose: list messages
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Implemented
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: session_id {"type": "string", "format": "uuid", "title": "Session Id"}
- Query Parameters: limit {"type": "integer", "maximum": 100, "minimum": 1, "default": 20, "title": "Limit"}; cursor {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Cursor"}
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/MessageListResponse"}}}
- Error Responses: 404, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.14. POST /api/v1/chat-sessions/{session_id}/messages

- Purpose: [Scaffold] send message
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Scaffold — authenticated valid requests return 501
- Request Headers: Accept: application/json; Content-Type: application/json; Authorization: Bearer <access_token> เมื่อใช้ User; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: session_id {"type": "string", "format": "uuid", "title": "Session Id"}
- Query Parameters: ไม่มี
- Request Body: {"application/json": {"schema": {"$ref": "#/components/schemas/SendMessageRequest"}}}
- Success Response: 201 {"application/json": {"schema": {"$ref": "#/components/schemas/SendMessageResponse"}}}
- Error Responses: 501, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.15. POST /api/v1/images

- Purpose: Upload Image
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Implemented
- Request Headers: Accept: application/json; Content-Type: multipart/form-data; Authorization: Bearer <access_token> เมื่อใช้ User; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: {"multipart/form-data": {"schema": {"$ref": "#/components/schemas/Body_upload_image_api_v1_images_post"}}}
- Success Response: 201 {"application/json": {"schema": {"$ref": "#/components/schemas/ImageUploadResponse"}}}
- Error Responses: 401, 403, 413, 415, 422; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.16. GET /api/v1/images/{image_id}

- Purpose: [Scaffold] get image
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Scaffold — authenticated valid requests return 501
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: image_id {"type": "string", "format": "uuid", "title": "Image Id"}
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/ImageDetailResponse"}}}
- Error Responses: 501, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.17. DELETE /api/v1/images/{image_id}

- Purpose: [Scaffold] delete image
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Scaffold — authenticated valid requests return 501
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: image_id {"type": "string", "format": "uuid", "title": "Image Id"}
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 204 {}
- Error Responses: 501, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.18. POST /api/v1/product-search/by-image

- Purpose: Search By Image
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Implemented
- Request Headers: Accept: application/json; Content-Type: application/json; Authorization: Bearer <access_token> เมื่อใช้ User; Origin: <allowed origin> ตาม policy กลาง
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: {"application/json": {"schema": {"$ref": "#/components/schemas/ProductSearchByImageRequest"}}}
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/ProductSearchByImageResponse"}}}
- Error Responses: 401, 404, 422, 503, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.19. GET /api/v1/products

- Purpose: [Scaffold] list products
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Scaffold — authenticated valid requests return 501
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: ไม่มี
- Query Parameters: q {"anyOf": [{"type": "string", "maxLength": 200}, {"type": "null"}], "title": "Q"}; category {"anyOf": [{"type": "string", "maxLength": 100}, {"type": "null"}], "title": "Category"}; brand {"anyOf": [{"type": "string", "maxLength": 100}, {"type": "null"}], "title": "Brand"}; limit {"type": "integer", "maximum": 100, "minimum": 1, "default": 20, "title": "Limit"}; cursor {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Cursor"}
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/ProductListResponse"}}}
- Error Responses: 501, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.20. GET /api/v1/products/{product_id}

- Purpose: [Scaffold] get product
- Authentication: User Bearer หรือ Guest cookie; Guest mutation ต้องมี Origin
- Status: Scaffold — authenticated valid requests return 501
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: product_id {"type": "string", "format": "uuid", "title": "Product Id"}
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/ProductResponse"}}}
- Error Responses: 501, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.21. POST /api/v1/admin/image-index

- Purpose: Rebuild Image Index
- Authentication: User Bearer + role admin
- Status: Implemented
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/IndexCatalogResponse"}}}
- Error Responses: 404, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.22. GET /api/v1/health

- Purpose: Health
- Authentication: Public + Origin สำหรับ mutation
- Status: Implemented
- Request Headers: Accept: application/json
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/HealthResponse"}}}
- Error Responses: 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.23. GET /api/v1/ready

- Purpose: [Scaffold] readiness
- Authentication: User Bearer + role admin
- Status: Scaffold — authenticated valid requests return 501
- Request Headers: Accept: application/json; Authorization: Bearer <access_token> เมื่อใช้ User
- Path Parameters: ไม่มี
- Query Parameters: ไม่มี
- Request Body: ไม่มี
- Success Response: 200 {"application/json": {"schema": {"$ref": "#/components/schemas/ReadinessResponse"}}}
- Error Responses: 501, 422, 401, 403; unexpected failure อาจเป็น 500
- Validation Rules / Business Rules / Security: ดูข้อกำหนดกลางหัวข้อ 2–4 และ schema fields หัวข้อ 6; ตรวจสิทธิ์ก่อน business logic

### 5.24. PATCH /api/v1/chat-sessions/{session_id}

- Purpose: เปลี่ยนชื่อแชตของ principal ปัจจุบัน
- Endpoint / Method: `/api/v1/chat-sessions/{session_id}` / PATCH
- Authentication Required: User Bearer หรือ Guest cookie
- Request Headers: Content-Type: application/json; Authorization: Bearer <access_token> สำหรับ User; Origin ที่อนุญาตสำหรับ Guest
- Path Parameters: session_id UUID (รับ ID เดิมได้)
- Query Parameters: ไม่มี
- Request Body: `{ "title": "สมุดที่สนใจ" }`
- Success Response: 200 SessionResponse ที่ updated_at เปลี่ยนแล้ว
- Error Responses: 401 credential expired/revoked; 403 Origin; 404 missing/not-owned/deleted; 422 invalid title; 500 unexpected failure
- Validation Rules: trim title ก่อนตรวจ; 1–200 chars ห้าม null/blank
- Business Rules: Guest lock ก่อน chat lock ตรวจ live session และ ownership ใน transaction; ไม่แก้ summary หรือ messages
- Security Considerations: ใช้เจ้าของจาก principal เท่านั้น ไม่มี owner ID ใน request; Cache-Control: no-store
- Example Request: `PATCH /api/v1/chat-sessions/019a0000-0000-7000-8000-000000000001` พร้อม body ข้างต้น
- Example Response: `{ "id":"019a0000-0000-7000-8000-000000000001", "title":"สมุดที่สนใจ", "summary":null, "created_at":"2026-10-04T00:00:00Z", "updated_at":"2026-10-04T01:00:00Z" }`

## 6. Schema fields

Required อ้างอิง OpenAPI; nullable ดู anyOf/null และค่า default

### Body_upload_image_api_v1_images_post

| Field | Required | Schema |
|---|---|---|
| file | Yes | `{"type": "string", "contentMediaType": "application/octet-stream", "description": "JPEG / PNG / WEBP, checked by content"}` |

### CreateSessionRequest

| Field | Required | Schema |
|---|---|---|
| title | No | `{"anyOf": [{"type": "string", "maxLength": 200, "minLength": 1}, {"type": "null"}]}` |

### ErrorBody

| Field | Required | Schema |
|---|---|---|
| code | Yes | `{"type": "string"}` |
| message | Yes | `{"type": "string"}` |
| details | No | `{"additionalProperties": true, "type": "object", "default": {}}` |

### ErrorResponse

| Field | Required | Schema |
|---|---|---|
| error | Yes | `{"$ref": "#/components/schemas/ErrorBody"}` |

### GuestClaimResponse

| Field | Required | Schema |
|---|---|---|
| guest_session_id | Yes | `{"type": "string", "format": "uuid"}` |
| user_id | Yes | `{"type": "string", "format": "uuid"}` |
| chat_sessions_claimed | Yes | `{"type": "integer", "minimum": 0.0}` |
| images_claimed | Yes | `{"type": "integer", "minimum": 0.0}` |

### GuestSessionResponse

| Field | Required | Schema |
|---|---|---|
| id | Yes | `{"type": "string", "format": "uuid"}` |
| expires_at | Yes | `{"type": "string", "format": "date-time"}` |
| image_upload_limit | No | `{"type": "integer", "const": 3, "default": 3}` |
| image_uploads_used | Yes | `{"type": "integer", "maximum": 3.0, "minimum": 0.0}` |
| image_uploads_remaining | Yes | `{"type": "integer", "maximum": 3.0, "minimum": 0.0}` |

### HealthResponse

| Field | Required | Schema |
|---|---|---|
| status | No | `{"type": "string", "const": "ok", "default": "ok"}` |

### ImageDetailResponse

| Field | Required | Schema |
|---|---|---|
| id | Yes | `{"type": "string", "format": "uuid"}` |
| status | Yes | `{"type": "string", "description": "ready | processing | failed"}` |
| mime_type | Yes | `{"type": "string"}` |
| size_bytes | Yes | `{"type": "integer"}` |
| created_at | Yes | `{"type": "string", "format": "date-time"}` |

### ImageUploadResponse

| Field | Required | Schema |
|---|---|---|
| id | Yes | `{"type": "string", "format": "uuid"}` |
| status | Yes | `{"type": "string", "description": "ready | processing | failed"}` |

### IndexCatalogResponse

| Field | Required | Schema |
|---|---|---|
| products | Yes | `{"type": "integer"}` |
| chunks_embedded | Yes | `{"type": "integer"}` |
| chunks_unchanged | Yes | `{"type": "integer"}` |
| chunks_deleted | Yes | `{"type": "integer"}` |
| warnings | No | `{"items": {"type": "string"}, "type": "array", "default": []}` |
| seconds | Yes | `{"type": "number"}` |

### LoginRequest

| Field | Required | Schema |
|---|---|---|
| email | Yes | `{"type": "string", "maxLength": 320, "format": "email"}` |
| password | Yes | `{"type": "string", "maxLength": 1024, "minLength": 1}` |

### MessageListResponse

| Field | Required | Schema |
|---|---|---|
| items | Yes | `{"items": {"$ref": "#/components/schemas/MessageResponse"}, "type": "array"}` |
| next_cursor | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |

### MessageResponse

| Field | Required | Schema |
|---|---|---|
| id | Yes | `{"type": "string", "format": "uuid"}` |
| session_id | Yes | `{"type": "string", "format": "uuid"}` |
| sequence_number | Yes | `{"type": "integer", "exclusiveMinimum": 0.0}` |
| role | Yes | `{"type": "string", "enum": ["user", "assistant", "system"]}` |
| content | Yes | `{"type": "string"}` |
| image_id | No | `{"anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]}` |
| product_refs | No | `{"anyOf": [{"items": {"additionalProperties": true, "type": "object"}, "type": "array"}, {"type": "null"}]}` |
| created_at | Yes | `{"type": "string", "format": "date-time"}` |

### ProductListResponse

| Field | Required | Schema |
|---|---|---|
| items | Yes | `{"items": {"$ref": "#/components/schemas/ProductResponse"}, "type": "array"}` |
| next_cursor | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |

### ProductMatch

| Field | Required | Schema |
|---|---|---|
| product_id | Yes | `{"type": "string", "format": "uuid"}` |
| sku | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| name | Yes | `{"type": "string"}` |
| category | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| brand | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| price | Yes | `{"anyOf": [{"type": "number"}, {"type": "null"}], "description": "null when the catalog has no price"}` |
| currency | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| availability | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}], "description": "null when the catalog has no availability data"}` |
| source_ref | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}], "description": "where the product data came from"}` |
| image_url | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| match_type | Yes | `{"type": "string", "enum": ["exact", "similar"]}` |
| score | Yes | `{"type": "number", "description": "retrieval score 0-1"}` |

### ProductResponse

| Field | Required | Schema |
|---|---|---|
| id | Yes | `{"type": "string", "format": "uuid"}` |
| sku | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| name | Yes | `{"type": "string"}` |
| category | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| brand | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| description | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| price | No | `{"anyOf": [{"type": "number"}, {"type": "null"}]}` |
| currency | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| availability | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| source_ref | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |

### ProductSearchByImageRequest

| Field | Required | Schema |
|---|---|---|
| image_id | Yes | `{"type": "string", "format": "uuid"}` |
| limit | No | `{"type": "integer", "maximum": 10.0, "minimum": 1.0, "default": 5}` |

### ProductSearchByImageResponse

| Field | Required | Schema |
|---|---|---|
| image_id | Yes | `{"type": "string", "format": "uuid"}` |
| description | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}], "description": "the vision model's reading of the photo; null on the fast path"}` |
| match_level | Yes | `{"type": "string", "enum": ["exact", "similar", "none"]}` |
| matches | Yes | `{"items": {"$ref": "#/components/schemas/ProductMatch"}, "type": "array"}` |
| path | Yes | `{"type": "string", "enum": ["fast", "full"], "description": "fast = embedding search only; full = vision model used"}` |
| timings_s | No | `{"additionalProperties": {"type": "number"}, "type": "object", "default": {}}` |

### ReadinessResponse

| Field | Required | Schema |
|---|---|---|
| status | Yes | `{"type": "string", "enum": ["ready", "not_ready"]}` |
| dependencies | Yes | `{"additionalProperties": {"type": "string"}, "type": "object"}` |

### SendMessageRequest

| Field | Required | Schema |
|---|---|---|
| content | No | `{"type": "string", "maxLength": 4000, "description": "Proposed MVP limit, pending policy confirmation", "default": ""}` |
| image_id | No | `{"anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]}` |

### SendMessageResponse

| Field | Required | Schema |
|---|---|---|
| user_message | Yes | `{"$ref": "#/components/schemas/MessageResponse"}` |
| assistant_message | Yes | `{"$ref": "#/components/schemas/MessageResponse"}` |

### SessionListResponse

| Field | Required | Schema |
|---|---|---|
| items | Yes | `{"items": {"$ref": "#/components/schemas/SessionResponse"}, "type": "array"}` |
| next_cursor | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |

### SessionResponse

| Field | Required | Schema |
|---|---|---|
| id | Yes | `{"type": "string", "format": "uuid"}` |
| title | Yes | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| summary | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| created_at | Yes | `{"type": "string", "format": "date-time"}` |
| updated_at | Yes | `{"type": "string", "format": "date-time"}` |

### TokenResponse

| Field | Required | Schema |
|---|---|---|
| access_token | Yes | `{"type": "string"}` |
| token_type | No | `{"type": "string", "const": "bearer", "default": "bearer"}` |
| expires_in | Yes | `{"type": "integer", "exclusiveMinimum": 0.0}` |

### UpdateProfileRequest

| Field | Required | Schema |
|---|---|---|
| display_name | No | `{"anyOf": [{"type": "string", "maxLength": 120, "minLength": 1}, {"type": "null"}]}` |

### UserProfileResponse

| Field | Required | Schema |
|---|---|---|
| id | Yes | `{"type": "string", "format": "uuid"}` |
| email | Yes | `{"type": "string"}` |
| display_name | No | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| role | Yes | `{"type": "string"}` |

## 7. Examples

Local Origin ค่าเริ่มต้น http://localhost:3000 JSON ตัวอย่างไม่ใช่ credential จริง

```http
POST /api/v1/auth/login HTTP/1.1
Content-Type: application/json
Origin: http://localhost:3000

{"email":"demo@example.com","password":"<password>"}
```

200 พร้อม Set-Cookie สำหรับ refresh:

```json
{"access_token":"<JWT>","token_type":"bearer","expires_in":899}
```

```http
POST /api/v1/auth/guest-sessions HTTP/1.1
Origin: http://localhost:3000
```

201 พร้อม Set-Cookie สำหรับ Guest:

```json
{"id":"123e4567-e89b-42d3-a456-426614174000","expires_at":"2026-10-04T00:00:00Z","image_upload_limit":3,"image_uploads_used":0,"image_uploads_remaining":3}
```

```http
POST /api/v1/product-search/by-image HTTP/1.1
Content-Type: application/json
Origin: http://localhost:3000
Cookie: ink_buddy_guest=<guest token>

{"image_id":"123e4567-e89b-42d3-a456-426614174000","limit":5}
```

รายละเอียดการใช้ cookie jar, Swagger และ scripts ดู [auth/README.md](auth/README.md)

## 8. Trade-offs และงานถัดไป

- DB session lookup ทุกคำขอเพิ่ม query แต่ทำ Logout/revoke/inactive account มีผลทันที
- Strict refresh reuse ทำ concurrent refresh revoke session ได้ client ต้องทำ single-flight
- memory limiter ง่ายสำหรับ localหนึ่ง worker แต่ไม่รองรับการจำกัดรวมหลายprocessหรือการรักษา counters หลัง restart
- Guest quota ต่อ session ไม่ป้องกันการล้าง cookie ต้องติดตาม abuse และพัฒนา rate-limit policy ตามโหลดจริง
- ยังไม่ทำ Chat logic, product endpoints, image detail/delete, streaming, model status และ frontend auth UI
- ไม่ตั้ง scheduler cleanup อัตโนมัติ; production ต้องตั้งพร้อม monitoring ก่อนใช้งานจริง
- Image pipeline ไม่ได้เปลี่ยนโมเดลหรือเกณฑ์ exact ในงาน Auth

## 9. Evidence

- Integration tests ผ่าน PostgreSQL16 + pgvector ใน Podman ใช้ database ชั่วคราวแยกจาก ink_buddy และ drop หลัง tests
- มี tests สำหรับ JWT, refresh rotation/reuse/concurrency, immediate Logout, Guest quota/concurrency, ownership, claim, cookies/Origin, cleanup และ migrations001–003
- Unit/regression tests แยกจาก PostgreSQL tests; รันทั้งหมดตามคำสั่งใน auth README
- SQL init ปัจจุบันมี13ตาราง; ฐาน local apply migration003 พร้อม backup แล้ว
- OpenAPI snapshot generate จาก app.openapi(); generate ใหม่เมื่อ routes/schemas เปลี่ยน

## 10. Guest session และโครงสร้างข้อมูล

Guest access session ครอบคลุมหลาย Chat sessions มีอายุ24ชั่วโมงและโควตา3รูป; user_id/guest_session_id ของแชตและรูปมีเจ้าของอย่างใดอย่างหนึ่งผ่าน CHECK XOR Token hash/expiry/revoked/claimed และ counter อยู่ใน guest_sessions ไม่มี Guest ปลอมใน users

Token lifecycle, whitelist และข้อจำกัดดู [TOKEN_AUTH_FLOW.md](../architecture/TOKEN_AUTH_FLOW.md); คอลัมน์ constraints/indexes/migration ดู [DATABASE_SCHEMA.md](../../database/DATABASE_SCHEMA.md)

## ผลตรวจหลัง implementation

2026-10-03: regression111passed;22skippedประกอบด้วยPostgreSQLtests18ที่รันแยกและmodel-dependent4 PostgreSQLintegrationรันแยกผ่าน18testsบนPodman dependencycheckผ่าน Localhealth200,profileไม่มีtoken401 ไม่มีการรันโมเดลAIจริงในAuthtests

## ผลรีวิว implementation ล่าสุด

ตรวจเอกสาร 2026-10-03: ดู [Auth review](auth/AUTH_REVIEW.md) สำหรับเคส token/Guest/authorization และประเด็น P2 ที่ยังเปิดอยู่ ฟีเจอร์ที่ระบุ scaffold เป็น proposed contract และยังไม่ทำ business logic ผลทดสอบ Auth ใช้ fake Vision pipeline จึงไม่ยืนยันโมเดลจริง


## UUIDv7 (2026-10-03)

ID ใหม่ที่เป็น UUID ใช้ UUIDv7: database defaults เรียก `public.ink_buddy_uuid_v7()` และ Python ใช้ `app.core.identifiers.uuid7()` ชนิด column/API ยังคง UUID เพื่อรองรับ ID เดิม ไม่มีการเปลี่ยน primary/foreign keys ที่มีอยู่ ฐานเดิมต้อง apply `database/migrations/004_uuid_v7.sql` หลัง 003; ฐานใหม่ใช้ init ปัจจุบัน migrations 001–003 เก็บเป็นประวัติเดิม

UUIDv7 มี Unix timestamp ระดับ millisecond และ random bits ตาม [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) ไม่รับประกันลำดับภายใน millisecond หรือเมื่อ clock ย้อนกลับ ไม่ใช้ ID เป็น credential และยังตรวจ ownership ตามเดิม PostgreSQL 16 ใช้ compatibility function เพราะ built-in generator เป็น UUIDv4; ไม่มีการเปลี่ยนคอลัมน์ integer เช่น product_image_embeddings.id

## Chat Session implementation — 2026-10-04

สร้างแชต title omitted/null ใช้ “แชตใหม่”; title ที่ส่งมาต้อง trim และมี 1–200 chars ใช้ UUIDv7 และ owner จาก principal API ไม่สร้างข้อความจำลอง

รายการเรียง updated_at DESC,id DESC; next_cursor เป็น opaque base64 JSON ผูก owner และชนิดรายการ แชตที่ updated_at เปลี่ยนระหว่าง pagination อาจย้ายหน้า ให้ reload รายการเพื่อดูสถานะล่าสุด ไม่ใช่ snapshot pagination

ประวัติโหลดหน้าล่าสุดก่อนด้วย sequence_number และคืน items ในหน้าเรียงเก่าไปใหม่; cursor ของ session/owner อื่นตอบ422 Frontend prepend ข้อความเก่าและ deduplicate ID

DELETE soft delete ผ่าน deleted_at คืน204; อ่าน/แก้ไข/ลบซ้ำตอบ404 เก็บ messages/images และไม่คืน Guest quota ทุก Guest operation lock Guest ก่อนแชตเพื่อ serialize กับ claim Read endpoints ใช้ transaction request-scoped; routes เก็บ Cache-Control: no-store

Frontend `/chat`, `/chat/{id}`, `/login` พร้อม Guest/User/claim และ prompt draft 3 รายการ ปุ่มส่งยัง disabled; POST messages ยัง501 รายละเอียด setup และโครง components ดู [Frontend README](../../frontend/README.md)

## Register / Password Recovery — 2026-10-04


# Register

## Purpose

สร้างบัญชี role=user active แล้ว Login ได้ทันที ไม่บังคับยืนยันอีเมล

## Endpoint

`/api/v1/auth/register`

## Method

POST

## Authentication Required

ไม่ต้อง Login; policy public และตรวจ Origin

## Request Headers

`Content-Type: application/json`, `Origin: http://localhost:3000` (ต้องอยู่ใน CORS_ORIGINS)

## Path Parameters

ไม่มี

## Query Parameters

ไม่มี

## Request Body

```json
{
  "email": "new@example.com",
  "password": "ExamplePass123!",
  "display_name": "ผู้ใช้ใหม่"
}
```

## Success Response

HTTP 201; Cache-Control: no-store

## Error Responses

409 EMAIL_ALREADY_REGISTERED; 503 เมื่อ role user ยังไม่ได้ตั้งค่า; 403 ORIGIN_NOT_ALLOWED, 422 validation, 429 rate limit พร้อม Retry-After; error envelope ตาม contract กลาง

## Validation Rules

email ถูก normalize เป็น lowercase; password 12–24 ตัวอักษร; display_name optional trim 1–120; extra fields เช่น role ถูกปฏิเสธ

## Business Rules

สร้างบัญชี role=user active แล้ว Login ได้ทันที ไม่บังคับยืนยันอีเมล. Reset token อายุเริ่มต้น 15 นาที ใช้ครั้งเดียว; ขอใหม่ revoke ตัวเดิม และ cooldown 60 วินาทีต่อบัญชี การสมัคร/รีเซ็ตไม่ออก JWT อัตโนมัติและไม่ claim Guest

## Security Considerations

Rate limit 5/hour/IP; Argon2id สำหรับ password; reset token สุ่มและเก็บเฉพาะ hash; reset ทำใน transaction พร้อม user/token/session locks การส่งอีเมลเป็น background best effort ดูคู่มือ Auth สำหรับข้อจำกัด SMTP

## Example Request

```http
POST /api/v1/auth/register HTTP/1.1
Origin: http://localhost:3000
Content-Type: application/json

{"email": "new@example.com", "password": "ExamplePass123!", "display_name": "ผู้ใช้ใหม่"}
```

## Example Response

```json
{"message": "Account created. Please log in."}
```

# Forgot Password

## Purpose

ขอลิงก์รีเซ็ตรหัสผ่านทางอีเมล

## Endpoint

`/api/v1/auth/forgot-password`

## Method

POST

## Authentication Required

ไม่ต้อง Login; policy public และตรวจ Origin

## Request Headers

`Content-Type: application/json`, `Origin: http://localhost:3000` (ต้องอยู่ใน CORS_ORIGINS)

## Path Parameters

ไม่มี

## Query Parameters

ไม่มี

## Request Body

```json
{
  "email": "new@example.com"
}
```

## Success Response

HTTP 202; Cache-Control: no-store

## Error Responses

ไม่มีบัญชี/inactive/cooldown/SMTP failure ยังคงคืนข้อความทั่วไป 202; 403 ORIGIN_NOT_ALLOWED, 422 validation, 429 rate limit พร้อม Retry-After; error envelope ตาม contract กลาง

## Validation Rules

email รูปแบบถูกต้อง ยาวไม่เกิน 320

## Business Rules

ขอลิงก์รีเซ็ตรหัสผ่านทางอีเมล. Reset token อายุเริ่มต้น 15 นาที ใช้ครั้งเดียว; ขอใหม่ revoke ตัวเดิม และ cooldown 60 วินาทีต่อบัญชี การสมัคร/รีเซ็ตไม่ออก JWT อัตโนมัติและไม่ claim Guest

## Security Considerations

Rate limit 10/hour/IP; Argon2id สำหรับ password; reset token สุ่มและเก็บเฉพาะ hash; reset ทำใน transaction พร้อม user/token/session locks การส่งอีเมลเป็น background best effort ดูคู่มือ Auth สำหรับข้อจำกัด SMTP

## Example Request

```http
POST /api/v1/auth/forgot-password HTTP/1.1
Origin: http://localhost:3000
Content-Type: application/json

{"email": "new@example.com"}
```

## Example Response

```json
{"message": "If the account is eligible, a reset link will be sent."}
```

# Reset Password

## Purpose

ตั้งรหัสผ่านใหม่และ revoke Login sessions/refresh tokens ทั้งหมดของบัญชี

## Endpoint

`/api/v1/auth/reset-password`

## Method

POST

## Authentication Required

ไม่ต้อง Login; policy public และตรวจ Origin

## Request Headers

`Content-Type: application/json`, `Origin: http://localhost:3000` (ต้องอยู่ใน CORS_ORIGINS)

## Path Parameters

ไม่มี

## Query Parameters

ไม่มี

## Request Body

```json
{
  "token": "<opaque token from email>",
  "password": "Replacement123!"
}
```

## Success Response

HTTP 200; Cache-Control: no-store

## Error Responses

400 INVALID_RESET_TOKEN สำหรับไม่พบ/หมดอายุ/ใช้แล้ว/revoked/inactive; 403 ORIGIN_NOT_ALLOWED, 422 validation, 429 rate limit พร้อม Retry-After; error envelope ตาม contract กลาง

## Validation Rules

token 43–128 ตัวอักษร; password 12–24; extra fields ถูกปฏิเสธ

## Business Rules

ตั้งรหัสผ่านใหม่และ revoke Login sessions/refresh tokens ทั้งหมดของบัญชี. Reset token อายุเริ่มต้น 15 นาที ใช้ครั้งเดียว; ขอใหม่ revoke ตัวเดิม และ cooldown 60 วินาทีต่อบัญชี การสมัคร/รีเซ็ตไม่ออก JWT อัตโนมัติและไม่ claim Guest

## Security Considerations

Rate limit 10/hour/IP; Argon2id สำหรับ password; reset token สุ่มและเก็บเฉพาะ hash; reset ทำใน transaction พร้อม user/token/session locks การส่งอีเมลเป็น background best effort ดูคู่มือ Auth สำหรับข้อจำกัด SMTP

## Example Request

```http
POST /api/v1/auth/reset-password HTTP/1.1
Origin: http://localhost:3000
Content-Type: application/json

{"token": "<opaque token from email>", "password": "Replacement123!"}
```

## Example Response

```json
{"message": "Password changed. Please log in again."}
```

## Password policy — 2026-10-05

การตั้งรหัสผ่านใหม่ผ่าน Register/Reset/local script ต้องยาว 12–24 ตัวอักษร มี a–z, A–Z, 0–9 และอย่างน้อยหนึ่ง ASCII punctuation (เช่น !@#_-); ห้าม Unicode whitespace ทุกชนิด ไม่มีการ trim Password ภาษาอื่นยังใช้ร่วมได้แต่ไม่นับแทนกลุ่มภาษาอังกฤษหรืออักขระพิเศษ Frontend ตรวจและยืนยันสองช่อง Backend ตรวจซ้ำและตอบ 422 เมื่อไม่ผ่าน Login ยังคงรับ 1–1024 ตัวเพื่อรองรับบัญชีเดิม ไม่มีการแก้ password hash เดิมโดย migration
