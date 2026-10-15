"""Constraint probes and measured answer usage; explicit live mode, no database writes."""
import argparse
import json
import hashlib
import math
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine, text
from app.core.config import Settings
from app.ai.llm.openrouter_client import OpenRouterClient
from app.schemas.text_retrieval import TextSearchRequest
from app.services.product.text_retrieval import TextRetrievalService
from app.services.session.adapter import AnswerInput
from app.services.session.openrouter_adapter import OpenRouterCatalogAdapter
from app.services.session.openrouter_adapter import SelectionOutput
from pydantic import ValidationError
from scripts.evaluate_rag_quality import ROOT, QueryCache
from app.services.product.text_index import source_for
from app.services.product.retrieval_policy import normalized


def check_constraints(case, response):
    checks={'status':response.guardrail_status in case['expected_status']}
    if case.get('empty'):checks['empty']=not response.items
    if case.get('require_hit'):checks['hit']=bool(response.items)
    for field in ('category','brand'):
        if field in case:checks[field]=all(getattr(hit.product,field)==case[field] for hit in response.items)
    if case.get('evidence_contains'):
        checks['catalog_evidence']=all(normalized(case['evidence_contains']) in normalized(source_for(hit.catalog_snapshot)) for hit in response.items)
    if 'min_price' in case or 'max_price' in case:
        checks['budget']=all(hit.product.price is not None and hit.product.currency=='THB'
            and Decimal(str(case.get('min_price',0)))<=hit.product.price<=Decimal(str(case.get('max_price','Infinity')))
            for hit in response.items)
    return checks


def percentiles(values):
    ordered=sorted(values)
    if not ordered:return {'count':0,'p50_ms':None,'p95_ms':None}
    return {'count':len(ordered),'p50_ms':ordered[math.ceil(len(ordered)*.5)-1],
            'p95_ms':ordered[math.ceil(len(ordered)*.95)-1]}


def review_markdown(review):
    lines=['# คำตอบสำหรับทีมประเมิน RAG','',
           'สถานะ: รอผู้ประเมิน — เป็นคำถามสังเคราะห์และข้อมูล catalog ไม่ใช่ประวัติผู้ใช้จริง',
           'ผลตรวจอัตโนมัติไม่ใช่คะแนนคุณภาพโดยมนุษย์ ดูแบบประเมินใน docs/architecture/RAG_HUMAN_REVIEW.md','']
    for row in review:
        lines.extend([f"## {row['id']}",'',f"คำถาม: {row['question']}",'',
                      'คำตอบ / error และรายการอ้างอิงจาก snapshot:',''])
        value=json.dumps(row,ensure_ascii=False,indent=2)
        fence='`'*max(3,1+max([len(run) for run in re.findall(r'`+',value)] or [0]))
        lines.extend([fence+'json',value,fence,'','คะแนนผู้ประเมิน: ยังไม่กรอก',''])
    return '\n'.join(lines)


class UsageClient:
    def __init__(self, client):self.client=client;self.calls=0;self.usage=None;self.diagnostics=None
    def chat(self,*args,**kwargs):
        self.calls+=1;result=self.client.chat(*args,**kwargs)
        self.usage={key:result.get(key) for key in ('prompt_eval_count','eval_count','usage_cost','model')}
        self.diagnostics={'finish_reason':result.get('done_reason')}
        try:
            selected=SelectionOutput.model_validate_json(result['message']['content'])
            facts={p['product_id']:p['evidence'] for p in json.loads(args[1][1]['content'])['catalog']}
            self.diagnostics['foreign_product_count']=sum(str(p.product_id) not in facts for p in selected.recommendations)
            self.diagnostics['foreign_evidence_count']=sum(e not in facts.get(str(p.product_id),{}) for p in selected.recommendations for e in p.evidence_ids)
            self.diagnostics['duplicate_product_count']=len(selected.recommendations)-len({p.product_id for p in selected.recommendations})
            self.diagnostics['duplicate_evidence_count']=sum(len(p.evidence_ids)-len(set(p.evidence_ids)) for p in selected.recommendations)
        except ValidationError as error:
            self.diagnostics['schema_errors']=[{'type':e['type'],'location':list(e['loc'])} for e in error.errors()]
        except (ValueError,KeyError,TypeError):self.diagnostics['unparseable']=True
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--answers',action='store_true')
    parser.add_argument('--label',default='current')
    parser.add_argument('--case',help='Run a single case for a deliberate diagnostic experiment')
    parser.add_argument('--suite',choices=('robustness','acceptance'),default='robustness')
    parser.add_argument('--review-artifact',action='store_true',help='Save synthetic evaluation questions and rendered catalog answers for human review')
    args=parser.parse_args()
    if not args.label.replace('-','').replace('_','').isalnum():parser.error('Invalid label')
    if args.review_artifact and not args.answers:parser.error('--review-artifact requires --answers')
    dataset=ROOT/f'backend/datasets/evaluation/rag_{args.suite}.json'
    cases=json.loads(dataset.read_text(encoding='utf-8'))['cases']
    if args.case and args.case not in {case['id'] for case in cases}:parser.error('Unknown case')
    settings=Settings();engine=create_engine(settings.database_url,connect_args={'connect_timeout':10})
    cache=QueryCache(settings);rows=[];review=[]
    try:
        with engine.connect() as conn:
            catalog_count=conn.execute(text('SELECT count(*) FROM products')).scalar_one()
        for case in cases:
            if args.case and case['id']!=args.case:continue
            started=time.monotonic();row={'id':case['id']};embedding_before=cache.calls
            review_row={'id':case['id'],'question':case['query']}
            try:
                response=TextRetrievalService(engine,settings,cache,deadline=time.monotonic()+60).search(TextSearchRequest(query=case['query']))
                row.update(status=response.guardrail_status,checks=check_constraints(case,response),
                    product_skus=[h.product.sku for h in response.items],retrieval_ms=round((time.monotonic()-started)*1000,2))
                if args.answers:
                    client=OpenRouterClient(settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else None,
                        settings.openrouter_base_url,min(settings.openrouter_timeout_s,max(.001,started+60-time.monotonic())),retries=0)
                    observed=UsageClient(client);answer_start=time.monotonic()
                    try:
                        answer=OpenRouterCatalogAdapter(settings,client=observed,deadline=started+60).answer(
                            AnswerInput(case['query'],(),tuple(h.catalog_snapshot for h in response.items),response.clarification))
                        row.update(answer_ms=round((time.monotonic()-answer_start)*1000,2),answer_model=answer.model_name)
                        review_row.update(answer=answer.content,model=answer.model_name,products=[
                            {'sku':hit.product.sku,'name':hit.product.name,'source_ref':hit.product.source_ref}
                            for hit in response.items if hit.product.id in answer.product_ids])
                        row['checks']['answer_ids']=set(answer.product_ids)<=set(h.product.id for h in response.items)
                        if not response.items:row['checks']['no_llm_for_policy']=observed.calls==0
                        elif case.get('answer'):row['checks']['nonempty_selection']=bool(answer.product_ids)
                    finally:
                        row['answer_ms']=round((time.monotonic()-answer_start)*1000,2)
                        row['answer_calls']=observed.calls;row['usage']=observed.usage;client.close()
                        row['output_diagnostics']=observed.diagnostics
                row['passed']=all(row['checks'].values())
            except Exception as error:
                row.update(passed=False,error_code=getattr(error,'code','EVALUATION_FAILED'))
                review_row['error_code']=row['error_code']
            row['embedding_calls']=cache.calls-embedding_before
            row['total_ms']=round((time.monotonic()-started)*1000,2);rows.append(row)
            review_row['automatic_checks_passed']=row['passed'];review.append(review_row)
            print(case['id'],'passed',row['passed'],'status',row.get('status'),flush=True)
    finally:cache.close();engine.dispose()
    usage=[row['usage'] for row in rows if row.get('usage')]
    report={'evaluated_at':datetime.now(timezone.utc).isoformat(),'label_status':'draft_constraints_not_human_quality_assessment',
        'dataset_sha256':hashlib.sha256(dataset.read_bytes()).hexdigest(),
        'suite':args.suite,'dataset_label_status':json.loads(dataset.read_text(encoding='utf-8')).get('label_status'),
        'adapter_sha256':hashlib.sha256((ROOT/'backend/app/services/session/openrouter_adapter.py').read_bytes()).hexdigest(),
        'renderer_sha256':hashlib.sha256((ROOT/'backend/app/services/session/catalog_answer.py').read_bytes()).hexdigest(),
        'retrieval_policy_sha256':hashlib.sha256((ROOT/'backend/app/services/product/retrieval_policy.py').read_bytes()).hexdigest(),
        'catalog_count':catalog_count,'embedding_model':settings.text_embed_model,'chat_model':settings.text_chat_model,
        'query_vectors_cached':True,'embedding_calls':cache.calls,'cache_hits':cache.hits,
        'passed':sum(row['passed'] for row in rows),'total':len(rows),
        'latency_total':percentiles([row['total_ms'] for row in rows]),
        'latency_llm':percentiles([row['answer_ms'] for row in rows if row.get('answer_calls') and 'answer_ms' in row]),
        'usage':{'prompt_tokens':sum(u.get('prompt_eval_count') or 0 for u in usage),
                 'completion_tokens':sum(u.get('eval_count') or 0 for u in usage),
                 'reported_chat_cost_usd':sum(u['usage_cost'] for u in usage) if usage and all(isinstance(u.get('usage_cost'),(int,float)) for u in usage) else None,
                 'cost_scope':'chat responses with usage, including rejected output; embedding costs and failed upstream calls excluded; verify billing in OpenRouter'},'cases':rows}
    prefix='RAG_ACCEPTANCE' if args.suite=='acceptance' else 'RAG_ROBUSTNESS'
    target=ROOT/'docs/report'/f'{prefix}_{args.label}.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.review_artifact:
        artifact={'status':'pending_human_review','source':'synthetic evaluation inputs and catalog only; not real user history',
                  'report':target.name,'cases':review}
        (ROOT/'docs/report'/f'{prefix}_{args.label}_HUMAN_REVIEW.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'docs/report'/f'{prefix}_{args.label}_HUMAN_REVIEW.md').write_text(review_markdown(review),encoding='utf-8')
    print('Passed',report['passed'],'/',report['total'],'report',target.name)
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':raise SystemExit(main())
