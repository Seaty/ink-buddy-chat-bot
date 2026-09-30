# Run Ink Buddy PostgreSQL with Podman

โฟลเดอร์นี้เก็บการตั้งค่า Podman Compose สำหรับ PostgreSQL + pgvector เฉพาะการพัฒนาในเครื่อง ยังไม่ได้รัน backend, frontend หรือ Ollama

## เริ่มใช้งานบน Windows (PowerShell)

จาก root ของ repository:

```powershell
Set-Location docker
Copy-Item .env.example .env
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
