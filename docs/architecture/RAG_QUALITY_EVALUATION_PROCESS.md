# Process 1–2: ประเมินคุณภาพ Text RAG และปรับ Retrieval

วันที่ทดลอง: 2026-10-13 — ประเมิน catalog ใน local PostgreSQL ใช้ query embeddings ผ่าน OpenRouter และทดลอง Answer Adapter จริง

## 1. เตรียมคำถามและคำตอบคาดหวัง

ไฟล์ `backend/datasets/evaluation/rag_quality.json` มี 24 คำถาม: development 12 และ holdout 12 ครอบคลุมชื่อรุ่น หมวด ยี่ห้อ สี วัสดุ งบ ไม่พบสินค้า นอกขอบเขต และคำถามที่ต้องขอข้อมูลเพิ่ม เป็น positive 19 และ negative/clarification 5 เคส

แต่ละข้อมี SKU ที่คาดหวัง สถานะ guardrail และเหตุผลจากข้อมูล catalog ไม่ใช้รายการที่ระบบคืนเป็น gold โดยตรง อย่างไรก็ตาม labels เป็นฉบับร่างที่ช่วยจัดทำจากข้อมูลสินค้า **ยังไม่ได้ตรวจโดยผู้ประเมินอิสระ** และไม่รับประกันว่าระบุสินค้าที่เกี่ยวข้องครบทุกชิ้น

ทั้งสองชุดใช้ catalog เดียวกัน บางข้ออ้างสินค้าซ้ำ และผล holdout เคยถูกดูระหว่างงานแล้ว จึงใช้เปรียบเทียบก่อน–หลังได้ แต่ไม่ใช่ blind holdout สำหรับอ้างความแม่นยำทั่วไป ต้องให้ทีมตรวจ labels และสร้างชุดใหม่ที่ไม่ใช้ปรับระบบก่อนนำไปอ้างเป็นผลวิจัย

## 2. วัด baseline

เครื่องมือ `backend/scripts/evaluate_rag_quality.py` อ่าน products/index จาก DB เรียก Hybrid Retrieval และเทียบ SKU กับ gold ไม่เขียนสินค้า embeddings หรือประวัติแชต

```text
คำถาม → Scope/constraints → Keyword + Semantic → RRF
       → ตรวจหลักฐานคุณสมบัติ → ผลสูงสุด 5 → เทียบ gold SKUs
```

ตัวชี้วัดคำนวณเฉพาะ positive cases ยกเว้น decision accuracy และ negative false-positive rate:

| ตัวชี้วัด | ความหมาย |
|---|---|
| Recall@5 | พบสินค้าที่ gold ระบุครบเพียงใด |
| Precision@5 | จำนวน gold ที่พบหาร 5 เสมอ |
| Precision returned | สัดส่วน gold ในรายการที่คืนจริง |
| HitRate@5 | สัดส่วนคำถามที่พบ gold อย่างน้อยหนึ่งรายการ |
| MRR | ลำดับของ gold รายการแรก |
| nDCG@5 | คุณภาพลำดับแบบ relevance 0/1 ไม่มีระดับความชอบ |
| Decision accuracy | สถานะ allowed/no_match/blocked/needs_clarification ตรงกับที่คาดหรือไม่ |
| Negative false-positive rate | คำถามที่ไม่ควรคืนสินค้ากลับคืนสินค้าเท่าใด |

ถ้า gold มีหนึ่งชิ้น และคืนถูกหนึ่งชิ้น Precision@5 เท่ากับ 0.2 ตามนิยาม ไม่ได้หมายถึงระบบตอบถูกเพียง 20% จึงต้องอ่านร่วมกับ Recall, Precision returned และ MRR

## 3. ปรับ Retrieval ตามปัญหาที่พบ

- เพิ่มหมวด aliases `สีไม้`, `ดินสอสี`, `colored pencil`
- เพิ่ม aliases ยี่ห้อไทย เช่น พลัส เพนเทล เอลเมอร์ และใช้ boundary ของชื่อภาษาอังกฤษ ป้องกัน `Uni` ตรงกับ `university`
- เพิ่มสีขาว น้ำตาล และใสในการตรวจคุณสมบัติ
- เมื่อถามวัสดุเหล็ก/พลาสติก หรือระบายน้ำ ต้องพบข้อความนั้นในข้อมูลสินค้า ไม่อนุมานจาก similarity
- ใช้ตัวตรวจยี่ห้อร่วมกันระหว่าง keyword และ semantic เพื่อให้ข้อจำกัดตรงกัน

Trade-off: การต้องมีหลักฐานช่วยลดคำแนะนำผิดคุณสมบัติ แต่สินค้าที่ข้อมูลขาด หรือเขียนวัสดุอีกภาษาหนึ่งอาจถูกตัดออก ขั้นต่อไปควรปรับข้อมูลและ aliases จากหลักฐาน ไม่เติมคุณสมบัติสมมติ

## 4. เปรียบเทียบผล

| กลุ่ม/Metric | Baseline | หลังปรับ |
|---|---:|---:|
| Development Recall@5 | 0.90 | 1.00 |
| Development Precision returned | 0.80 | 1.00 |
| Development Decision accuracy | 0.917 | 1.00 |
| Holdout Recall@5 | 1.00 | 1.00 |
| Holdout Precision returned | 0.731 | 1.00 |
| Holdout MRR / nDCG@5 | 1.00 / 1.00 | 1.00 / 1.00 |
| Negative false-positive rate ทั้งสองกลุ่ม | 0 | 0 |

ผลนี้ใช้ได้เฉพาะ 24 ข้อที่ labels ยังเป็นฉบับร่าง ไม่ใช่ความแม่นยำรวมของ chatbot และคำถามส่วนใหญ่เป็นการค้นสินค้าเจาะจง ไม่ครอบคลุมคำแนะนำหลายเงื่อนไขหรือบทสนทนาต่อเนื่อง

เทียบ similarity threshold 0.35, 0.45, 0.55, 0.65 บน development เท่านั้น: ทุกค่ามี Recall/MRR/nDCG/Precision returned = 1 และ decision accuracy = 1 จึง **คงค่าเริ่มต้น 0.35** ไม่มีหลักฐานในชุดนี้ว่าการเพิ่ม threshold ดีกว่า ผลเท่ากันใน Hybrid ไม่ได้แปลว่า semantic scores ของทุกสินค้าสูงกว่า threshold เพราะ keyword channel ยังช่วยคืนผลได้

หลักฐาน: `docs/report/RAG_QUALITY_baseline.json`, `RAG_QUALITY_tuned.json` และ `RAG_QUALITY_dev_0_35.json` ถึง `RAG_QUALITY_dev_0_65.json`

## 5. ตรวจ Answer Adapter และ Regression

- เรียก Qwen3 14B จริงสำหรับ positive holdout 9 ข้อ: ผ่าน evidence contract 9/9 และเลือก SKU ที่อยู่ใน gold ทุกข้อ
- ตรวจ contract คือ JSON/IDs และความสัมพันธ์กับ snapshot ไม่ใช่การประเมินความพึงพอใจ ความลื่นไหล หรือคุณภาพเหตุผลโดยมนุษย์
- Unit/adapter/retrieval regression: 43 passed
- PostgreSQL transaction/auth/message regression: 54 passed ในฐานชั่วคราวที่สร้างและลบทิ้ง แยกจากฐานหลัก
- ไม่ได้ทดลอง Browser ครบเส้นทางใหม่ในรอบนี้ หลักฐาน Browser ของรอบเชื่อมแชตดู `RAG_CHAT_VERIFICATION.json`

## 6. วิธีรันซ้ำ

จาก `backend` หลังตั้ง `.env` สำหรับฐาน local และ OpenRouter:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_rag_quality --live --label trial
.\.venv\Scripts\python.exe -m scripts.evaluate_rag_quality --live --split development --threshold 0.45 --label dev_trial
.\.venv\Scripts\python.exe -m scripts.evaluate_rag_quality --live --label answer_trial --answers
.\.venv\Scripts\python.exe -m pytest tests/test_rag_quality.py tests/test_retrieval_policy.py tests/test_chat_search.py tests/test_openrouter_adapter.py -q
.\.venv\Scripts\python.exe -m scripts.test_auth_postgres
```

`--live` จำเป็นเพื่อยืนยันการอ่าน DB/ใช้ provider จริง ครั้งแรกอาจเสียเครดิต embedding; `--answers` เสียเครดิต LLM ด้วย ไม่มี retry/fallback อัตโนมัติ Query vectors เก็บใน `.local/rag-quality-query-cache.json` ซึ่งไม่ขึ้น git โดย key รวม model/dimensions/query hash การทดลอง threshold ใช้ cache ไม่เรียก embeddings ซ้ำ โมเดลหรือ catalog ที่เปลี่ยนทำให้ผลเทียบข้ามรอบไม่ได้โดยตรง

Reports ใหม่มีเวลา โมเดล มิติ และ dataset hash; baseline/tuned เดิมสร้างก่อนเพิ่ม metadata เหล่านี้ ไม่เติมย้อนหลังเป็นข้อมูลวัดจริง รายงานไม่เก็บ key/token หรือคำตอบสนทนาเต็ม

## งานต่อจาก Process นี้

ให้ทีมตรวจ gold labels เพิ่มคำถามคำแนะนำแบบกว้าง งบหลายช่วง ภาษาอังกฤษ คำผิด ข้อมูลสินค้าไม่ครบ และโจมตีที่ยังไม่เคยใช้ปรับระบบ จากนั้นประเมินชุดอิสระและต้นทุน/latency จึงสรุปภาพรวมทุก process ตามที่ตกลง
