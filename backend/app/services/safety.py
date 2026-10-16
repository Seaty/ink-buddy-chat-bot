"""Application-owned input/output safety, including paths without a text LLM."""
import json
import re
import time

from loguru import logger

from app.ai.llm.openrouter_client import OpenRouterClient
from app.core.errors import ApiError
from app.services.product.retrieval_policy import normalized, UNSAFE_PATTERNS

REFUSAL = 'ผมช่วยแนะนำสินค้าหรือวิธีใช้เพื่อทำร้ายคน ทำร้ายตนเอง หรือทำสิ่งที่ไม่ปลอดภัยไม่ได้ครับ หากต้องการเครื่องเขียนสำหรับเขียน วาดรูป หรือเรียน บอกลักษณะการใช้งานได้เลยครับ'
INJECTION_REFUSAL = 'กรุณาถามเกี่ยวกับเครื่องเขียนโดยไม่ใส่คำสั่งเปลี่ยนกติกาหรือขอข้อมูลลับของระบบครับ'
SELF_HARM_REFUSAL = 'ผมช่วยเลือกอุปกรณ์เพื่อทำร้ายตัวเองไม่ได้ครับ ถ้าตอนนี้รู้สึกไม่ปลอดภัย ลองวางอุปกรณ์ให้ห่างตัวและติดต่อคนที่ไว้ใจให้อยู่เป็นเพื่อนก่อนนะครับ'


def rule_reason(value):
    text = normalized(value)
    if any(re.search(pattern, text) for pattern in UNSAFE_PATTERNS):
        return 'PROMPT_INJECTION'
    compact = re.sub(r'\s+', '', text)
    # Intent phrases, not words like "แหลม" or "ฆ่าเชื้อ" used legitimately.
    if re.search(normalized(r'ฆ่า(?:คน|เพื่อน|ตัวเอง|ผู้อื่น)|ทำร้าย(?:คน|เพื่อน|ตัวเอง|ตนเอง|ผู้อื่น)|แทง(?:คน|เพื่อน|คอ|ตา|ผู้อื่น)|กรีด(?:ข้อมือ|แขนตัวเอง)|(?:kill|stab|hurt)\s*(?:someone|people|myself)|suicide'), compact):
        return 'HARMFUL_INTENT'
    return None


def bounded_history(history):
    remaining = 8000
    out = []
    for item in reversed(history[-10:]):
        if item.get('role') not in ('user', 'assistant'):
            continue
        content = str(item.get('content') or '')
        # Keep complete recent turns; do not silently drop the dangerous half.
        if len(content) > remaining:
            break
        remaining -= len(content)
        out.append({'role': item['role'], 'content': content})
    return list(reversed(out))


def moderation_history(question,history):
    # Native Llama Guard labels the whole supplied conversation. A standalone
    # new question must not inherit a previous refused harmful request.
    # Keep context for references; never exempt the current question from checks.
    reference=re.search(r'รุ่นนี้|รุ่นนั้น|ตัวนี้|ตัวนั้น|อันนี้|อันนั้น|แบบนี้|แบบนั้น|อันไหน|ตัวไหน|แบบไหน|แบบเดิม|ที่แนะนำ|เมื่อกี้|ก่อนหน้า|ตัวที่|อันที่|แบบที่|เอาไป|เหมือนเดิม',normalized(question))
    if not reference:return []
    return bounded_history(history)


class SafetyGate:
    def __init__(self, settings, deadline, client=None):
        self.settings, self.deadline, self.client = settings, deadline, client

    def classify(self, messages, direction):
        """Native Llama Guard chat template classifies the last role's content."""
        start = time.monotonic()
        timeout = min(self.settings.safety_timeout_seconds, self.deadline - start)
        if timeout <= 0:
            raise ApiError(503, 'GUARD_UNAVAILABLE', 'safety check unavailable')
        client = self.client or OpenRouterClient(
            self.settings.openrouter_api_key.get_secret_value() if self.settings.openrouter_api_key else None,
            self.settings.openrouter_base_url, timeout, retries=0, fallback_models=[])
        try:
            result = client.chat(self.settings.safety_model, messages,
                                 options={'temperature': 0, 'num_predict': 64})
            content = result.get('message', {}).get('content', '').strip()
            if result.get('done_reason') != 'stop' or time.monotonic() > self.deadline:
                raise ValueError('incomplete classification')
            if content == 'safe':
                unsafe, categories = False, []
            elif re.fullmatch(r'unsafe\s+S(?:[1-9]|1[0-4])(?:\s*,\s*S(?:[1-9]|1[0-4]))*', content):
                unsafe, categories = True, re.findall(r'S\d+', content)
            else:
                raise ValueError('invalid classification')
            logger.info('safety direction={} unsafe={} categories={} model={} duration_ms={} input_tokens={} output_tokens={} cost={}',
                        direction, unsafe, categories, result.get('model'), round((time.monotonic()-start)*1000),
                        result.get('prompt_eval_count'), result.get('eval_count'), result.get('usage_cost'))
            return unsafe
        except Exception:
            logger.warning('safety unavailable direction={}', direction)
            raise ApiError(503, 'GUARD_UNAVAILABLE', 'safety check unavailable; no answer generated') from None
        finally:
            if self.client is None:
                client.close()

    def precheck(self, content):
        reason = rule_reason(content)
        if reason:
            logger.info('safety blocked direction=input reason={}', reason)
            if reason == 'PROMPT_INJECTION':return INJECTION_REFUSAL
            if any(word in normalized(content) for word in ('ตัวเอง','ตนเอง','myself','suicide')):return SELF_HARM_REFUSAL
            return REFUSAL

    def input(self, content, history=(), image=None):
        refusal=self.precheck(content)
        if refusal:return refusal
        message = {'role': 'user', 'content': content}
        if image:
            message['images'] = [image]
        if self.classify([*moderation_history(content,history), message], 'input'):
            return REFUSAL
        return None

    def output(self, content, products, question, history=()):
        # Include every field used by the reference cards, not just answer prose.
        rendered = content + '\n' + json.dumps(products, ensure_ascii=False, default=str)
        if len(rendered)>32000:
            raise ApiError(503,'GUARD_UNAVAILABLE','safety output exceeds supported size')
        if rule_reason(rendered):
            return REFUSAL
        messages = [*moderation_history(question,history), {'role': 'user', 'content': question},
                    {'role': 'assistant', 'content': rendered}]
        return REFUSAL if self.classify(messages, 'output') else None
