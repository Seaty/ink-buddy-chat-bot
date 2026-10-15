"""Audit saved synthetic answers against current DB facts, without calling an LLM."""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine,text
from app.core.config import Settings
from app.services.session.openrouter_adapter import catalog_evidence
from app.services.session.catalog_answer import product_lines
from scripts.evaluate_rag_quality import ROOT

HEADER='ตัวเลือกจาก catalog ที่ AI เลือกตามคำถาม:'
FOOTER='รายละเอียดเป็นข้อมูลตามแหล่งสินค้า ไม่ใช่ผลทดสอบคุณสมบัติ ราคาและสถานะเป็น snapshot ของ catalog ไม่ใช่ข้อมูลสด'
MISSING_PRICE='ยังไม่มีราคาที่ตรวจสอบพร้อมใช้'


def verify_rendered(answer,products,question=''):
    facts,_=catalog_evidence(products)
    by_name={p['name']:p for p in products};current=None;failures=[];checked=0
    for line in answer.splitlines():
        if line in (HEADER,FOOTER):continue
        if line in by_name:current=by_name[line];continue
        if line.startswith('• ') and current is not None:
            value=line[2:]
            if value==MISSING_PRICE:
                valid=current.get('price') is None
            else:
                own=facts.get(str(current['id']),{})
                derived={line[2:] for eid in own for line in product_lines(question,current,own,[eid]) if line.startswith('• ')}
                # Frozen older answers quoted the full description; audit that exact DB value too.
                legacy='รายละเอียดตามแหล่งสินค้า: '+str(current.get('description') or '')
                valid=value in own.values() or value in derived or value==legacy
            if not valid:failures.append('BULLET_NOT_IN_CURRENT_PRODUCT_EVIDENCE')
            checked+=1
        else:failures.append('UNRECOGNIZED_RENDERED_LINE')
    if not answer.startswith(HEADER+'\n') or not answer.endswith(FOOTER):failures.append('MISSING_ATTRIBUTION')
    if any(p['name'] not in answer.splitlines() for p in products):failures.append('SELECTED_PRODUCT_NOT_RENDERED')
    if not checked:failures.append('NO_EVIDENCE_BULLETS')
    return {'passed':not failures,'checked_bullets':checked,'failures':failures}


def main():
    evidence=ROOT/'docs/report/RAG_ACCEPTANCE_frozen_HUMAN_REVIEW.json'
    saved=json.loads(evidence.read_text(encoding='utf-8'))
    evaluation=json.loads((ROOT/'docs/report/RAG_ACCEPTANCE_frozen.json').read_text(encoding='utf-8'))
    original={r['id']:r for r in evaluation['cases']}
    engine=create_engine(Settings().database_url,connect_args={'connect_timeout':10});results=[]
    try:
        with engine.connect() as conn:
            for case in saved['cases']:
                row={'id':case['id'],'reviewer':'automated_catalog_audit','human_score':None}
                if not case.get('answer'):
                    row.update(passed=False,failures=['NO_SAVED_ANSWER'])
                elif case['model']=='catalog_policy':
                    record=original[case['id']]
                    row.update(passed=not case['products'] and record['status']!='allowed' and record.get('answer_calls')==0,
                        audit_scope='policy result/no-LLM verified from original report; wording not human-rated')
                else:
                    products=[];mismatches=[]
                    for reference in case['products']:
                        product=conn.execute(text('SELECT * FROM products WHERE sku=:sku'),{'sku':reference['sku']}).mappings().one_or_none()
                        if product is None:mismatches.append('PRODUCT_NOT_IN_CURRENT_CATALOG');continue
                        product=dict(product);products.append(product)
                        if any(product[field]!=reference[field] for field in ('name','source_ref')):mismatches.append('CATALOG_REFERENCE_CHANGED')
                    row.update(verify_rendered(case['answer'],products,case['question']))
                    row['failures'].extend(mismatches);row['passed']=not row['failures']
                    row['catalog_checked_at']='current database at audit time; original full snapshot was not saved'
                    row['product_facts']=[{'sku':p['sku'],'name':p['name'],'category':p['category'],'brand':p['brand'],
                        'price':str(p['price']) if p['price'] is not None else None,'currency':p['currency'],'source_ref':p['source_ref']} for p in products]
                results.append(row)
    finally:engine.dispose()
    report={'audited_at':datetime.now(timezone.utc).isoformat(),'review_type':'automated_not_independent_human_review',
        'source_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest(),'provider_calls':0,
        'limitation':'DB consistency only. Does not verify retailer pages, complete relevance, product quality or human satisfaction.',
        'passed':sum(r['passed'] for r in results),'total':len(results),'cases':results}
    (ROOT/'docs/report/RAG_ANSWER_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved-answer catalog audit:',report['passed'],'/',report['total'],'provider calls: 0')
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':raise SystemExit(main())
