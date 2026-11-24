"""Route của control: /api/desk/auth/*, /api/desk/control/*, /api/desk/users/*."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select

from app.core.config import settings
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, Conflict, NotFound, Unauthorized
from app.core.pagination import Page, Paginated, paginate
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timeutil import now_utc
from app.modules.control import service
from app.modules.control.models import (
    ActivityMode,
    AIActivity,
    AIRun,
    AIRunStatus,
    ApprovalItem,
    ApprovalStatus,
    AuditLog,
    AutonomyLevel,
    User,
)
from app.modules.control.registry import INTENTS
from app.modules.control.schemas import (
    ActivityOut,
    AICostsOut,
    AIRunOut,
    ApprovalItemOut,
    ApproveIn,
    AuditOut,
    AutonomyOut,
    AutonomyUpdate,
    BudgetUpdate,
    CommandIn,
    CommandOut,
    IntentOut,
    LoginIn,
    PasswordChange,
    ReturnIn,
    SettingOut,
    SettingUpdate,
    TodayOut,
    UserCreate,
    UserOut,
    UserUpdate,
)

# ---- xác thực ----------------------------------------------------------------------------------------------------

auth_router = APIRouter(prefix="/api/desk/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )


@auth_router.post("/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, request: Request, db: DbSession) -> User:
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Email hoặc mật khẩu chưa đúng.", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("Tài khoản đã bị khoá.", code="inactive")
    user.last_login_at = now_utc()
    _set_cookie(response, create_access_token(user.id, user.role.value))
    await service.audit(db, "auth.login", user=user, entity_type="user", entity_id=user.id,
                        ip=request.client.host if request.client else None)  # fmt: skip
    return user


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response.delete_cookie(settings.cookie_name, path="/", domain=settings.cookie_domain)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@auth_router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@auth_router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChange, user: CurrentUser, db: DbSession) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise BadRequest("Mật khẩu hiện tại chưa đúng.", code="invalid_credentials")
    user.password_hash = hash_password(body.new_password)
    await service.audit(db, "auth.password_changed", user=user, entity_type="user", entity_id=user.id)


# ---- người dùng (k4) ---------------------------------------------------------------------------------------------

users_router = APIRouter(prefix="/api/desk/users", tags=["users"])


@users_router.get("", response_model=list[UserOut])
async def list_users(_: OwnerUser, db: DbSession) -> list[User]:
    return list((await db.execute(select(User).order_by(User.created_at))).scalars())


@users_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, owner: OwnerUser, db: DbSession) -> User:
    if (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none():
        raise Conflict("Email này đã có tài khoản.", code="email_taken")
    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    await db.flush()
    await service.audit(db, "users.created", user=owner, entity_type="user", entity_id=user.id,
                        summary=f"Tạo tài khoản {body.email} ({body.role})")  # fmt: skip
    return user


@users_router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: uuid.UUID, body: UserUpdate, owner: OwnerUser, db: DbSession) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("Không tìm thấy tài khoản.")
    if user.id == owner.id and body.is_active is False:
        raise BadRequest("Chị không tự khoá tài khoản của mình được.")
    if body.name is not None:
        user.name = body.name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.is_active is not None:
        user.is_active = body.is_active
    await service.audit(db, "users.updated", user=owner, entity_type="user", entity_id=user.id,
                        data=body.model_dump(exclude={"password"}, exclude_none=True))  # fmt: skip
    return user


# ---- control -----------------------------------------------------------------------------------------------------

router = APIRouter(prefix="/api/desk/control", tags=["control"])


@router.get("/today", response_model=TodayOut, summary="Hôm nay (i1)")
async def get_today(_: CurrentUser, db: DbSession) -> dict:
    return await service.today(db)


# hàng chờ duyệt (i2)


@router.get("/approvals", response_model=Paginated[ApprovalItemOut], summary="Hàng chờ duyệt (i2)")
async def list_approvals(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    status_: Annotated[ApprovalStatus | None, Query(alias="status")] = ApprovalStatus.PENDING,
    action: str | None = None,
    module: str | None = None,
) -> Paginated[ApprovalItemOut]:
    q = select(ApprovalItem)
    if status_ is not None:
        q = q.where(ApprovalItem.status == status_)
    if action:
        q = q.where(ApprovalItem.action == action)
    if module:
        q = q.where(ApprovalItem.module == module)
    order = (ApprovalItem.priority.desc(), ApprovalItem.created_at.asc())
    if status_ != ApprovalStatus.PENDING:
        order = (ApprovalItem.updated_at.desc(),)  # type: ignore[assignment]
    return await paginate(db, q.order_by(*order), page, ApprovalItemOut)


@router.get("/approvals/{item_id}", response_model=ApprovalItemOut)
async def get_approval(item_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ApprovalItem:
    return await service.get_item(db, item_id)


@router.post("/approvals/{item_id}/approve", response_model=ApprovalItemOut, summary="Duyệt / sửa rồi duyệt")
async def approve_item(item_id: uuid.UUID, body: ApproveIn, user: OwnerUser, db: DbSession) -> ApprovalItem:
    return await service.approve(db, item_id, user, edited_payload=body.payload, note=body.note)


@router.post("/approvals/{item_id}/return", response_model=ApprovalItemOut, summary="Trả lại kèm lời nhắn")
async def return_approval(item_id: uuid.UUID, body: ReturnIn, user: OwnerUser, db: DbSession) -> ApprovalItem:
    return await service.return_item(db, item_id, user, body.note)


# nhật ký AI (i4)


@router.get("/activity", response_model=Paginated[ActivityOut], summary="Nhật ký AI (i4)")
async def list_activity(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    action: str | None = None,
    module: str | None = None,
    mode: ActivityMode | None = None,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> Paginated[ActivityOut]:
    q = select(AIActivity)
    for col, val in (
        (AIActivity.action, action),
        (AIActivity.module, module),
        (AIActivity.mode, mode),
        (AIActivity.ref_type, ref_type),
        (AIActivity.ref_id, ref_id),
    ):
        if val is not None:
            q = q.where(col == val)
    return await paginate(db, q.order_by(AIActivity.created_at.desc()), page, ActivityOut)


@router.post("/activity/{activity_id}/undo", response_model=ActivityOut, summary="Hoàn tác")
async def undo_activity(activity_id: uuid.UUID, user: OwnerUser, db: DbSession) -> AIActivity:
    return await service.undo(db, activity_id, user)


# mức tự chủ (i3)


@router.get("/autonomy", response_model=list[AutonomyOut], summary="Bảng mức tự chủ (i3)")
async def list_autonomy(_: CurrentUser, db: DbSession) -> list[dict]:
    return await service.list_autonomy(db)


@router.patch("/autonomy/{action}", response_model=AutonomyOut)
async def update_autonomy(action: str, body: AutonomyUpdate, user: OwnerUser, db: DbSession) -> dict:
    await service.set_level(db, action, AutonomyLevel(body.level), user)
    return next(a for a in await service.list_autonomy(db) if a["action"] == action)


# chi phí AI (k2)


@router.get("/ai/costs", response_model=AICostsOut, summary="Chi phí AI theo tháng (k2)")
async def get_ai_costs(
    _: CurrentUser, db: DbSession, month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None
) -> dict:
    return await service.ai_costs(db, month)


@router.patch("/ai/budget", response_model=AICostsOut)
async def update_ai_budget(body: BudgetUpdate, user: OwnerUser, db: DbSession) -> dict:
    await service.set_budget(db, body.monthly_budget_vnd, user)
    await db.commit()  # ai_costs đọc trần bằng phiên riêng
    return await service.ai_costs(db)


@router.get("/ai/runs", response_model=Paginated[AIRunOut])
async def list_ai_runs(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    task: str | None = None,
    status_: Annotated[AIRunStatus | None, Query(alias="status")] = None,
) -> Paginated[AIRunOut]:
    q = select(AIRun)
    if task:
        q = q.where(AIRun.task == task)
    if status_:
        q = q.where(AIRun.status == status_)
    return await paginate(db, q.order_by(AIRun.created_at.desc()), page, AIRunOut)


# cài đặt + lưu vết (k3)


@router.get("/settings", response_model=list[SettingOut])
async def list_settings(_: CurrentUser, db: DbSession) -> list[dict]:
    return await service.list_settings(db)


@router.patch("/settings/{key}", response_model=SettingOut)
async def update_setting(key: str, body: SettingUpdate, user: OwnerUser, db: DbSession) -> dict:
    await service.set_setting(db, key, body.value, user)
    return next(s for s in await service.list_settings(db) if s["key"] == key)


@router.get("/audit", response_model=Paginated[AuditOut], summary="Lưu vết (k3)")
async def list_audit(
    _: OwnerUser,
    db: DbSession,
    page: Page,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> Paginated[AuditOut]:
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    return await paginate(db, q.order_by(AuditLog.created_at.desc()), page, AuditOut)


# ra lệnh bằng lời (i6)


@router.get("/commands", response_model=list[IntentOut], summary="Các việc giao được bằng lời")
async def list_intents(_: CurrentUser) -> list[IntentOut]:
    return [
        IntentOut(key=s.key, label=s.label, description=s.description, examples=s.examples) for s in INTENTS.values()
    ]


@router.post("/command", response_model=CommandOut, summary="Ra lệnh bằng lời (i6)")
async def command(body: CommandIn, user: CurrentUser, db: DbSession) -> dict:
    return await service.run_command(db, user, body.text, body.context)


routers = [auth_router, users_router, router]
