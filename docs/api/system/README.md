# System API

ตรวจล่าสุด 2026-10-03 จาก OpenAPI snapshot ดูรายละเอียด request/response และสิทธิ์ใน [API_SPEC](../API_SPEC.md)

| Operation | สถานะ | Policy |
|---|---|---|
| GET /api/v1/health | implemented | public |
| GET /api/v1/ready | scaffold | admin |

scaffold ตรวจสิทธิ์ก่อนตอบ 501; ยังไม่มี business logic ดู [Auth review](../auth/AUTH_REVIEW.md) สำหรับเคส credential และข้อจำกัด
