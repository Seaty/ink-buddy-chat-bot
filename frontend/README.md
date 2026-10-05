# Ink Buddy Frontend

## เริ่มใช้งาน

ต้องมี Node.js >=20.9 และ pnpm 11.25.0 (packageManager ใน package.json) ใช้ Next.js App Router, React, TypeScript และ Tailwind CSS dependencies จริงอ้าง package.json/lockfile ไม่ใช่ library-guide เดิม

จาก frontend:

```powershell
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local # เฉพาะเมื่อยังไม่มี .env.local
pnpm dev
```

เปิด http://localhost:3000 รัน backend ที่ http://localhost:8000 พร้อม DATABASE_URL/AUTH_JWT_SECRET และ PostgreSQL ตาม Auth setup Backend ต้องอนุญาต Origin frontend เช่น http://localhost:3000 ไม่สลับ localhost กับ127.0.0.1เพราะ cookie/Origin ต้องสอดคล้องกัน `NEXT_PUBLIC_API_BASE_URL` ตั้งก่อน build; local HTTP ใช้ development cookies

สมัครบัญชี User ผ่าน /register ได้แล้ว; สร้าง Admin ผ่าน backend local script ไม่มีบัญชีหรือ password เริ่มต้น

## หน้าที่แต่ละส่วน

| ตำแหน่ง | หน้าที่ |
|---|---|
| src/app | Routes /chat, /chat/[id], /login และ root layout |
| src/features/auth/provider.tsx | Bootstrap, identity, claim และ drafts memory ที่ล้างเมื่อเปลี่ยน principal |
| src/lib/api.ts | Cookie/Bearer requests, error mapping และ single-flight refresh |
| src/features/chat/workspace.tsx | รายการ/detail/history, pagination, rename/delete และ responsive shell |
| src/features/chat/composer.tsx | Prompt cards, draft editor และ replacement confirmation |
| src/features/chat/prompts.ts | typed prompt configuration: id,label,text,enabled |
| src/components/ui/dialog.tsx | Native modal พร้อม focus containment และ Escape |
| src/app/globals.css | theme tokens และ breakpoints |

## พฤติกรรม

- สร้าง/เปลี่ยนชื่อ/ลบ/เปิดแชต และอ่านประวัติได้ทั้ง Guest/User ลบแบบ soft delete ไม่คืนโควตารูป
- กด prompt เติม draft เท่านั้น ไม่สร้าง chat/message; ปุ่มส่ง disabled และ Enter ไม่ส่ง
- Draft แยกต่อหน้า/แชตใน memory รักษาระหว่าง client navigation ล้างเมื่อ reload/logout/principal change
- Prompt มี 3 รายการ เพิ่ม/แก้/ซ่อนผ่าน configuration ไม่มี management API
- Bootstrap refresh ก่อน Guest; GET401 refresh และ retry ได้หนึ่งครั้ง; mutation401 refresh แต่ไม่ retry ให้ผู้ใช้ลองใหม่
- Login ให้เลือก claim Guest; claim สำเร็จ reload รายการ Guestหมดอายุแจ้งและให้เริ่มใหม่ ไม่คืนรายการเก่า
- Mobile<768px รายการกับแชตทีละหน้า; Tablet768–1023px drawer; Desktop>=1024px sidebar

## ตรวจสอบ

```powershell
pnpm typecheck
pnpm test
pnpm build
pnpm test:e2e
```

Browser tests ใช้ Microsoft Edge ที่ติดตั้งในเครื่อง หรือกำหนด PLAYWRIGHT_CHANNEL=chrome หากมี Chrome (หากใช้ chromium ต้องติดตั้ง browser ของ Playwright ก่อน) ทดสอบ API mocks ไม่ใช้ฐานจริง; PostgreSQL integration รันจาก backend ด้วย `python -m scripts.test_auth_postgres` ใน .venv

ผล 2026-10-05: unit/component 18 passed, browser 9 passed, TypeScript และ production build ผ่าน ส่วน backend PostgreSQL 27 passed แยก ชุด Auth ใช้ fake Vision ไม่ยืนยัน AI จริง

## ขอบเขตที่ยังไม่ทำ

ส่งข้อความ/AI, upload UI, citations, summary และ Product browsing ยังไม่อยู่ในรอบนี้ ดู [API Spec](../docs/api/API_SPEC.md), [Token Flow](../docs/architecture/TOKEN_AUTH_FLOW.md) และ [Auth Review](../docs/api/auth/AUTH_REVIEW.md)

## Account pages

/register สมัคร role user แล้วไป Login, /forgot-password ขอลิงก์, /reset-password อ่าน token จาก fragment เข้า memory และลบจาก URL ไม่ auto Login หลัง reset Backend URL และ Origin ต้องตั้งตรงกัน Local email อ่านที่ http://localhost:8025 ดู [Auth setup](../docs/api/auth/README.md) Node 24.19.0 ตรวจแล้ว

## Podman container

ใช้ `podman compose up -d --build frontend` จาก docker/ แล้วเปิด http://localhost:3000 เป็น production standalone ไม่มี hot reload Backend ยังรันบนเครื่อง ดู [การตั้งค่า Container/API URL](../docker/README.md)

## Password policy — 2026-10-05

การตั้งรหัสผ่านใหม่ผ่าน Register/Reset/local script ต้องยาว 12–24 ตัวอักษร มี a–z, A–Z, 0–9 และอย่างน้อยหนึ่ง ASCII punctuation (เช่น !@#_-); ห้าม Unicode whitespace ทุกชนิด ไม่มีการ trim Password ภาษาอื่นยังใช้ร่วมได้แต่ไม่นับแทนกลุ่มภาษาอังกฤษหรืออักขระพิเศษ Frontend ตรวจและยืนยันสองช่อง Backend ตรวจซ้ำและตอบ 422 เมื่อไม่ผ่าน Login ยังคงรับ 1–1024 ตัวเพื่อรองรับบัญชีเดิม ไม่มีการแก้ password hash เดิมโดย migration
