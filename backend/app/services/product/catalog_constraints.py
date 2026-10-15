"""Literal catalog constraints, model identity and sale-unit comparisons."""
import re
from app.services.product.retrieval_policy import COLORS,normalized,contains_identifier

PEN_CATEGORIES={'ballpoint_pen','gel_pen','marker','whiteboard_marker','highlighter'}


def query_colors(query):
    q=normalized(query);ink=[];body=[];generic=[]
    for color in COLORS:
        c=normalized(color)
        if re.search(r'(?:หมึก|ink)\s*(?:สี)?\s*'+re.escape(c),q):ink.append(color)
        elif re.search(r'(?:ด้าม|ตัวด้าม|body)\s*(?:สี)?\s*'+re.escape(c),q):body.append(color)
        elif re.search(r'(?:สี\s*|ปากกา\s*)'+re.escape(c),q):generic.append(color)
    if ink and ('หรือ' in q or ' or ' in q):ink.extend(generic);generic=[]
    return tuple(ink),tuple(body),tuple(generic)


def product_colors(product):
    attrs=product.get('attributes') or {};name=normalized(product.get('name') or '')
    desc=normalized(product.get('description') or '')
    ink=set();body=set();generic=set()
    for color in COLORS:
        c=normalized(color)
        if normalized(str(attrs.get('ink_color',''))) in (c,'สี'+c):ink.add(color)
        if normalized(str(attrs.get('body_color',''))) in (c,'สี'+c):body.add(color)
        if re.search(r'หมึก\s*(?:สี)?\s*'+re.escape(c),name+' '+desc):ink.add(color)
        if re.search(r'ด้าม\s*(?:สี)?\s*'+re.escape(c),name):body.add(color)
        if 'สี'+c in name:generic.add(color)
        if normalized(str(attrs.get('color',''))) in (c,'สี'+c):generic.add(color)
    # A title color does not prove ink or body color. Keep unspecified colors
    # separate; never use URL/notes as color proof.
    return ink,body,generic


def color_matches(product,query):
    wanted_ink,wanted_body,wanted_generic=query_colors(query)
    ink,body,generic=product_colors(product)
    if wanted_ink and not ink.intersection(wanted_ink):return False
    if wanted_body and not body.intersection(wanted_body):return False
    if wanted_generic:
        known=(ink or (generic if not body else set())) if product.get('category') in PEN_CATEGORIES else generic
        if not known.intersection(wanted_generic):return False
    return True


def model_tokens(value):
    tokens=re.findall(r'\b[a-z]+[a-z0-9.-]*\d[a-z0-9.-]*\b',normalized(value))
    return tuple(t for t in tokens if not re.fullmatch(r'[ab]\d',t))


def same_family(first,other):
    if not first.get('brand') or normalized(first.get('brand',''))!=normalized(other.get('brand','')) or first.get('category')!=other.get('category'):return False
    a=(first.get('attributes') or {}).get('model_family');b=(other.get('attributes') or {}).get('model_family')
    if a and b:return normalized(str(a))==normalized(str(b))
    named=re.search(r'รุ่น\s+([a-z][a-z0-9_.-]*)',normalized(first.get('name','')))
    tokens=(named.group(1),) if named else model_tokens(first.get('name',''))
    return bool(tokens) and all(contains_identifier(token,normalized(other.get('name',''))) for token in tokens)


def sale_unit(product):
    attrs=product.get('attributes') or {}
    unit=str(attrs.get('price_selling_unit') or attrs.get('unit') or '')
    if 'ยังยืนยัน' in unit or 'ไม่ยืนยัน' in unit:return 'ambiguous',unit,None
    if unit in ('ด้าม','เล่ม','ชิ้น','แท่ง','ก้อน'):return 'single',unit,1
    name=product.get('name','')
    match=re.search(r'(?:แพ็ค|แพ็ก|กล่อง|โหล)\s*(\d+)|(\d+)\s*(?:ด้าม|ก้อน|แท่ง|ชิ้น)\s*/\s*(?:แพ็ค|แพ็ก|กล่อง)',unit+' '+name)
    qty=(attrs.get('pack_qty') or (next((x for x in match.groups() if x),None) if match else None))
    try:qty=int(qty) if qty else None
    except (ValueError,TypeError):qty=None
    if qty is not None and qty<1:qty=None
    if any(word in unit+' '+name for word in ('แพ็ค','แพ็ก','กล่อง','โหล')):
        return 'pack',unit or 'แพ็ค',qty
    return 'single','รายการ catalog (หน่วยขายไม่ได้ยืนยัน)',None
