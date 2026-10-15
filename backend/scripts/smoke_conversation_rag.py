"""Small paid live trial against the main catalog; read-only, no chat writes."""
import json
import time
import argparse
from decimal import Decimal
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import create_engine,text
from app.core.config import Settings
from app.services.product.text_retrieval import TextRetrievalService
from app.services.session.conversation_rag import respond
from app.schemas.session import ProductReference


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audit-only',action='store_true');args=parser.parse_args()
    settings=Settings();engine=create_engine(settings.database_url);results=[];history=[]
    try:
        questions=['ปากกาหมึกน้ำเงิน สามรุ่นถูกที่สุด และมีสีอื่นไหม','ตัวที่สองราคาเท่าไร','ปากกาหมึกน้ำเงิน ด้ามสีส้ม']
        with engine.connect() as conn:
            count=conn.execute(text('SELECT count(*) FROM products')).scalar_one()
            rows=conn.execute(text('SELECT * FROM products')).mappings().all()
        manifest=json.loads(Path('datasets/reviewed_catalog.json').read_text(encoding='utf-8'))['products']
        approved={p['sku']:p for p in manifest}
        # Fail closed before any provider call: only previously reviewed public
        # retail catalog facts may enter this paid trial, never arbitrary DB data.
        for row in rows:
            public=approved[row['sku']]
            assert str(public['source_ref']).startswith('https://')
            for field in ('name','brand','category','description','currency'):
                assert row[field]==public.get(field),(row['sku'],field)
            assert row['price']==(Decimal(str(public['price'])) if public.get('price') is not None else None)
            for field in ('color','size','unit','pack_qty','category_th'):
                assert (row['attributes'] or {}).get(field)==(public.get('attributes') or {}).get(field)
            assert row.get('availability') in (None,public.get('availability'))
        if args.audit_only:
            print(json.dumps({'reviewed_public_catalog_products':count,'provider_calls':0,'account_fields_sent':False}));return
        for question in questions:
            started=time.monotonic();deadline=started+settings.chat_timeout_seconds
            products,answer=respond(TextRetrievalService(engine,settings,deadline=deadline),settings,question,tuple(history),deadline)
            selected={p['id']:p for p in products}
            refs=[ProductReference(**selected[i]).model_dump(mode='json') for i in answer.product_ids]
            if len(results)==0:
                assert 1<=len(refs)<=3 and all(r['ink_color']=='น้ำเงิน' and r['price'] is not None for r in refs)
                assert [float(r['price']) for r in refs]==sorted(float(r['price']) for r in refs)
            if len(results)==1:assert refs[0]['id']==results[0]['references'][1]['id']
            if len(results)==2:assert all(r['ink_color']=='น้ำเงิน' and r['body_color']=='ส้ม' for r in refs)
            results.append({'question':question,'status':'passed','model':answer.model_name,'duration_ms':round((time.monotonic()-started)*1000),'references':refs})
            history.extend([{'role':'user','content':question},{'role':'assistant','content':answer.content,'product_refs':refs}])
        # No context from another chat and no paid call when the question is ambiguous.
        _,policy=respond(TextRetrievalService(engine,settings),settings,'ขอสามรุ่นถูกที่สุด',(),time.monotonic()+60)
        assert policy.model_name=='catalog_policy'
        report={'status':'passed','tested_at':datetime.now(timezone.utc).isoformat(),'catalog_count':count,'main_database_writes':False,'history_source':'in-memory synthetic test conversation','results':results,'fresh_chat_policy':policy.model_name}
        Path('../docs/report/RAG_CONVERSATION_LIVE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':'passed','cases':len(results)+1,'catalog_count':count,'models':[r['model'] for r in results]},ensure_ascii=False))
    finally:engine.dispose()


if __name__=='__main__':main()
