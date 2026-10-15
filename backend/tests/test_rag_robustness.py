from types import SimpleNamespace
from decimal import Decimal
from scripts.evaluate_rag_robustness import check_constraints,percentiles
from app.services.product.retrieval_policy import relevant


def test_constraints_require_hits_and_known_thb_prices():
    case={'expected_status':['allowed'],'require_hit':True,'min_price':50,'max_price':100}
    response=SimpleNamespace(guardrail_status='allowed',items=[])
    assert not all(check_constraints(case,response).values())
    response.items=[SimpleNamespace(product=SimpleNamespace(price=None,currency='THB'))]
    assert not check_constraints(case,response)['budget']
    response.items[0].product.price=Decimal('75')
    assert all(check_constraints(case,response).values())
    response.items[0].product.currency='USD'
    assert not check_constraints(case,response)['budget']


def test_latency_nearest_rank_and_empty():
    assert percentiles([])['p95_ms'] is None
    assert percentiles([30,10,20])=={'count':3,'p50_ms':20,'p95_ms':30}


def test_gold_and_silver_need_catalog_evidence():
    assert not relevant({'name':'สมุดสีฟ้า'},'สมุดสีทอง')
    assert relevant({'name':'สมุดสีทอง'},'สมุดสีทอง')
    assert not relevant({'name':'ปากกาสีดำ'},'ปากกาสีเงิน')
