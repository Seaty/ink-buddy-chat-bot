# Authentication review และเคส API

ตรวจล่าสุด: 2026-10-03 — สถานะ implementation ไม่ใช่รายการงานที่แก้ครบแล้ว

## ประเด็นที่ยังเปิดอยู่

| ระดับ | ประเด็น | ผลกระทบและแนวทางแก้ |
|---|---|---|
| P2 | Limiter สร้างจาก settings ตอน import แต่ create_app(custom_settings) ใช้ global limiter เดิม | ทดสอบ custom Redis URI/2 workers แล้วพบ MemoryStorage แม้ validation ผ่าน ต้องสร้าง limiter ให้ใช้ configuration เดียวกับ app และทดสอบ storage จริงก่อนหลาย workers |
| P2 | ImageStorage เขียนไฟล์ปลายทางโดยตรง และ service รู้ storage key หลัง save สำเร็จ | จำลองเขียนบางส่วนแล้ว OSError พบไฟล์ค้าง แม้ DB/counter rollback ควรให้ storage ล้างไฟล์เมื่อเขียนไม่สำเร็จและใช้ temporary file + atomic rename พร้อม failure test |

สองประเด็นนี้ยังไม่ได้แก้โค้ดในการตรวจเอกสารครั้งนี้ Cleanup ที่อ้าง image rows ไม่พบ orphan file ที่ไม่เคยบันทึกลง DB

## วิธีรองรับเคสแต่ละ API

ทุก path ด้านล่างอยู่ใต้ `/api/v1` รายละเอียด status/error payload และ validation อยู่ใน [API Spec](../API_SPEC.md)

| API / เคส | วิธีรองรับปัจจุบัน |
|---|---|
| POST /auth/login — สำเร็จ | ตรวจบัญชี active/password สร้าง Login session; access JWT 15 นาทีและ refresh cookie อายุสูงสุด 7 วัน |
| Login — email/password ผิดหรือ inactive | ปฏิเสธด้วย error เดียวกันเพื่อไม่เปิดเผยว่ามีบัญชีหรือไม่ |
| Login — bcrypt เดิม | ตรวจ legacy hash และเปลี่ยนเป็น Argon2id หลัง login สำเร็จ; บัญชีใหม่ใช้ Argon2id |
| POST /auth/refresh — token ปัจจุบัน | Lock session/token และ rotate ใน transaction เดียว; ไม่ขยายวันหมดอายุเกิน 7 วันจาก login |
| Refresh — token เก่าใช้ซ้ำ/พร้อมกัน | Reuse revoke Login session รวม access token; frontend ต้อง single-flight เพื่อหลีกเลี่ยง refresh ซ้อน |
| POST /auth/logout | Revoke Login session ทันทีและล้าง refresh cookie; access token ที่ผูก session ใช้ต่อไม่ได้ ไม่มี/ไม่รู้จัก refresh credential ถูกปฏิเสธ |
| GET /users/me | ใช้ User Bearer และตรวจ JWT signature, issuer, audience, expiry พร้อม session/account ใน DB |
| Bearer ผิด/หมดอายุ/session revoked | 401; เมื่อส่ง Bearer ใน guest_or_user จะไม่ fallback เป็น Guest |
| POST /auth/guest-sessions — ครั้งแรก | สุ่ม token เก็บ hash ใน DB ส่ง HttpOnly cookie; อายุคงที่ 24 ชั่วโมง |
| Create Guest — cookie เดิมยังใช้ได้ | คืน session เดิม ไม่ reset อายุหรือโควตา; rate limit ยังนับการเรียก reuse |
| GET /auth/guest-sessions/current | ต้องมี Guest cookie ที่ valid; expired/revoked ถูกปฏิเสธ |
| POST /auth/guest-sessions/current/claim | ต้องมี User Bearer + Guest cookie + allowed Origin; lock และย้าย chats/images ใน transaction เดียว แล้ว revoke Guest |
| Claim ซ้ำ/Guest หมดอายุ | ปฏิเสธ ไม่ย้ายไปบัญชีอื่น; login ไม่ claim อัตโนมัติ |
| POST /images — Guest | Lock Guest row; image insert กับ quota counter ใน transaction เดียว อัปโหลดสำเร็จได้ 3 รูปรวมทุกแชต |
| Upload รูปที่ 4/พร้อมกัน | ตรวจ counter ภายใต้ lock ปฏิเสธเมื่อเต็ม; validation/DB failure ไม่เพิ่มโควตา การลบไม่คืนโควตา |
| Image search — ownership | ใช้ verified principal; รูปของคนอื่นตอบ 404 Guest search ถือ lock ระหว่าง pipeline เพื่อไม่แข่งกับ claim |
| Guest เข้า User/Admin | ไม่มี User Bearer ตอบ 401; User ที่ role ไม่ใช่ admin ตอบ 403 |
| Admin indexing | ตรวจ admin role และ feature flag ก่อน indexing; ค้นจริงยังต้อง AI/storage configuration |
| Send message/Product/Profile PATCH/Image detail-delete/Readiness | ตรวจ policy ก่อนตอบ 501; ownership/business rules ของ stub ยังไม่ได้ implement ครบ |
| Health | Public; health สำเร็จไม่เท่ากับยืนยัน DB และ AI พร้อมใช้งาน |

## Security และการปฏิบัติการ

- ทุก operation ต้องประกาศ policy; startup ตรวจ routes ที่ไม่ประกาศ CORS preflight ยังทำงาน
- Cookie mutation ต้องมี Origin ตรง allowlist รวม Login/Create Guest; Bearer-only mutation ไม่ต้องอาศัย cookie
- Cookies: HttpOnly, SameSite=Lax, Path=/api/v1, ไม่มี Domain และ Secure ใน production; access token ควรอยู่ frontend memory ยังไม่มี frontend implementation
- Rate limit: Login 10/min/IP, Guest creation 5/hour/IP, Refresh 30/min/IP, Image search 20/min/verified principal Shared IP อาจใช้โควตา rate limit ร่วมกัน
- Guest search lock ทำให้ upload/claim ต้องรอ AI; เป็น trade-off เพื่อป้องกัน ownership race
- Cleanup เลือก unclaimed Guest ที่หมดอายุแล้วอีก 24 ชั่วโมง มี dry-run, ตรวจ private storage path และ retry ได้ การลบไฟล์กับ DB ไม่ atomic; ยังไม่มี scheduler ที่ตั้งใช้งานจริง

## หลักฐานทดสอบและขอบเขต

ผลจาก implementation verification วันที่ 2026-10-03: regression 111 passed, 22 skipped (PostgreSQL 18 ที่รันแยก และ model-dependent 4); PostgreSQL integration ผ่าน 18 tests บน Podman ในฐานแยก ครอบคลุม rotation/reuse, logout, Guest quota/concurrency, claim, cleanup และ migration ตาม tests ที่มี

Auth tests ใช้ fake Vision pipeline ไม่ยืนยัน Ollama/embedding จริง ความแม่นยำสินค้า หรือ frontend ไม่ได้รันชุดทดสอบโค้ดใหม่ในการปรับเอกสารเท่านั้นครั้งนี้ และผลผ่านเดิมไม่ได้หมายความว่าสอง P2 ข้างต้นถูกแก้แล้ว

ดู [Auth setup](README.md), [Token flow](../../architecture/TOKEN_AUTH_FLOW.md), [Database Schema](../../../database/DATABASE_SCHEMA.md)


อัปเดต 2026-10-04: Chat Session CRUD/rename/history ใช้งานแล้วและทดสอบ ownership/claim race ผ่าน PostgreSQL; Frontend Auth/Guest UI ทำแล้ว ส่วนสอง P2 ด้านบนยังเปิดอยู่
