# Product API

ตรวจล่าสุด 2026-10-03 จาก OpenAPI snapshot ดูรายละเอียด request/response และสิทธิ์ใน [API_SPEC](../API_SPEC.md)

| Operation | สถานะ | Policy |
|---|---|---|
| POST /api/v1/product-search/by-image | implemented | guest_or_user |
| GET /api/v1/products | scaffold | guest_or_user |
| GET /api/v1/products/{product_id} | scaffold | guest_or_user |

scaffold ตรวจสิทธิ์ก่อนตอบ 501; ยังไม่มี business logic ดู [Auth review](../auth/AUTH_REVIEW.md) สำหรับเคส credential และข้อจำกัด
