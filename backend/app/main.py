"""Application factory. Fail closed before serving unconfigured routes."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.deps import authorize
from app.api.policy import prepare_policies
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import error_response, install_error_handlers
from app.core.rate_limit import limiter


def create_app(config: Settings | None = None) -> FastAPI:
    settings = config or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        settings.validate_auth()
        prepare_policies(app)
        yield

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        dependencies=[Depends(authorize)],
        docs_url="/docs" if settings.app_environment == "development" else None,
        redoc_url="/redoc" if settings.app_environment == "development" else None,
        openapi_url="/openapi.json"
        if settings.app_environment == "development"
        else None,
    )
    if config is not None:
        app.dependency_overrides[get_settings] = lambda: config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_error(request: Request, error):
        response = error_response(429, "RATE_LIMITED", "request rate limit exceeded")
        response = limiter._inject_headers(response, request.state.view_rate_limit)
        return response

    prepare_policies(api_router)
    app.include_router(api_router)
    prepare_policies(app)
    original_openapi = app.openapi

    def openapi():
        schema = original_openapi()
        schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
            {
                "UserBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                },
                "GuestCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "ink_buddy_guest",
                },
                "RefreshCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "ink_buddy_refresh",
                },
            }
        )
        security = {
            "public": [],
            "refresh": [{"RefreshCookie": []}],
            "guest": [{"GuestCookie": []}],
            "user": [{"UserBearer": []}],
            "admin": [{"UserBearer": []}],
            "guest_or_user": [{"UserBearer": []}, {"GuestCookie": []}],
            "claim": [{"UserBearer": [], "GuestCookie": []}],
        }
        for item in schema["paths"].values():
            for operation in item.values():
                if isinstance(operation, dict) and "x-access-policy" in operation:
                    operation["security"] = security[operation["x-access-policy"]]
        return schema

    app.openapi = openapi
    return app


app = create_app()
