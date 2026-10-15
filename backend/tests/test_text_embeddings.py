import httpx
import pytest
from app.core.config import Settings
from app.ai.embeddings.openrouter_embedding import OpenRouterTextEmbedder, EmbeddingError

def client(payload, status=200):
    settings = Settings(_env_file=None, openrouter_api_key='test-key', text_embed_dim=32)
    return OpenRouterTextEmbedder(settings, httpx.MockTransport(lambda request: httpx.Response(status, json=payload)))

def test_order_and_normalization():
    c=client({'data':[{'index':1,'embedding':[2.0]*32},{'index':0,'embedding':[1.0]+[0.0]*31}]})
    result=c.embed_texts(['pen','notebook'])
    assert result[0][0]==1
    assert sum(v*v for v in result[1]) == pytest.approx(1)
    c.close()

@pytest.mark.parametrize('payload', [ {'data':[]}, {'data':[{'index':0,'embedding':[0.0]*32}]}, {'data':[{'index':0,'embedding':[1.0]*31}]}, {'data':[{'index':1,'embedding':[1.0]*32}]}])
def test_invalid_response(payload):
    c=client(payload)
    with pytest.raises(EmbeddingError): c.embed_texts(['pen'])
    c.close()

def test_credit_error_is_safe():
    c=client({'error':{'message':'private provider detail'}},402)
    with pytest.raises(EmbeddingError, match='HTTP 402'): c.embed_texts(['pen'])
    c.close()
