"""Use the existing Vision pipeline; only catalog facts may enter chat history."""
import time
from sqlalchemy import text,bindparam
from sqlalchemy.orm import Session
from app.core.errors import ApiError
from app.repositories.image_repository import ImageUploadRepository
from app.services.session.service import ChatSessionService
from app.services.session.adapter import AnswerOutput
from app.services.session.catalog_answer import display_price
from app.services.session.conversation_rag import reference_fields
from app.services.product.retrieval_policy import UNSAFE_PATTERNS,normalized
import re


def respond_to_image(engine,settings,principal,image_id,prompt,deadline,service=None):
    if any(re.search(pattern,normalized(prompt)) for pattern in UNSAFE_PATTERNS):
        return [],AnswerOutput('ถามเกี่ยวกับเครื่องเขียนในรูปได้เลยครับ โดยไม่ใส่คำสั่งเปลี่ยนกติกาของระบบ',(),'catalog_policy')
    if service is None:
        if settings.image_retriever!='pgvector':raise ApiError(503,'IMAGE_SEARCH_NOT_CONFIGURED','configure the real image index before using vision chat')
        from app.services.vision_service import get_vision_service
        service=get_vision_service()
    # Snapshot the image in a short transaction, then release ownership locks.
    with Session(engine) as db:
        ChatSessionService(db).authorize(principal)
        upload=ImageUploadRepository(db).get_owned(image_id,principal)
        if upload is None or upload.status!='ready':raise ApiError(404,'IMAGE_NOT_FOUND','image not found')
        try:image=service.storage.open(upload.storage_key)
        except FileNotFoundError:raise ApiError(404,'IMAGE_NOT_FOUND','image not found') from None
        db.commit()
    from app.services.vision_service import _vision_errors
    try:
        pipeline=service.pipeline
        if time.monotonic()>=deadline:raise ApiError(504,'ANSWER_TIMEOUT','image model initialization timed out')
        with _vision_errors():result=pipeline.run(image,prompt,limit=5,with_answer=False)
    finally:image.close()
    if time.monotonic()>=deadline:raise ApiError(504,'ANSWER_TIMEOUT','vision answer timed out')
    if result.analysis is not None and not result.analysis.is_stationery:
        return [],AnswerOutput('รูปนี้ยังไม่เห็นสินค้าเครื่องเขียนชัดเจนครับ ลองแนบรูปเครื่องเขียนที่ต้องการหาอีกครั้ง',(),'vision_catalog')
    from app.ai.prompts.vision_prompt import MatchLevel
    is_suggestion=result.match_level==MatchLevel.NONE
    items=result.suggestions if is_suggestion else result.products
    threshold=settings.image_tau_suggest if is_suggestion else settings.image_tau_similar
    items=[p for p in items if isinstance(p.get('score'),(int,float)) and p['score']>=threshold][:5]
    skus=list(dict.fromkeys(p['sku'] for p in items))
    with Session(engine) as db:
        statement=text('SELECT * FROM products WHERE sku IN :skus').bindparams(bindparam('skus',expanding=True))
        catalog={row['sku']:dict(row) for row in db.execute(statement,{'skus':skus}).mappings()} if skus else {}
    products=[]
    for p in items:
        row=catalog.get(p['sku'])
        if row is None or any(row['id']==r['id'] for r in products):continue
        exact=result.match_level==MatchLevel.EXACT and result.products and p['sku']==result.products[0]['sku']
        products.append({**row,**reference_fields(row),'match_method':'image_embedding','match_type':'suggestion' if is_suggestion else 'exact' if exact else 'similar','match_score':max(0,min(1,float(p['score'])))})
    if not products:content='ยังไม่เจอสินค้าที่ใกล้เคียงกับรูปนี้ครับ ลองถ่ายให้เห็นตัวสินค้าและชื่อรุ่นชัดขึ้นอีกนิดได้ไหมครับ'
    else:
        content=('พบรุ่นที่ตรงกับข้อมูลบนสินค้าในรูปครับ' if products[0]['match_type']=='exact' else
                 'ยังยืนยันรุ่นในรูปไม่ได้ครับ ลองดูตัวเลือกเหล่านี้ว่าใช่แบบที่กำลังหาหรือเปล่า' if is_suggestion else
                 'เจอสินค้าที่คล้ายกับในรูปครับ ลองดูว่าเป็นรุ่นที่ต้องการไหม')
        content+='\n'+'\n'.join('• '+p['name']+' — '+display_price(p) for p in products)
        if any(word in prompt for word in ('พร้อมส่ง','สต็อก','มีของ')):content+='\nส่วนของพร้อมส่ง ยังยืนยันให้ไม่ได้ครับ'
    return products,AnswerOutput(content,tuple(p['id'] for p in products),'vision_catalog')
