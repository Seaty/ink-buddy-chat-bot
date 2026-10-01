from pathlib import Path

import pytest
from PIL import Image

from app.ai.rag.chunker import build_catalog_chunks
from app.ai.rag.indexing_service import CatalogError, build_brand_aliases, load_catalog

CATALOG = Path(__file__).resolve().parents[1] / "datasets" / "catalog"
HEADER = "filename,category,group,sku,brand,name,price_thb,price_date,source_url,image_url,license,notes"


def make_catalog(tmp_path, rows, header=HEADER):
    (tmp_path / "pen").mkdir(exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(tmp_path / "pen" / "a.jpg")
    (tmp_path / "metadata.csv").write_text("\n".join([header, *rows]), encoding="utf-8-sig")
    return tmp_path


@pytest.mark.skipif(not CATALOG.exists(), reason="dataset not present")
def test_real_catalog_loads_without_errors():
    products, report = load_catalog(CATALOG)
    assert report.ok
    assert len(products) == len({p.sku for p in products}) == 50
    assert all(p.image_path.is_file() for p in products)


@pytest.mark.skipif(not CATALOG.exists(), reason="dataset not present")
def test_real_catalog_chunks_exclude_price():
    products, _ = load_catalog(CATALOG)
    chunks = build_catalog_chunks(products)
    assert len(chunks) == 2 * len(products)
    for c in chunks:
        if c.chunk_type == "caption":
            assert "บาท" not in c.content
            assert str(c.metadata["price_thb"]) not in c.content.split("\n", 1)[1]


def test_brand_aliases_prefer_official_spelling():
    aliases = build_brand_aliases(["Montmarte", "Mont Marte", "Pentel", "PENTEL", "Pentel"])
    assert aliases["Montmarte"] == aliases["Mont Marte"] == "Mont Marte"
    assert aliases["PENTEL"] == "Pentel"


def test_errors_are_reported(tmp_path):
    rows = [
        "pen/a.jpg,ballpoint_pen,g,s1,B,n,10,2026-09-27,u,i,l,",  # folder ≠ category
        "pen/missing.jpg,pen,g,s2,B,n,-1,2026-13-01,u,i,l,",  # unknown category, bad price/date, no file
        "pen/a.jpg,pen,g,s2,B,n,10,2026-09-27,u,i,l,",  # duplicate sku (and unknown category)
    ]
    root = make_catalog(tmp_path, rows)
    with pytest.raises(CatalogError):
        load_catalog(root)
    products, report = load_catalog(root, strict=False)
    assert products == []
    text = "\n".join(report.errors)
    for expected in ("≠ category", "unknown category", "price_thb must be > 0", "not YYYY-MM-DD",
                     "image not found", "duplicate sku"):
        assert expected in text


def test_extended_columns_parsed(tmp_path):
    header = HEADER + ",stock_qty,unit,pack_qty,is_active"
    (tmp_path / "ruler").mkdir()
    rows = ["ruler/a.jpg,ruler,g,s1,B,n,90,2026-09-27,u,i,l,,0,แพ็ค,3,true"]
    root = make_catalog(tmp_path, rows, header)
    Image.new("RGB", (8, 8)).save(root / "ruler" / "a.jpg")
    (p,), report = load_catalog(root)
    assert report.ok
    assert (p.stock_qty, p.unit, p.pack_qty, p.unit_price) == (0, "แพ็ค", 3, 30)


def test_missing_extended_columns_is_a_warning(tmp_path):
    (tmp_path / "ruler").mkdir()
    root = make_catalog(tmp_path, ["ruler/a.jpg,ruler,g,s1,B,n,10,2026-09-27,u,i,l,"])
    Image.new("RGB", (8, 8)).save(root / "ruler" / "a.jpg")
    (p,), report = load_catalog(root)
    assert report.ok and report.warnings
    assert p.stock_qty is None and p.unit_price is None


def test_embed_device_aliases():
    torch = pytest.importorskip("torch")
    from app.ai.embeddings.qwen3_vl_embedding import _resolve_device

    assert _resolve_device("cpu").type == "cpu"
    assert _resolve_device(None).type in ("cpu", "cuda")
    with pytest.raises(ValueError, match="invalid IMAGE_EMBED_DEVICE"):
        _resolve_device("banana")
    if torch.cuda.is_available():
        assert _resolve_device("gpu") == torch.device("cuda")
        assert _resolve_device("GPU:0") == torch.device("cuda:0")


def test_settings_resolve_relative_catalog_dir_and_empty_device():
    from app.core.config import BACKEND_DIR, Settings

    s = Settings(_env_file=None, catalog_dir="datasets/catalog", image_embed_device="")
    assert s.catalog_dir == BACKEND_DIR / "datasets" / "catalog"
    assert s.image_embed_device is None


def test_env_example_lists_every_setting():
    from app.core.config import BACKEND_DIR, Settings

    keys = {line.split("=", 1)[0] for line in (BACKEND_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")}
    assert keys == {name.upper() for name in Settings.model_fields}
