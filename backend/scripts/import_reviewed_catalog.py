"""Explicit local catalog import; uses backend DATABASE_URL, no embeddings API calls."""
import json
from pathlib import Path
from sqlalchemy import create_engine,text
from app.core.config import Settings

def main():
    data=json.loads((Path(__file__).resolve().parents[1]/'datasets/reviewed_catalog.json').read_text(encoding='utf-8'))
    engine=create_engine(Settings().database_url,connect_args={'connect_timeout':10})
    with engine.begin() as c:
        for r in data['products']:
            pid=c.execute(text('''INSERT INTO products(sku,name,category,brand,description,attributes,price,currency,source_ref)
                VALUES(:sku,:name,:category,:brand,:description,CAST(:attributes AS jsonb),:price,:currency,:source_ref)
                ON CONFLICT(sku) WHERE sku IS NOT NULL DO UPDATE SET name=EXCLUDED.name,category=EXCLUDED.category,
                brand=EXCLUDED.brand,description=EXCLUDED.description,attributes=products.attributes || EXCLUDED.attributes,
                price=EXCLUDED.price,currency=EXCLUDED.currency,source_ref=EXCLUDED.source_ref,updated_at=now() RETURNING id'''),
                {**{k:r[k] for k in ('sku','name','category','brand','description','price','currency','source_ref')},'attributes':json.dumps(r['attributes'],ensure_ascii=False)}).scalar_one()
            c.execute(text('UPDATE product_images SET is_primary=false WHERE product_id=:id'),{'id':pid})
            for i,path in enumerate(r['images']):
                c.execute(text('''INSERT INTO product_images(product_id,storage_key,is_primary,alt_text) VALUES(:id,:path,:primary,:name)
                    ON CONFLICT(storage_key) DO UPDATE SET product_id=EXCLUDED.product_id,is_primary=EXCLUDED.is_primary,alt_text=EXCLUDED.alt_text'''),
                    {'id':pid,'path':path,'primary':i==0,'name':r['name']})
        print('Imported manifest products:',len(data['products']))
    engine.dispose()

if __name__=='__main__': main()
