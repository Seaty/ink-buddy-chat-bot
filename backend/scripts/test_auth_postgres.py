"""Create/drop a unique test database using the local compose credentials."""

import os
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy.engine import URL

from app.core.identifiers import uuid7


def main():
    repo = Path(__file__).resolve().parents[2]
    config = dotenv_values(repo / "docker/.env")
    name = "ink_buddy_test_" + uuid7().hex
    connection = dict(
        host="127.0.0.1",
        port=int(config.get("POSTGRES_PORT") or 5432),
        user=config.get("POSTGRES_USER") or "ink_buddy",
        password=config["POSTGRES_PASSWORD"],
        dbname=config.get("POSTGRES_DB") or "ink_buddy",
    )
    with psycopg.connect(**connection, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            connection["dbname"] = name
            with psycopg.connect(**connection, autocommit=True) as db:
                db.execute(
                    (repo / "database/ddl/001_init.sql").read_text(encoding="utf-8")
                )
            url = URL.create(
                "postgresql+psycopg",
                username=connection["user"],
                password=connection["password"],
                host=connection["host"],
                port=connection["port"],
                database=name,
            )
            os.environ["INK_BUDDY_TEST_DATABASE_URL"] = url.render_as_string(
                hide_password=False
            )
            return pytest.main(
                ["tests/test_auth_postgres.py", "-q", "--tb=line", "--show-capture=no"]
            )
        finally:
            # Exact UUID-based name created above; never drop the application database.
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


if __name__ == "__main__":
    raise SystemExit(main())
