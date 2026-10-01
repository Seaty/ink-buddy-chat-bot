"""All /api/v1 routes. Other features add their routers here."""
from fastapi import APIRouter

from app.api.v1 import admin, images, product_search

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(images.router)
api_router.include_router(product_search.router)
api_router.include_router(admin.router)


@api_router.get("/health", tags=["admin"])
def health() -> dict:
    return {"status": "ok"}
