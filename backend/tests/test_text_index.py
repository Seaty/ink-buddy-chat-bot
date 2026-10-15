import os
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from app.core.config import Settings
from app.core.errors import ApiError
from app.schemas.admin import TextIndexRequest, TextValidateRequest
from app.services.product.text_index import TextIndexService, source_for, issues, LOCK_ID

def test_source_deterministic_and_safe():
    row={'id':uuid4(),'name':'pen','attributes':{'z':'blue','source_image_url':'https://private','a':1}}
    assert source_for(row)==source_for({**row,'attributes':dict(reversed(list(row['attributes'].items())))})
    assert 'https://' not in source_for(row)
    assert 'price:' not in source_for({**row,'price':10})

def test_missing_and_length():
    row={'id':uuid4(),'name':' ','description':'x'*16001}
    errors,warnings=issues(row)
    assert {e.code for e in errors}=={'MISSING_NAME','TEXT_TOO_LONG'}
    assert any(w.field=='price' for w in warnings)

@pytest.fixture
def engine():
    url=os.getenv('TEXT_INDEX_TEST_URL')
    if not url: pytest.skip('disposable PostgreSQL required')
    assert url.endswith('/ink_buddy_test') and ':55439/' in url
    e=create_engine(url)
    with e.begin() as c: c.execute(text('TRUNCATE products CASCADE'))
    yield e
    e.dispose()

def insert(e,name='pen'):
    with e.begin() as c:
        return c.execute(text('INSERT INTO products(name) VALUES(:name) RETURNING id'),{'name':name}).scalar_one()

class Fake:
    calls=0
    def embed_texts(self, texts):
        self.calls+=1
        return [[1.0]+[0.0]*1023 for _ in texts]

def service(e,f=None,**kwargs):
    return TextIndexService(e,Settings(_env_file=None,text_embed_batch_size=1,**kwargs),f or Fake())

def test_index_replay_uuid_and_update(engine):
    pid=insert(engine); f=Fake(); s=service(engine,f); req=TextIndexRequest(product_ids=[pid])
    assert s.index(req).indexed==1
    assert s.index(req).unchanged==1 and f.calls==1
    with engine.begin() as c:
        assert c.execute(text('SELECT id FROM product_embeddings')).scalar_one().version==7
        c.execute(text("UPDATE products SET name='new pen' WHERE id=:id"),{'id':pid})
    assert s.index(req).indexed==1

def test_failure_atomic_and_retry(engine):
    pid=insert(engine)
    class Bad(Fake):
        def embed_texts(self,texts): return [[1.0]*31]
    assert service(engine,Bad()).index(TextIndexRequest()).failed==1
    with engine.connect() as c: assert c.execute(text('SELECT count(*) FROM product_embeddings')).scalar_one()==0
    assert service(engine).index(TextIndexRequest()).indexed==1

def test_limit_and_previous_batch_survives(engine):
    insert(engine); insert(engine); insert(engine)
    class Partial(Fake):
        def embed_texts(self,texts):
            if self.calls==1:
                self.calls+=1
                raise RuntimeError('provider down')
            return super().embed_texts(texts)
    r=service(engine,Partial()).index(TextIndexRequest(limit=2))
    assert (r.indexed,r.failed,r.remaining)==(1,1,1)
    assert service(engine).index(TextIndexRequest()).indexed==2

def test_batch_rollback(engine):
    insert(engine); insert(engine)
    class BadBatch(Fake):
        def embed_texts(self,texts): return [[1.0]+[0.0]*1023,[1.0]*31]
    s=TextIndexService(engine,Settings(_env_file=None,text_embed_batch_size=2),BadBatch())
    assert s.index(TextIndexRequest()).failed==2
    with engine.connect() as c: assert c.execute(text('SELECT count(*) FROM product_embeddings')).scalar_one()==0

@pytest.mark.parametrize('delete',[False,True])
def test_changed_or_deleted(engine,delete):
    pid=insert(engine)
    class Change(Fake):
        def embed_texts(self,texts):
            with engine.begin() as c:
                c.execute(text('DELETE FROM products WHERE id=:id' if delete else "UPDATE products SET name='changed' WHERE id=:id"),{'id':pid})
            return super().embed_texts(texts)
    r=service(engine,Change()).index(TextIndexRequest())
    assert r.indexed==0 and r.remaining==1

def test_lock_and_missing_id(engine):
    with engine.connect() as c:
        c.execute(text('SELECT pg_advisory_lock(:k)'),{'k':LOCK_ID}); c.commit()
        with pytest.raises(ApiError) as err: service(engine).index(TextIndexRequest())
        assert err.value.status==409
        c.execute(text('SELECT pg_advisory_unlock(:k)'),{'k':LOCK_ID}); c.commit()
    with pytest.raises(ApiError): service(engine).validate(TextValidateRequest(product_ids=[uuid4()]))
    assert service(engine).index(TextIndexRequest()).examined==0

def test_api_guards_and_flag(engine):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.db.database import get_db
    from sqlalchemy.orm import Session
    from app.services.auth.service import AuthService
    from types import SimpleNamespace
    settings=Settings(_env_file=None,auth_jwt_secret='a'*40)
    app=create_app(settings)
    def db():
        with Session(engine) as s: yield s
    app.dependency_overrides[get_db]=db
    with TestClient(app) as c:
        assert c.post('/api/v1/admin/text-index/validate',json={}).status_code==401
        from unittest.mock import patch
        with patch.object(AuthService,'authenticate_user',return_value=SimpleNamespace(kind='user',role='user')):
            assert c.post('/api/v1/admin/text-index',headers={'Authorization':'Bearer test'},json={}).status_code==403
        with patch.object(AuthService,'authenticate_user',return_value=SimpleNamespace(kind='user',role='admin')):
            assert c.post('/api/v1/admin/text-index',headers={'Authorization':'Bearer test'},json={}).status_code==404
