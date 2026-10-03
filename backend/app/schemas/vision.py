"""Compatibility exports; new code imports schemas by module."""
from app.schemas.image import ImageUploadResponse
from app.schemas.product import MAX_IMAGE_SEARCH_LIMIT, ProductMatch, ProductSearchByImageRequest, ProductSearchByImageResponse
from app.schemas.admin import IndexCatalogResponse
