"""database/seed/generate_catalog_seed.py builds valid, idempotent upserts."""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "database" / "seed" / "generate_catalog_seed.py"
pytestmark = pytest.mark.skipif(not (SCRIPT.exists() and (REPO / "backend/datasets/catalog").exists()),
                                reason="seed script or dataset missing")


@pytest.fixture(scope="module")
def seed():
    spec = importlib.util.spec_from_file_location("generate_catalog_seed", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_quote_escapes_single_quotes(seed):
    assert seed.q("Elmer's") == "'Elmer''s'"
    assert seed.q(None) == "NULL"


def test_product_sql_never_invents_missing_fields(seed):
    from app.ai.rag.indexing_service import load_catalog

    products, _ = load_catalog(seed.CATALOG_DIR)
    sql = seed.product_sql(products[0])
    assert "ON CONFLICT (sku) WHERE sku IS NOT NULL DO UPDATE" in sql
    assert "ON CONFLICT (storage_key) DO UPDATE" in sql
    assert "availability" not in sql and "description" not in sql
    assert "'THB'" in sql and "catalog/" in sql


def test_attributes_skip_empty_values(seed):
    from app.ai.rag.indexing_service import load_catalog

    products, _ = load_catalog(seed.CATALOG_DIR)
    attrs = seed.attributes(products[0])
    assert attrs["category_th"] and attrs["price_date"]
    assert None not in attrs.values() and "" not in attrs.values()
