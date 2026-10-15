"""Catalog-specific scope and relevance rules; OpenRouter owns upstream security policy."""
import re
import unicodedata
from dataclasses import dataclass
from app.ai.rag.indexing_service import CATEGORY_TH
from app.services.product.text_index import source_for

POLICY_VERSION='catalog-scope-v1'
ALIASES={
    'gel_pen':('ปากกาเจล','gel pen'),
    'notebook':('สมุด','notebook'),
    'highlighter':('ไฮไลต์','ไฮไลท์','เน้นข้อความ','highlighter'),
    'mechanical_pencil':('ดินสอกด','mechanical pencil'),
    'eraser':('ยางลบ','eraser'),
    'correction_tape':('เทปลบคำผิด','correction tape'),
    'colored_pencil':('สีไม้','ดินสอสี','colored pencil'),
}
OUTSIDE=('คอมพิวเตอร์','โน้ตบุ๊ก','โน๊ตบุ๊ค','การ์ดจอ','เล่นเกม','โทรศัพท์','มือถือ','รักษาโรค','วินิจฉัยโรค','laptop','gaming computer','smartphone')
COLORS=('น้ำเงิน','แดง','ดำ','เขียว','เหลือง','ม่วง','ชมพู','ส้ม','ฟ้า','เทา','ขาว','น้ำตาล','ใส','ทอง','เงิน')
BRAND_ALIASES={'pentel':('เพนเทล',),'plus':('พลัส',),'elephant':('ตราช้าง',),
               'stabilo':('สตาบิโล',),'elmers':('เอลเมอร์','elmer')}
UNSAFE_PATTERNS=(r'ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions',
                 r'(?:reveal|print|show)\s+(?:your\s+|the\s+)?system\s+prompt',
                 r'ไม่ต้องทำตามคำสั่ง(?:ก่อนหน้า|เดิม)',r'เปิดเผย(?:คำสั่งระบบ|system prompt)')

def normalized(value):
    value=unicodedata.normalize('NFKC',value).replace('นํ้า','น้ำ')
    return ''.join(c for c in value.lower() if unicodedata.category(c)!='Cf')

def contains_identifier(identifier,evidence):
    return bool(re.search(r'(?<![a-z0-9])'+re.escape(normalized(identifier))+r'(?![a-z0-9])',evidence))

def matched_brands(brands,query):
    q=normalized(query);out=[]
    for brand in brands:
        if not brand:continue
        key=re.sub(r'[^a-z0-9]','',normalized(brand))
        aliases=BRAND_ALIASES.get(key,())
        if contains_identifier(brand,q) or any(contains_identifier(a,q) for a in aliases):out.append(brand)
    return out

@dataclass
class ScopeDecision:
    status: str
    reason: str
    message: str | None
    categories: list[str]

def scope(query,category,brands,names):
    q=normalized(query)
    if any(re.search(normalized(pattern),q) for pattern in UNSAFE_PATTERNS):
        return ScopeDecision('blocked','UNSAFE_QUERY','กรุณาถามเกี่ยวกับสินค้าโดยไม่ใส่คำสั่งเปลี่ยนกติกาของระบบ',[])
    categories=[k for k,v in CATEGORY_TH.items() if normalized(v) in q or k.replace('_',' ') in q]
    for key,aliases in ALIASES.items():
        if any(a in q for a in aliases) and key not in categories:categories.append(key)
    if not categories and ('ปากกา' in q or re.search(r'\bpen\b',q)):
        categories=['ballpoint_pen','gel_pen','marker','whiteboard_marker']
    anchor=bool(categories or 'เครื่องเขียน' in q or 'stationery' in q or matched_brands(brands,q))
    models=re.findall(r'\b[a-z]+[a-z0-9.-]*\d[a-z0-9.-]*\b',q)
    known_model=any(contains_identifier(model,normalized(name)) for model in models for name in names)
    if any(term in q for term in OUTSIDE):
        if anchor or known_model:
            return ScopeDecision('needs_clarification','MIXED_SCOPE','กรุณาระบุคำถามเฉพาะเครื่องเขียนหรือสินค้าที่ต้องการค้นหา',[])
        return ScopeDecision('blocked','OUT_OF_SCOPE','ระบบนี้ค้นหาเฉพาะสินค้าเครื่องเขียนใน catalog',[])
    if category:categories=[category]
    if not anchor and not known_model and not category:
        return ScopeDecision('needs_clarification','INSUFFICIENT_CONTEXT','กรุณาระบุประเภท ยี่ห้อ หรือรุ่นเครื่องเขียน เช่น ปากกาเจล หรือสมุด หากถามต่อถึงสินค้าก่อนหน้า กรุณาระบุชื่อสินค้าอีกครั้ง',[])
    return ScopeDecision('allowed','CATALOG_SCOPE',None,categories)

def relevant(row,query):
    """Require explicit color/model evidence; similarity alone cannot satisfy these constraints."""
    q=normalized(query)
    evidence=normalized(source_for(row))
    from app.services.product.catalog_constraints import color_matches
    if not color_matches(row,query):return False
    # Explicit attributes need evidence; do not infer physical properties from similarity.
    for trait in ('เหล็ก','พลาสติก','ระบายน้ำ'):
        if normalized(trait) in q and normalized(trait) not in evidence:return False
    models=re.findall(r'\b[a-z]+[a-z0-9.-]*\d[a-z0-9.-]*\b',q)
    return all(contains_identifier(model,evidence) for model in models)
