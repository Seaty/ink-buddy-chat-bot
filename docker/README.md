# Run Ink Buddy PostgreSQL with Podman

โฟลเดอร์นี้เก็บการตั้งค่า Podman Compose สำหรับ PostgreSQL + pgvector เฉพาะการพัฒนาในเครื่อง ยังไม่ได้รัน backend, frontend หรือ Ollama

## เริ่มใช้งานบน Windows (PowerShell)

จาก root ของ repository:

```powershell
Set-Location docker
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

เปิด `docker/.env` และกำหนด `POSTGRES_PASSWORD` เป็นรหัสผ่านของคุณเอง จากนั้น:

```powershell
podman machine start
podman compose up -d
podman compose ps
```

หากยังไม่เคยสร้าง Podman machine ให้รัน `podman machine init` หนึ่งครั้งก่อน `podman machine start` และต้องมี Compose provider ที่ `podman compose` ใช้งานได้

## การตั้งค่า

| ค่าใน `.env` | ค่าแนะนำ | ความหมาย |
|---|---|---|
| `POSTGRES_DB` | `ink_buddy` | ชื่อฐานข้อมูล |
| `POSTGRES_USER` | `ink_buddy` | ชื่อผู้ใช้ฐานข้อมูล |
| `POSTGRES_PORT` | `5432` | พอร์ตบนเครื่อง; เปลี่ยนได้หากถูกใช้อยู่ |
| `POSTGRES_PASSWORD` | กำหนดเอง | ต้องไม่ว่าง; `.env` ถูก ignore จาก Git |

การเชื่อมจากเครื่องนี้ใช้ host `127.0.0.1` และพอร์ตใน `.env` Compose bind พอร์ตเฉพาะ loopback; เครื่องอื่นในเครือข่ายเชื่อมเข้ามาไม่ได้โดยตรง ข้อมูลอยู่ใน named volume `postgres_data`

## SQL init และการดูแล

`compose.yaml` mount `../database/ddl/001_init.sql` ไปยัง `/docker-entrypoint-initdb.d/001_init.sql` และ PostgreSQL จะเรียกไฟล์นี้เมื่อสร้าง data volume เปล่าครั้งแรก การแก้ init script ภายหลังไม่เปลี่ยนฐานข้อมูลที่สร้างแล้ว ให้ใช้ migration

```powershell
podman compose logs postgres
podman compose down
```

`down` ไม่ลบ named volume; อย่าใช้ `down -v` เมื่อมีข้อมูลที่ต้องเก็บ รายละเอียดตารางและ index อยู่ใน [`../database/DATABASE_SCHEMA.md`](../database/DATABASE_SCHEMA.md)

## สถานะ schema ที่ตรวจล่าสุด

2026-10-03: init ปัจจุบันมี 13 ตาราง ฐาน local เครื่องที่ทดสอบ apply migration 004 แล้ว สถานะนี้ไม่หมายความว่าฐานของสมาชิกทีมอื่นอัปเดตแล้ว ฐานเดิมให้ตรวจ migrations 001–004 ตาม Database Schema และสำรองก่อนอัปเดต ห้ามใช้ init ซ้ำเพื่ออัปเกรด volume เดิม

วิธีรัน integration tests ในฐานแยกอยู่ใน [Auth setup](../docs/api/auth/README.md)


## UUIDv7 (2026-10-03)

ID ใหม่ที่เป็น UUID ใช้ UUIDv7: database defaults เรียก `public.ink_buddy_uuid_v7()` และ Python ใช้ `app.core.identifiers.uuid7()` ชนิด column/API ยังคง UUID เพื่อรองรับ ID เดิม ไม่มีการเปลี่ยน primary/foreign keys ที่มีอยู่ ฐานเดิมต้อง apply `database/migrations/004_uuid_v7.sql` หลัง 003; ฐานใหม่ใช้ init ปัจจุบัน migrations 001–003 เก็บเป็นประวัติเดิม

UUIDv7 มี Unix timestamp ระดับ millisecond และ random bits ตาม [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7) ไม่รับประกันลำดับภายใน millisecond หรือเมื่อ clock ย้อนกลับ ไม่ใช้ ID เป็น credential และยังตรวจ ownership ตามเดิม PostgreSQL 16 ใช้ compatibility function เพราะ built-in generator เป็น UUIDv4; ไม่มีการเปลี่ยนคอลัมน์ integer เช่น product_image_embeddings.id
