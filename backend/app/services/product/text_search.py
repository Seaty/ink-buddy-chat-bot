"""Bounded catalog search with literal LIKE patterns and explicit budget parsing."""

import re
from decimal import Decimal

from sqlalchemy import text

from app.ai.rag.indexing_service import CATEGORY_TH

FIELDS = "id,sku,name,category,brand,description,attributes,price,currency,availability,source_ref"


def budget(question):
    numbers = r"([0-9]+(?:\.[0-9]{1,2})?)"
    ranges = re.findall(numbers + r"\s*[-–]\s*" + numbers + r"\s*บาท", question)
    caps = re.findall(r"(?:ไม่เกิน|ไม่เกินงบ|สูงสุด)\s*" + numbers + r"\s*บาท", question)
    if len(ranges) + len(caps) > 1:
        return None, "กรุณาระบุช่วงงบประมาณเดียว เช่น 50–100 บาท หรือไม่เกิน 100 บาท"
    if ranges:
        low, high = map(Decimal, ranges[0])
        if low > high:
            return None, "กรุณาระบุงบขั้นต่ำไม่เกินงบสูงสุด"
        return (low, high), None
    if caps:
        return (Decimal(0), Decimal(caps[0])), None
    if re.search(r"บาท|งบ|ราคา(?:ถูก|ต่ำ|สูง)|ไม่เกิน|สูงสุด", question):
        return None, "กรุณาระบุงบให้ชัดเจน เช่น ไม่เกิน 100 บาท หรือ 50–100 บาท"
    return None, None


def literal(value):
    return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


class CatalogTextSearch:
    def __init__(self, db):
        self.db = db

    def search(self, question):
        limits, clarification = budget(question)
        if clarification:
            return [], clarification
        categories = [
            k
            for k, v in CATEGORY_TH.items()
            if v in question or k.replace("_", " ") in question.lower()
        ]
        if not categories and "ปากกา" in question:
            categories = ["ballpoint_pen", "gel_pen", "marker", "whiteboard_marker"]
        clean = re.sub(
            r"[0-9]+(?:\.[0-9]+)?\s*(?:[-–]\s*[0-9]+)?\s*บาท", "", question.lower()
        )
        for filler in [
            "ช่วย",
            "แนะนำ",
            "ค้นหา",
            "หาสินค้า",
            "อยากได้",
            "ไม่เกิน",
            "สูงสุด",
            "ราคา",
            "สำหรับ",
            "หน่อย",
            "งบ",
        ]:
            clean = clean.replace(filler, " ")
        terms = [x for x in re.findall(r"[a-z0-9_]+|[ก-๙]+", clean) if len(x) > 1][:12]
        if not terms and not categories:
            return [], "กรุณาระบุประเภท ยี่ห้อ หรือชื่อเครื่องเขียนที่ต้องการค้นหา"
        params = {}
        clauses = []
        scores = []
        for i, t in enumerate(terms):
            key = f"q{i}"
            params[key] = literal(t)
            for field, weight in [
                ("name", 8),
                ("brand", 6),
                ("category", 4),
                ("description", 1),
            ]:
                condition = f"lower(COALESCE({field},'')) LIKE :{key} ESCAPE '!'"
                clauses.append(condition)
                scores.append(f"CASE WHEN {condition} THEN {weight} ELSE 0 END")
        if categories:
            cats = []
            for i, c in enumerate(categories):
                params[f"c{i}"] = c
                cats.append(f":c{i}")
            category = f"category IN ({','.join(cats)})"
            clauses.append(category)
            scores.append(f"CASE WHEN {category} THEN 12 ELSE 0 END")
        where = "(" + " OR ".join(clauses) + ")"
        if categories:
            where += " AND " + category
        brands = (
            self.db.execute(
                text(
                    "SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL ORDER BY brand LIMIT 200"
                )
            )
            .scalars()
            .all()
        )
        matched = [b for b in brands if b.lower() in question.lower()]
        if matched:
            brand_terms = []
            for i, b in enumerate(matched):
                params[f"brand{i}"] = b
                brand_terms.append(f":brand{i}")
            where += f" AND brand IN ({','.join(brand_terms)})"
        if limits:
            where += " AND price IS NOT NULL AND currency='THB' AND price BETWEEN :low AND :high"
            params.update(low=limits[0], high=limits[1])
        rows = (
            self.db.execute(
                text(
                    f"SELECT {FIELDS} FROM products WHERE {where} ORDER BY ({'+'.join(scores)}) DESC,id ASC LIMIT 5"
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [dict(x) for x in rows], None
