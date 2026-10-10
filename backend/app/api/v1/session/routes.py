from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_principal
from app.api.policy import access_policy
from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.core.security import Principal
from app.db.database import get_db
from app.schemas.session import (
    CreateSessionRequest,
    MessageListResponse,
    RenameSessionRequest,
    SendMessageRequest,
    SendMessageResponse,
    SessionListResponse,
    SessionResponse,
)
from app.services.session.message_service import MessageService
from app.services.session.service import ChatSessionService

router = APIRouter(
    prefix="/chat-sessions",
    tags=["session"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


def service(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return ChatSessionService(db)


@router.post("", status_code=201, response_model=SessionResponse)
@access_policy("guest_or_user")
def create_chat_session(
    body: CreateSessionRequest,
    principal: Principal = Depends(get_principal),
    chats: ChatSessionService = Depends(service),
):
    return chats.create(principal, body.title)


@router.get("", response_model=SessionListResponse)
@access_policy("guest_or_user")
def list_chat_sessions(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    principal: Principal = Depends(get_principal),
    chats: ChatSessionService = Depends(service),
):
    return chats.list(principal, limit, cursor)


@router.get("/{session_id}", response_model=SessionResponse)
@access_policy("guest_or_user")
def get_chat_session(
    session_id: UUID,
    principal: Principal = Depends(get_principal),
    chats: ChatSessionService = Depends(service),
):
    return chats.get(principal, session_id)


@router.patch("/{session_id}", response_model=SessionResponse)
@access_policy("guest_or_user")
def rename_chat_session(
    session_id: UUID,
    body: RenameSessionRequest,
    principal: Principal = Depends(get_principal),
    chats: ChatSessionService = Depends(service),
):
    return chats.rename(principal, session_id, body.title)


@router.delete("/{session_id}", status_code=204)
@access_policy("guest_or_user")
def delete_chat_session(
    session_id: UUID,
    principal: Principal = Depends(get_principal),
    chats: ChatSessionService = Depends(service),
):
    chats.delete(principal, session_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/{session_id}/messages", response_model=MessageListResponse)
@access_policy("guest_or_user")
def list_messages(
    session_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    principal: Principal = Depends(get_principal),
    chats: ChatSessionService = Depends(service),
):
    return chats.messages(principal, session_id, limit, cursor)


def message_service(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    return MessageService(db, settings)


@router.post(
    "/{session_id}/messages",
    status_code=201,
    response_model=SendMessageResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
@access_policy("guest_or_user")
def send_message(
    session_id: UUID,
    body: SendMessageRequest,
    response: Response,
    principal: Principal = Depends(get_principal),
    messages: MessageService = Depends(message_service),
):
    response.headers["Cache-Control"] = "no-store"
    return messages.send(principal, session_id, body)
