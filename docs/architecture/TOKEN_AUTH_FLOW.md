# Ink Buddy — Token และการควบคุมสิทธิ์ API

เอกสารสำหรับทีม · อัปเดต 2026-10-03

**สถานะ:** แนวทางออกแบบสำหรับขั้น Auth ยังไม่ได้ implement ปัจจุบัน backend ใช้ dev user ส่วน routes Auth/Guest เป็น scaffold ที่ตอบ 501 เอกสารนี้ไม่ได้หมายความว่า JWT หรือ Guest token ใช้งานได้แล้ว

## 1. แนวคิดหลัก

API ต้องยืนยันตัวตนเป็นค่าเริ่มต้น กำหนดรายการ Public และรายการที่อนุญาต Guest อย่างชัดเจน API ใหม่ที่ยังไม่กำหนด policy ต้องถูกปฏิเสธก่อน ไม่เปิด Public โดยอัตโนมัติ

แยกหลักฐานการเข้าถึงเป็นสองชนิด:

| Token | ใครใช้ | รูปแบบที่เสนอ | การตรวจ |
|---|---|---|---|
| User access token | ผู้ใช้ที่ Login | JWT อายุสั้น ส่ง Authorization: Bearer | ตรวจ signature, algorithm ที่อนุญาต, issuer, audience, expiry และสถานะบัญชี |
| User refresh token | ผู้ใช้ที่ Login | ค่าสุ่มใน HttpOnly cookie; เก็บ hash ใน refresh_tokens | ตรวจ hash, expiry, revocation และ rotation |
| Guest token | ผู้ใช้ที่ยังไม่ Login | ค่าสุ่มใน HttpOnly cookie; เก็บ hash ใน guest_sessions | ตรวจ hash, expiry, revocation และ claimed state |

Guest token ระบุตัวตนชั่วคราว ไม่ได้ให้สิทธิ์เทียบเท่าบัญชีที่ Login ไม่ใช้ Guest token เป็น User JWT และไม่ใช้ dev user คนเดียวแทนลูกค้าทุกราย

## 2. ระดับสิทธิ์และ whitelist

ทุก path ใช้ prefix `/api/v1`

| ระดับ | Paths ที่เสนอ | หลักฐานที่ต้องมี |
|---|---|---|
| Public | POST /auth/login, POST /auth/guest-sessions, GET /health | ไม่ต้องมี token; login/session creation ต้องมี rate limit |
| Refresh credential | POST /auth/refresh, POST /auth/logout | refresh cookie; ไม่จำเป็นต้องมี access token ที่ยังไม่หมดอายุ |
| Guest หรือ User | /chat-sessions และ messages, /images, /products, POST /product-search/by-image | Guest token หรือ User access token ที่ถูกต้อง |
| User | GET/PATCH /users/me | User access token และบัญชีที่ active |
| Claim | POST /auth/guest-sessions/current/claim | ต้องมีทั้ง User access token และ Guest token |
| Guest credential | GET /auth/guest-sessions/current | Guest token |
| Admin | POST /admin/image-index | User access token + role admin |

Readiness `/ready` ต้องกำหนด policy ก่อน deploy อาจจำกัดสำหรับระบบตรวจสุขภาพภายใน; Swagger/OpenAPI ต้องกำหนดว่าจะเปิดให้ใครในแต่ละ environment เช่นกัน

Whitelist ต้องระบุ **method + route ที่ลงทะเบียน** ไม่ใช้การตรวจ prefix กว้าง ๆ เช่นอนุญาตทุกอย่างที่เริ่ม /auth เพราะ claim ต้องมีสิทธิ์ต่างจาก login และไม่เปิดทั้ง module ให้ Guest โดยไม่มีการตรวจแต่ละ operation

ตรวจสองขั้นเสมอ: (1) token ให้ principal ที่ถูกต้อง (2) principal มีสิทธิ์ทำ operation และเป็นเจ้าของ resource ที่ขอ แม้มี token ก็อ่านแชต/รูปของคนอื่นไม่ได้

## 3. Guest ได้ token เมื่อไร

เมื่อเปิดแอป frontend ตรวจ session ที่มีอยู่ก่อน ถ้ามี User session ให้ใช้บัญชี ถ้าไม่มีบัญชีแต่ Guest session ยังใช้ได้ ให้ใช้ Guest เดิม ถ้าไม่มีทั้งสองอย่างจึงขอสร้าง Guest session **ไม่สร้าง Guest ใหม่ทุกครั้งที่เรียก API**

```text
เปิดแอป
  |
  +-- User session ใช้งานได้ ----------> ใช้บัญชี
  |
  +-- Guest session ใช้งานได้ ---------> ใช้ Guest เดิม
  |
  +-- ไม่มี session ที่ใช้ได้
         |
         POST /api/v1/auth/guest-sessions
         |
         Server สร้าง session และ random token
         เก็บ token hash ใน DB
         ส่ง token จริงผ่าน Set-Cookie
         |
         Browser แนบ cookie ในคำขอถัดไป
```

HttpOnly cookie อ่านจาก JavaScript ไม่ได้ frontend จึงตรวจ session ผ่าน API ไม่ใช่อ่าน cookie โดยตรง สำหรับ User access token ที่หมดอายุให้ลอง refresh ตาม lifecycle ก่อนสรุปว่าเป็น Guest; API ที่มี token ผิดหรือหมดอายุห้าม downgrade เป็น Guest แบบเงียบ ๆ

ข้อเสนอ: create Guest session ใช้ session เดิมหาก cookie ยังถูกต้อง เพื่อไม่ให้ reload หรือหลาย tabs รีเซ็ตโควตา แต่การสร้างครั้งแรกพร้อมกันยังต้องจัดการฝั่ง client เช่น bootstrap request เดียว และใช้ rate limit ฝั่ง server

## 4. Cookie และการส่ง token

Guest/refresh cookie เสนอให้ใช้ HttpOnly, SameSite ตาม deployment และ Secure ใน production ส่งผ่าน HTTPS เก็บค่าดิบเฉพาะ browser ไม่ส่ง token hash ให้ client และไม่บันทึก token ใน logs

User access token เสนอเก็บใน memory ของ frontend แล้วส่ง:

```http
Authorization: Bearer <user_access_token>
```

Guest ส่ง cookie โดย browser อัตโนมัติ ไม่ส่ง guest_session_id ใน body เพื่อใช้เป็นหลักฐานสิทธิ์ UUID ที่รู้เพียงอย่างเดียวไม่ใช่ credential

Frontend/backend คนละ origin ต้องตั้ง credentials ของ HTTP client และ CORS ให้ตรงกันโดยระบุ origin ชัดเจน Cookie path/domain ต้องครอบคลุม routes ที่ใช้จริง และ mutation ที่อาศัย cookie ต้องมี CSRF/Origin protection; HttpOnly ไม่ได้ป้องกัน CSRF ด้วยตัวเอง

ชื่อ cookie, SameSite, path/domain และระยะเวลาหมดอายุยังต้องกำหนดตอน implementation ห้ามตั้ง Secure=false ใน production เพื่อแก้ปัญหา cookie

## 5. Server ตรวจคำขออย่างไร

```text
รับ request
   |
หา policy ของ method + route
   |
Public? --> ทำ validation/rate limit และดำเนินการ
   |
Protected
   |
ตรวจ credential ตาม policy --> ไม่ผ่าน: 401
   |
สร้าง principal: User หรือ Guest
   |
ตรวจ role/ประเภท principal --> ไม่มีสิทธิ์: 403
   |
ตรวจ ownership/quota --> resource ไม่พบหรือไม่ใช่เจ้าของ: 404
   |
เรียก service และบันทึก transaction
```

หากมีทั้ง User Bearer และ Guest cookie ให้ User เป็น principal สำหรับ routes ที่รับทั้งสองชนิด; Guest cookie เป็นหลักฐานเพิ่มเติมเฉพาะ claim หากส่ง User Bearer ที่ผิด ไม่ fallback ไป Guest เพื่อกลบข้อผิดพลาด ต้องกำหนดและทดสอบ rule นี้ใน resolver

แนวทาง code: แยก credential verification/principal resolver ออกจาก policy guards เช่น require_user, require_guest_or_user, require_admin และ require_claim_credentials แล้วผูก policy ทุก route พร้อม gate ที่ปฏิเสธ routes ที่ยังไม่ประกาศ policy

## 6. โควตา Guest: 3 รูปต่อ free session

Free session ในแบบที่เสนอหมายถึง **Guest access session** ซึ่งมีหลาย Chat sessions ได้ การเปิดแชตใหม่หรือ refresh หน้าไม่คืนโควตา สมมติฐานนี้ยังต้องยืนยันพร้อมอายุ session

- โควตาอยู่ใน DB: image_upload_limit=3 และ image_uploads_used
- ข้อเสนอ: นับรูปที่ผ่าน validation และบันทึกสำเร็จเท่านั้น
- ค้นด้วยรูปเดิมไม่เสียโควตาเพิ่ม; ลบรูปไม่คืนโควตา; อัปโหลดใหม่เป็นอีกคำขอให้นับใหม่
- Lock แถว Guest session ตรวจสถานะ/โควตา แล้วเพิ่ม counter และ insert รูปใน transaction เดียว เพื่อกันคำขอพร้อมกันเกิน 3
- เมื่อครบ เสนอ 403 GUEST_IMAGE_QUOTA_EXCEEDED พร้อม limit/used/remaining และชวน Login
- 429 ใช้กับ rate limit; ไม่ใช้แทนโควตาที่ไม่มีการคืนตามเวลา

การล้าง cookie หรือเปลี่ยนอุปกรณ์อาจสร้าง Guest ใหม่ได้ โควตาต่อ session ไม่ใช่โควตาต่อคน ต้องมี server rate limit ในการสร้าง session/เรียก AI เพิ่มตามการใช้งานจริง

## 7. User Login, Refresh และ Logout

```text
Login ด้วย email/password
  -> ตรวจ password hash และบัญชี active
  -> ออก access JWT + refresh cookie

Access token หมดอายุ
  -> POST /auth/refresh พร้อม refresh cookie
  -> ตรวจ refresh credential
  -> rotate: revoke ตัวเก่า และออก access/refresh ใหม่

Logout
  -> revoke refresh credential และล้าง cookie
  -> frontend ล้าง access token ใน memory
```

Rotation ต้อง atomic และตรวจ reuse; ต้องกำหนดว่าจะ revoke token family หรือ sessions ใดเมื่อพบ reuse ปัจจุบัน refresh_tokens ยังไม่มี family/replaced_by columns จึงอาจต้อง migration เพิ่มเมื่อเลือก policy นี้

การ revoke refresh token ไม่ทำให้ access JWT ที่ออกไปแล้วหมดอายุทันที หากต้องการ logout มีผลทันทีต้องตรวจ server-side session/revocation หรือใช้กลไกเพิ่มเติม มิฉะนั้น JWT ใช้ได้จนหมดอายุ ต้องเลือกนโยบายและอายุ access tokenให้เหมาะสม

## 8. ย้าย Guest เข้าบัญชีหลัง Login

Login สำเร็จไม่ได้ย้ายข้อมูลอัตโนมัติจนกว่า claim flow จะสำเร็จ client ส่งคำขอ claim พร้อมทั้ง User access token และ Guest cookie

Server lock Guest session ตรวจว่ายังไม่หมดอายุ/ถูก revoke/ถูก claim แล้วเปลี่ยน owner ของแชตและรูปเป็น user ใน transaction เดียว ตั้ง claimed_by_user_id/claimed_at และ revoke Guest token เมื่อ commit แล้วจึงล้าง Guest cookie

Claim ซ้ำต้องไม่ย้ายข้อมูลไปบัญชีอื่น อัปโหลดที่เกิดพร้อม claim ต้องใช้ lock/rules เดียวกัน รูปยังเป็น private หลังย้ายข้อมูล Guest เก่าที่หมดอายุไม่ควรถูก claim โดยไม่มีนโยบายเพิ่มเติม

## 9. Token expiry และข้อมูลหมดอายุเป็นคนละเรื่อง

Token หมดอายุทำให้เรียก API ไม่ได้ แต่ไม่ได้ลบประวัติหรือไฟล์ทันที ต้องกำหนด retention และ cleanup worker แยกกัน ลบแถว DB อย่างเดียวไม่ลบ private storage และต้องจัดลำดับลบตาม FK

ยังไม่ได้กำหนด Guest expiry, data retention, User access/refresh expiry และโควตาของผู้ Login ไม่ควรใส่ค่าตายตัวใน implementation จนตกลง policy

## 10. สิ่งที่มีแล้วและงานที่จะทำ

| ส่วน | สถานะ |
|---|---|
| DDL guest_sessions และ Guest ownership | มี SQL init/migration; ยังไม่ได้ apply ฐานจริง |
| โควตา 3 รูปใน business requirement | ยืนยันแล้ว |
| Routes Login/Refresh/Logout/Guest/Claim | มี scaffold ตอบ 501 |
| User JWT / Guest credential verification | ยังไม่ได้ implement |
| Default-deny policy และ Guest whitelist | ยังไม่ได้ implement |
| Quota transaction / Claim / Cleanup | ยังไม่ได้ implement |
| Admin guard | ยังไม่มี; image indexing คงปิดไว้ตาม default |

ลำดับที่แนะนำ: กำหนดอายุ token/cookie policy → สร้าง principal และ policy guards → Login/Refresh/Logout → Guest issuance/verification → ownership/quota → claim/cleanup พร้อมทดสอบ expired/revoked tokens, cross-owner access, Guest เข้า User/Admin ไม่ได้, routes ที่ไม่มี policy และ concurrency

## เอกสารที่เกี่ยวข้อง

- [API Spec](../api/API_SPEC.md)
- [Database Schema](../../database/DATABASE_SCHEMA.md)
- [Backend Structure](BACKEND_STRUCTURE.md)
- [Business Requirements](../../BUSINESS_REQUIREMENTS.md)
