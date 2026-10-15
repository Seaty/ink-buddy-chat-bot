"""Build a reviewed text catalog manifest without changing the Vision CSV."""
import csv
import json
import sys
from pathlib import Path
from decimal import Decimal
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.ai.rag.indexing_service import load_catalog

OUT = ROOT / 'backend/datasets/reviewed_catalog.json'

def read(folder):
    return list(csv.DictReader((ROOT/'backend/datasets'/folder/'products.csv').open(encoding='utf-8-sig')))

def prepare():
    products,report=load_catalog(ROOT/'backend/datasets/catalog',strict=True)
    rows=[]; held=[]
    for p in products:
        if not p.is_active: continue
        ambiguous=p.sku=='b2s_1091933'
        rows.append(dict(sku=p.sku,name=p.name,category=p.category,brand=p.brand_norm,
            description=None,price=None if ambiguous else str(p.price_thb),currency='THB',source_ref=p.source_url,
            attributes={'category_th':p.category_th,'source_price':str(p.price_thb),'price_date':str(p.price_date),'source_image_url':p.image_url,
                'catalog_note':p.notes,'rights_status':'not_verified','price_review':'unit_ambiguous' if ambiguous else 'original_catalog_snapshot'},
            images=['catalog/'+p.filename]))
    for folder in ('officework_candidates','officemate_candidates'):
        for r in read(folder):
            if folder=='officemate_candidates' and r['sku']=='Y013221':
                held.append({'sku':r['sku'],'reason':'Unclear sales unit and generic marketing description'});continue
            officework=folder=='officework_candidates'
            category=r['category'] if officework else ('gel_pen' if r['sku']=='YA32995' else 'notebook')
            brand=('Pentel' if category=='gel_pen' else 'Elephant' if category=='notebook' else 'STABILO') if officework else r['brand']
            images=[folder+'/'+p for p in (r['local_images'] if officework else r['local_image']).split('|') if p]
            if not images: raise ValueError('Missing image: '+r['sku'])
            for path in images:
                with Image.open(ROOT/'backend/datasets'/path) as im: im.verify()
            attrs={'source_price':r['price_thb'] if officework else r['price'],
                   'price_date':r['checked_date'],'tax_status':r['tax_note'] if officework else 'not_verified',
                   'unit':r['unit'] if officework else ('แพ็ค' if category=='gel_pen' else 'เล่ม'),
                   'rights_status':'not_verified','source_image_url':r['image_urls'] if officework else r['image_url']}
            # Preserve the source amount, but exclude uncertain tax/unit prices from budget search.
            # Product-specific OfficeMate features are taken from the title, not SEO marketing copy.
            description=r['description'] if officework else r['name']
            rows.append(dict(sku=r['sku'] if officework else 'officemate_'+r['sku'],name=r['name'],
                category=category,brand=brand,description=description,price=None,currency='THB',
                source_ref=r['source_url'],attributes=attrs,images=images))
    if len({r['sku'] for r in rows})!=len(rows): raise ValueError('Duplicate SKU')
    # Exact title duplicates are held; distinct model/color variants remain separate.
    seen=set(); approved=[]
    for r in rows:
        key=''.join(r['name'].lower().split())
        if key in seen: held.append({'sku':r['sku'],'reason':'Exact normalized name duplicate'});continue
        seen.add(key);approved.append(r)
    payload={'products':approved,'held':held,'review_notes':[
        'Model/color/size compared manually with original 50 names; no exact overlapping variants found.',
        'SKU is namespaced by retailer; cross-retailer product matching still needs future canonical IDs.',
        'New prices retained in attributes only until tax basis/units are verified; availability not imported.',
        'Image rights are unverified; collected for local project review only.']}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Reviewed products:',len(approved),'held:',len(held))

if __name__=='__main__': prepare()
