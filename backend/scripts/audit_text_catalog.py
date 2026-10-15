"""Read-only catalog completeness and index freshness report; no provider calls."""
import json
import hashlib
from datetime import datetime,timezone
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
from app.core.config import Settings
from app.services.product.text_index import source_for
from scripts.evaluate_rag_quality import ROOT


def product_issues(product,indexed):
    found=[]
    for field in ('name','category','brand','description','price','source_ref'):
        if product.get(field) is None or product.get(field)=='':found.append({'field':field,'code':'MISSING_VALUE'})
    source=product.get('source_ref')
    if source:
        try:
            url=urlsplit(source)
            if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:
                found.append({'field':'source_ref','code':'INVALID_PUBLIC_URL'})
        except ValueError:found.append({'field':'source_ref','code':'INVALID_PUBLIC_URL'})
    if not (product.get('attributes') or {}).get('unit'):found.append({'field':'unit','code':'STRUCTURED_UNIT_NOT_PROVIDED'})
    description=product.get('description') or ''
    if 'สีขาว' in description and any(term in description for term in ('สีนวล','สีกระดาษนวล')):
        found.append({'field':'description','code':'POSSIBLE_COLOR_WORDING_CONFLICT_REQUIRES_REVIEW'})
    if any(term in description for term in ('ถนอมสายตา','ไม่ซีดจาง','กันน้ำ')):
        found.append({'field':'description','code':'RETAILER_PERFORMANCE_CLAIM_NOT_INDEPENDENTLY_VERIFIED'})
    if indexed is None:found.append({'field':'embedding','code':'MISSING_TEXT_INDEX'})
    elif indexed!=source_for(product):found.append({'field':'embedding','code':'STALE_TEXT_INDEX'})
    return found


def main():
    settings=Settings();engine=create_engine(settings.database_url,connect_args={'connect_timeout':10})
    try:
        with engine.connect() as conn:
            products=[dict(r) for r in conn.execute(text('SELECT * FROM products ORDER BY id')).mappings()]
            indexed=dict(conn.execute(text('SELECT product_id,source_text FROM product_embeddings WHERE model_name=:model'),{'model':settings.text_embed_model}).all())
    finally:engine.dispose()
    rows=[{'sku':p['sku'],'name':p['name'],'issues':product_issues(p,indexed.get(p['id']))} for p in products]
    counts={}
    for row in rows:
        for issue in row['issues']:
            key=issue['field']+':'+issue['code'];counts[key]=counts.get(key,0)+1
    report={'audited_at':datetime.now(timezone.utc).isoformat(),'products':len(products),'embedding_model':settings.text_embed_model,
        'provider_calls':0,'writes':0,'source_urls_checked':'syntax only; no live reachability or retailer fact verification',
        'catalog_sha256':hashlib.sha256(json.dumps(products,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest(),
        'issue_counts':counts,'cases':rows}
    (ROOT/'docs/report/TEXT_CATALOG_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'products':len(products),'issue_counts':counts},ensure_ascii=False))


if __name__=='__main__':main()
