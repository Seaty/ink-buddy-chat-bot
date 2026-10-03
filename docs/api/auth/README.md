# Authentication — Setup และวิธีลองใช้งาน

สถานะ2026-10-03: Login/Refresh/Logout, Guest create/current/claim, Profile GET และ principal guards implement แล้ว Profile PATCH ยังเป็น scaffold

## Local setup

1. เริ่ม PostgreSQL จาก docker ด้วย `podman compose up -d` เก็บ volume เดิมไว้
2. ฐานใหม่ใช้ init ปัจจุบัน ฐานเดิม apply migrations ตาม [Database Schema](../../../database/DATABASE_SCHEMA.md) local เครื่องนี้ apply003แล้วและสำรองไว้ .local/backups
3. backend/.env ต้องมี DATABASE_URL และ AUTH_JWT_SECRET อย่างน้อย32bytes ไม่มี default key งานนี้สร้าง local .env แล้วโดยไม่เปิดเผยค่าและไม่ commit
4. จาก backend ใช้ Python ใน .venv รันคำสั่งต่อไปนี้

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user --email demo@example.com --role user --display-name Demo
.\.venv\Scripts\python.exe -m scripts.create_user --email admin@example.com --role admin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

สคริปต์ถาม password แบบซ่อน รับ12–1024charsและยืนยันสองครั้ง ไม่ใส่ password ใน command arguments ไม่มีบัญชี/passwordเริ่มต้น และไม่เขียนทับบัญชีเดิม ยังไม่มี Register API

## นโยบาย token

| Credential | อายุ | ที่เก็บ |
|---|---|---|
| User access JWT | 15นาที หรือไม่เกิน session expiry | frontend memory; Authorization Bearer |
| Refresh token | สูงสุด7วันนับจาก Login | HttpOnly cookie; DB hash |
| Guest token | 24ชั่วโมงคงที่ | HttpOnly cookie; DB hash |

Refresh ต้อง single-flight: token เก่าที่ใช้ซ้ำทำให้ revokeทั้ง Login session รวม access tokenทันที Logout revokeเฉพาะsessionปัจจุบัน ไม่ใช่ทุกอุปกรณ์ Refresh เมื่อใกล้ครบ7วันไม่ขยายรอบ Login

Guest3รูปต่อsession อัปโหลดไม่ผ่าน validation/DBไม่สำเร็จไม่เสียโควตา เปิดแชตใหม่ไม่ reset ลบรูปไม่คืน Guestที่หมดอายุเรียกAPIไม่ได้ Claimต้องมีทั้งUserBearerและGuestcookieที่ยังvalid

## Origin / CORS / Cookies

Origin ค่าเริ่มต้น `http://localhost:3000` Login/CreateGuest/Refresh/Logout/Claim และ Guestmutationต้องมี Origin ที่ตรง CORS_ORIGINS มิฉะนั้น403 Bearer-only mutationไม่ต้องพึ่งcookieจึงไม่บังคับOrigin

Cookies ชื่อ ink_buddy_refresh/ink_buddy_guest, Path=/api/v1, HttpOnly, SameSite=Lax, ไม่มีDomain; Secureในproduction แนะนำ frontend fetch credentials:include และเก็บ access tokenในmemoryเท่านั้น

Swagger `/docs` มี Authorize สำหรับ UserBearer เปิดเฉพาะdevelopment หากต้อง Login/ใช้cookiesจากSwagger ให้เพิ่ม origin ของbackend เช่น http://localhost:8000 ใน CORS_ORIGINS แล้วrestart BrowserจะจัดการHttpOnlycookieเอง ไม่สามารถเติมGuestcookieผ่านJavaScriptAuthorizeได้

## ตัวอย่าง HTTP client

ตัวอย่างใช้ placeholder ไม่ใช่password/tokenจริง cookie jar เป็นไฟล์ที่มีcredential ห้ามcommit

```powershell
curl.exe -i -c guest.cookies -H "Origin: http://localhost:3000" -X POST http://localhost:8000/api/v1/auth/guest-sessions
curl.exe -b guest.cookies http://localhost:8000/api/v1/auth/guest-sessions/current
curl.exe -b guest.cookies -H "Origin: http://localhost:3000" -F "file=@sample.png" http://localhost:8000/api/v1/images
```

Login ส่ง JSON email/password ผ่านHTTPbody ไม่ส่งpasswordเป็นquery การทดลองจากPowerShellให้ใช้ไฟล์JSONชั่วคราวที่ดูแลอย่างปลอดภัยหรือHTTPclient:

```http
POST /api/v1/auth/login
Content-Type: application/json
Origin: http://localhost:3000

{"email":"demo@example.com","password":"<password>"}
```

เก็บrefreshcookieจากresponse และใช้access_tokenใน Authorization: Bearer สำหรับGET /users/me; POST /auth/refresh หมุนtokenใหม่โดยแนบrefreshcookie+Origin; POST /auth/logout ตอบ204และaccessเดิมใช้ต่อไม่ได้

Claim: POST /auth/guest-sessions/current/claim พร้อม UserBearer, Guestcookie และOrigin ย้ายทั้งแชต/รูป แล้วล้างGuestcookie ไม่claimอัตโนมัติเมื่อLogin

## Tests ผ่าน Podman PostgreSQL

จาก backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.test_auth_postgres
```

คำสั่งที่สองอ่าน credential จาก docker/.env โดยไม่print สร้างdatabaseชื่อ ink_buddy_test_<uuid>, initและทดสอบแล้วdropเฉพาะฐานที่สร้าง ไม่ล้างฐาน ink_buddy ผู้ใช้DBต้องมีCREATEDB Local compose userมีสิทธิ์นี้

ชุดทั่วไปskipPostgreSQL testsหากไม่มี test DSN ไม่ถือว่าการskipเป็นintegrationผ่าน ห้ามตั้ง INK_BUDDY_TEST_DATABASE_URL เป็นฐานใช้งานจริง

## Cleanup Guest

```powershell
.\.venv\Scripts\python.exe -m scripts.cleanup_guests
.\.venv\Scripts\python.exe -m scripts.cleanup_guests --apply
```

เริ่มด้วยdry-run คัดเลือกGuestที่หมดอายุมาแล้ว24ชั่วโมงและยังไม่claim --applyลบแชต/รูป/Guestพร้อมprivatefiles รันซ้ำได้ ตรวจpathภายในstorageก่อนลบ หากลบไฟล์ล้มเหลวDBไม่commitจึงretryได้ ข้อมูลGuestหมดอายุแล้วจึงไม่มีการให้ผู้ใช้เข้าถึงระหว่างcleanup

ตั้งWindowsTaskSchedulerให้รันคำสั่ง --apply ทุกชั่วโมง โดยกำหนดworkingdirectoryเป็น backend และใช้Pythonใน .venv; ขั้นนี้ยังไม่ได้สร้างscheduledtaskให้ ตรวจexitcode/logจากscheduler และอย่าlogcredentials ถ้าปริมาณข้อมูลโตให้เพิ่มbatch/workerต่อไป

## Production และข้อจำกัด

- APP_ENVIRONMENT=production เปิดSecurecookiesและปิด docs/redoc/openapi; ใช้HTTPS
- memory limiterรองรับหนึ่งworkerเท่านั้น หลายworkersตั้งAUTH_WORKERSให้ตรงและAUTH_LIMITER_STORAGE_URIไปsharedstore เช่นRedis (ติดตั้งdriver Redisเพิ่มเติมเมื่อตั้งinfraนี้)
- Login10/min/IP, Guestcreation5/hour/IP, Refresh30/min/IP, ImageSearch20/min/verifiedprincipal; ไม่trustX-Forwarded-Forโดยอัตโนมัติ
- ยังไม่มีfrontendAuthUI/Register/ResetPassword/EmailVerification และbusinesslogicChat/Product/ImageDetailDelete
- Visionintegrationtestsใช้fakepipeline ไม่ได้ยืนยันOllama/embeddingจริงหรือความแม่นยำค้นสินค้า

ดู [API_SPEC.md](../API_SPEC.md), [TOKEN_AUTH_FLOW.md](../../architecture/TOKEN_AUTH_FLOW.md) และ [Database Schema](../../../database/DATABASE_SCHEMA.md)

ผลล่าสุด: regression111passed และPostgreSQLintegration18passed; testsโมเดลจริง4รายการยังskipตามเงื่อนไขเดิม

## ผลรีวิวเพิ่มเติม

[AUTH_REVIEW.md](AUTH_REVIEW.md) อธิบายแต่ละเคสและข้อจำกัดล่าสุด การตั้ง shared limiter ใน custom create_app configuration ยังมีประเด็น P2 ต้องแก้และยืนยัน backend storage ก่อนใช้งานหลาย workers อีกประเด็นคือ partial image file เมื่อเขียนไฟล์ล้มเหลว ซึ่ง cleanup ที่อ้าง DB ไม่สามารถหาได้ทุกกรณี


## UUIDv7 (2026-10-03)

ID ใหม่ที่เป็น UUID ใช้ UUIDv7: database defaults เรียก `public.ink_buddy_uuid_v7()` และ Python ใช้ `app.core.identifiers.uuid7()` ชนิด column/API ยังคง UUID เพื่อรองรับ ID เดิม ไม่มีการเปลี่ยน primary/foreign keys ที่มีอยู่ ฐานเดิมต้อง apply `database/migrations/004_uuid_v7.sql` หลัง 003; ฐานใหม่ใช้ init ปัจจุบัน migrations 001–003 เก็บเป็นประวัติเดิม

UUIDv7 มี Unix timestamp ระดับ millisecond และ random bits ตาม [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) ไม่รับประกันลำดับภายใน millisecond หรือเมื่อ clock ย้อนกลับ ไม่ใช้ ID เป็น credential และยังตรวจ ownership ตามเดิม PostgreSQL 16 ใช้ compatibility function เพราะ built-in generator เป็น UUIDv4; ไม่มีการเปลี่ยนคอลัมน์ integer เช่น product_image_embeddings.id
