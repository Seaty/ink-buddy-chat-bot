"""Apply the explicitly approved 2026-10-14 demo prices; backup before atomic write."""
import json
import argparse
from decimal import Decimal
from datetime import datetime,timezone
from sqlalchemy import create_engine,text
from app.core.config import Settings
from app.services.product.text_index import source_for
from scripts.evaluate_rag_quality import ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true',required=True,help='Explicitly apply the user-approved demo prices')
    parser.parse_args()
    proposal=json.loads((ROOT/'docs/report/PRODUCT_PRICE_REVIEW_2026-10-14.json').read_text(encoding='utf-8'))
    proposed={r['sku']:r for r in proposal['products']}
    if len(proposed)!=18:raise RuntimeError('Expected exactly 18 approved demo candidates')
    engine=create_engine(Settings().database_url,connect_args={'connect_timeout':10})
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=ROOT/f'.local/backups/prices_before_demo_{stamp}.json'
    backup.parent.mkdir(parents=True,exist_ok=True)
    updated=[]
    try:
        with engine.begin() as conn:
            rows=[dict(r) for r in conn.execute(text('SELECT * FROM products ORDER BY id FOR UPDATE')).mappings()]
            by_sku={r['sku']:r for r in rows}
            if set(proposed)-set(by_sku):raise RuntimeError('Missing catalog SKU')
            for sku,candidate in proposed.items():
                old=by_sku[sku]['price'];new=Decimal(candidate['candidate_price'])
                if old is not None and old!=new:raise RuntimeError('Price conflict; abort before changing data')
                if new<=0:raise RuntimeError('Expected positive price')
            backup.write_text(json.dumps({'backed_up_at':stamp,'products':rows},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            for row in rows:
                metadata={
                    'price_tax_basis':'excludes_vat',
                    'price_tax_basis_verification':'user_assumed_for_coursework_not_verified',
                    'price_usage':'coursework_demo_snapshot_not_live',
                }
                candidate=proposed.get(row['sku'])
                price=row['price']
                if candidate:
                    price=Decimal(candidate['candidate_price'])
                    metadata.update(price_review='user_approved_demo_2026_10_14',price_researched_on='2026-10-14',
                        price_source_ref=candidate['price_source_ref'],price_selling_unit=candidate['selling_unit'],
                        price_source_evidence_type=candidate['evidence_type'],price_source_match_status=candidate['match_status'],
                        price_source_note=candidate['note'],price_source_tax_status=candidate['tax_status'])
                    if candidate['tax_status']=='excludes_vat_explicit_on_source':
                        metadata['price_tax_basis_verification']='source_explicitly_excludes_vat'
                    updated.append({'sku':row['sku'],'old_price':str(row['price']) if row['price'] is not None else None,
                        'new_price':str(price),'currency':'THB','tax_basis_verification':metadata['price_tax_basis_verification']})
                attrs={**(row['attributes'] or {}),**metadata}
                if source_for(row)!=source_for({**row,'attributes':attrs,'price':price}):
                    raise RuntimeError('Would alter embedding source; abort without stale indexes')
                conn.execute(text('UPDATE products SET price=:price,attributes=CAST(:attrs AS jsonb),updated_at=now() WHERE id=:id'),
                    {'price':price,'attrs':json.dumps(attrs,ensure_ascii=False),'id':row['id']})
            missing=conn.execute(text('SELECT count(*) FROM products WHERE price IS NULL')).scalar_one()
            if missing:raise RuntimeError('Unexpected remaining NULL prices; abort')
    finally:engine.dispose()
    # Keep the import manifest aligned so later imports cannot restore the old NULLs.
    manifest_path=ROOT/'backend/datasets/reviewed_catalog.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    for product in manifest['products']:
        metadata={'price_tax_basis':'excludes_vat','price_tax_basis_verification':'user_assumed_for_coursework_not_verified',
                  'price_usage':'coursework_demo_snapshot_not_live'}
        candidate=proposed.get(product['sku'])
        if candidate:
            product['price']=candidate['candidate_price']
            metadata.update(price_review='user_approved_demo_2026_10_14',price_researched_on='2026-10-14',
                price_source_ref=candidate['price_source_ref'],price_selling_unit=candidate['selling_unit'],
                price_source_evidence_type=candidate['evidence_type'],price_source_match_status=candidate['match_status'],
                price_source_note=candidate['note'],price_source_tax_status=candidate['tax_status'])
            if candidate['tax_status']=='excludes_vat_explicit_on_source':metadata['price_tax_basis_verification']='source_explicitly_excludes_vat'
        product['attributes'].update(metadata)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report={'applied_on':'2026-10-14','authorization':'User approved all available proposed prices as excludes-VAT coursework demo',
            'new_prices':len(updated),'catalog_products':len(rows),'missing_prices':missing,'price_tax_basis':'excludes_vat',
            'vat_conversion_performed':False,'existing_49_price_amounts_unchanged':True,'embedding_source_changed':False,
            'provider_calls':0,'backup_path':str(backup.relative_to(ROOT)),'products':updated,
            'limitation':'52 tax bases are demo assumptions, not source verification. 3 new prices retain variant/unit/tax evidence limitations.'}
    (ROOT/'docs/report/PRODUCT_PRICE_APPLY_2026-10-14.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('new_prices','catalog_products','missing_prices','embedding_source_changed','provider_calls')}))


if __name__=='__main__':main()
