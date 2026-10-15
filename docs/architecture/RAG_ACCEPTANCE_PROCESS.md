# Process 4: ชุดคำถามใหม่และ Browser Acceptance

วันที่ทดลอง 2026-10-13 — ต่อจาก Quality/Tuning และ Robustness ไม่ใช่สรุปโครงการทั้งหมด

## ขอบเขต

สร้างคำถามใหม่ 12 ข้อใน `backend/datasets/evaluation/rag_acceptance.json` ก่อนรัน และไม่ปรับ retrieval/adapter จากผลชุดนี้ ตรวจสี วัสดุ ยี่ห้อ งบ คำถามกว้าง ภาษาอังกฤษ/นอกขอบเขต injection และคำถามต่อเนื่องที่ข้อมูลไม่พอ

คำถามต่างจากชุดก่อน แต่ใช้ catalog เดียวกันและบางสินค้าซ้ำ Labels ยังเป็น draft ที่ผู้ช่วยจัดทำ **ไม่ใช่ชุดประเมินอิสระโดยมนุษย์** ผล 12/12 หมายถึงผ่าน constraints ที่ประกาศ ไม่ใช่ความแม่นยำคำแนะนำหรือความพึงพอใจของผู้ใช้

รายงานบันทึก dataset SHA256, adapter/policy SHA256, model, จำนวน catalog และเวลา เพื่อระบุเวอร์ชันที่ทดลอง ไฟล์คำถามและผลต้องเก็บคู่กัน หากแก้ label ภายหลังให้ระบุเหตุผลและอย่าเขียนทับหลักฐานเดิม

## A. ทดลอง Catalog จริงผ่าน Retrieval/AI

ใช้ catalog local 67 สินค้า ไม่เขียนสินค้า embeddings หรือข้อความใหม่ เรียก query embeddings 8 ครั้ง และ Text LLM 7 ครั้ง; อีก 5 เคสตอบจาก catalog policy โดยไม่เรียก Text LLM

- ผ่าน constraints 12/12
- Input tokens 2,403 / output tokens 459
- ค่า chat ที่ provider รายงาน 0.00038206 USD เฉพาะรอบนี้ ไม่รวม embedding หรือ browser trials
- Pipeline p50 2,525.81 ms / p95 9,963.97 ms
- LLM 7 calls: p50 2,362.74 ms / p95 8,556.03 ms

จำนวนตัวอย่างน้อย ไม่ใช่ production SLA หรือค่ารายเดือน เวลา pipeline นี้เป็น service evaluation ไม่รวม Browser/API; query vectors เป็นการเรียกใหม่ในรอบนี้ ต่างจากรอบ tuning ที่ใช้ cache จึงไม่ควรนำ percentile มาเปรียบเทียบว่าระบบช้าลงโดยตรง

หลักฐาน [ผลอัตโนมัติ](../report/RAG_ACCEPTANCE_frozen.json) และ [คำถาม/คำตอบให้ทีมตรวจ](../report/RAG_ACCEPTANCE_frozen_HUMAN_REVIEW.md) คำตอบเป็นข้อความสังเคราะห์จากชุดทดลองและ catalog ไม่ใช่ประวัติผู้ใช้ ไม่เก็บ password/token/ข้อมูลบัญชี

## B. Browser → API → Disposable PostgreSQL → OpenRouter

ใช้หน้า Next.js ที่รัน local และ browser viewport 390×844 จริง Browser forwarding ส่งคำขอไป backend ทดสอบ port 8001 ซึ่งใช้ฐาน `ink_buddy_test_<UUIDv7>` ใหม่ แล้วลบทิ้งใน finally ไม่ seed ฐานหลัก

```text
Browser :3000 → forwarded real HTTP API :8001
             → disposable PostgreSQL + indexed synthetic product
             → OpenRouter embedding / Qwen3 14B
             → atomic message history → Browser
```

ไม่ใช้ canned API responses แต่ใช้สินค้าทดสอบ Browser Smoke Pen ราคา 50 THB และ source `example.test` เพื่อทดสอบ plumbing เท่านั้น รูปแบบสินค้านี้ไม่ใช่หลักฐานคุณภาพ catalog จริง ซึ่งทดสอบแยกในส่วน A

ตรวจผ่าน:

1. Guest ส่งข้อความแล้วได้รับคู่ User/Assistant และ product_refs
2. replay Request ID/content เดิม คืนคู่เดิมแบบเดียวกัน HTTP 201
3. reload แล้วเห็นประวัติและสินค้า
4. Register/Login และ claim แชต Guest
5. User ส่งข้อความใหม่แล้วได้ป้าย AI
6. งบไม่พบสินค้าตอบจากกฎระบบพร้อมป้ายแหล่งคำตอบ

รอบแรกตัวทดสอบคาด HTTP 200 ผิดจาก API specification ซึ่งคืน 201 แก้ assertion ให้ตรง API ไม่แก้ระบบ ต่อมาพบ environment ของ report/screenshot ไม่ถูกส่งให้ Node process จึงแก้ runner และตรวจซ้ำ ทั้งสองประเด็นเป็นตัวทดสอบ หลักฐานล่าสุดบันทึกสำเร็จที่ [Browser acceptance](../report/RAG_BROWSER_ACCEPTANCE.json)

ภาพ Mobile อยู่ใน `.local/browser-smoke/acceptance-mobile.png` ซึ่งไม่ขึ้น Git ตรวจภาพแล้วมีข้อความ สินค้า ป้ายแหล่งคำตอบและช่องพิมพ์ ไม่มีเนื้อหาล้นแนวนอนในภาพที่ตรวจ ยังไม่ได้ทดสอบ Tablet/Desktop ใหม่ใน process นี้ และไม่ได้ยืนยัน UI error/timeout ด้วย provider จริงในรอบนี้; regression/mocks ของรอบก่อนยังเป็นหลักฐานแยก

## C. หลักฐานสำหรับทีมประเมิน

ไฟล์ HUMAN_REVIEW มี 12 คำถาม คำตอบที่ระบบประกอบ และ SKU/name/source ของสินค้าแต่ละข้อ เก็บทั้งผล success/error ถ้ามี คะแนนยังว่าง ใช้ [แบบประเมิน](RAG_HUMAN_REVIEW.md) ตรวจความตรงคำถาม ข้อเท็จจริง หลักฐาน ที่มา ความเข้าใจง่าย และการขอข้อมูลเพิ่ม

หากทีมพบข้อผิดพลาดและใช้ผลนี้ปรับระบบ ชุดนี้จะกลายเป็น development data รอบถัดไปต้องเตรียมชุดใหม่เพื่อประเมิน ไม่ตีความคะแนนของผู้ช่วยเป็นคะแนนผู้ประเมินอิสระ

## รันซ้ำ

จาก backend เมื่อ local Frontend/Podman PostgreSQL พร้อมและตั้ง OpenRouter key ใน `.env` แล้ว:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_rag_robustness --live --answers --suite acceptance --review-artifact --label next_trial
.\.venv\Scripts\python.exe -m scripts.test_chat_browser --rag
.\.venv\Scripts\python.exe -m pytest tests/test_rag_robustness.py tests/test_rag_quality.py tests/test_openrouter_adapter.py -q
```

ใช้เครดิตจริง ไม่มี retry/fallback อัตโนมัติ ชุด evaluation เก็บรายงานตาม label; browser report ล่าสุดใช้ชื่อเดิม หากต้องเก็บหลายรอบให้คัดลอกรายงานก่อนรันครั้งถัดไป

Focused regression รอบนี้ 21 passed; PostgreSQL auth/message transaction 54 passed เป็นหลักฐานจาก process ก่อน ไม่ได้รัน suite นั้นใหม่ใน process นี้ แต่ Browser ใช้ disposable PostgreSQL จริงในรอบนี้

## สิ่งที่ยังต้องทำก่อนสรุปทุก Process

- ทีมกรอกคะแนนและข้อสังเกต โดยเฉพาะคุณภาพเหตุผลหนึ่งหลักฐานและคำแนะนำแบบกว้าง
- เพิ่มคำถามจากผู้ทดลองที่ไม่ใช่ผู้พัฒนา สำหรับการประเมินอิสระที่แท้จริง
- รวบรวมค่าใช้จ่ายจริงทั้งหมดจาก OpenRouter และตรวจความสม่ำเสมอหลายรอบหากจะอ้างเชิงวิจัย
- รีวิว diff/เอกสารและเตรียม PR หลังจบงานที่ตกลง ยังไม่เปิด PR ใน process นี้
