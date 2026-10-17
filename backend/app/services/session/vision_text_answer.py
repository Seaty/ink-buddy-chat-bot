"""Hosted Vision reads the image; existing Text RAG retrieves real DB products.

This is NOT image-vector similarity and never establishes an exact visual match.
"""
import re,time
from loguru import logger
from sqlalchemy.orm import Session
from app.ai.llm.qwen_vision import QwenVision,VisionModelError
from app.ai.llm.openrouter_client import OpenRouterClient,OpenRouterError
from app.ai.rag.indexing_service import CATEGORY_TH
from app.core.errors import ApiError
from app.repositories.image_repository import ImageUploadRepository
from app.services.image_storage import ImageStorage
from app.services.session.service import ChatSessionService
from app.services.session.adapter import AnswerOutput
from app.services.session.catalog_answer import display_price
from app.services.session.conversation_rag import reference_fields
from app.services.product.text_retrieval import TextRetrievalService
from app.services.product.retrieval_policy import scope,UNSAFE_PATTERNS,normalized
from app.schemas.text_retrieval import TextSearchRequest


class VisionChatClient(OpenRouterClient):
    def chat(self,*args,**kwargs):
        started=time.monotonic();result=super().chat(*args,**kwargs)
        logger.info('vision chat model={} input_tokens={} output_tokens={} cost={} duration_ms={}',result.get('model'),result.get('prompt_eval_count'),result.get('eval_count'),result.get('usage_cost'),round((time.monotonic()-started)*1000))
        if result.get('done_reason')!='stop':raise VisionModelError('incomplete image analysis')
        return result


def image_query(analysis,prompt):
    """Treat VLM labels as hints. Never impose a contradictory guessed category.

    Model codes read from an image are not user-specified exact constraints;
    leave those out of the hard text filters. Retrieval still verifies every
    explicit requirement in the user's original prompt.
    """
    values=[analysis.description,analysis.brand_text,analysis.model_text,prompt]
    if any(len(value)>1000 or any(re.search(p,normalized(value)) for p in UNSAFE_PATTERNS) for value in values):
        raise ApiError(502,'INVALID_VISION_ANALYSIS','unsafe or oversized image analysis')
    category=analysis.category_guess if analysis.category_guess in CATEGORY_TH else None
    described=scope(analysis.description,None,[],[]).categories
    requested=scope(prompt,None,[],[]).categories
    if requested:
        category=requested[0] if len(requested)==1 else None
    elif described and category not in described:
        category=described[0] if len(described)==1 else None
    anchor=CATEGORY_TH.get(category,'') or ('ปากกา' if 'ปากกา' in analysis.description else '')
    # Do not turn an unverified visual description into price/color/material
    # constraints. Use its category only, and preserve explicit user constraints.
    model=re.sub(r'\b[a-z]+[a-z0-9.-]*\d[a-z0-9.-]*\b','',analysis.model_text,flags=re.I)
    query=' '.join(value.strip() for value in (anchor,analysis.brand_text,model,prompt) if value.strip())
    if len(query)>4000:raise ApiError(502,'INVALID_VISION_ANALYSIS','image search query too long')
    return query,category


def respond(engine,settings,principal,image_id,prompt,deadline,vision=None,retrieval=None):
    def policy(message):return [],AnswerOutput(message,(),'catalog_policy')
    decision=scope(prompt,None,[],[])
    if decision.reason in ('UNSAFE_QUERY','OUT_OF_SCOPE','MIXED_SCOPE','NON_CATALOG_HELP'):return policy(decision.message)
    with Session(engine) as db:
        ChatSessionService(db).authorize(principal)
        upload=ImageUploadRepository(db).get_owned(image_id,principal)
        if upload is None or upload.status!='ready':raise ApiError(404,'IMAGE_NOT_FOUND','image not found')
        try:image=ImageStorage(settings.image_storage_dir).open(upload.storage_key)
        except FileNotFoundError:raise ApiError(404,'IMAGE_NOT_FOUND','image not found') from None
        db.commit()
    client=None
    try:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ApiError(504,'ANSWER_TIMEOUT','vision deadline exceeded')
        if vision is None:
            client=VisionChatClient(settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else None,
                settings.openrouter_base_url,min(remaining,settings.openrouter_timeout_s),retries=0,fallback_models=[])
            vision=QwenVision(client=client,model=settings.vision_chat_model,num_predict=settings.vision_num_predict)
        analysis=vision.analyze(image,prompt,retries=0)
    except OpenRouterError as error:
        if error.status_code==403:raise ApiError(403,'OPENROUTER_POLICY_REJECTED','vision model rejected by upstream policy') from None
        if error.status_code in (408,504):raise ApiError(504,'ANSWER_TIMEOUT','vision request timed out') from None
        raise ApiError(503,'VISION_UNAVAILABLE','vision provider unavailable') from None
    except VisionModelError:raise ApiError(502,'INVALID_VISION_ANALYSIS','vision analysis contract invalid') from None
    finally:
        image.close()
        if client:client.close()
    if time.monotonic()>=deadline:raise ApiError(504,'ANSWER_TIMEOUT','vision deadline exceeded')
    if not analysis.is_stationery:
        return policy('รูปนี้ยังไม่เห็นสินค้าเครื่องเขียนชัดเจนครับ ลองแนบรูปเครื่องเขียนที่ต้องการหาอีกครั้ง')
    query,category=image_query(analysis,prompt)
    # Never treat a color read from the body as proof of ink color. Only explicit
    # user color requirements enter the query; image color is not a hard filter.
    needs_price=bool(re.search(r'ราคา|บาท|งบ|เท่าไหร่|เท่าไร',prompt))
    result=(retrieval or TextRetrievalService(engine,settings,deadline=deadline)).search(TextSearchRequest(query=query,category=category,limit=5),requires_price=needs_price)
    if result.guardrail_status in ('blocked','needs_clarification'):return policy(result.clarification or 'ช่วยระบุเงื่อนไขสินค้าที่ต้องการอีกนิดครับ')
    if not result.items:
        return policy('ยังไม่เจอสินค้าที่ตรงกับรายละเอียดในรูปนี้ครับ ลองถ่ายให้เห็นยี่ห้อหรือชื่อรุ่นชัดขึ้นอีกนิดได้ไหมครับ')
    products=[]
    for hit in result.items:
        row=dict(hit.catalog_snapshot)
        products.append({**row,**reference_fields(row),'match_type':'similar','match_method':'vision_text_catalog',
                         'match_score':max(0,min(1,hit.semantic_similarity)) if hit.semantic_similarity is not None else None})
    lines=['จากรายละเอียดที่เห็นในรูป ลองดูสินค้าเหล่านี้ครับ']
    lines.extend('• '+p['name']+' — '+display_price(p) for p in products)
    lines.append('ถ้าใช่รุ่นที่กำลังหา บอกลำดับสินค้าแล้วถามต่อได้เลยครับ')
    if any(word in prompt for word in ('พร้อมส่ง','สต็อก','มีของ')):lines.append('ส่วนของพร้อมส่ง ยังยืนยันให้ไม่ได้ครับ')
    return products,AnswerOutput('\n'.join(lines),tuple(p['id'] for p in products),'vision_catalog')
