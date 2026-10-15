# Process 3: ทดสอบ Guardrails ความสม่ำเสมอ เวลา และ Token Usage

วันที่ทดลอง 2026-10-13; ใช้ catalog 67 สินค้าใน local PostgreSQL, Qwen3 Embedding 4B และ Qwen3 14B ผ่าน OpenRouter ไม่แก้ Image Embedding

## เป้าหมายและวิธีทำ

ขยายจากการค้นชื่อสินค้าตรง ๆ เป็นคำถามแนะนำแบบกว้าง ภาษาอังกฤษ ยี่ห้อไทย ช่วงงบ ไม่พบข้อมูล คำถามต่อเนื่อง ขอบเขตผสม prompt injection ที่เปลี่ยนตัวพิมพ์/แทรก zero-width และ SQL special characters

ไฟล์ `backend/datasets/evaluation/rag_robustness.json` มี 13 ข้อ ตรวจสถานะ guardrail ประเภท/ยี่ห้อ/งบของผลค้นหา และการไม่เรียก LLM เมื่อระบบต้องปฏิเสธหรือถามเพิ่ม Labels เป็นกติกาฉบับร่าง ไม่ใช่คะแนนคุณภาพคำตอบจากมนุษย์ และชุดนี้ถูกใช้แก้ระบบแล้ว จึงไม่ใช่ชุดทดสอบอิสระ

```text
คำถาม → Input Policy → Hybrid Retrieval → Constraint checks
       → ถ้าไม่มีสินค้า: Catalog Policy (ไม่เรียก LLM)
       → ถ้ามีสินค้า: LLM เลือก Product/Evidence IDs
       → Output validation → วัดเวลา / usage / ผลตรวจ
```

เครื่องมือ `backend/scripts/evaluate_rag_robustness.py` อ่าน DB จริง ไม่เขียนสินค้า/เวกเตอร์/ข้อความ ใช้ query-vector cache จาก process ก่อน เก็บเฉพาะ SKU สถานะ error code token counts และชนิดข้อผิดพลาดของ output ไม่เก็บคำตอบเต็มหรือ credentials

## สิ่งที่พบและแก้

1. สีทองยังไม่อยู่ในกติกาตรวจสี ทำให้คืนสมุดสีอื่น เพิ่มสีทอง/สีเงินแล้วต้องพบหลักฐานใน catalog
2. เคสเดิมคาดว่าปากกาเจล 50–100 บาทต้องพบสินค้า แต่ตรวจ DB พบราคาที่พร้อมใช้เพียง 42 THB แก้ expectation เป็น no_match และเพิ่มช่วง 40–50 บาทเป็น positive โดยเก็บรายงานเดิมไว้ ไม่เติมราคาสินค้าหรือใช้ราคา NULL เป็นศูนย์
3. คำถามกว้างมีผลค้นหาถูกต้อง แต่ AI เคยเลือก Evidence ID ที่ไม่ตรงสินค้า และบางรอบมี ID ซ้ำ ตัวตรวจตอบ INVALID_ANSWER ตามเดิม ไม่ปล่อยผ่าน ไม่ fallback และไม่ retry อัตโนมัติ
4. ทดลอง generation schema แบบแยกรายสินค้าแล้ว provider ตอบ ANSWER_FAILED จึงไม่ใช้แบบนั้น รายงานไม่เก็บ upstream response body จึงยังสรุปสาเหตุ HTTP เชิงลึกไม่ได้
5. ใช้ schema เดิมเพิ่มเติม enum ของ Product/Evidence IDs ที่มีจริง และให้โมเดลเลือกหลักฐานสำคัญ **หนึ่งข้อ** ต่อสินค้า ลดโอกาส ID ซ้ำและจำนวน output tokens

Validator ยังรองรับ contract เดิม 1–4 หลักฐาน ตรวจความสัมพันธ์ ID กับสินค้าและรายการซ้ำทุกครั้ง; generation จำกัดหนึ่งข้อซึ่งเป็นส่วนย่อยของ contract เดิม ไม่ deduplicate หรือซ่อมคำตอบผิดเงียบ ๆ Adapter input/output และ API ไม่เปลี่ยน ไม่มี migration

Trade-off: หนึ่งหลักฐานอ่านง่ายและลด output แต่เหตุผลที่แสดงไม่ครอบคลุมหลายคุณสมบัติ ต้องประเมินกับทีมว่าพอสำหรับคำแนะนำหรือไม่ ข้อมูลราคาและที่มาของสินค้าใน product_refs ยังมาจาก snapshot จริง

## หลักฐานก่อน–หลัง

| รอบ | ผล | หมายเหตุ |
|---|---:|---|
| initial | 9/12 | พบสีที่ไม่ตรวจ เคสงบ expectation ผิด และ output AI ไม่ผ่าน |
| corrected | 12/13 | แก้สี/งบ แต่คำถามกว้างยังผิด contract |
| broad_diagnostic / trial_2 / trial_3 | 1/1, 0/1, 0/1 | การทดลองที่สั่งแยกเอง แสดงความไม่สม่ำเสมอ ไม่มี retry ใน production |
| grounded_schema | 9/13 | provider errors สำหรับ schema ที่ทดลอง ไม่ใช่เวอร์ชันใช้งาน |
| enum_schema | 12/13 | ไม่มี foreign ID ในคำถามกว้าง แต่ยังพบ evidence ซ้ำ |
| final | 13/13 | enum + หนึ่งหลักฐานต่อสินค้า |

รายงานอยู่ใน `docs/report/RAG_ROBUSTNESS_*.json` เก็บรอบที่ไม่ผ่านไว้ด้วย ผล final เป็นการทดลองครั้งเดียว ไม่รับประกันทุกคำตอบในอนาคต ผู้ใช้ยังอาจได้รับ INVALID_ANSWER และคงร่างเพื่อส่งใหม่ด้วยตัวเอง

## เวลาและต้นทุนที่วัดได้จากรอบ final

- Total pipeline p50 312.94 ms / p95 3,648.93 ms สำหรับ 13 เคส ซึ่งรวมเคสปฏิเสธที่ไม่เรียก LLM
- เฉพาะ LLM 4 เคส: p50 1,606.68 ms / p95 3,266.26 ms
- nearest-rank percentiles; จำนวนตัวอย่างน้อย p95 ของ 4 เคสคือค่าสูงสุด ไม่ใช่ production SLA
- Query embeddings ใช้ cache 8 ครั้ง ไม่มี embedding call ใหม่ในรอบ final จึงไม่ใช่ latency แบบ cold embedding หรือ Browser/API end-to-end
- Chat input 2,147 tokens / output 476 tokens
- Provider รายงานค่า Chat รวม **0.0003652 USD** สำหรับรอบ final 4 calls เท่านั้น ไม่รวมรอบทดลองก่อนหน้า embedding หรือ failed upstream requests; ค่าไม่พบถือว่าไม่ทราบ ไม่ตีความว่าเป็นศูนย์
- ค่าใช้จ่ายจริงทั้งหมดตรวจจาก OpenRouter dashboard; ไม่ใช้ราคาคาดเดาและไม่ประมาณค่ารายเดือนจากตัวอย่างเล็กนี้

63 unit/client/adapter/policy/search tests passed และ PostgreSQL disposable transaction regression 54 passed หลังปรับกติกา ไม่มี Browser smoke ใหม่ใน process นี้ ผล browser รอบก่อนอยู่ใน RAG_CHAT_VERIFICATION.json

## วิธีรันซ้ำ

จาก `backend` หลังตั้ง `.env`:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_rag_robustness --live --answers --label trial
.\.venv\Scripts\python.exe -m scripts.evaluate_rag_robustness --live --answers --case general-gel --label broad_trial
.\.venv\Scripts\python.exe -m pytest tests/test_rag_robustness.py tests/test_openrouter_client.py tests/test_openrouter_adapter.py tests/test_retrieval_policy.py tests/test_chat_search.py -q
.\.venv\Scripts\python.exe -m scripts.test_auth_postgres
```

`--live` จำเป็น, `--answers` ใช้เครดิตจริง; ไม่ใส่ `--answers` จะตรวจ retrieval เท่านั้น Exit 1 เมื่อมีเคสไม่ผ่าน แต่ยังสร้างรายงานให้ตรวจได้ ไม่ควรยิงซ้ำจนผ่านแล้วทิ้งรอบล้มเหลว

## ทีมตรวจคุณภาพก่อนสรุปทุก Process

ให้ผู้ประเมินตรวจคำตอบจากหน้าเว็บและ catalog โดยบันทึกแต่ละข้อใน [แบบประเมิน](RAG_HUMAN_REVIEW.md) ยังไม่ได้มีคะแนนมนุษย์ในรอบนี้ งานต่อไปคือชุดใหม่ที่ไม่ใช้ปรับระบบและทดลอง Browser ครบเส้นทางก่อนปิดงาน/PR
