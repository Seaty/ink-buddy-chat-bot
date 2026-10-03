from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Query
from app.api.scaffold import SCAFFOLD_OPENAPI, SCAFFOLD_RESPONSES, not_implemented
from app.schemas.product import ProductResponse, ProductListResponse
from app.api.v1.product.search import router as search_router
router = APIRouter(tags=["product"])
router.include_router(search_router)


@router.get("/products", status_code=200, response_model=ProductListResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] list products", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def list_products(q: str | None = Query(None, max_length=200), category: str | None = Query(None, max_length=100), brand: str | None = Query(None, max_length=100), limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None)):
    not_implemented("list_products")


@router.get("/products/{product_id}", status_code=200, response_model=ProductResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] get product", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def get_product(product_id: UUID):
    not_implemented("get_product")
