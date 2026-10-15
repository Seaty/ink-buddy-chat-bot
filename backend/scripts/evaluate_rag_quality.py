"""Draft catalog-fact relevance evaluation; explicit paid mode, reusable query-vector cache."""
import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from app.core.config import Settings
from app.ai.embeddings.openrouter_embedding import OpenRouterTextEmbedder
from app.services.product.text_retrieval import TextRetrievalService
from app.schemas.text_retrieval import TextSearchRequest
from app.services.session.openrouter_adapter import OpenRouterCatalogAdapter
from app.services.session.adapter import AnswerInput

ROOT=Path(__file__).resolve().parents[2]

def metrics(gold,predicted,k=5):
    gold=set(gold);predicted=predicted[:k];hits=[1 if p in gold else 0 for p in predicted]
    dcg=sum(hit/math.log2(i+2) for i,hit in enumerate(hits))
    ideal=sum(1/math.log2(i+2) for i in range(min(len(gold),k)))
    return {'recall_at_5':sum(hits)/len(gold) if gold else None,
            'precision_at_5':sum(hits)/k,'precision_returned':sum(hits)/len(predicted) if predicted else 0,
            'hit_rate_at_5':int(any(hits)), 'mrr':next((1/(i+1) for i,v in enumerate(hits) if v),0),
            'ndcg_at_5':dcg/ideal if ideal else None}

class QueryCache:
    def __init__(self,settings):
        self.settings=settings;self.path=ROOT/'.local/rag-quality-query-cache.json'
        self.path.parent.mkdir(exist_ok=True)
        self.cache=json.loads(self.path.read_text()) if self.path.exists() else {}
        self.calls=0;self.hits=0;self.client=None
    def embed_texts(self,texts):
        out=[]
        for query in texts:
            key=hashlib.sha256((self.settings.text_embed_model+':'+str(self.settings.text_embed_dim)+':'+query).encode()).hexdigest()
            if key not in self.cache:
                if self.client is None:self.client=OpenRouterTextEmbedder(self.settings)
                self.cache[key]=self.client.embed_texts([query])[0];self.calls+=1
                self.path.write_text(json.dumps(self.cache),encoding='utf-8')
            else:self.hits+=1
            out.append(self.cache[key])
        return out
    def close(self):
        if self.client:self.client.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true',required=True)
    p.add_argument('--label',required=True);p.add_argument('--threshold',type=float,default=0.35)
    p.add_argument('--answers',action='store_true')
    p.add_argument('--split',choices=('all','development','holdout'),default='all');args=p.parse_args()
    if not args.label.replace('-','').replace('_','').isalnum():p.error('Invalid label')
    settings=Settings(text_search_min_similarity=args.threshold)
    cases=json.loads((ROOT/'backend/datasets/evaluation/rag_quality.json').read_text(encoding='utf-8'))['cases']
    if args.split!='all':cases=[case for case in cases if case['split']==args.split]
    engine=create_engine(settings.database_url,connect_args={'connect_timeout':10});cache=QueryCache(settings);rows=[]
    try:
        for case in cases:
            start=time.monotonic();response=TextRetrievalService(engine,settings,cache).search(TextSearchRequest(query=case['query']))
            skus=[h.product.sku for h in response.items]
            row={'id':case['id'],'split':case['split'],'gold_skus':case['gold_skus'],'predicted_skus':skus,
                'guardrail_status':response.guardrail_status,'expected_status':case['expected_status'],
                'decision_correct':response.guardrail_status in case['expected_status'],'metrics':metrics(case['gold_skus'],skus),
                'duration_ms':round((time.monotonic()-start)*1000,2)}
            if args.answers and case['split']=='holdout' and case['gold_skus']:
                try:
                    answer=OpenRouterCatalogAdapter(settings,deadline=time.monotonic()+60).answer(AnswerInput(case['query'],(),tuple(h.catalog_snapshot for h in response.items)))
                    by_id={h.product.id:h.product.sku for h in response.items};chosen=[by_id[i] for i in answer.product_ids]
                    row['answer']={'model':answer.model_name,'selected_skus':chosen,
                        'selection_precision':sum(sku in case['gold_skus'] for sku in chosen)/len(chosen) if chosen else 0,
                        'evidence_contract_passed':answer.model_name!='catalog_policy'}
                except Exception as error:
                    row['answer']={'error_code':getattr(error,'code','EVALUATION_FAILED'),'evidence_contract_passed':False}
            rows.append(row);print(case['id'],response.guardrail_status,'recall',row['metrics']['recall_at_5'],'results',len(skus),flush=True)
    finally:cache.close();engine.dispose()
    summary={}
    for split in ('development','holdout'):
        group=[r for r in rows if r['split']==split];positive=[r for r in group if r['gold_skus']]
        if not group:continue
        summary[split]={'cases':len(group),'positive_cases':len(positive),'decision_accuracy':sum(r['decision_correct'] for r in group)/len(group)}
        for key in ('recall_at_5','precision_at_5','precision_returned','hit_rate_at_5','mrr','ndcg_at_5'):
            summary[split][key]=sum(r['metrics'][key] for r in positive)/len(positive)
        negative=[r for r in group if not r['gold_skus']]
        summary[split]['negative_false_positive_rate']=sum(bool(r['predicted_skus']) for r in negative)/len(negative)
    report={'label':args.label,'threshold':args.threshold,'evaluated_at':datetime.now(timezone.utc).isoformat(),
        'embedding_model':settings.text_embed_model,'embedding_dimensions':settings.text_embed_dim,
        'dataset_sha256':hashlib.sha256((ROOT/'backend/datasets/evaluation/rag_quality.json').read_bytes()).hexdigest(),
        'gold_status':'draft_catalog_facts_not_independent_human_labels',
        'embedding_calls':cache.calls,'cache_hits':cache.hits,'summary':summary,'cases':rows}
    (ROOT/'docs/report'/('RAG_QUALITY_'+args.label+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
