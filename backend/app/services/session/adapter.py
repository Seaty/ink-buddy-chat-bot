"""Pure answer contract. Implementations cannot own storage or authentication."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class AnswerInput:
    question: str
    history: tuple[dict, ...]
    products: tuple[dict, ...]
    clarification: str | None = None


@dataclass(frozen=True)
class AnswerOutput:
    content: str
    product_ids: tuple[UUID, ...]
    model_name: str


class AnswerAdapter(Protocol):
    def answer(self, request: AnswerInput) -> AnswerOutput: ...


class CatalogTemplateAdapter:
    def answer(self, request):
        if request.clarification:
            return AnswerOutput(request.clarification, (), "catalog_template")
        if not request.products:
            return AnswerOutput(
                "ยังไม่พบสินค้าที่ตรงกับคำถามในข้อมูล catalog กรุณาระบุประเภท ยี่ห้อ หรือรุ่นเพิ่มเติม",
                (),
                "catalog_template",
            )
        lines = ["พบสินค้าจาก catalog ที่เกี่ยวข้องดังนี้:"]
        for p in request.products:
            price = (
                f" — {p['price']} {p['currency']}"
                if p.get("price") is not None
                else " — ยังไม่มีข้อมูลราคา"
            )
            lines.append(p["name"] + price)
        lines.append(
            "ราคาและสถานะเป็นข้อมูลจาก catalog ไม่ใช่ข้อมูลสด กรุณาตรวจสอบกับแหล่งข้อมูลก่อนตัดสินใจ"
        )
        return AnswerOutput(
            "\n".join(lines),
            tuple(p["id"] for p in request.products),
            "catalog_template",
        )
