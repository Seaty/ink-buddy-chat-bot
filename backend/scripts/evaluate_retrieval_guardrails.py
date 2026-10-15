"""Run the public fixed evaluation set on local catalog; --live uses paid query embeddings."""
import argparse
import json
from pathlib import Path
from sqlalchemy import create_engine
from app.core.config import Settings
from app.schemas.text_retrieval import TextSearchRequest
from app.services.product.text_retrieval import TextRetrievalService
from app.services.product.retrieval_policy import scope
from app.services.product.text_search import budget

def main():
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--live',action='store_true');mode.add_argument('--offline',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    cases=json.loads((root/'backend/datasets/evaluation/text_guardrails.json').read_text(encoding='utf-8'))
    if args.offline:
        catalog=json.loads((root/'backend/datasets/reviewed_catalog.json').read_text(encoding='utf-8'))['products']
        results=[]
        for case in cases:
            if not set(case['expected_status']) <= {'blocked','needs_clarification'}:continue
            req=case['request'];d=scope(req['query'],req.get('category'),[r['brand'] for r in catalog],[r['name'] for r in catalog])
            status=d.status
            if status=='allowed' and budget(req['query'])[1]:status='needs_clarification'
            results.append({'id':case['id'],'status':status,'passed':status in case['expected_status']})
        report={'mode':'offline_input_policy_only','passed':sum(r['passed'] for r in results),'total':len(results),'skipped_retrieval_cases':len(cases)-len(results),'results':results}
        (root/'docs/report/TEXT_GUARDRAIL_INPUT_EVAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Offline input policy:',report['passed'],'/',report['total'],'retrieval cases skipped:',report['skipped_retrieval_cases'])
        if report['passed']!=report['total']:raise SystemExit(1)
        return
    s=Settings();engine=create_engine(s.database_url,connect_args={'connect_timeout':10});service=TextRetrievalService(engine,s)
    results=[]
    for case in cases:
        r=service.search(TextSearchRequest(**case['request']))
        checks=[r.guardrail_status in case['expected_status']]
        if case.get('empty'):checks.append(not r.items)
        if case.get('category'):checks.append(all(h.product.category==case['category'] for h in r.items))
        if case.get('max_price') is not None:checks.append(all(h.product.price is not None and h.product.currency=='THB' and h.product.price<=case['max_price'] for h in r.items))
        if case.get('require_hit'):checks.append(bool(r.items))
        results.append({'id':case['id'],'passed':all(checks),'response':r.model_dump(mode='json')})
        print(case['id'],r.guardrail_status,'hits',len(r.items),'pass',all(checks),flush=True)
    report={'policy_version':'catalog-scope-v1','passed':sum(r['passed'] for r in results),'total':len(results),'results':results}
    (root/'docs/report/TEXT_GUARDRAIL_EVAL.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');engine.dispose()
    print('Passed:',report['passed'],'/',report['total'])
    if report['passed']!=report['total']:raise SystemExit(1)

if __name__=='__main__':main()
