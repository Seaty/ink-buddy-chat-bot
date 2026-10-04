# API documentation

- [API_SPEC.md](API_SPEC.md) — เอกสารหลักรวม paths, contracts, Guest design และสถานะ implemented/scaffold
- [openapi.current.json](openapi.current.json) — snapshot จาก FastAPI; generate ใหม่เมื่อเปลี่ยน schemas/routes
- [Backend structure](../architecture/BACKEND_STRUCTURE.md) — ตำแหน่งโค้ดและกติกาการแบ่ง module

25 operations: 13 implemented และ 12 scaffold ที่ตรวจสิทธิ์ก่อนตอบ 501 Auth/Guest token, whitelist, quota 3 รูป และ claim ใช้งานแล้ว ดู [คู่มือ Auth](auth/README.md) สำหรับ setup/testing

## Modules

| Folder | Responsibility |
|---|---|
| [auth](auth/README.md) | Login, refresh/logout, Guest credentials |
| [user](user/README.md) | Profile ของบัญชี |
| [session](session/README.md) | Chat sessions, messages และ Guest ownership |
| [image](image/README.md) | Upload/detail/delete และโควตา Guest |
| [product](product/README.md) | Product metadata และ image search |
| [admin](admin/README.md) | Catalog indexing และสิทธิ์ admin |
| [system](system/README.md) | Health/readiness |
