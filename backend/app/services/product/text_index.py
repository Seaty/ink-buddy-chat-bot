"""Catalog-only text indexing with short transactions and a dedicated advisory lock."""
import json
import time
from sqlalchemy import text
from app.core.errors import ApiError
from app.ai.embeddings.openrouter_embedding import OpenRouterTextEmbedder
from app.schemas.admin import TextIssue, TextValidateResponse, TextIndexResponse

LOCK_ID = 482901731
FIELDS = 'id,sku,name,category,brand,description,attributes,price,source_ref'

def safe_attributes(value):
    if isinstance(value, dict):
        return {k: safe_attributes(v) for k,v in sorted(value.items())
                if not any(word in k.lower() for word in ('url','image','photo','password','token','secret','price'))}
    if isinstance(value, list):
        return [safe_attributes(v) for v in value]
    if isinstance(value, str) and ('http://' in value or 'https://' in value):
        return None
    return value

def source_for(row):
    parts = [f'{k}: {row[k]}' for k in ('name','sku','category','brand','description') if row.get(k)]
    attrs = safe_attributes(row.get('attributes') or {})
    if attrs:
        parts.append('attributes: '+json.dumps(attrs, sort_keys=True, ensure_ascii=False, separators=(',',':')))
    return '\n'.join(parts)

def issues(row):
    errors=[]; warnings=[]
    def issue(field, code): return TextIssue(product_id=row['id'], field=field, code=code)
    if not (row.get('name') or '').strip(): errors.append(issue('name','MISSING_NAME'))
    if len(source_for(row))>16000: errors.append(issue('source_text','TEXT_TOO_LONG'))
    for field in ('category','brand','description','price','source_ref'):
        if row.get(field) is None or row.get(field)=='': warnings.append(issue(field,'MISSING_VALUE'))
    return errors,warnings

class TextIndexService:
    def __init__(self, engine, settings, embedder=None):
        self.engine=engine; self.settings=settings; self.embedder=embedder

    def rows(self, conn, ids):
        query='SELECT '+FIELDS+' FROM products'
        params={}
        if ids is not None:
            query+=' WHERE id = ANY(CAST(:ids AS uuid[]))'; params['ids']=[str(i) for i in ids]
        rows=[dict(r) for r in conn.execute(text(query+' ORDER BY id'),params).mappings()]
        if ids is not None and set(ids)-{r['id'] for r in rows}:
            raise ApiError(422,'PRODUCT_NOT_FOUND','one or more product IDs do not exist')
        return rows

    def validate(self, request):
        with self.engine.connect() as conn: rows=self.rows(conn, request.product_ids)
        errors=[]; warnings=[]; invalid=0
        for row in rows:
            e,w=issues(row); errors.extend(e); warnings.extend(w); invalid+=bool(e)
        return TextValidateResponse(examined=len(rows), valid=len(rows)-invalid, invalid=invalid, errors=errors, warnings=warnings)

    def index(self, request):
        started=time.monotonic(); report=TextIndexResponse()
        if self.settings.text_embed_dim != 1024:
            raise ApiError(422,'EMBEDDING_DIMENSION_UNSUPPORTED','database requires 1024 dimensions')
        # Dedicated connection: session-level lock must be released before returning to pool.
        with self.engine.connect() as conn:
            acquired=conn.execute(text('SELECT pg_try_advisory_lock(:key)'),{'key':LOCK_ID}).scalar_one()
            conn.commit()
            if not acquired: raise ApiError(409,'TEXT_INDEX_BUSY','text indexing already running')
            embedder=None
            try:
                rows=self.rows(conn,request.product_ids)
                existing=dict(conn.execute(text('SELECT product_id,source_text FROM product_embeddings WHERE model_name=:model'),{'model':self.settings.text_embed_model}).all())
                conn.commit(); pending=[]; report.examined=len(rows)
                for row in rows:
                    e,w=issues(row); report.warnings.extend(w)
                    if e: report.invalid+=1; report.errors.extend(e)
                    elif existing.get(row['id'])==source_for(row): report.unchanged+=1
                    else: pending.append(row)
                selected=pending[:request.limit]; report.remaining=len(pending)-len(selected)
                if selected: embedder=self.embedder or OpenRouterTextEmbedder(self.settings)
                for offset in range(0,len(selected),self.settings.text_embed_batch_size):
                    batch=selected[offset:offset+self.settings.text_embed_batch_size]
                    try:
                        vectors=embedder.embed_texts([source_for(r) for r in batch])
                        if len(vectors)!=len(batch): raise ValueError('invalid batch')
                        changed=[]; saved=0
                        with conn.begin():
                            for row,vector in zip(batch,vectors):
                                fresh=conn.execute(text('SELECT '+FIELDS+' FROM products WHERE id=:id FOR UPDATE'),{'id':row['id']}).mappings().one_or_none()
                                if fresh is None or source_for(fresh)!=source_for(row):
                                    changed.append(TextIssue(product_id=row['id'],field='source_text',code='PRODUCT_CHANGED')); continue
                                conn.execute(text('INSERT INTO product_embeddings(product_id,model_name,source_text,embedding) VALUES(:id,:model,:source,CAST(:vector AS vector)) ON CONFLICT(product_id,model_name) DO UPDATE SET source_text=EXCLUDED.source_text,embedding=EXCLUDED.embedding'),{'id':row['id'],'model':self.settings.text_embed_model,'source':source_for(row),'vector':json.dumps(vector)})
                                saved+=1
                        report.indexed+=saved; report.remaining+=len(changed); report.warnings.extend(changed)
                    except Exception:
                        conn.rollback(); report.failed+=len(batch)
                        report.errors.extend(TextIssue(product_id=r['id'],field='embedding',code='BATCH_FAILED') for r in batch)
            finally:
                try:
                    conn.rollback()
                    conn.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':LOCK_ID})
                    conn.commit()
                except Exception:
                    conn.invalidate()
                    raise
                finally:
                    if embedder is not None and self.embedder is None: embedder.close()
        report.seconds=round(time.monotonic()-started,3)
        return report
