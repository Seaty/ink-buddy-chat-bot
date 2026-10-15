from scripts.audit_text_catalog import product_issues
from app.services.product.text_index import source_for


def test_missing_price_does_not_become_zero_and_stale_index_is_detected():
    product={'name':'Pen','price':None,'source_ref':'https://example.test/p','attributes':{}}
    findings=product_issues(product,'old source')
    assert {'field':'price','code':'MISSING_VALUE'} in findings
    assert {'field':'embedding','code':'STALE_TEXT_INDEX'} in findings
    assert product['price'] is None


def test_private_url_credentials_are_flagged_and_fresh_index_passes():
    product={'name':'Pen','price':10,'source_ref':'https://user:password@example.test/p','attributes':{'unit':'piece'}}
    findings=product_issues(product,source_for(product))
    assert {'field':'source_ref','code':'INVALID_PUBLIC_URL'} in findings
    assert not any(f['field']=='embedding' for f in findings)
