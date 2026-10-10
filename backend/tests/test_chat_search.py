from decimal import Decimal
from uuid import UUID

import pytest
from app.core.identifiers import uuid7
from app.schemas.session import SendMessageRequest
from app.services.product.text_search import budget, literal
from app.services.session.adapter import AnswerInput, CatalogTemplateAdapter


@pytest.mark.parametrize(
    "question,result",
    [
        ("ปากกาไม่เกิน 100 บาท", (Decimal(0), Decimal(100))),
        ("สมุด 50–100 บาท", (Decimal(50), Decimal(100))),
    ],
)
def test_budget(question, result):
    assert budget(question) == (result, None)


@pytest.mark.parametrize(
    "question", ["ราคาถูก", "งบ 100", "100–50 บาท", "ไม่เกิน 100 บาท ไม่เกิน 200 บาท"]
)
def test_budget_clarification(question):
    assert budget(question)[1]


def test_literal():
    assert literal("%_!") == "%!%!_!!%"


def test_template_does_not_invent_products():
    answer = CatalogTemplateAdapter().answer(AnswerInput("ปากกา", (), ()))
    assert not answer.product_ids and "ยังไม่พบ" in answer.content


@pytest.mark.parametrize(
    "payload",
    [
        {"content": " "},
        {"content": "x", "image_id": str(uuid7())},
        {"content": "x", "client_request_id": str(UUID(int=0))},
    ],
)
def test_send_validation(payload):
    with pytest.raises(ValueError):
        SendMessageRequest(**payload)
