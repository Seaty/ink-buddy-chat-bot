"""RFC 9562 UUIDv7 IDs; no ordering guarantee within one millisecond."""

import secrets
import time
from uuid import UUID


def uuid7() -> UUID:
    """48-bit Unix milliseconds and 74 cryptographically random bits."""
    milliseconds = time.time_ns() // 1_000_000
    random = secrets.randbits(74)
    return UUID(
        int=(milliseconds << 80)
        | (7 << 76)
        | ((random >> 62) << 64)
        | (2 << 62)
        | (random & ((1 << 62) - 1))
    )
