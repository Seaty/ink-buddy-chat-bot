from sqlalchemy import create_engine,text
from app.core.config import Settings
from app.schemas.admin import TextValidateRequest,TextIndexRequest
from app.services.product.text_index import TextIndexService
from app.ai.embeddings.openrouter_embedding import OpenRouterTextEmbedder
s=Settings()
e=create_engine("postgresql+psycopg://postgres:test_index_only@127.0.0.1:55439/ink_buddy_test")
with e.begin() as c:
 pid=c.execute(text("INSERT INTO products(name,category,brand) VALUES('Pilot gel pen','gel_pen','Pilot') RETURNING id")).scalar_one()
class Count:
 calls=0
 def __init__(self): self.client=OpenRouterTextEmbedder(s)
 def embed_texts(self,texts):
  self.calls+=1
  return self.client.embed_texts(texts)
f=Count()
try:
 service=TextIndexService(e,s,f)
 print('Validate:',service.validate(TextValidateRequest(product_ids=[pid])).valid)
 first=service.index(TextIndexRequest(product_ids=[pid],limit=1)); print('Indexed:',first.indexed,'Failed:',first.failed)
 second=service.index(TextIndexRequest(product_ids=[pid],limit=1)); print('Replay unchanged:',second.unchanged,'Provider calls:',f.calls)
 with e.connect() as c: print('Stored dimensions:',c.execute(text('SELECT vector_dims(embedding) FROM product_embeddings WHERE product_id=:id'),{'id':pid}).scalar_one())
 assert first.indexed==1 and second.unchanged==1 and f.calls==1
finally:
 f.client.close(); e.dispose()
