import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine,text
from app.core.config import Settings
from app.schemas.text_retrieval import TextSearchRequest
from app.services.product.text_retrieval import fuse,TextRetrievalService
from app.services.product.text_index import TextIndexService
from app.schemas.admin import TextIndexRequest
from app.ai.embeddings.openrouter_embedding import EmbeddingError
from app.core.errors import ApiError

def test_fusion_overlap_and_stable_ties():
    a,b=uuid4(),uuid4()
    hits=fuse([{'id':a},{'id':b}],[{'id':b,'similarity':0.8}],5)
    assert hits[0]['row']['id']==b and hits[0]['keyword_rank']==2
    assert hits[0]['semantic_rank']==1
    assert len(hits)==2

@pytest.mark.parametrize('body',[{'query':' '},{'query':'x','limit':11},{'query':'x','image_id':str(uuid4())}])
def test_validation(body):
    with pytest.raises(ValueError):TextSearchRequest(**body)

class Fake:
    calls=0
    def embed_texts(self,texts):self.calls+=1;return [[1.0]+[0.0]*1023 for t in texts]

@pytest.fixture
def engine():
    url=os.getenv('TEXT_INDEX_TEST_URL')
    if not url:pytest.skip('disposable PostgreSQL required')
    from sqlalchemy.engine import make_url
    assert make_url(url).database.startswith('ink_buddy_test'), 'Refuse application DB'
    e=create_engine(url)
    with e.begin() as c:
        c.execute(text('TRUNCATE products CASCADE'))
        for name,price,category in [('Pilot pen',80,'gel_pen'),('Unknown price pen',None,'gel_pen'),('Notebook',20,'notebook')]:
            c.execute(text("INSERT INTO products(name,price,currency,category,brand) VALUES(:n,:p,'THB',:cat,'Pilot')"),{'n':name,'p':price,'cat':category})
    yield e
    e.dispose()

def setup_search(e):
    s=Settings(_env_file=None);f=Fake()
    TextIndexService(e,s,f).index(TextIndexRequest(limit=100))
    return TextRetrievalService(e,s,f),f

def test_budget_category_and_no_write(engine):
    service,f=setup_search(engine)
    r=service.search(TextSearchRequest(query='ปากกาเจล ไม่เกิน 100 บาท'))
    assert len(r.items)==1 and r.items[0].product.price==80
    assert r.index_status=='ready'
    assert f.calls==2
    with engine.connect() as c:assert c.execute(text('SELECT count(*) FROM chat_messages')).scalar_one()==0

def test_price_intent_filters_both_retrieval_channels(engine):
    service,_=setup_search(engine)
    r=service.search(TextSearchRequest(query='ปากกาเจลราคาเท่าไร'),requires_price=True)
    assert len(r.items)==1 and r.items[0].product.price==80

def test_stale_and_low_similarity(engine):
    service,_=setup_search(engine)
    with engine.begin() as c:c.execute(text("UPDATE products SET description='new details' WHERE name='Pilot pen'"))
    r=service.search(TextSearchRequest(query='สินค้าจดบันทึก',category='gel_pen'))
    assert r.stale_skipped==1 and r.index_status=='partial'
    service.settings.text_search_min_similarity=1
    with engine.begin() as c:c.execute(text("UPDATE product_embeddings SET embedding=CAST(:v AS vector)"),{'v':'['+','.join(['0','1']+['0']*1022)+']'})
    r=service.search(TextSearchRequest(query='xyzunmatched'))
    assert r.items==[]

def test_clarification_and_missing_index(engine):
    s=Settings(_env_file=None);f=Fake();service=TextRetrievalService(engine,s,f)
    r=service.search(TextSearchRequest(query='ปากกา งบจำกัด'))
    assert r.clarification and f.calls==0
    r=service.search(TextSearchRequest(query='Pilot'))
    assert r.index_status=='missing' and r.items and f.calls==0
    with pytest.raises(ApiError):service.search(TextSearchRequest(query='x',category='invalid'))

def test_provider_failure(engine):
    service,_=setup_search(engine)
    class Bad:
        def embed_texts(self,t):raise EmbeddingError('private detail')
    service.embedder=Bad()
    with pytest.raises(ApiError) as err:service.search(TextSearchRequest(query='Pilot'))
    assert err.value.status==503

def test_upstream_policy_rejection(engine):
    service,_=setup_search(engine)
    class Blocked:
        def embed_texts(self,t):raise EmbeddingError('policy rejected',403)
    service.embedder=Blocked()
    with pytest.raises(ApiError) as err:service.search(TextSearchRequest(query='Pilot'))
    assert err.value.status==403 and err.value.code=='OPENROUTER_POLICY_REJECTED'

def test_outside_no_paid_call_and_unknown_model(engine):
    service,f=setup_search(engine);before=f.calls
    r=service.search(TextSearchRequest(query='คอมพิวเตอร์เล่นเกม',category='notebook'))
    assert r.guardrail_status=='blocked' and r.items==[] and f.calls==before
    r=service.search(TextSearchRequest(query='มีสีอื่นไหม'))
    assert r.guardrail_status=='needs_clarification' and f.calls==before
    r=service.search(TextSearchRequest(query='ปากกา BL999'))
    assert r.guardrail_status=='no_match' and r.items==[]

def test_api_credentials_guest_and_flag(engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from app.main import create_app
    from app.db.database import get_db
    from app.api.v1.product.search import get_text_retrieval
    from app.core.config import get_settings
    from app.core.rate_limit import limiter
    s=Settings(_env_file=None,auth_jwt_secret='test-secret-for-retrieval-integration-12345',text_search_enabled=True)
    app=create_app(s)
    def db():
        with Session(engine) as session:yield session
    service,_=setup_search(engine)
    app.dependency_overrides[get_db]=db
    app.dependency_overrides[get_text_retrieval]=lambda: service
    limiter.reset()
    headers={'Origin':'http://localhost:3000'}
    with TestClient(app) as c:
        assert c.post('/api/v1/product-search/by-text',json={'query':'Pilot'}).status_code==401
        assert c.post('/api/v1/auth/guest-sessions',headers=headers).status_code==201
        assert c.post('/api/v1/product-search/by-text',json={'query':'Pilot'}).status_code==403
        r=c.post('/api/v1/product-search/by-text',headers=headers,json={'query':'Pilot'})
        assert r.status_code==200 and r.json()['items']
        assert c.post('/api/v1/product-search/by-text',headers={**headers,'Authorization':'Bearer invalid'},json={'query':'Pilot'}).status_code==401
        assert c.post('/api/v1/product-search/by-text',headers=headers,json={'query':' '}).status_code==422
        for _ in range(21):r=c.post('/api/v1/product-search/by-text',headers=headers,json={'query':'Pilot'})
        assert r.status_code==429
        limiter.reset()
        app.dependency_overrides.pop(get_text_retrieval)
        s.text_search_enabled=False
        assert c.post('/api/v1/product-search/by-text',headers=headers,json={'query':'Pilot'}).status_code==404
