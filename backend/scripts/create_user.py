"""Run from backend: python -m scripts.create_user --email ... --role user|admin"""

import argparse
from getpass import getpass

from app.core.password_policy import validate_new_password
from app.core.security import hash_password
from app.db.database import get_sessionmaker
from email_validator import validate_email
from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser(
        description="Create a local Ink Buddy account; never supply passwords in command arguments"
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=["user", "admin"], default="user")
    parser.add_argument("--display-name")
    args = parser.parse_args()
    email = validate_email(args.email, check_deliverability=False).normalized
    password = getpass("Password (12-24 chars, a-z/A-Z/0-9/special, no whitespace): ")
    try:
        validate_new_password(password)
    except ValueError as error:
        parser.error(str(error))
    if password != getpass("Confirm password: "):
        parser.error("Passwords must match")
    with get_sessionmaker()() as db:
        role = db.execute(
            text("SELECT id FROM roles WHERE name=:name"), {"name": args.role}
        ).scalar_one()
        db.execute(
            text(
                "INSERT INTO users(role_id,email,password_hash,display_name) VALUES(:role,:email,:hash,:display)"
            ),
            {
                "role": role,
                "email": email,
                "hash": hash_password(password),
                "display": args.display_name,
            },
        )
        db.commit()
    print("Account created. Existing accounts are never overwritten.")


if __name__ == "__main__":
    main()
