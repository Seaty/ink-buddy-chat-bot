"""Every API operation must declare its access policy explicitly."""

from fastapi.routing import APIRoute

from app.api.deps import POLICIES
from app.core.errors import ErrorResponse


def access_policy(policy: str):
    if policy not in POLICIES:
        raise ValueError(f"unknown access policy: {policy}")

    def decorate(endpoint):
        endpoint.access_policy = policy
        return endpoint

    return decorate


def prepare_policies(app):
    for route in app.routes:
        if hasattr(route, "original_router"):
            prepare_policies(route.original_router)
            continue
        if not isinstance(route, APIRoute):
            continue
        policy = getattr(route.endpoint, "access_policy", None)
        if policy not in POLICIES:
            raise RuntimeError(f"Missing access policy: {route.methods} {route.path}")
        route.openapi_extra = {**(route.openapi_extra or {}), "x-access-policy": policy}
        for status in (401, 403):
            route.responses.setdefault(
                status,
                {
                    "model": ErrorResponse,
                    "description": "Authentication or policy rejected",
                },
            )
