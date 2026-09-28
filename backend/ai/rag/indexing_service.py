"""Indexing service.

Image RAG part: load and validate the product catalog
(``datasets/catalog/metadata.csv`` + images) before chunking and embedding.
See IMAGE_RAG_DESIGN.md §2.1 for the schema.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from PIL import Image

CATEGORY_TH: dict[str, str] = {
    "ballpoint_pen": "ปากกาลูกลื่น",
    "gel_pen": "ปากกาเจล",
    "marker": "ปากกามาร์คเกอร์",
    "whiteboard_marker": "ปากกาไวท์บอร์ด",
    "highlighter": "ปากกาเน้นข้อความ",
    "mechanical_pencil": "ดินสอกด",
    "colored_pencil": "ดินสอสี",
    "eraser": "ยางลบ",
    "correction_tape": "เทปลบคำผิด",
    "sharpener": "กบเหลาดินสอ",
    "ruler": "ไม้บรรทัด",
    "compass": "วงเวียน",
    "scissors": "กรรไกร",
    "cutter": "คัตเตอร์",
    "glue": "กาว",
    "clear_tape": "เทปใส",
    "sticky_note": "กระดาษโน้ตกาว",
    "notebook": "สมุด",
    "file_folder": "แฟ้มเอกสาร",
    "pencil_case": "กระเป๋าดินสอ",
}

# Official spellings that win over frequency when variants tie (key = _brand_key).
BRAND_CANONICAL = {"montmarte": "Mont Marte"}

UNITS = {"ด้าม", "แท่ง", "แพ็ค", "กล่อง", "ชิ้น", "เล่ม", "ม้วน", "ชุด", "อัน", "หลอด", "ขวด", "ซอง"}

REQUIRED_COLUMNS = [
    "filename", "category", "group", "sku", "brand", "name",
    "price_thb", "price_date", "source_url", "image_url", "license", "notes",
]
# Added by the Image RAG design; optional until metadata.csv is updated.
EXTENDED_COLUMNS = [
    "stock_qty", "unit", "pack_qty", "brand_norm", "color", "size", "visual_caption", "is_active",
]


class CatalogError(ValueError):
    """Catalog has errors that make it unsafe to index."""


@dataclass(frozen=True)
class CatalogProduct:
    sku: str
    filename: str
    image_path: Path
    category: str
    group: str
    brand: str
    brand_norm: str
    name: str
    price_thb: float
    price_date: date
    source_url: str
    image_url: str
    license: str
    notes: str = ""
    stock_qty: int | None = None
    unit: str | None = None
    pack_qty: int | None = None
    color: str = ""
    size: str = ""
    visual_caption: str = ""
    is_active: bool = True

    @property
    def category_th(self) -> str:
        return CATEGORY_TH.get(self.category, self.category)

    @property
    def unit_price(self) -> float | None:
        """Price per piece, for fair price comparison across pack sizes."""
        return self.price_thb / self.pack_qty if self.pack_qty else None

    def to_metadata(self) -> dict:
        """Fields stored in the vector table's JSONB and shown to the LLM."""
        return {
            "sku": self.sku,
            "name": self.name,
            "category": self.category,
            "category_th": self.category_th,
            "group": self.group,
            "brand": self.brand_norm,
            "price_thb": self.price_thb,
            "unit": self.unit,
            "pack_qty": self.pack_qty,
            "unit_price": self.unit_price,
            "price_date": self.price_date.isoformat(),
            "stock_qty": self.stock_qty,
            "color": self.color,
            "size": self.size,
            "image_path": self.filename,
            "image_url": self.image_url,
            "source_url": self.source_url,
            "is_active": self.is_active,
        }


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"errors={len(self.errors)} warnings={len(self.warnings)}"]
        lines += [f"  ERROR   {e}" for e in self.errors]
        lines += [f"  WARNING {w}" for w in self.warnings]
        return "\n".join(lines)


def _brand_key(brand: str) -> str:
    return re.sub(r"[^0-9a-z]", "", brand.lower())


def build_brand_aliases(brands: list[str]) -> dict[str, str]:
    """Map spelling variants (``Montmarte`` / ``Mont Marte``) to one canonical form.

    Variants share a key after lower-casing and dropping non-alphanumerics;
    BRAND_CANONICAL wins, then the most frequent spelling, then the first seen.
    """
    groups: dict[str, Counter] = defaultdict(Counter)
    for b in brands:
        groups[_brand_key(b)][b] += 1
    aliases = {}
    for key, counter in groups.items():
        canonical = BRAND_CANONICAL.get(key) or counter.most_common(1)[0][0]
        for variant in counter:
            aliases[variant] = canonical
    return aliases


def _parse_int(value: str, column: str, where: str, report: ValidationReport, minimum: int) -> int | None:
    if value == "":
        return None
    try:
        n = int(value)
    except ValueError:
        report.errors.append(f"{where}: {column}={value!r} is not an integer")
        return None
    if n < minimum:
        report.errors.append(f"{where}: {column}={n} must be ≥ {minimum}")
        return None
    return n


def _parse_bool(value: str) -> bool:
    return value.strip().lower() not in {"false", "0", "no", "n"}


def load_catalog(catalog_dir: str | Path, strict: bool = True) -> tuple[list[CatalogProduct], ValidationReport]:
    """Load ``metadata.csv`` and validate rows and image files.

    With ``strict=True`` raises CatalogError when the report has errors.
    Rows with errors are skipped either way.
    """
    catalog_dir = Path(catalog_dir)
    report = ValidationReport()
    with open(catalog_dir / "metadata.csv", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        raw_rows = [{k: (v or "").strip() for k, v in row.items()} for row in reader]

    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        report.errors.append(f"metadata.csv missing columns: {missing}")
        if strict:
            raise CatalogError(str(report))
        return [], report
    absent_ext = [c for c in EXTENDED_COLUMNS if c not in columns]
    if absent_ext:
        report.warnings.append(
            f"extended columns not in metadata.csv yet: {absent_ext} "
            "(stock / unit-price answers will say the data is unavailable)"
        )

    aliases = build_brand_aliases([r["brand"] for r in raw_rows if r["brand"]])
    for variant, canonical in sorted(aliases.items()):
        if variant != canonical:
            report.warnings.append(f"brand {variant!r} normalized to {canonical!r}")

    products: list[CatalogProduct] = []
    seen_skus: set[str] = set()
    for line_no, row in enumerate(raw_rows, start=2):
        where = f"line {line_no} ({row.get('sku') or row.get('filename')})"
        n_errors = len(report.errors)

        for col in ("filename", "category", "sku", "brand", "name", "price_thb", "price_date", "source_url"):
            if not row[col]:
                report.errors.append(f"{where}: {col} is empty")
        if row["sku"] in seen_skus:
            report.errors.append(f"{where}: duplicate sku")
        seen_skus.add(row["sku"])

        if row["category"] and row["category"] not in CATEGORY_TH:
            report.errors.append(f"{where}: unknown category {row['category']!r}")
        folder = Path(row["filename"]).parts[0] if row["filename"] else ""
        if row["category"] and folder != row["category"]:
            report.errors.append(f"{where}: image folder {folder!r} ≠ category {row['category']!r}")

        image_path = catalog_dir / row["filename"]
        if row["filename"]:
            if not image_path.is_file():
                report.errors.append(f"{where}: image not found {row['filename']}")
            else:
                try:
                    with Image.open(image_path) as img:
                        img.verify()
                except Exception as e:  # noqa: BLE001 — any decode failure means unusable
                    report.errors.append(f"{where}: image unreadable ({e})")

        price = None
        try:
            price = float(row["price_thb"])
            if price <= 0:
                report.errors.append(f"{where}: price_thb must be > 0")
        except ValueError:
            report.errors.append(f"{where}: price_thb={row['price_thb']!r} is not a number")
        price_date = None
        try:
            price_date = date.fromisoformat(row["price_date"])
        except ValueError:
            report.errors.append(f"{where}: price_date={row['price_date']!r} is not YYYY-MM-DD")

        stock_qty = _parse_int(row.get("stock_qty", ""), "stock_qty", where, report, minimum=0)
        pack_qty = _parse_int(row.get("pack_qty", ""), "pack_qty", where, report, minimum=1)
        unit = row.get("unit") or None
        if unit and unit not in UNITS:
            report.warnings.append(f"{where}: unit {unit!r} not in {sorted(UNITS)}")
        if row["notes"]:
            report.warnings.append(f"{where}: note — {row['notes']}")

        if len(report.errors) > n_errors:
            continue
        products.append(CatalogProduct(
            sku=row["sku"],
            filename=row["filename"],
            image_path=image_path,
            category=row["category"],
            group=row["group"],
            brand=row["brand"],
            brand_norm=row.get("brand_norm") or aliases.get(row["brand"], row["brand"]),
            name=row["name"],
            price_thb=price,
            price_date=price_date,
            source_url=row["source_url"],
            image_url=row["image_url"],
            license=row["license"],
            notes=row["notes"],
            stock_qty=stock_qty,
            unit=unit,
            pack_qty=pack_qty,
            color=row.get("color", ""),
            size=row.get("size", ""),
            visual_caption=row.get("visual_caption", ""),
            is_active=_parse_bool(row.get("is_active", "true")),
        ))

    if strict and report.errors:
        raise CatalogError(str(report))
    return products, report


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    target = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "datasets" / "catalog"
    items, rep = load_catalog(target, strict=False)
    print(f"loaded {len(items)} products")
    print(rep)
    sys.exit(0 if rep.ok else 1)
