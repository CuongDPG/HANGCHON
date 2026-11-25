"""Route của trợ lý. `/api/store/assistant/**` công khai (phiên ẩn danh qua cookie); `/api/desk/assistant/**` cho chị."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import settings
from app.core.db import DbSession
from app.core.deps import CurrentUser
from app.core.pagination import Page, Paginated, paginate
from app.core.security import hmac_sha256, random_token
from app.modules.assistant import service
from app.modules.assistant.models import AssistantConversation
from app.modules.assistant.schemas import (
    AskIn,
    AskOut,
    AssistantConversationOut,
    AssistantMessageOut,
    ContactIn,
    FeedbackIn,
    PublicConversation,
    PublicMessage,
)

store = APIRouter(prefix="/api/store/assistant", tags=["assistant (khách)"])
desk = APIRouter(prefix="/api/desk/assistant", tags=["assistant (desk)"])
routers = [store, desk]

SESSION_COOKIE = "hc_asst"


def session_key(request: Request, response: Response) -> str:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw or len(raw) > 64:
        raw = random_token(18)
        response.set_cookie(
            SESSION_COOKIE, raw, max_age=30 * 24 * 3600, httponly=True, samesite="lax", secure=settings.cookie_secure
        )
    return raw


def ip_hash(request: Request) -> str:
    ip = ratelimit.client_ip(request)
    return hmac_sha256(settings.jwt_secret, f"ip:{ip}".encode())[:64]


async def _public(db: AsyncSession, conv: AssistantConversation) -> PublicConversation:
    msgs = await service.messages(db, conv)
    return PublicConversation(
        id=conv.id,
        status=conv.status,
        product_id=conv.product_id,
        contact_saved=bool(conv.contact),
        messages=[PublicMessage.model_validate(m, from_attributes=True) for m in msgs],
    )


@store.post("/ask", response_model=AskOut)
async def ask(body: AskIn, request: Request, response: Response, db: DbSession) -> Any:
    conv, _, bot = await service.ask(
        db,
        session_key=session_key(request, response),
        ip_hash=ip_hash(request),
        question=body.question,
        product_slug=body.product_slug,
        conversation_id=body.conversation_id,
        page_path=body.page_path,
    )
    return AskOut(
        conversation=await _public(db, conv),
        answer=PublicMessage.model_validate(bot, from_attributes=True),
        handed_off=bot.unknown,
    )


@store.get("/conversations/{conversation_id}", response_model=PublicConversation)
async def conversation(conversation_id: uuid.UUID, request: Request, response: Response, db: DbSession) -> Any:
    conv = await service.get_conversation(db, conversation_id, session_key(request, response))
    return await _public(db, conv)


@store.post("/conversations/{conversation_id}/contact", response_model=PublicConversation)
async def contact(
    conversation_id: uuid.UUID, body: ContactIn, request: Request, response: Response, db: DbSession
) -> Any:
    conv = await service.get_conversation(db, conversation_id, session_key(request, response))
    await service.set_contact(db, conv, body.contact)
    return await _public(db, conv)


@store.post("/conversations/{conversation_id}/feedback", response_model=PublicConversation)
async def feedback(
    conversation_id: uuid.UUID, body: FeedbackIn, request: Request, response: Response, db: DbSession
) -> Any:
    conv = await service.get_conversation(db, conversation_id, session_key(request, response))
    await service.set_feedback(db, conv, body.message_id, body.value)
    return await _public(db, conv)


@desk.get("/conversations", response_model=Paginated[AssistantConversationOut])
async def list_conversations(_: CurrentUser, db: DbSession, page: Page) -> Any:
    stmt = select(AssistantConversation).order_by(AssistantConversation.last_message_at.desc().nulls_last())
    return await paginate(db, stmt, page, AssistantConversationOut)


@desk.get("/conversations/{conversation_id}/messages", response_model=list[AssistantMessageOut])
async def conversation_messages(conversation_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    conv = await db.get(AssistantConversation, conversation_id)
    if conv is None:
        from app.core.errors import NotFound

        raise NotFound("Không tìm thấy cuộc trò chuyện.")
    return await service.messages(db, conv)
