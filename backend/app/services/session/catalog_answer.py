"""Bounded catalog quotes and deterministic reasons; never generate new product claims."""
import re
from decimal import Decimal
from app.services.product.retrieval_policy import normalized
from app.services.product.text_search import budget


def description_quotes(value):
    """Return complete, short source spans; omit long spans instead of cutting a claim."""
    spans=re.split(r'\n+|[;；,]|(?<=[.!?])\s+|\s+เพิ่มเติม\s*:',value)
    result=[]
    for span in spans:
        span=span.strip()
        if span and len(span)<=180 and span not in result:
            result.append(span)
        if len(result)==6:break
    return result


def display_price(product):
    if product.get('price') is None:return 'ยังไม่มีราคาครับ'
    amount=format(Decimal(str(product['price'])),',.2f').rstrip('0').rstrip('.')
    currency='บาท' if product.get('currency')=='THB' else product.get('currency') or ''
    unit=(product.get('attributes') or {}).get('price_selling_unit') or (product.get('attributes') or {}).get('unit')
    suffix=' / '+unit if unit in ('ด้าม','เล่ม','ชิ้น','แท่ง','ก้อน') else ''
    return amount+' '+currency+suffix


def product_lines(question,product,evidence,selected_ids):
    # Render only grounded facts, using conversational Thai rather than exposing
    # evidence labels, model decisions or repetitive technical disclaimers.
    q=normalized(question)
    title=product['name'];brand=product.get('brand')
    if brand and normalized(brand) not in normalized(title):title+=' ('+brand+')'
    lines=[title+' — '+display_price(product)]
    limits,clarification=budget(question)
    if limits and not clarification and product.get('price') is not None and product.get('currency')=='THB' and limits[0]<=product['price']<=limits[1]:
        lines.append('อยู่ในงบที่ตั้งไว้ครับ')
    if re.search(r'คุณสมบัติ|รายละเอียด|ต่างกัน|เหมาะ|ทำไม|แนะนำ',q):
        for eid in selected_ids:
            if '_description_' in eid:
                quote=evidence[eid].removeprefix('รายละเอียดตามแหล่งสินค้า: ').strip()
                if len(quote)<=120:lines.append('ร้านระบุว่า '+quote)
                break
    return lines
