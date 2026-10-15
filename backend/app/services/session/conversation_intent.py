"""Resolve bounded conversation references into catalog conditions; no free-text LLM rewrite."""
import re
from dataclasses import dataclass,field
from uuid import UUID
from app.services.product.retrieval_policy import scope,normalized,matched_brands,UNSAFE_PATTERNS,BRAND_ALIASES
from app.services.product.catalog_constraints import query_colors,model_tokens,product_colors,PEN_CATEGORIES
from app.services.product.text_search import budget
from app.ai.rag.indexing_service import CATEGORY_TH

NUMBERS={'หนึ่ง':1,'สอง':2,'สาม':3,'สี่':4,'ห้า':5,'หก':6,'เจ็ด':7,'แปด':8,'เก้า':9,'สิบ':10}

@dataclass
class ConversationIntent:
    query:str
    limit:int=5
    requires_price:bool=False
    order:str|None=None
    allowed_ids:tuple|None=None
    categories:tuple=()
    brands:tuple=()
    variants:bool=False
    variant_color:str|None=None
    variant_only:bool=False
    clarification:str|None=None
    note:str=''


def number(value):return int(value) if value.isdigit() else NUMBERS[value]


def reference_topic(refs,catalog):
    ids={str(r['id']) for r in refs};products=[p for p in catalog if str(p['id']) in ids]
    if not products:return ''
    categories={p['category'] for p in products}
    query='ปากกา' if categories<=PEN_CATEGORIES else ' '.join(CATEGORY_TH.get(c,c) for c in categories)
    inks=[product_colors(p)[0] for p in products]
    common=set.intersection(*inks) if inks else set()
    if len(common)==1:query+=' หมึกสี'+next(iter(common))
    elif categories<=PEN_CATEGORIES:
        colors=[product_colors(p)[0] or (product_colors(p)[2] if not product_colors(p)[1] else set()) for p in products]
        common=set.intersection(*colors) if colors else set()
        if len(common)==1:query+=' สี'+next(iter(common))
    brands={p.get('brand') for p in products}
    if len(brands)==1 and next(iter(brands)):query+=' '+next(iter(brands))
    return query


def resolve_intent(question,history,catalog):
    q=normalized(question);names=[p['name'] for p in catalog];brands=[p.get('brand') for p in catalog]
    decision=scope(q,None,brands,names)
    plan=ConversationIntent(query=question)
    if decision.reason in ('UNSAFE_QUERY','OUT_OF_SCOPE','MIXED_SCOPE'):
        plan.clarification=decision.message;return plan
    count=re.search(r'(\d+|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)\s*(?:รุ่น|รายการ|ตัวเลือก)',q)
    if count:
        plan.limit=number(count.group(1))
        if not 1<=plan.limit<=5:
            plan.clarification='กรุณาขอครั้งละ 1–5 รายการ เพื่อให้ตรวจหลักฐานได้ครบ';return plan
    plan.order='asc' if re.search(r'ถูกที่สุด|ถูกสุด|ราคาถูก|ต่ำที่สุด|ต่ำสุด|ถูกไปแพง',q) else 'desc' if re.search(r'แพงที่สุด|แพงสุด|สูงที่สุด|แพงไปถูก',q) else None
    plan.requires_price=bool(plan.order or re.search(r'ราคา|งบ|บาท|เท่าไหร่|เท่าไร',q))
    if re.search(r'เรียงราคา',q) and plan.order is None:plan.order='asc'
    plan.variants=bool(re.search(r'สีอื่น|สี(?:แดง|ดำ|น้ำเงิน|เขียว|ม่วง|ชมพู|ฟ้า|เหลือง).*ไหม',q))
    plan.variant_only=plan.variants and not count and not plan.order and not decision.categories and not model_tokens(q) and not matched_brands(brands,q)
    _,body,generic=query_colors(q);ink,_,_=query_colors(q)
    if plan.variants and 'สีอื่น' not in q:
        plan.variant_color=next(iter((*ink,*body,*generic)),None)
    latest_assistant=next((r for r in reversed(history) if r.get('role')=='assistant'),None)
    refs=(latest_assistant or {}).get('product_refs') or []
    refs=[r for r in refs if isinstance(r,dict) and r.get('id')]
    explicit_all=bool(re.search(r'ทั้งหมด.*catalog|ทั้ง.*แคตตาล็อก|ทั้งหมดในร้าน|ใน catalog ทั้งหมด',q))
    ordinal=re.search(r'(?:ตัว|รุ่น|รายการ)ที่\s*(\d+|หนึ่ง|สอง|สาม|สี่|ห้า)',q)
    pronoun=bool(re.search(r'รุ่นนั้น|รุ่นนี้|ตัวนั้น|ตัวนี้|อันแรก|อันนี้',q))
    if 'อันแรก' in q:ordinal=re.search(r'(1)', '1')
    if ordinal or pronoun or plan.variant_only:
        if not refs or (not ordinal and len(refs)!=1):
            plan.clarification='กรุณาระบุชื่อรุ่นหรือลำดับสินค้า เช่น ตัวที่สอง เพื่อยืนยันว่าหมายถึงสินค้าใด';return plan
        index=number(ordinal.group(1))-1 if ordinal else 0
        if not 0<=index<len(refs):
            plan.clarification='ไม่มีสินค้าลำดับนั้นในคำตอบล่าสุด กรุณาระบุชื่อรุ่น';return plan
        try:plan.allowed_ids=(UUID(str(refs[index]['id'])),)
        except (ValueError,TypeError):plan.clarification='กรุณาระบุชื่อรุ่นสินค้าอีกครั้ง';return plan
        plan.limit=1;plan.note='อ้างอิงสินค้าลำดับที่ '+str(index+1)+' ในคำตอบล่าสุด'
        product=next((p for p in catalog if p['id'] in plan.allowed_ids),None)
        if not product:plan.clarification='ไม่พบสินค้าที่อ้างใน catalog ปัจจุบัน';return plan
        plan.query=product['name'] if plan.variant_only else product['name']+' '+question
        plan.categories=(product['category'],);plan.brands=(product.get('brand'),) if product.get('brand') else ()
        return plan
    current_has_topic=bool(decision.categories or matched_brands(brands,q) or model_tokens(q))
    base=question
    if not current_has_topic or (history and not decision.categories and not model_tokens(q) and matched_brands(brands,q)):
        safe_users=[r['content'] for r in history if r.get('role')=='user' and isinstance(r.get('content'),str) and len(r['content'])<=4000
                    and not any(re.search(pattern,normalized(r['content'])) for pattern in UNSAFE_PATTERNS)]
        # Only the latest user turn can supply context. If it is a follow-up,
        # infer topic from latest displayed product names, not another chat.
        prior=safe_users[-1] if safe_users else ''
        pd=scope(prior,None,brands,names)
        if not pd.categories and refs:prior=reference_topic(refs,catalog)
        pd=scope(prior,None,brands,names)
        if not pd.categories:
            plan.clarification=decision.message or 'กรุณาระบุประเภทสินค้าก่อน';return plan
        # Strip old budget/order before applying new user constraints.
        prior=re.sub(r'(?:ไม่เกิน|งบ)?\s*\d+(?:\.\d+)?\s*(?:[-–]\s*\d+(?:\.\d+)?)?\s*บาท','',prior)
        prior=re.sub(r'ถูกที่สุด|ถูกสุด|ราคาถูก|ต่ำที่สุด|ต่ำสุด|ถูกไปแพง|แพงที่สุด|แพงสุด|สูงที่สุด|แพงไปถูก','',prior)
        if re.search(r'ต่อ(?:แพ็ค|แพ็ก|กล่อง|ด้าม|เล่ม|ชิ้น|แท่ง|ก้อน)',q):
            prior=re.sub(r'ต่อ(?:แพ็ค|แพ็ก|กล่อง|ด้าม|เล่ม|ชิ้น|แท่ง|ก้อน)','',prior)
        if matched_brands(brands,q):
            for brand in matched_brands(brands,prior):
                aliases=BRAND_ALIASES.get(re.sub(r'[^a-z0-9]','',normalized(brand)),())
                for name in (brand,*aliases):prior=re.sub(re.escape(name),'',prior,flags=re.I)
        new_ink,new_body,new_generic=query_colors(q)
        if new_ink or new_body or new_generic:
            from app.services.product.retrieval_policy import COLORS
            def replace_color(match):
                prefix=match.group(1) or ''
                if prefix=='ด้าม' and not new_body:return match.group(0)
                if prefix!='ด้าม' and not (new_ink or new_generic):return match.group(0)
                return prefix
            prior=re.sub(r'(หมึก|ด้าม)?\s*(?:สี)?\s*('+'|'.join(COLORS)+')',replace_color,prior)
        base=prior+' '+question
        if refs and not explicit_all and plan.order:
            try:plan.allowed_ids=tuple(UUID(str(r['id'])) for r in refs)
            except (ValueError,TypeError):plan.clarification='กรุณาระบุสินค้าอีกครั้ง';return plan
            plan.note='จัดอันดับเฉพาะรายการจากคำตอบล่าสุด'
        else:plan.note='ใช้ประเภทสินค้าจากคำถามก่อนหน้าในแชตนี้'
    elif re.search(r'จากที่แนะนำ|เมื่อกี้|รายการเดิม',q) and refs and not explicit_all:
        plan.allowed_ids=tuple(UUID(str(r['id'])) for r in refs);plan.note='ใช้รายการจากคำตอบล่าสุด'
    if plan.variants:
        # Keep alternative-color clauses out of the primary recommendation filter.
        base=re.split(r'\s*(?:และ|แล้ว)?\s*(?:มีสีอื่น|มีสี(?:แดง|ดำ|ม่วง|เขียว).*ไหม)',base,maxsplit=1)[0]
    plan.query=base.strip()
    if len(plan.query)>4000:
        plan.clarification='คำถามรวมบริบทยาวเกินไป กรุณาระบุประเภทและเงื่อนไขสินค้าใหม่ให้กระชับ';return plan
    resolved=scope(plan.query,None,brands,names)
    plan.categories=tuple(resolved.categories);plan.brands=tuple(matched_brands(brands,plan.query))
    if resolved.status!='allowed':plan.clarification=resolved.message
    return plan
