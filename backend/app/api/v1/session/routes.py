from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Query
from app.api.scaffold import SCAFFOLD_OPENAPI, SCAFFOLD_RESPONSES, not_implemented
from app.schemas.session import CreateSessionRequest, SessionResponse, SessionListResponse, SendMessageRequest, SendMessageResponse, MessageListResponse
router = APIRouter(prefix="/chat-sessions", tags=["session"])


@router.post("", status_code=201, response_model=SessionResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] create chat session", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def create_chat_session(body: CreateSessionRequest):
    not_implemented("create_chat_session")


@router.get("", status_code=200, response_model=SessionListResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] list chat sessions", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def list_chat_sessions(limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None)):
    not_implemented("list_chat_sessions")


@router.get("/{session_id}", status_code=200, response_model=SessionResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] get chat session", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def get_chat_session(session_id: UUID):
    not_implemented("get_chat_session")


@router.delete("/{session_id}", status_code=204, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] delete chat session", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def delete_chat_session(session_id: UUID):
    not_implemented("delete_chat_session")


@router.get("/{session_id}/messages", status_code=200, response_model=MessageListResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] list messages", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def list_messages(session_id: UUID, limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None)):
    not_implemented("list_messages")


@router.post("/{session_id}/messages", status_code=201, response_model=SendMessageResponse, responses=SCAFFOLD_RESPONSES, openapi_extra=SCAFFOLD_OPENAPI,
    summary="[Scaffold] send message", description="Returns 501 for valid requests. Success schema is a proposed contract, not implemented behavior.")
def send_message(session_id: UUID, body: SendMessageRequest):
    not_implemented("send_message")
