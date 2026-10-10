"""Policy for newly set passwords; existing Login credentials remain compatible."""

import re
import string

PASSWORD_MESSAGE = "Password must be 12-24 characters with a-z, A-Z, 0-9 and an ASCII special character; whitespace is not allowed"


def validate_new_password(password: str) -> str:
    if (
        not 12 <= len(password) <= 24
        or any((c.isspace() or c == "\ufeff") for c in password)
        or not re.search(r"[a-z]", password)
        or not re.search(r"[A-Z]", password)
        or not re.search(r"[0-9]", password)
        or not any(c in string.punctuation for c in password)
    ):
        raise ValueError(PASSWORD_MESSAGE)
    return password
