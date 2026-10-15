# สรุปหลักฐาน Catalog + Text Index — 13 ตุลาคม 2026

## สิ่งที่ทำจริง

| ขั้นตอน | หลักฐาน |
|---|---|
| รวมข้อมูล | เดิม 50 + Officework 15 + OfficeMate 2 = 67 สินค้า |
| พักข้อมูล | OfficeMate Y013221 หน่วยขายไม่ชัด 1 รายการ |
| สำรอง | PostgreSQL dump ก่อนนำเข้าใน .local/backups/before-reviewed-catalog-20261013.dump |
| Import | Transaction/upsert; สินค้า 67 และข้อมูลรูป 67 แถว |
| Validate | 67 examined, 0 invalid, 68 warnings |
| Index จริง | OpenRouter Qwen3 Embedding 4B: indexed 67, failed 0, remaining 0 |
| ตรวจเวกเตอร์ | 67 แถว; min/max dimensions = 1024/1024 |
| Index ซ้ำ | indexed 0, unchanged 67, failed 0; ไม่มีสินค้าเปลี่ยนที่ต้องเรียก provider |
| Import ซ้ำ | จำนวนสินค้า/รูปคงเดิม และ index ซ้ำยัง unchanged 67 |
| IDs | สินค้าทั้ง 67 ใช้ UUIDv7 |
| Tests รอบนี้ | 20 passed, 8 skipped; PostgreSQL disposable suite ไม่ได้เปิดในรอบนี้ |
| Diff | git diff --check ผ่าน |

ผล Validate/Index แบบมี Product IDs ดู CATALOG_INDEX_RESULT.json ไม่มีบัญชีหรือ credentials ในรายงาน

## ประเด็นที่ต้องพูดตรง ๆ ต่ออาจารย์

- การสร้างเวกเตอร์สำเร็จยังไม่ใช่ผลวัดความแม่นยำ ต้องทำ semantic retrieval และ evaluation ต่อ
- หน้าแชตยังใช้ template ไม่ใช่ LLM answer
- 68 warnings เป็นข้อมูลที่ยังขาด เช่น description เดิม 50 รายการ และราคา 18 รายการที่พักไว้ ไม่ใช่ provider error
- ข้อมูลสินค้าใหม่มีราคา snapshot ต้นทาง แต่ราคาใน products เป็น NULL เพื่อไม่ใช้ราคา VAT/หน่วยไม่ชัดกับ budget search
- ไม่อ้างว่า availability เป็น stock ปัจจุบัน
- สิทธิ์การใช้ภาพยังไม่ยืนยัน; ไม่ควรอ้างว่าได้สิทธิ์เผยแพร่จากการดาวน์โหลด
- CSV Vision เดิมยังมี 50 รายการ ส่วน manifest Text/DB มี 67 จึงต้องตกลงการ sync กับเพื่อนก่อนเพิ่ม Vision

## ใช้เล่า flow สั้น ๆ

“เราควบคุมแหล่งข้อมูลสินค้า ตรวจความครบถ้วนและราคา นำเข้าฐานข้อมูลแบบรันซ้ำได้ แล้วแปลงข้อความสินค้าเป็นเวกเตอร์ 1024 มิติผ่าน OpenRouter เก็บใน pgvector เวกเตอร์นี้เตรียมใช้ค้นหาตามความหมาย ขั้นถัดไปจะนำสินค้าที่ค้นได้ให้ LLM เรียบเรียงและตรวจคำตอบให้ตรงกับ catalog”

วิธีทำงานทุกขั้นดู ../architecture/CATALOG_RAG_PROCESS.md
