from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings


def principal_or_ip(request):
    principal = getattr(request.state, "principal", None)
    return (
        f"{principal.kind}:{principal.id}" if principal else get_remote_address(request)
    )


limiter = Limiter(
    key_func=principal_or_ip,
    storage_uri=get_settings().auth_limiter_storage_uri,
    headers_enabled=True,
)
