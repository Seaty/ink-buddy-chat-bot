import os

os.environ.setdefault(
    "AUTH_JWT_SECRET", "test-only-signing-key-never-use-in-production-12345"
)
