"""Versioned router composition. Business logic belongs in services, not here."""
from fastapi import APIRouter
from app.api.v1.auth.routes import router as auth_router
from app.api.v1.user.routes import router as user_router
from app.api.v1.session.routes import router as session_router
from app.api.v1.image.routes import router as image_router
from app.api.v1.product.routes import router as product_router
from app.api.v1.admin.routes import router as admin_router
from app.api.v1.system.routes import router as system_router

api_router = APIRouter(prefix="/api/v1")
for router in (auth_router, user_router, session_router, image_router, product_router, admin_router, system_router):
    api_router.include_router(router)
