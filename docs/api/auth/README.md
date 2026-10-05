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

สคริปต์ถาม password แบบซ่อน รับ12–24charsและยืนยันสองครั้ง ไม่ใส่ password ใน command arguments ไม่มีบัญชี/passwordเริ่มต้น และไม่เขียนทับบัญชีเดิม Register API ใช้งานแล้ว; สคริปต์ local ใช้สร้าง Admin ได้

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
- Frontend Auth/Session UI ทำแล้ว; ยังไม่มี EmailVerification และ businesslogic SendMessage/Product/ImageDetailDelete
- Visionintegrationtestsใช้fakepipeline ไม่ได้ยืนยันOllama/embeddingจริงหรือความแม่นยำค้นสินค้า

ดู [API_SPEC.md](../API_SPEC.md), [TOKEN_AUTH_FLOW.md](../../architecture/TOKEN_AUTH_FLOW.md) และ [Database Schema](../../../database/DATABASE_SCHEMA.md)

ผลล่าสุด: regression111passed และPostgreSQLintegration18passed; testsโมเดลจริง4รายการยังskipตามเงื่อนไขเดิม

## ผลรีวิวเพิ่มเติม

[AUTH_REVIEW.md](AUTH_REVIEW.md) อธิบายแต่ละเคสและข้อจำกัดล่าสุด การตั้ง shared limiter ใน custom create_app configuration ยังมีประเด็น P2 ต้องแก้และยืนยัน backend storage ก่อนใช้งานหลาย workers อีกประเด็นคือ partial image file เมื่อเขียนไฟล์ล้มเหลว ซึ่ง cleanup ที่อ้าง DB ไม่สามารถหาได้ทุกกรณี


## UUIDv7 (2026-10-03)

ID ใหม่ที่เป็น UUID ใช้ UUIDv7: database defaults เรียก `public.ink_buddy_uuid_v7()` และ Python ใช้ `app.core.identifiers.uuid7()` ชนิด column/API ยังคง UUID เพื่อรองรับ ID เดิม ไม่มีการเปลี่ยน primary/foreign keys ที่มีอยู่ ฐานเดิมต้อง apply `database/migrations/004_uuid_v7.sql` หลัง 003; ฐานใหม่ใช้ init ปัจจุบัน migrations 001–003 เก็บเป็นประวัติเดิม

UUIDv7 มี Unix timestamp ระดับ millisecond และ random bits ตาม [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) ไม่รับประกันลำดับภายใน millisecond หรือเมื่อ clock ย้อนกลับ ไม่ใช้ ID เป็น credential และยังตรวจ ownership ตามเดิม PostgreSQL 16 ใช้ compatibility function เพราะ built-in generator เป็น UUIDv4; ไม่มีการเปลี่ยนคอลัมน์ integer เช่น product_image_embeddings.id


Frontend setup ปัจจุบันดู [Frontend README](../../../frontend/README.md) มี single-flight refresh, Guest/Login/Logout/claim และ draft clearing แล้ว PostgreSQL tests รวม Chat Session ตอนนี้ผ่าน 23 tests

## Register / Reset Password — 2026-10-04

- POST /api/v1/auth/register: สร้างบัญชี user ที่ active; password 12–24 ตัวอักษร hash Argon2id; สมัครแล้ว Login ได้ทันที ไม่มี email verification หรือ auto Login/claim Guest
- POST /api/v1/auth/forgot-password: ส่งคำตอบทั่วไป 202 ทั้งบัญชีที่มี/ไม่มี/inactive/cooldown; token สุ่ม เก็บเฉพาะ SHA-256 hash อายุ 900 วินาที ขอใหม่ revoke token เดิม cooldown 60 วินาทีต่อบัญชี
- POST /api/v1/auth/reset-password: ใช้ token ครั้งเดียว transaction ล็อก user/token/auth sessions; เปลี่ยน hash และ revoke Login sessions/refresh tokens ทั้งหมด พร้อมแจ้งอีเมลและล้าง refresh cookie ไม่มี auto Login
- Public mutations ทั้งสามต้องส่ง Origin ที่อยู่ใน CORS_ORIGINS; limit Register 5/hour/IP, Forgot/Reset 10/hour/IP
- ลิงก์ใช้ /reset-password#token=... fragment ไม่ถูกส่งเป็น URL request ไป server หน้าเว็บอ่านเข้า memory และลบจาก address bar; reload ต้องเปิดลิงก์ในอีเมลใหม่ ใช้ Referrer-Policy no-referrer

### Mailpit local

จาก docker/ รัน `podman compose up -d` แล้วเปิด [Mailpit](http://localhost:8025) SMTP อยู่ 127.0.0.1:1025 รับอีเมลทดลองโดยไม่ส่งออกภายนอก ทั้งสองพอร์ต bind loopback เก็บสูงสุด 100 ข้อความใน container ไม่ได้ mount volume อีเมล

backend/.env ใช้ค่าตัวอย่างนี้ (DB/JWT ใช้ค่าของเครื่องเดิม):

```dotenv
AUTH_FRONTEND_URL=http://localhost:3000
AUTH_RESET_SECONDS=900
AUTH_RESET_COOLDOWN_SECONDS=60
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_STARTTLS=false
SMTP_SSL=false
SMTP_SENDER=Ink Buddy <noreply@ink-buddy.local>
SMTP_TIMEOUT_SECONDS=10
```

SMTP_USERNAME/SMTP_PASSWORD ไม่ต้องตั้งสำหรับ Mailpit. หาก backend รันใน Compose network เดียวกันให้ใช้ SMTP_HOST=mailpit

### SMTP production

กำหนด AUTH_FRONTEND_URL เป็น HTTPS origin ที่เชื่อถือได้; SMTP_HOST/PORT/SENDER/USERNAME/PASSWORD ตาม provider และเลือก SMTP_STARTTLS=true หรือ SMTP_SSL=true เพียงอย่างเดียว Production startup ตรวจ HTTPS frontend และ SMTP TLS นอกเหนือจาก JWT/cookie configuration เดิม ตัวอย่างทุกค่าอยู่ backend/.env.example เก็บ secret นอก Git

ส่งอีเมลด้วย FastAPI BackgroundTasks หลัง commit แบบ best effort ไม่ใช่ durable queue ไม่มี retry อัตโนมัติ; server หยุดหรือ SMTP ล้มเหลวอาจไม่ได้รับอีเมล API ยังตอบทั่วไปเพื่อไม่เปิดเผยบัญชี Log บอก delivery failed โดยไม่บันทึก recipient/token/body ควรเพิ่ม outbox/worker/retry ก่อน production ที่ต้องรับประกันการส่ง ไม่เก็บ password ในอีเมล

### ผลตรวจ

2026-10-04: backend regression 109 passed; PostgreSQL integration 27 passed บน Podman; frontend unit/component 11 passed; browser 9 passed ผ่าน API mocks แยกจาก PG; typecheck/build ผ่าน; SMTP transport ส่งเข้า Mailpit จริงผ่าน Main DB apply migration 005 หลัง backup ไม่มีการสร้างบัญชีทดลองในฐานหลัก

อ้างอิงแนวทาง [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) และ [Mailpit Docker](https://mailpit.axllent.org/docs/install/docker/)

## Password policy — 2026-10-05

การตั้งรหัสผ่านใหม่ผ่าน Register/Reset/local script ต้องยาว 12–24 ตัวอักษร มี a–z, A–Z, 0–9 และอย่างน้อยหนึ่ง ASCII punctuation (เช่น !@#_-); ห้าม Unicode whitespace ทุกชนิด ไม่มีการ trim Password ภาษาอื่นยังใช้ร่วมได้แต่ไม่นับแทนกลุ่มภาษาอังกฤษหรืออักขระพิเศษ Frontend ตรวจและยืนยันสองช่อง Backend ตรวจซ้ำและตอบ 422 เมื่อไม่ผ่าน Login ยังคงรับ 1–1024 ตัวเพื่อรองรับบัญชีเดิม ไม่มีการแก้ password hash เดิมโดย migration
