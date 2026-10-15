from uuid import UUID
from scripts.audit_rag_answers import verify_rendered,HEADER,FOOTER

PRODUCT={'id':UUID('00000000-0000-7000-8000-000000000001'),'name':'Pen','brand':'Pilot','price':None,'attributes':{}}


def test_audit_rejects_invented_price_and_cross_product_evidence():
    def answer(bullet):return '\n'.join([HEADER,'Pen','• '+bullet,FOOTER])
    assert verify_rendered(answer('ยี่ห้อ: Pilot'),[PRODUCT])['passed']
    assert not verify_rendered(answer('ราคา catalog: 0 THB'),[PRODUCT])['passed']
    other={**PRODUCT,'id':UUID('00000000-0000-7000-8000-000000000002'),'name':'Pencil','brand':'Other'}
    text='\n'.join([HEADER,'Pen','• ยี่ห้อ: Other','Pencil','• ยี่ห้อ: Other',FOOTER])
    assert not verify_rendered(text,[PRODUCT,other])['passed']


def test_audit_requires_attribution_and_rejects_unknown_prose():
    assert not verify_rendered('\n'.join([HEADER,'Pen','waterproof',FOOTER]),[PRODUCT])['passed']
    assert not verify_rendered('\n'.join([HEADER,'Pen','• ยี่ห้อ: Pilot']),[PRODUCT])['passed']


def test_audit_accepts_grounded_brand_fallback_without_accepting_other_brand():
    text='\n'.join([HEADER,'Pen','• ยี่ห้อตาม catalog: Pilot',FOOTER])
    assert verify_rendered(text,[PRODUCT])['passed']
    assert not verify_rendered(text.replace('catalog: Pilot','catalog: Invented'),[PRODUCT])['passed']
