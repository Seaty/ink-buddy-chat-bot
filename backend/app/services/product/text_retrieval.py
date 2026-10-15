"""Text retrieval only: fresh catalog facts and RRF fusion, no answer generation."""
import json
import time
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.ai.rag.indexing_service import CATEGORY_TH
from app.ai.embeddings.openrouter_embedding import OpenRouterTextEmbedder, EmbeddingError
from app.core.errors import ApiError
from app.schemas.text_retrieval import TextSearchResponse,TextSearchHit
from app.schemas.product import ProductResponse
from app.services.product.text_search import CatalogTextSearch,budget
from app.services.product.text_index import source_for
from app.services.product.retrieval_policy import scope,relevant,matched_brands

def fuse(keyword,semantic,limit):
    merged={}
    for kind,hits in [('keyword',keyword),('semantic',semantic)]:
        for rank,row in enumerate(hits,1):
            pid=row['id'];hit=merged.setdefault(pid,{'row':row,'score':0,'keyword_rank':None,'semantic_rank':None,'semantic_similarity':None})
            hit['score']+=1/(60+rank);hit[kind+'_rank']=rank
            if kind=='semantic':hit['semantic_similarity']=float(row['similarity'])
    return sorted(merged.values(),key=lambda h:(-h['score'],str(h['row']['id'])))[:limit]

class TextRetrievalService:
    def __init__(self,engine,settings,embedder=None,deadline=None):
        self.engine=engine;self.settings=settings;self.embedder=embedder;self.deadline=deadline

    def remaining(self):
        remaining=self.deadline-time.monotonic() if self.deadline else self.settings.openrouter_timeout_s
        if remaining<=0:raise ApiError(504,'ANSWER_TIMEOUT','retrieval timed out')
        return remaining

    @contextmanager
    def connection(self):
        with self.engine.connect() as conn:
            if self.deadline:conn.execute(text("SELECT set_config('statement_timeout',:ms,true)"),{'ms':str(max(1,int(self.remaining()*1000)))})
            yield conn

    @contextmanager
    def session(self):
        with Session(self.engine) as db:
            if self.deadline:db.execute(text("SELECT set_config('statement_timeout',:ms,true)"),{'ms':str(max(1,int(self.remaining()*1000)))})
            yield db

    def search(self,request,requires_price=False):
        start=time.monotonic();s=self.settings
        result=TextSearchResponse(items=[],embedding_model=s.text_embed_model,index_status='not_checked')
        if s.text_embed_dim!=1024:raise ApiError(422,'EMBEDDING_DIMENSION_UNSUPPORTED','database requires 1024 dimensions')
        if request.category and request.category not in CATEGORY_TH:
            raise ApiError(422,'INVALID_CATEGORY','category must be a catalog category key')
        with self.connection() as conn:
            catalog=conn.execute(text('SELECT name,brand FROM products')).mappings().all()
        decision=scope(request.query,request.category,[r['brand'] for r in catalog],[r['name'] for r in catalog])
        result.guardrail_status=decision.status;result.guardrail_reason=decision.reason
        if decision.status!='allowed':
            result.clarification=decision.message;return result
        limits,clarification=budget(request.query)
        if clarification:
            result.guardrail_status='needs_clarification';result.guardrail_reason='AMBIGUOUS_BUDGET'
            result.clarification=clarification;return result
        if request.category and request.category not in CATEGORY_TH:
            raise ApiError(422,'INVALID_CATEGORY','category must be a catalog category key')
        categories=decision.categories
        if not categories and 'ปากกา' in request.query:categories=['ballpoint_pen','gel_pen','marker','whiteboard_marker']
        with self.session() as db:
            keyword,_=CatalogTextSearch(db).search(request.query,limit=20,category_filter=categories[0] if len(categories)==1 else request.category,brand_filter=request.brand,requires_price=requires_price)
            brands=db.execute(text('SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL')).scalars().all()
            matched=[request.brand] if request.brand else matched_brands(brands,request.query)
            products=db.execute(text('SELECT count(*) FROM products')).scalar_one()
            indexed=db.execute(text('SELECT count(*) FROM product_embeddings WHERE model_name=:m'),{'m':s.text_embed_model}).scalar_one()
        result.index_status='missing' if indexed==0 else 'partial' if indexed<products else 'ready'
        semantic=[]
        if indexed:
            embed_settings=s.model_copy(update={'openrouter_timeout_s':min(s.openrouter_timeout_s,self.remaining())})
            embedder=self.embedder or OpenRouterTextEmbedder(embed_settings);embed_start=time.monotonic()
            try:vector=embedder.embed_texts([request.query])[0]
            except EmbeddingError as error:
                if error.status_code in (408,504):
                    raise ApiError(504,'ANSWER_TIMEOUT','query embedding timed out') from None
                if error.status_code==403:
                    raise ApiError(403,'OPENROUTER_POLICY_REJECTED','request rejected by upstream policy; check configured guardrails') from None
                raise ApiError(503,'TEXT_EMBEDDING_UNAVAILABLE','query embedding unavailable') from None
            finally:
                if self.embedder is None:embedder.close()
            result.timings_ms['embedding']=round((time.monotonic()-embed_start)*1000,2)
            filters=['e.model_name=:model'];params={'model':s.text_embed_model,'vector':json.dumps(vector)}
            for field,values in [('category',categories),('brand',matched)]:
                if values:
                    names=[]
                    for i,v in enumerate(values):key=f'{field}{i}';params[key]=v;names.append(':'+key)
                    filters.append(f'p.{field} IN ({",".join(names)})')
            if requires_price:filters.append("p.price IS NOT NULL AND p.currency='THB'")
            if limits:
                filters.append("p.price IS NOT NULL AND p.currency='THB' AND p.price BETWEEN :low AND :high")
                params.update(low=limits[0],high=limits[1])
            with self.connection() as conn:
                rows=conn.execute(text('SELECT p.*,e.source_text,1-(e.embedding <=> CAST(:vector AS vector)) AS similarity FROM products p JOIN product_embeddings e ON e.product_id=p.id WHERE '+ ' AND '.join(filters)+' ORDER BY e.embedding <=> CAST(:vector AS vector),p.id LIMIT 100'),params).mappings().all()
            for row in rows:
                if source_for(row)!=row['source_text']:
                    result.stale_skipped+=1;continue
                if row['similarity'] is not None and row['similarity']>=s.text_search_min_similarity:
                    semantic.append(dict(row))
                    if len(semantic)==20:break
            if result.stale_skipped:result.index_status='partial'
        rejected={row['id'] for row in [*keyword,*semantic] if not relevant(row,request.query)}
        result.relevance_rejected=len(rejected)
        keyword=[row for row in keyword if row['id'] not in rejected]
        semantic=[row for row in semantic if row['id'] not in rejected]
        result.items=[TextSearchHit(product=ProductResponse(**h['row']),catalog_snapshot=h['row'],**{k:v for k,v in h.items() if k!='row'}) for h in fuse(keyword,semantic,request.limit)]
        if not result.items:
            result.guardrail_status='no_match';result.guardrail_reason='NO_GROUNDED_MATCH'
            result.clarification=('ยังไม่พบสินค้าที่ตรงกับคำถามในข้อมูล catalog ลองปรับช่วงงบหรือระบุเงื่อนไขที่ยืดหยุ่นได้ โดยระบบจะไม่เสนอสินค้าที่เกินงบให้เอง'
                if limits else 'ยังไม่พบสินค้าที่ตรงกับคำถามในข้อมูล catalog ลองตรวจชื่อรุ่น ยี่ห้อ หรือระบุลักษณะสินค้าที่ต้องการเพิ่มเติม')
        result.timings_ms['total']=round((time.monotonic()-start)*1000,2)
        return result
