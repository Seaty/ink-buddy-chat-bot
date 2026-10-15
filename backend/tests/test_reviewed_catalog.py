import json
from pathlib import Path
from decimal import Decimal
from app.services.product.text_index import source_for

def test_review_manifest():
    data=json.loads((Path(__file__).resolve().parents[1]/'datasets/reviewed_catalog.json').read_text(encoding='utf-8'))
    rows=data['products']
    assert len(rows)==67 and len({r['sku'] for r in rows})==67
    assert any(r['sku']=='Y013221' for r in data['held'])
    assert all(r['price'] is not None and Decimal(r['price'])>0 for r in rows)
    assert next(r for r in rows if r['sku']=='b2s_1091933')['price']=='590.00'
    approved=[r for r in rows if r['attributes'].get('price_review')=='user_approved_demo_2026_10_14']
    assert len(approved)==18
    assert sum(r['attributes']['price_tax_basis_verification']=='source_explicitly_excludes_vat' for r in rows)==15
    assert all(r['attributes']['price_tax_basis']=='excludes_vat' for r in rows)
    for r in rows:
        assert r['images'] and r['source_ref'].startswith('https://')
        source=source_for(r)
        assert 'source_price:' not in source and 'https://' not in source
        assert 'price_tax_basis' not in source and 'price_source_note' not in source
