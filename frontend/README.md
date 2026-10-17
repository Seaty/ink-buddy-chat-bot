# Ink Buddy Frontend

## Safety unavailable — 2026-10-16

เมื่อ backend คืน GUARD_UNAVAILABLE จะแจ้งว่าระบบตรวจความปลอดภัยยังไม่พร้อม ร่าง/รูปและการ retry แบบ manual เดิมยังอยู่ คำถาม unsafe ที่ถูกปฏิเสธแสดงป้ายกฎระบบและไม่มีการ์ดสินค้า ดู [Safety process](../docs/architecture/CHAT_SAFETY_GUARDRAILS.md)

## แนบรูปถามสินค้า — 2026-10-15

กด ＋ รูปภาพ แนบ JPEG/PNG/WEBP ≤5 MiB พร้อมคำถาม ≤500 ตัวอักษร หรือส่งรูปอย่างเดียว ใช้ Vision + Text RAG แนะนำสินค้าจาก catalog มี preview/remove, Guest quota, error/retry โดยไม่ upload ซ้ำเมื่อมี image ID แล้ว และรูปในประวัติเป็น private ดู [Process / วิธีทดสอบ](../docs/architecture/VISION_CHAT_PROCESS.md)

## Chat UI presentation — 2026-10-15

เพิ่ม loading animation, แสดงคำตอบใหม่ทีละคำพร้อม auto-scroll ที่พักเมื่อเลื่อนขึ้นอ่าน, ปุ่มแสดงทั้งหมด และ reduced-motion. การ์ดสินค้าจัดกลุ่มชื่อ/ราคา/สี/variants/แหล่งข้อมูลใหม่ ใช้ palette เดิม ดู [รายละเอียดและวิธีทดสอบ](../docs/architecture/CHAT_UI_PRESENTATION.md). เป็น presentation หลัง REST response ไม่ใช่ backend streaming และไม่เปลี่ยน provider/API contract

## Conversational RAG UAT — 2026-10-14

ProductReferenceCard แสดงสีหมึก/ด้าม, หน่วยราคา, ฐาน VAT demo, แหล่งสินค้า/แหล่งราคาแยกกัน และ variants ใต้รุ่นหลัก. ป้าย AI/กฎระบบแยกจาก Ink Buddy ชัดเจน ใช้ React text และเฉพาะลิงก์ HTTP/HTTPS

ทดสอบตาม [Process 7](../docs/architecture/RAG_CONVERSATION_PROCESS.md): ส่ง 3 รุ่นถูกที่สุด → ตัวที่สองราคาเท่าไร → สีอื่น → reload. UI/routing/auth/draft/retry เดิมคงไว้ ไม่มี upload UI ใหม่

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
- กด prompt เติม draft เท่านั้น ไม่สร้าง chat/message; ปุ่มส่งเปิดเมื่อข้อความพร้อม Enter ส่ง/Shift+Enter ขึ้นบรรทัดใหม่ ไม่ส่งระหว่าง IME
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

LLM response, streaming, upload UI, summary และ Product browsing ยังไม่อยู่ในรอบนี้ ดู [API Spec](../docs/api/API_SPEC.md), [Token Flow](../docs/architecture/TOKEN_AUTH_FLOW.md) และ [Auth Review](../docs/api/auth/AUTH_REVIEW.md)

## Account pages

/register สมัคร role user แล้วไป Login, /forgot-password ขอลิงก์, /reset-password อ่าน token จาก fragment เข้า memory และลบจาก URL ไม่ auto Login หลัง reset Backend URL และ Origin ต้องตั้งตรงกัน Local email อ่านที่ http://localhost:8025 ดู [Auth setup](../docs/api/auth/README.md) Node 24.19.0 ตรวจแล้ว

## Podman container

ใช้ `podman compose up -d --build frontend` จาก docker/ แล้วเปิด http://localhost:3000 เป็น production standalone ไม่มี hot reload Backend ยังรันบนเครื่อง ดู [การตั้งค่า Container/API URL](../docker/README.md)

## Password policy — 2026-10-05

การตั้งรหัสผ่านใหม่ผ่าน Register/Reset/local script ต้องยาว 12–24 ตัวอักษร มี a–z, A–Z, 0–9 และอย่างน้อยหนึ่ง ASCII punctuation (เช่น !@#_-); ห้าม Unicode whitespace ทุกชนิด ไม่มีการ trim Password ภาษาอื่นยังใช้ร่วมได้แต่ไม่นับแทนกลุ่มภาษาอังกฤษหรืออักขระพิเศษ Frontend ตรวจและยืนยันสองช่อง Backend ตรวจซ้ำและตอบ 422 เมื่อไม่ผ่าน Login ยังคงรับ 1–1024 ตัวเพื่อรองรับบัญชีเดิม ไม่มีการแก้ password hash เดิมโดย migration

## Text chat / catalog answer — 2026-10-05

ส่งข้อความ 1–4000 ตัวผ่าน POST messages พร้อม client_request_id UUIDv7 ค้น products DB ตอบจาก template และแสดง product refs; ไม่ใช่คำตอบ LLM หน้า home กดส่งจึงสร้างแชต Prompt click ไม่สร้างข้อมูล Retry reuse ID เดิมเมื่อข้อความไม่เปลี่ยนและไม่สร้าง chat ใหม่หลังสร้างสำเร็จ ไม่มี automatic mutation retry Draft/errors/attempt IDs อยู่ใน memory ล้างเมื่อ principal เปลี่ยน/claim/reload คำขอที่หมดสิทธิ์ไม่คืนร่างส่วนตัวให้ principal ใหม่

pending text เป็น UI ชั่วคราวไม่ใช่ committed history Success บันทึกคู่และล้างร่าง Errorรักษาร่าง/แสดงข้อความ Retry ด้วยปุ่มส่ง ลิงก์สินค้าเฉพาะ HTTP(S) renderผ่าน React ไม่ใช้ raw HTML

ผล: Frontend19 passed, browser15 passed (API mocks), typecheck/container build ผ่าน เพิ่ม real browser smoke ผ่าน APIจริง+PGชั่วคราว สำหรับ Guest/User/claim/reload/no-match จาก backend รัน `.\.venv\Scripts\python.exe -m scripts.test_chat_browser` ต้องมี Frontend container localhost:3000 และพอร์ต8001ว่าง runner forward HTTP API ไป isolated backend ไม่ mock response และลบ DB ทิ้งเมื่อจบ

## RAG Chat sources
Backend CHAT_ADAPTER=openrouter_catalog enables hybrid retrieval plus controlled OpenRouter Qwen3 14B selection. UI labels AI / Catalog Template / กฎระบบ via model_name, preserved in history. No client model choice. Error/retry/draft behavior is unchanged; source values are server-controlled. API/postman guide: ../docs/api/session/RAG_CHAT_API.md.

## Real container RAG verification

Backend runner supports `python -m scripts.test_chat_browser --rag --frontend-url http://localhost:3002 --viewports all` when a standalone frontend test container runs on 3002. It forwards browser API calls to a real backend on 8001 and creates/drops an isolated DB. No response mocks. Mobile 390×844, Tablet 820×1180 and Desktop 1440×900 cover Guest/User, claim, replay (history remains 2 rows), reload and no-match. Synthetic fixture data does not measure real catalog recommendation quality. See ../docs/architecture/RAG_TECHNICAL_COMPLETION_PROCESS.md.
