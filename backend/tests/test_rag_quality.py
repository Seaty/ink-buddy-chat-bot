import pytest
from scripts.evaluate_rag_quality import metrics
from app.services.product.retrieval_policy import matched_brands,relevant,scope

def test_metrics_known_ranking():
    m=metrics(['a','b'],['x','b','a'])
    assert m['recall_at_5']==1 and m['mrr']==0.5
    assert m['precision_at_5']==0.4 and m['precision_returned']==pytest.approx(2/3)
    assert 0<m['ndcg_at_5']<1
    assert metrics(['a'],[])['recall_at_5']==0

def test_aliases_and_attribute_evidence():
    assert matched_brands(['Plus','Pentel',"Elmer's"],'เทปลบคำผิด พลัส')==['Plus']
    assert matched_brands(['Uni'],'university')==[]
    assert scope('สีไม้ระบายน้ำ',None,[],[]).categories==['colored_pencil']
    assert relevant({'name':'ไม้บรรทัดเหล็ก'},'ไม้บรรทัดเหล็ก')
    assert not relevant({'name':'ไม้บรรทัดพลาสติก'},'ไม้บรรทัดเหล็ก')
    assert not relevant({'name':'สีไม้ธรรมดา'},'สีไม้ระบายน้ำ')
    assert not relevant({'name':'เทปลบคำผิดคละสี'},'เทปลบคำผิดสีขาว')
