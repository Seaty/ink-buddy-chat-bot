"""Integration tests against a real PostgreSQL + pgvector.

Skipped unless TEST_DATABASE_URL is set, e.g.
  TEST_DATABASE_URL=postgresql+psycopg://inkbuddy:inkbuddy@127.0.0.1:5432/inkbuddy
Uses a throwaway schema, so existing tables are untouched.
"""

import os

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.identifiers import uuid7

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

DIM = 2048


@pytest.fixture
def session():
    import app.models  # noqa: F401
    from app.db.database import Base
    from app.repositories.product_repository import ProductRepository

    schema = f"test_{uuid7().hex[:8]}"
    base_engine = create_engine(URL)
    with base_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    # Qualify every table with the throwaway schema. A search_path alone is not
    # enough: create_all would find public.product_image_embeddings and the
    # test would then write to (and delete from) the real table.
    engine = base_engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    assert ProductRepository(s).count() == 0, (
        "not an empty test table — refusing to run"
    )
    yield s
    s.close()
    with base_engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    base_engine.dispose()


def unit(i: int) -> np.ndarray:
    v = np.zeros(DIM, dtype=np.float32)
    v[i] = 1.0
    return v


def row(sku, chunk_type, vec, h="h", **meta):
    return {
        "sku": sku,
        "chunk_type": chunk_type,
        "variant": 0,
        "content": sku,
        "content_hash": h,
        "embedding": vec,
        "embed_model": "m",
        "meta": {"sku": sku, "is_active": True, **meta},
    }


def test_upsert_search_refresh_delete(session):
    from app.repositories.product_repository import ProductRepository

    repo = ProductRepository(session)
    near_a = unit(0) * 0.9 + unit(1) * 0.1
    repo.upsert(
        [
            row("a", "image", unit(0)),
            row("b", "image", unit(1)),
            row("a", "caption", unit(2)),
        ]
    )
    session.commit()
    assert repo.count() == 3

    hits = repo.best_by_sku(near_a, "image", limit=5)
    assert list(hits) == ["a", "b"]
    assert hits["a"][0] == pytest.approx(0.9 / np.linalg.norm([0.9, 0.1]), abs=1e-4)
    assert list(repo.best_by_sku(unit(2), "caption", 5)) == ["a"]

    # upsert replaces on (sku, chunk_type, variant)
    repo.upsert([row("b", "image", unit(0), h="h2")])
    session.commit()
    assert repo.existing_hashes("m")[("b", "image", 0)] == "h2"

    # metadata refresh without re-embedding; inactive products drop out of search
    repo.refresh_metadata({"b": {"sku": "b", "is_active": False}})
    session.commit()
    assert "b" not in repo.best_by_sku(unit(0), "image", 5)

    assert repo.delete_except({("a", "image", 0)}) == 2
    session.commit()
    assert repo.count() == 1
