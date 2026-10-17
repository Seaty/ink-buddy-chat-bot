# Vision + Text RAG Chat — 2026-10-15

## จุดประสงค์

แนบรูปเครื่องเขียนพร้อมคำถาม เช่น “มีสินค้านี้ไหม” เพื่อค้นสินค้าใน catalog เดิม ใช้ OpenRouter Vision อ่านรายละเอียด แล้วใช้ Text RAG ค้น PostgreSQL/pgvector ไม่ใช่การเทียบ image vectors และไม่ยืนยันรุ่นหรือสต็อกจากรูป

## กระบวนการ

1. เลือกรูปหนึ่งรูป JPEG/PNG/WEBP ไม่เกิน 5 MiB: preview อยู่ใน browser ยังไม่อัปโหลด กดลบเพื่อเปลี่ยนรูปได้
2. พิมพ์คำถามไม่เกิน 500 ตัวอักษร หรือใช้คำถามเริ่มต้น “มีสินค้านี้ไหม”; ข้อความล้วนยังได้ 4,000 ตัวอักษร
3. เมื่อกดส่ง จึงสร้างแชตหากจำเป็น แล้ว `POST /api/v1/images` แบบ multipart รับ image ID ส่วนตัว
4. `POST /api/v1/chat-sessions/{id}/messages` รับ `content`, `image_id`, `client_request_id` UUIDv7 ตรวจ credential/ownership และ replay ก่อนเรียกโมเดล
5. เปิดรูปผ่าน private storage ส่งให้ `qwen/qwen3-vl-8b-instruct` บน OpenRouter อ่านหมวด/ยี่ห้อ/รุ่น ไม่ส่งข้อมูลบัญชีหรือ token
6. ตรวจข้อมูล Vision และ scope: หมวดที่คาดเดาขัดกับคำบรรยายไม่เป็น hard filter; รหัสรุ่นจากรูปไม่ใช่ข้อกำหนด exact ของผู้ใช้ สีด้ามจากภาพไม่ถูกตีความเป็นสีหมึก
7. ส่งคำค้นให้ Text RAG เดิม ซึ่งใช้ query embedding และ Hybrid retrieval จาก catalog ถ้าถามราคา เลือกเฉพาะรายการที่มีราคา THB และใช้เงื่อนไขงบเดิม
8. ระบบประกอบคำตอบและการ์ดจาก snapshot สินค้า ไม่สร้างราคา/URL/คุณสมบัติเอง ผลลัพธ์ระบุ `match_method=vision_text_catalog`, `match_type=similar`; similarity ไม่ใช่ความน่าจะเป็นว่าสินค้าตรงรุ่น
9. ตรวจสิทธิ์และลำดับแชตซ้ำ บันทึก User/Assistant พร้อมกัน โดย `image_id` อยู่ในข้อความ User; ไม่มี DB row lock ระหว่างรอ provider
10. เปิดประวัติใช้ `GET /api/v1/images/{id}/content` ผ่าน credential ปัจจุบัน แสดง private blob ไม่เปิด public URL หรือ token ใน URL

## ข้อผิดพลาดและสิทธิ์

- Guest ใช้โควตา 3 รูปตลอด session ร่วมทุกแชต การลบ preview หลังอัปโหลดไม่คืนโควตา ข้อความล้วนใช้ต่อได้
- อัปโหลดสำเร็จแต่ตอบล้มเหลว: เก็บร่าง รูป และ image ID ไว้ให้ลองใหม่ ไม่อัปโหลดซ้ำ ไม่ retry mutation อัตโนมัติ
- Request ID เดิม + ข้อความและรูปเดิมคืนคู่เดิม ไม่เรียก Vision ซ้ำ; เปลี่ยนข้อความหรือรูปแต่ใช้ ID เดิมตอบ 409
- ไม่มีสิทธิ์ในรูปตอบ 404; credential หมดอายุ/revoked ตอบ 401; claim/delete/logout ระหว่างวิเคราะห์จะไม่บันทึกข้ามเจ้าของ
- รูปไม่ใช่เครื่องเขียน/ไม่พบสินค้าให้คำตอบตามกฎ ไม่เติมสินค้าเอง Provider/timeout/invalid analysis ไม่บันทึกคู่ข้อความและคงร่างไว้
- Login/logout/เปลี่ยน principal ล้างไฟล์แนบและร่างจาก memory; reload ล้างไฟล์ที่ยังไม่ส่ง แต่รูปที่บันทึกแล้วอยู่ในประวัติ
- ถ้าเครือข่ายขาดหลัง server รับ upload แต่ client ไม่ได้รับ image ID โควตาอาจถูกใช้แล้ว ต้องตรวจโควตา ไม่รับประกัน upload idempotency

## Configuration

ใน `backend/.env`:

```dotenv
VISION_CHAT_RETRIEVAL=text_catalog
VISION_CHAT_MODEL=qwen/qwen3-vl-8b-instruct
```

ใช้ `OPENROUTER_API_KEY`, base URL และ Text Embedding configuration เดิม ต้องอนุญาต Vision model นี้ใน OpenRouter guardrail ด้วย การอ่านรูปและ query embedding ใช้เครดิตจริง ไม่มี fallback/retry อัตโนมัติ จำกัดงานร่วมกับข้อความเดิม 4 งาน และ deadline รวม 60 วินาที

Image embedding/Ollama pipeline ของทีมยังอยู่ตามเดิม ไม่ต้องดาวน์โหลดโมเดลหรือสร้าง image index สำหรับ flow นี้ การสลับ `image_embedding` ต้องเตรียมโมเดลและ real pgvector index ก่อน ไม่ใช้ผล mock เป็นผลค้นใน chat

## Database และการทดสอบ

ใช้ `image_uploads`, `chat_messages.image_id` และ JSONB `product_refs` เดิม **ไม่มี migration ใหม่** API content ตรวจ ownership ทุกครั้งและส่ง `Cache-Control: private, no-store`

- Unit: request/default/bounds, lazy model init, guessed-category contradiction, image text injection และ storage
- PostgreSQL disposable: upload/ownership/replay/image change conflict, quota และ claim/delete/logout/failure ระหว่าง Vision รวม regression Auth/Text RAG
- Browser mocks: แนบรูป+คำถาม, validation/removal ไม่เรียก upload, failed send/retry ไม่ upload ซ้ำ, แสดง private preview/history ทั้ง Mobile/Tablet/Desktop
- Real smoke: `cd backend` แล้ว `.\.venv\Scripts\python.exe -m scripts.test_vision_chat_browser` ใช้ public catalog photo + สำเนาสินค้า/เวกเตอร์ใน disposable DB เท่านั้น ไม่คัดลอกบัญชี/ประวัติ ทดสอบ browser จริง → API → PostgreSQL → OpenRouter Vision → Text RAG แล้ว reload รูปและผลค้น ดู [ผลจริง](../report/VISION_CHAT_BROWSER.json)

Live smoke เป็นหนึ่งตัวอย่างที่ผ่าน ไม่ใช่ผลประเมินความแม่นยำ Vision ทุกภาพ รูปเบลอ ชื่อรุ่นอ่านผิด และ catalog ไม่ครบยังเป็นข้อจำกัด ไม่มี streaming จริง, หลายรูปต่อข้อความ หรือการซื้อสินค้า

### ผลตรวจรอบนี้

- Focused Vision/storage unit: **8 ผ่าน**
- PostgreSQL disposable regression: **74 ผ่าน** (Vision ใน transaction tests เป็น fake)
- Frontend unit: **29 ผ่าน**, TypeScript ผ่าน
- Browser API mocks: **30 ผ่าน** รวม Mobile/Tablet/Desktop
- Real browser smoke: **ผ่าน 1 รูปสาธารณะ** ใช้ OpenRouter Vision และ query embedding จริง พบสินค้าและเปิดรูป/ประวัติหลัง reload ได้; ไม่ใช้ผล mock เป็นหลักฐานว่าโมเดลจริงแม่นยำ
- Legacy `test_vision_api.py` แบบ TestClient ค้างและยุติ ไม่รายงานว่าผ่าน ชุด PostgreSQL API และ live browser ข้างต้นตรวจเส้นทางที่เพิ่มในรอบนี้แล้ว

## ลองด้วยตัวเอง

เปิด `/chat` → กด **＋ รูปภาพ** → เลือกรูปเครื่องเขียน → พิมพ์ “มีสินค้านี้ไหม” หรือเลือก prompt → ส่ง → ตรวจการ์ดสินค้าใกล้เคียง → reload ต้องยังเห็นรูปและข้อความ ทดสอบถามราคาพร้อมรูป แล้วลองข้อความล้วนต่อได้

Postman: [Collection](../api/image/vision-chat.postman_collection.json) ตั้ง `base_url=http://localhost:8000/api/v1`, `origin=http://localhost:3000` ใช้ cookie jar จาก Create Guest แล้วเลือกไฟล์ใน Upload เก็บ image/session IDs อัตโนมัติ ก่อน Send/Replay ใช้ request UUIDv7 เดียวกัน
