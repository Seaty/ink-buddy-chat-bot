# Ink Buddy — Token และการควบคุมสิทธิ์ API

อัปเดต2026-10-03 · Authentication และGuestaccess implementแล้ว; Chat/Product/ImageDetailDelete/Readiness ยังเป็น scaffold ที่ตรวจสิทธิ์ก่อนตอบ501

## 1. Tokenสามชนิด

| Token | ใช้ทำอะไร | รูปแบบและอายุ |
|---|---|---|
| User access | ยืนยันผู้ใช้ที่Login | HS256 JWT15นาที ส่งBearer;ตรวจDBsessionทุกrequest |
| User refresh | ออกaccessใหม่ | ค่าสุ่มในHttpOnlycookie;DBเก็บhash;สูงสุด7วันนับจากLogin |
| Guest | ระบุตัวตนชั่วคราวก่อนLogin | ค่าสุ่มในHttpOnlycookie;DBเก็บhash;24ชั่วโมงไม่ต่ออายุ |

Guestมีtokenแต่ไม่ได้ถือว่าLogin Tokenไม่ใช่UUIDของบัญชี/sessionและห้ามlogหรือเก็บค่าดิบในDB Passwordใหม่ใช้Argon2id; bcryptเดิมupgradeเมื่อLoginสำเร็จ

## 2. Guestได้tokenเมื่อไร

```text
เปิดแอป
  +-- User sessionยังใช้ได้ -> ใช้บัญชี
  +-- ไม่มีUser แต่Guestยังใช้ได้ -> ใช้Guestเดิม
  +-- ไม่มีทั้งสอง -> POST /api/v1/auth/guest-sessions
                        -> Serverสร้างGuestและrandom token
                        -> เก็บhashในDB
                        -> ส่งSet-Cookie
                        -> Browserแนบcookieในrequestถัดไป
```

Frontend bootstrap flow ยังต้องพัฒนา HttpOnlyอ่านผ่านJavaScriptไม่ได้จึงตรวจGuestผ่าน current endpoint User accessหมดอายุให้ลองrefreshก่อนสรุปว่าเป็นGuest ไม่สร้างGuestใหม่ทุกrequest และไม่downgradeBearerผิดเป็นGuestแบบเงียบๆ

CreateGuestเมื่อมีcookievalidคืน200พร้อมsessionเดิม expiry/quotaเดิม; ใหม่ตอบ201 Cookieหมดอายุ/ถูกrevokeอาจสร้างใหม่ได้ภายใต้ratelimit Guestquotaต่อsessionไม่ใช่ต่อคน การล้างcookieหรือเปลี่ยนอุปกรณ์ยังต้องควบคุมabuseเพิ่มเติม

## 3. Default-denyและwhitelist

ทุกoperationประกาศpolicyผ่านaccess_policy Startupตรวจครบทุกrouterรวมnested; ถ้าไม่มีpolicyแอปไม่เริ่ม GlobalauthorizeตรวจทุกAPIอีกชั้น ไม่ใช้prefixกว้างๆเพื่อเปิดสิทธิ์

| Policy | Operation |
|---|---|
| Public | Login,CreateGuest,Health |
| Refresh credential | Refresh,Logout |
| Guest credential | CurrentGuest |
| GuestหรือUser | Chat/Message,Image,Product,ImageSearch |
| User | Profile |
| UserและGuestพร้อมกัน | Claim |
| Admin | ImageIndex,Readiness |

Protected routeตรวจcredentialและownership Resourceของคนอื่นตอบ404 Adminต้องroleadminจากDB ImageIndexต้องfeatureflagเปิดด้วย Readinessยัง501หลังตรวจadmin Authของscaffoldไม่ได้หมายความว่าbusinessfeatureนั้นใช้งานได้

## 4. Requestตรวจอย่างไร

```text
method + route policy
   -> ตรวจBearerหรือcookieตามpolicy
   -> สร้างUser/Guest principalจากserver
   -> ตรวจrole/ownership/Origin/quota
   -> serviceทำtransaction
```

401คือcredentialไม่มี/ผิด/expired/revoked;403คือroleไม่อนุญาตหรือOrigin/quotaผิด;404คือresourceไม่มีหรือไม่ใช่เจ้าของ

ถ้ามีUserBearerในrouteGuest-or-Userให้ใช้User หากBearerผิดตอบ401แม้Guestcookievalid Claimใช้ทั้งUserBearerและGuestcookie ไม่มีการใช้client-supplied owner UUIDเป็นหลักฐานสิทธิ์

## 5. CookieและCSRF

ชื่อink_buddy_refreshและink_buddy_guest, Path=/api/v1, HttpOnly, SameSite=Lax, ไม่มีDomain; Secureในproduction ใช้HTTPS Useraccessเก็บfrontendmemoryส่งAuthorizationBearer ไม่ใช้localStorage

Login/CreateGuest/Refresh/Logout/ClaimและGuestmutationต้องส่งOriginที่ตรงCORS_ORIGINS Defaulthttp://localhost:3000 ไม่รับOriginหาย/null/ไม่ตรง Browserจัดการcookieเอง frontendต้องcredentials:include ถ้าข้ามorigin HttpOnlyเพียงอย่างเดียวไม่ป้องกันCSRFจึงมีOrigincheckด้วย

Swaggerเปิดdevelopmentเท่านั้น ใช้Bearerผ่านAuthorize CookieflowจากSwaggerต้องallowbackendoriginก่อน ไม่เปิดCORSเป็นwildcard คู่มือHTTPclientดูauthREADME

## 6. Login / Refresh / Logout

LoginตรวจpasswordและactiveuserออกJWT+refreshcookie refreshหมุนค่าสุ่มใหม่ในauth_sessionเดิม ไม่ต่ออายุเกิน7วัน เก็บrotated_at/replaced_by_idเพื่อจับreuse

Refresh/logoutlockparent auth_sessionก่อนrefreshrow ให้คำขอพร้อมกันserialize ถ้าrefreshเก่าถูกใช้ซ้ำrevokeทั้งsessionทันที **clientต้องทำrefreshsingle-flight** ไม่ให้หลายtabs/requestrefreshด้วยcookieเก่าพร้อมกัน

LogoutrevokeLoginsessionปัจจุบันและrefreshทั้งชุด ล้างcookie AccessJWTผูกsidและตรวจauth_sessionsทุกrequestจึงใช้ต่อไม่ได้ทันที อุปกรณ์ที่Loginคนละsessionยังใช้งานได้ บัญชีถูกinactiveก็ถูกปฏิเสธทันที

## 7. Guestquota3รูป

หนึ่งGuestaccesssessionมีหลายChatthreadsได้ quotaสะสม3รูป เปิดแชตใหม่/refreshหน้าไม่reset นับเมื่อรับรูปสำเร็จเท่านั้น ลบรูปไม่คืน ค้นรูปเดิมไม่เพิ่ม

Uploadvalidateรูปก่อน จากนั้นlockGuestrowตรวจexpiry/revoked/claimed/quota เพิ่มcounterและinsertimageในtransactionเดียว FailDBrollbackcounterและcleanupไฟล์รูปที่เพิ่งเขียน รูปที่4ตอบ403GUEST_IMAGE_QUOTA_EXCEEDEDพร้อมlimit/used/remaining

SearchตรวจGuestและownership ใช้lockเดียวกันเพื่อไม่ชนclaimระหว่างวิเคราะห์ ปัจจุบันถือGuestlockตลอดsearchจึงserializeกับupload/claimของGuestเดียวกัน แลกกับความสอดคล้องของowner หากAIช้าควรพัฒนาjobworkflowภายหลัง

## 8. ClaimหลังLogin

Loginไม่ย้ายข้อมูลเอง Claimต้องมีUserBearer+Guestcookie+Originที่ถูกต้อง service lockGuestและตรวจสถานะซ้ำ ย้ายownerของแชต/รูปทั้งหมดในtransactionเดียว ตั้งclaimeduser/time+revoked_atแล้วล้างcookie

Claimซ้ำ/expired/revokedGuestถูกปฏิเสธ ไม่claimไปบัญชีอื่น Uploadที่ชนclaimจะสำเร็จก่อนแล้วถูกย้าย หรือถูกปฏิเสธหลังGuestrevoked ไม่มีGuestimageหลงเหลือ ข้อมูลที่ย้ายยังprivateต่อบัญชี

## 9. ExpiryกับRetention

Guesttokenหมดอายุเมื่อ24ชั่วโมงทำให้ใช้APIไม่ได้ แต่ไม่ลบข้อมูลทันที CleanupGuestที่ไม่claimหลังexpires_atอีก24ชั่วโมง ลบแชต/รูป/Guestและprivatefiles ข้อมูลที่claimแล้วไม่ถูกcleanupGuest

มีscriptdry-runและ--applyแบบretryได้ ยังไม่ได้ตั้งscheduler ให้ทีมตั้งรันทุกชั่วโมงพร้อมmonitoring อายุข้อมูลบัญชีLoginยังต้องกำหนดต่างหาก

## 10. สถานะและการทดสอบ

UserJWT,opaqueGuest/refresh,refreshrotation/reuse,immediateLogout,default-deny,Guestwhitelist,quotaและclaim implementแล้ว SQLinit13ตารางและmigration003พร้อม ฐานlocalapplyแล้วพร้อมbackup

ทดสอบPostgreSQLในPodmanโดยใช้databaseชั่วคราวแยกจากฐานหลัก ครอบคลุมconcurrency/ownership/migrations/cleanup VisionpipelineในAuthtestsเป็นfake ไม่ยืนยันAIความแม่นยำหรือโมเดลจริง ยังไม่มีfrontendAuthUIหรือRegisterAPI

เอกสารเกี่ยวข้อง: [Auth setup](../api/auth/README.md), [API Spec](../api/API_SPEC.md), [Database Schema](../../database/DATABASE_SCHEMA.md), [Backend Structure](BACKEND_STRUCTURE.md)

## ประเด็นจากรีวิวที่ยังเปิดอยู่

ดู [Auth review](../api/auth/AUTH_REVIEW.md): custom app configuration ยังอาจไม่ถูกใช้โดย global limiter และการเขียนไฟล์ภาพล้มเหลวระหว่างทางอาจเหลือไฟล์บางส่วน โค้ดยังไม่ได้แก้สองประเด็นนี้ ผลทดสอบเดิมไม่ครอบคลุมการยืนยันว่าแก้แล้ว


## UUIDv7 update — 2026-10-03

UUID ที่สร้างใหม่ใช้ v7 ทั้ง database defaults, Python storage keys และ scripts ฐาน local สำรองแล้วและ apply migration 004 เรียบร้อย ID เดิมและ FK ไม่เปลี่ยน API ยังรับ UUID เดิมได้ ดู [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) สำหรับรูปแบบ

ผลทดสอบหลังเปลี่ยน: regression 113 passed / 23 skipped; PostgreSQL integration 19 passed แยกผ่าน Podman (รวม migration repeat-safe, defaults ทั้ง 12 UUID tables, timestamp/version และ uniqueness) ค่า integer ID คงชนิดเดิม
