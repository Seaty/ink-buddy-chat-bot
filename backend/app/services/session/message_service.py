"""Two short transactions around retrieval/answer; never hold locks during inference."""

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from copy import deepcopy
from threading import BoundedSemaphore
from uuid import UUID

from loguru import logger
from sqlalchemy import text

from app.core.errors import ApiError
from app.core.security import unauthorized, utcnow
from app.schemas.session import MessageResponse, ProductReference, SendMessageResponse
from app.services.product.text_search import CatalogTextSearch
from app.services.session.adapter import (
    AnswerInput,
    AnswerOutput,
    CatalogTemplateAdapter,
)
from app.services.session.service import ChatSessionService

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat-answer")
_SLOTS = BoundedSemaphore(4)


class MessageService(ChatSessionService):
    def __init__(self, db, settings, adapter=None):
        super().__init__(db)
        self.settings = settings
        self.adapter = adapter or CatalogTemplateAdapter()

    def check(self, principal, sid):
        self.db.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(int(self.settings.chat_timeout_seconds * 1000))},
        )
        if principal.access_expires_at and principal.access_expires_at <= utcnow():
            raise unauthorized()
        if principal.kind == "user":
            # Serialize logout/reset revocation with the final write.
            self.db.execute(
                text("SELECT id FROM auth_sessions WHERE id=:id FOR UPDATE"),
                {"id": principal.session_id},
            )
        self.authorize(principal)
        row = self.owned(principal, sid, lock=True)
        self.authorize(principal)
        if principal.access_expires_at and principal.access_expires_at <= utcnow():
            raise unauthorized()
        return row

    def replay(self, sid, body):
        user = (
            self.db.execute(
                text(
                    "SELECT * FROM chat_messages WHERE session_id=:sid AND client_request_id=:rid"
                ),
                {"sid": sid, "rid": body.client_request_id},
            )
            .mappings()
            .one_or_none()
        )
        if not user:
            return None
        if user["content"] != body.content:
            raise ApiError(
                409,
                "REQUEST_ID_CONFLICT",
                "request ID already used with different content",
            )
        assistant = (
            self.db.execute(
                text(
                    "SELECT * FROM chat_messages WHERE session_id=:sid AND sequence_number=:seq AND role='assistant'"
                ),
                {"sid": sid, "seq": user["sequence_number"] + 1},
            )
            .mappings()
            .one()
        )
        return SendMessageResponse(
            user_message=MessageResponse(**user),
            assistant_message=MessageResponse(**assistant),
        )

    def latest(self, sid):
        return self.db.execute(
            text(
                "SELECT COALESCE(MAX(sequence_number),0) FROM chat_messages WHERE session_id=:sid"
            ),
            {"sid": sid},
        ).scalar_one()

    def send(self, principal, sid, body):
        start = time.monotonic()
        try:
            self.check(principal, sid)
            existing = self.replay(sid, body)
            if existing:
                self.db.commit()
                return existing
            boundary = self.latest(sid)
            history = (
                self.db.execute(
                    text(
                        "SELECT role,content FROM chat_messages WHERE session_id=:sid ORDER BY sequence_number DESC LIMIT 10"
                    ),
                    {"sid": sid},
                )
                .mappings()
                .all()
            )
            history = tuple(dict(x) for x in reversed(history))
            self.db.commit()
            search_start = time.monotonic()
            self.db.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": str(int(self.settings.chat_timeout_seconds * 1000))},
            )
            products, clarification = CatalogTextSearch(self.db).search(body.content)
            self.db.commit()
            logger.info(
                "chat search duration_ms={}",
                round((time.monotonic() - search_start) * 1000),
            )
            remaining = self.settings.chat_timeout_seconds - (time.monotonic() - start)
            if remaining <= 0:
                raise ApiError(504, "ANSWER_TIMEOUT", "answer timed out")
            if not _SLOTS.acquire(blocking=False):
                raise ApiError(503, "ANSWER_BUSY", "answer service busy")
            try:
                future = _POOL.submit(
                    self.adapter.answer,
                    AnswerInput(
                        body.content,
                        deepcopy(history),
                        tuple(deepcopy(products)),
                        clarification,
                    ),
                )
            except Exception:
                _SLOTS.release()
                raise
            future.add_done_callback(lambda _: _SLOTS.release())
            try:
                answer = future.result(timeout=remaining)
            except TimeoutError:
                raise ApiError(504, "ANSWER_TIMEOUT", "answer timed out") from None
            except Exception:
                raise ApiError(
                    502, "ANSWER_FAILED", "answer generation failed"
                ) from None
            if time.monotonic() - start > self.settings.chat_timeout_seconds:
                raise ApiError(504, "ANSWER_TIMEOUT", "answer timed out")
            allowed = {p["id"]: p for p in products}
            if (
                not isinstance(answer, AnswerOutput)
                or not isinstance(answer.content, str)
                or not answer.content.strip()
                or len(answer.content) > 16000
                or not isinstance(answer.model_name, str)
                or not answer.model_name
                or len(answer.model_name) > 100
                or not isinstance(answer.product_ids, tuple)
                or any(
                    not isinstance(i, UUID) or i not in allowed
                    for i in answer.product_ids
                )
            ):
                raise ApiError(502, "INVALID_ANSWER", "answer contract invalid")
            refs = [
                ProductReference(**allowed[i])
                for i in dict.fromkeys(answer.product_ids)
            ]
            self.check(principal, sid)
            existing = self.replay(sid, body)
            if existing:
                self.db.commit()
                return existing
            if self.latest(sid) != boundary:
                raise ApiError(409, "CHAT_CHANGED", "chat history changed; try again")
            if boundary > 2147483645:
                raise ApiError(409, "CHAT_FULL", "chat sequence exhausted")
            pair = []
            for role, content, seq, rid, product_refs, model in [
                (
                    "user",
                    body.content,
                    boundary + 1,
                    body.client_request_id,
                    None,
                    None,
                ),
                (
                    "assistant",
                    answer.content,
                    boundary + 2,
                    None,
                    json.dumps([r.model_dump(mode="json") for r in refs]),
                    answer.model_name,
                ),
            ]:
                row = (
                    self.db.execute(
                        text(
                            "INSERT INTO chat_messages(session_id,sequence_number,role,content,client_request_id,product_refs,model_name) VALUES(:sid,:seq,:role,:content,:rid,CAST(:refs AS jsonb),:model) RETURNING *"
                        ),
                        {
                            "sid": sid,
                            "seq": seq,
                            "role": role,
                            "content": content,
                            "rid": rid,
                            "refs": product_refs,
                            "model": model,
                        },
                    )
                    .mappings()
                    .one()
                )
                pair.append(MessageResponse(**row))
            self.db.execute(
                text(
                    "UPDATE chat_sessions SET updated_at=clock_timestamp() WHERE id=:sid"
                ),
                {"sid": sid},
            )
            self.db.commit()
            logger.info(
                "chat answer duration_ms={}", round((time.monotonic() - start) * 1000)
            )
            return SendMessageResponse(user_message=pair[0], assistant_message=pair[1])
        except ApiError as error:
            self.db.rollback()
            logger.warning("chat request refused code={}", error.code)
            raise
        except Exception as error:
            self.db.rollback()
            if getattr(getattr(error, "orig", None), "sqlstate", None) == "57014":
                raise ApiError(
                    504, "ANSWER_TIMEOUT", "database operation timed out"
                ) from None
            logger.error("chat request failed")
            raise ApiError(
                500, "MESSAGE_FAILED", "message could not be saved"
            ) from None
