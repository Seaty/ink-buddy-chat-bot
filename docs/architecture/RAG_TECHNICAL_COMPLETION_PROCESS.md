# Process 6: ปิดงานเทคนิค Text RAG ก่อน Human Evaluation

วันที่ตรวจ 2026-10-13 — งานรอบนี้ทำส่วนที่ไม่ต้องรอคะแนนทีม ไม่ใช่สรุปคะแนนหรือรับรองความพร้อม production

## 1. ปรับเหตุผลโดยไม่สร้างข้อมูลสินค้าใหม่

- AI ยังเลือก Product IDs และ Evidence IDs เท่านั้น ไม่มีข้อความอิสระ/ราคา/URL จากโมเดล
- Description แยกเป็นข้อความที่ยกจากต้นทางตรง ๆ: span ที่ครบไม่เกิน 180 ตัว สูงสุด 6 spans ต่อสินค้า ถ้า span ยาวเกินจะไม่ใส่ในชุดหลักฐานคำตอบ ไม่ตัดข้อกล่าวอ้างครึ่งประโยค
- Embedding source text เดิมไม่เปลี่ยน ไม่แก้ products และไม่ต้อง reindex
- Renderer เพิ่มเหตุผลตามข้อมูลจริง: ยี่ห้อตรงคำถาม ราคาอยู่ในช่วงงบ และคำค้นสี/วัสดุที่พบในสินค้า
- แสดงข้อมูลได้ไม่เกิน 3 bullets ต่อสินค้า พร้อมข้อความราคาขาดเมื่อจำเป็น และ attribution ว่าเป็นข้อมูล catalog/คำกล่าวจากร้าน ไม่ใช่ผลทดสอบคุณสมบัติหรือข้อมูลสด
- ไม่ซ้ำชื่อ/หมวดเป็น bullet ถ้าไม่มีข้อมูลอธิบายความแตกต่างเพียงพอให้แจ้งข้อจำกัด ไม่แต่งประโยชน์หรือเหตุผลขึ้นมา
- กรอง known instruction patterns ใน attributes/availability เพิ่มเติม; ยังเป็น heuristic ไม่ใช่หลักฐานว่าป้องกันทุก injection ได้

ไฟล์หลัก: `backend/app/services/session/catalog_answer.py` และ `openrouter_adapter.py` Interface AnswerInput/AnswerOutput, request/response และฐานข้อมูลไม่เปลี่ยน

## 2. ข้อความขอข้อมูลเพิ่ม

| กรณี | การตอบ |
|---|---|
| งบระบุชัดแต่ไม่พบ | ชวนปรับช่วงงบ/บอกเงื่อนไขที่ยืดหยุ่น ไม่เสนอเกินงบเอง |
| ไม่พบตามรุ่น/ยี่ห้อ/ลักษณะ | ชวนตรวจชื่อรุ่นหรือบอกลักษณะเพิ่มเติม |
| งบขั้นต่ำสูงกว่าขั้นสูง | ขอแก้ช่วง พร้อมตัวอย่าง 50–100 บาท |
| ไม่รู้ว่าสินค้าใด / follow-up | ขอชื่อ/รุ่นอีกครั้ง ยังไม่ทำ query rewriting |

ส่ง clarification จาก retrieval ไปยัง adapter โดยตรง ทำให้ standalone search และแชตใช้เหตุผลเดียวกัน ไม่เรียก Text LLM สำหรับ refusals/no-match/clarification

## 3. ทดสอบความสม่ำเสมอ OpenRouter

ใช้ชุด robustness 13 ข้อเดิม รัน 3 รอบที่บันทึกแยกกัน:

| รอบ | ผ่าน |
|---|---:|
| technical_1 | 13/13 |
| technical_2 | 13/13 |
| technical_3 | 13/13 |

รวม 39/39 ตรวจสถานะเงื่อนไขและ output contract ไม่ใช่คะแนนความเหมาะสมของคำแนะนำจากมนุษย์ ไม่ใช่ชุดอิสระ และไม่รับประกันโมเดลตอบผ่านทุกครั้งในอนาคต เก็บทั้งสามรายงาน `docs/report/RAG_ROBUSTNESS_technical_*.json` ไม่มี retry/fallback อัตโนมัติในระบบใช้งาน

12 Text LLM calls ในสามรอบนี้ provider รายงาน chat cost รวม 0.00110386 USD ไม่รวม Browser trials, query/catalog embedding หรือรอบก่อนหน้า Query embeddings รอบนี้ใช้ cache ค่าใช้จ่ายรวมจริงต้องดู billing ของ OpenRouter

## 4. ตรวจ catalog แบบอ่านอย่างเดียว

`python -m scripts.audit_text_catalog` สร้าง [Text Catalog Audit](../report/TEXT_CATALOG_AUDIT.json)

- catalog 67 สินค้า มี text index ของโมเดลปัจจุบันครบและไม่ stale ตาม source_text ณ เวลา audit
- ขาดราคา 18 สินค้า: ไม่เติมราคาและไม่ใช้เป็นศูนย์เมื่อกรองงบ
- ขาด description 50 และหน่วยขายแบบ structured 50
- 15 คำบรรยายมี retailer performance claims ที่ยังไม่ยืนยันอิสระ ต้องคง attribution
- 5 คำบรรยายมีถ้อยคำสีที่อาจขัดกัน ต้องให้ทีมตรวจต้นทางก่อนแก้
- source_ref ไม่พบปัญหารูปแบบ URL จากการตรวจ syntax รอบนี้ ไม่ได้ตรวจ live reachability หรือความถูกต้องของเนื้อหาเว็บ

ไม่มี DB writes หรือ provider calls จาก audit ทีมสามารถใช้รายการ SKU/field/code ในรายงานเพื่อเติมข้อมูลภายหลัง ไม่ใช่ทุก warning เป็นสินค้าผิดหรือใช้ไม่ได้

## 5. Container และ Browser จริงสามขนาด

Build `docker/frontend.Containerfile` ผ่านด้วย Node 24.19.0 / pnpm 11.25.0 / Next standalone ใช้ image ทดสอบ `localhost/ink-buddy-rag-frontend-test:latest` และพอร์ต 3002 แยกจาก frontend local 3000

```text
Browser (Mobile/Tablet/Desktop)
  → Frontend standalone บน Podman :3002
  → browser forwarding → Backend local ที่แยกทดสอบ :8001
  → disposable DB ใน PostgreSQL/pgvector บน Podman
  → OpenRouter embedding + Qwen3 14B
  → atomic history → Browser
```

ไม่ mock API responses ใช้สินค้าสังเคราะห์ Browser Smoke Pen ในฐานชั่วคราว ไม่ใช้สินค้าจำลองในฐานหลัก ไม่ใช่การวัดคุณภาพ catalog จริง backend ยังรันบน host ตาม architecture ปัจจุบัน ไม่ได้เพิ่ม Backend container

ผ่าน Mobile 390×844, Tablet 820×1180, Desktop 1440×900 ทุกขนาด:

- Guest/User ส่งข้อความและแสดง product_refs/ป้าย AI
- replay คืนคู่เดิม และประวัติยังมี 2 แถวหลัง replay
- reload เปิดประวัติกลับมาได้
- Register/Login/claim แล้วย้ายแชตเข้าบัญชี
- no-match แสดงป้ายกฎระบบ
- ไม่มี horizontal overflow ตามการตรวจ browser; ตรวจภาพทั้งสามขนาดแล้ว

รายงาน [Browser Acceptance](../report/RAG_BROWSER_ACCEPTANCE.json) ภาพเก็บใน `.local/browser-smoke/acceptance-mobile-{mobile,tablet,desktop}.png` ซึ่งไม่ขึ้น Git ฐานและ backend ทดสอบลบทิ้ง/ปิดใน finally; test container ลบหลังจบงาน Image คงไว้ใช้รันซ้ำ

Podman OCI build แจ้งว่า image HEALTHCHECK ถูกละไว้ จึงเพิ่ม healthcheck ใน Compose โดยตรงและตรวจ `config --quiet` ผ่าน ไม่ apply Compose ใหม่กับฐานหลัก healthcheck config ไม่ใช่ผลทดสอบ health state ของ container เดิม ถ้ารัน image โดยตรงและต้องการ image healthcheck ให้ build ด้วย `--format docker`

## 6. Regression และการตรวจส่งมอบ

| การตรวจ | ผล / ขอบเขต |
|---|---|
| Backend focused | 72 passed สำหรับ renderer/audit/RAG/client/policy/search |
| Audit/render/catalog targeted หลังปรับ helper ล่าสุด | 8 passed |
| PostgreSQL auth/message transactions | 54 passed บน disposable DB |
| Frontend unit/component | 23 passed |
| TypeScript | passed |
| Browser API mocks | 15 passed รวม error/retry บนสามขนาด แยกจาก real smoke |
| Real container Browser | 3 viewports passed ดังรายละเอียดข้างบน |
| Container build | passed |
| Compose syntax | passed ไม่แสดง secrets และไม่ restart ฐานหลัก |
| OpenAPI | snapshot ตรง app, 32 operations / 26 paths, ทุก operation มี policy |

ไม่ได้รัน full Backend suite หรือ Vision models ในรอบนี้ เป็นงานแยก ไม่เพิ่ม migration ไม่มีการเปลี่ยน image embeddings หรือระบบซื้อสินค้า

## 7. วิธีรันซ้ำ

จาก root เมื่อ Podman/PostgreSQL พร้อม:

```powershell
podman build -f docker/frontend.Containerfile -t localhost/ink-buddy-rag-frontend-test:latest frontend
podman run -d --name ink-buddy-rag-frontend-test -p 127.0.0.1:3002:3000 localhost/ink-buddy-rag-frontend-test:latest
```

จาก backend:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_chat_browser --rag --frontend-url http://localhost:3002 --viewports all
.\.venv\Scripts\python.exe -m scripts.evaluate_rag_robustness --live --answers --label your_trial
.\.venv\Scripts\python.exe -m scripts.audit_text_catalog
.\.venv\Scripts\python.exe -m scripts.test_auth_postgres
```

ชื่อ container ต้องว่างและพอร์ต 8001 ต้องว่าง; smoke runner ไม่แทนที่ backend/user DB ที่ใช้งานอยู่ OpenRouter live calls ใช้เครดิตจริง รันจบแล้วลบเฉพาะ test container ที่สร้างเอง:

```powershell
podman rm -f ink-buddy-rag-frontend-test
```

## สิ่งที่รอทีม / ขอบเขตต่อไป

งานเทคนิคตามรายการนี้ครบแล้ว เหลือ human evaluation และยืนยัน/เติมข้อมูล catalog ที่ขาด ก่อนสรุปคุณภาพทั้งหมดและเปิด PR ตามขั้นตอนทีม ไม่ใช้ผลอัตโนมัติแทนคะแนนมนุษย์

Query rewriting, streaming, summary, Vision UI, production shared limiter และ Backend container เป็นงานเพิ่มเติม ไม่ได้รวมในรอบนี้ รอบ acceptance เดิมอยู่ตามเวอร์ชันก่อนปรับ renderer; อย่าอ้างว่าเป็นผลคุณภาพของ renderer ใหม่
