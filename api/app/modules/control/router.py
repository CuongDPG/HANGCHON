"""Route của control: /api/desk/auth/*, /api/desk/control/*, /api/desk/users/*."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.ai import config as ai_config
from app.core import ratelimit
from app.core.config import MOCK_EFFECTS, MOCKABLE_INTEGRATIONS, settings
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, Conflict, NotFound, Unauthorized
from app.core.pagination import Page, Paginated, paginate
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timeutil import VN_TZ, now_utc
from app.integrations import channel_config, source_config
from app.integrations.base import KINDS, driver_name
from app.modules.control import ai_settings, channels, links, service, sources
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
from app.modules.control.registry import INTENTS, SETTINGS
from app.modules.control.schemas import (
    ActivityOut,
    AIConfigIn,
    AIConfigOut,
    AICostsOut,
    AIRunOut,
    AITestOut,
    ApprovalGroupOut,
    ApprovalItemOut,
    ApproveIn,
    AuditOut,
    AutonomyOut,
    AutonomyUpdate,
    BatchApproveIn,
    BatchApproveOut,
    BudgetUpdate,
    ChannelAccountIn,
    ChannelAccountOut,
    ChannelCheckIn,
    ChannelCheckOut,
    ChannelConnectOut,
    CommandIn,
    CommandOut,
    IntegrationOut,
    IntentOut,
    LoginIn,
    PasswordChange,
    ReturnIn,
    SettingOut,
    SettingsBulkUpdate,
    SettingUpdate,
    SourceAccountIn,
    SourceAccountOut,
    SourceCheckOut,
    SourceRouteIn,
    SourcesOverviewOut,
    TodayOut,
    UserCreate,
    UserOut,
    UserUpdate,
)

# ---- xác thực ----------------------------------------------------------------------------------------------------

auth_router = APIRouter(prefix="/api/desk/auth", tags=["auth"])

LOGIN_WINDOW = 15 * 60
LOGIN_MAX_PER_ACCOUNT = 10
LOGIN_MAX_PER_IP = 30
LOGIN_LOCKED = "Đăng nhập sai nhiều lần, chị đợi 15 phút rồi thử lại."
_DUMMY_HASH = hash_password("khong-phai-mat-khau-cua-ai")


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
    # chống dò mật khẩu: theo tài khoản (đổi IP không thoát) và theo IP (dò nhiều tài khoản).
    # Chỉ đếm lần SAI; vượt ngưỡng thì khoá cả lần đúng cho tới hết cửa sổ.
    keys = (
        (f"login:email:{body.email}", LOGIN_MAX_PER_ACCOUNT),
        (f"login:ip:{ratelimit.client_ip(request)}", LOGIN_MAX_PER_IP),
    )
    for key, cap in keys:
        if not await ratelimit.hit(key, cap, LOGIN_WINDOW, record=False):
            raise ratelimit.RateLimited(LOGIN_LOCKED, code="login_locked")
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    # email không có vẫn băm thử một lần: thời gian trả lời không lộ email nào có tài khoản
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok:
        for key, cap in keys:
            await ratelimit.hit(key, cap, LOGIN_WINDOW)
        raise Unauthorized("Email hoặc mật khẩu chưa đúng.", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("Tài khoản đã bị khoá.", code="inactive")
    user.last_login_at = now_utc()
    _set_cookie(response, create_access_token(user.id, user.role.value, user.password_hash))
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
async def change_password(body: PasswordChange, user: CurrentUser, response: Response, db: DbSession) -> Response:
    if not verify_password(body.current_password, user.password_hash):
        raise BadRequest("Mật khẩu hiện tại chưa đúng.", code="invalid_credentials")
    user.password_hash = hash_password(body.new_password)
    # phiên khác (máy khác, cookie bị lấy) hết hiệu lực theo dấu mật khẩu; phiên đang dùng nhận cookie mới
    _set_cookie(response, create_access_token(user.id, user.role.value, user.password_hash))
    response.status_code = status.HTTP_204_NO_CONTENT
    await service.audit(db, "auth.password_changed", user=user, entity_type="user", entity_id=user.id)
    return response


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
    out = await service.today(db)
    await links.attach(db, out["pending"]["items"])
    return out


# hàng chờ duyệt (i2)


@router.get("/approvals", response_model=Paginated[ApprovalItemOut], summary="Hàng chờ duyệt (i2)")
async def list_approvals(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    status_: Annotated[list[ApprovalStatus] | None, Query(alias="status")] = None,
    action: str | None = None,
    module: str | None = None,
) -> Paginated[ApprovalItemOut]:
    """`status` lặp được (`?status=approved&status=returned`); bỏ trống = đang chờ."""
    statuses = status_ or [ApprovalStatus.PENDING]
    q = select(ApprovalItem).where(ApprovalItem.status.in_(statuses))
    if action:
        q = q.where(ApprovalItem.action == action)
    if module:
        q = q.where(ApprovalItem.module == module)
    order = (ApprovalItem.priority.desc(), ApprovalItem.created_at.asc())
    if statuses != [ApprovalStatus.PENDING]:
        order = (ApprovalItem.updated_at.desc(),)  # type: ignore[assignment]
    res = await paginate(db, q.order_by(*order), page, ApprovalItemOut)
    await links.attach(db, res.items)
    return res


@router.get("/approvals/groups", response_model=list[ApprovalGroupOut], summary="Việc chờ theo loại")
async def approval_groups(_: CurrentUser, db: DbSession) -> list[dict]:
    return await service.pending_groups(db)


@router.post("/approvals/approve-batch", response_model=BatchApproveOut, summary="Duyệt hàng loạt (i2)")
async def approve_batch(body: BatchApproveIn, user: OwnerUser, db: DbSession) -> dict:
    results = await service.approve_many(db, body.ids, user, note=body.note)
    ok = sum(1 for r in results if r["status"] == ApprovalStatus.APPROVED)
    return {"approved": ok, "failed": len(results) - ok, "results": results}


@router.get("/approvals/{item_id}", response_model=ApprovalItemOut)
async def get_approval(item_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ApprovalItem:
    item = await service.get_item(db, item_id)
    await links.attach(db, [item])
    return item


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
    date_from: Annotated[date | None, Query(description="Từ ngày (giờ VN), gồm cả ngày này")] = None,
    date_to: Annotated[date | None, Query(description="Tới ngày (giờ VN), gồm cả ngày này")] = None,
) -> Paginated[ActivityOut]:
    q = select(AIActivity)
    if date_from:
        q = q.where(AIActivity.created_at >= datetime.combine(date_from, time.min, tzinfo=VN_TZ))
    if date_to:
        q = q.where(AIActivity.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=VN_TZ))
    for col, val in (
        (AIActivity.action, action),
        (AIActivity.module, module),
        (AIActivity.mode, mode),
        (AIActivity.ref_type, ref_type),
        (AIActivity.ref_id, ref_id),
    ):
        if val is not None:
            q = q.where(col == val)
    res = await paginate(db, q.order_by(AIActivity.created_at.desc()), page, ActivityOut)
    await links.attach(db, res.items)
    return res


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


# cấu hình AI: provider, khoá (mã hoá), model, effort, trần — chỉ owner


@router.get("/ai/config", response_model=AIConfigOut, summary="Cấu hình AI đang dùng (khoá chỉ trả dạng che)")
async def get_ai_config(_: OwnerUser, db: DbSession) -> dict:
    return await ai_settings.get_config(db)


@router.patch("/ai/config", response_model=AIConfigOut, summary="Lưu cấu hình AI và chuyển sang dùng provider này")
async def update_ai_config(body: AIConfigIn, user: OwnerUser, db: DbSession) -> dict:
    await ai_settings.save_config(db, body, user)
    await db.commit()
    ai_config.invalidate()  # có hiệu lực ngay ở tiến trình này; worker thấy sau ≤ CACHE_SECONDS
    return await ai_settings.get_config(db)


@router.post("/ai/config/test", response_model=AITestOut, summary="Kiểm tra kết nối bằng cấu hình đang nhập")
async def test_ai_config(body: AIConfigIn, _: OwnerUser, db: DbSession) -> dict:
    return await ai_settings.test_connection(db, body)


@router.delete("/ai/config/{provider}/key", status_code=status.HTTP_204_NO_CONTENT, summary="Xoá khoá đã lưu")
async def delete_ai_key(provider: str, user: OwnerUser, db: DbSession) -> Response:
    await ai_settings.clear_key(db, provider, user)
    await db.commit()
    ai_config.invalidate()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.patch("/settings", response_model=list[SettingOut], summary="Lưu nhiều cài đặt một lần")
async def update_settings(body: SettingsBulkUpdate, user: OwnerUser, db: DbSession) -> list[dict]:
    unknown = [k for k in body.values if k not in SETTINGS]
    if unknown:
        raise BadRequest(f"Không có cài đặt: {', '.join(unknown)}.")
    for key, value in body.values.items():
        if (
            key.endswith("_vnd")
            and value is not None
            and (not isinstance(value, int) or isinstance(value, bool) or value < 0)
        ):
            raise BadRequest(f"«{SETTINGS[key].label}» phải là số tiền nguyên, không âm.")
    current = {s["key"]: s["value"] for s in await service.list_settings(db)}
    for key, value in body.values.items():
        if current.get(key) != value:
            await service.set_setting(db, key, value, user)
    return await service.list_settings(db)


@router.patch("/settings/{key}", response_model=SettingOut)
async def update_setting(key: str, body: SettingUpdate, user: OwnerUser, db: DbSession) -> dict:
    if key.startswith((channel_config.PREFIX, source_config.PREFIX)):  # có khoá mã hoá: chỉ sửa qua màn hình riêng
        raise BadRequest("Cài đặt này sửa ở Cài đặt → Mạng xã hội / Nguồn hàng.")
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
    actions: Annotated[list[str] | None, Query(description="Lọc nhiều khoá hành động")] = None,
) -> Paginated[AuditOut]:
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if actions:
        q = q.where(AuditLog.action.in_(actions))
    q = q.add_columns(User.name).outerjoin(User, User.id == AuditLog.actor_user_id)

    def _row(r: Any) -> AuditOut:
        out = AuditOut.model_validate(r[0])
        out.actor_name = r[1]
        return out

    return await paginate(db, q.order_by(AuditLog.created_at.desc()), page, _row, scalars=False)


# tài khoản kênh: Cài đặt → Mạng xã hội — chỉ owner (khoá chỉ trả dạng che)


@router.get("/channels", response_model=list[ChannelAccountOut], summary="Tài khoản từng kênh + công tắc thật/giả lập")
async def list_channel_accounts(_: OwnerUser, db: DbSession) -> list[dict]:
    return await channels.list_views(db)


@router.patch("/channels/{channel}", response_model=ChannelAccountOut, summary="Lưu khoá / công tắc của một kênh")
async def save_channel_account(channel: str, body: ChannelAccountIn, user: OwnerUser, db: DbSession) -> dict:
    return await channels.save(db, channel, mode=body.mode, values=body.values, clear=body.clear, user=user)


@router.post("/channels/{channel}/check", response_model=ChannelCheckOut, summary="Kiểm tra kết nối với nền tảng")
async def check_channel_account(channel: str, body: ChannelCheckIn, user: OwnerUser, db: DbSession) -> dict:
    return await channels.run_check(db, channel, body.values, user)


@router.post("/channels/{channel}/connect", response_model=ChannelConnectOut, summary="Link cấp quyền (OAuth)")
async def connect_channel_account(channel: str, user: OwnerUser, db: DbSession) -> dict:
    return await channels.start_connect(db, channel, user)


# nguồn hàng: Cài đặt → Nguồn hàng — chỉ owner (khoá chỉ trả dạng che)


@router.get("/sources", response_model=SourcesOverviewOut, summary="Cách lấy hàng từng sàn + khoá dịch vụ")
async def list_sources(_: OwnerUser, db: DbSession) -> dict:
    return await sources.overview(db)


@router.patch("/sources/platforms/{platform}", response_model=SourcesOverviewOut, summary="Chọn cách lấy hàng một sàn")
async def save_source_route(platform: str, body: SourceRouteIn, user: OwnerUser, db: DbSession) -> dict:
    return await sources.set_route(db, platform, body.driver, user)


@router.patch("/sources/accounts/{account}", response_model=SourceAccountOut, summary="Lưu khoá dịch vụ nguồn hàng")
async def save_source_account(account: str, body: SourceAccountIn, user: OwnerUser, db: DbSession) -> dict:
    return await sources.save_account(db, account, values=body.values, clear=body.clear, user=user)


@router.post("/sources/accounts/{account}/check", response_model=SourceCheckOut, summary="Gọi thử dịch vụ nguồn hàng")
async def check_source_account(account: str, body: ChannelCheckIn, user: OwnerUser, db: DbSession) -> dict:
    return await sources.run_check(db, account, body.values, user)


oauth_hooks = APIRouter(prefix="/api/hooks/oauth", tags=["hooks"])


@oauth_hooks.get("/{channel}", include_in_schema=False)
async def oauth_callback(channel: str, request: Request, db: DbSession) -> RedirectResponse:
    """Nền tảng chuyển chị về đây sau khi cấp quyền; xác thực bằng `state` một lần (15 phút) do chị tạo."""
    url = await channels.finish_connect(db, channel, dict(request.query_params))
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


INTEGRATION_LABELS = {
    "sources": "Nguồn hàng (săn hàng)",
    "social": "Mạng xã hội",
    "payments": "Thanh toán chuyển khoản",
    "shipping": "Vận chuyển",
    "notify": "Báo tin cho khách",
    "marketplaces": "Sàn TMĐT",
    "einvoice": "Hoá đơn điện tử",
    "storage": "Lưu trữ tệp",
}


@router.get("/integrations", response_model=list[IntegrationOut], summary="Driver tích hợp đang bật")
async def list_integrations(_: CurrentUser) -> list[IntegrationOut]:
    from importlib import resources

    out = []
    for kind in KINDS:
        try:
            files = resources.files(f"app.integrations.{kind}")
            available = sorted(
                f.name.removesuffix(".py")
                for f in files.iterdir()
                if f.name.endswith(".py") and not f.name.startswith("_")
            )
        except ModuleNotFoundError:
            available = []
        name = driver_name(kind)
        used = settings.integration_drivers(kind) if kind in MOCKABLE_INTEGRATIONS else [name]
        if kind in ("social", "marketplaces"):  # công tắc từng kênh ở Cài đặt → Mạng xã hội thắng biến môi trường
            chans = channel_config.SOCIAL_CHANNELS if kind == "social" else channel_config.MARKETPLACE_CHANNELS
            if any(channel_config.mode(c) for c in chans):
                used = list(
                    dict.fromkeys(
                        channel_config.SPECS[c].driver if channels.effective_mode(c) == "real" else "mock"
                        for c in chans
                    )
                )
        if kind == "sources" and name == "routed":  # cách lấy hàng từng sàn ở Cài đặt → Nguồn hàng
            used = source_config.drivers_in_use()
        any_mock = "mock" in used
        out.append(
            IntegrationOut(
                kind=kind,
                label=INTEGRATION_LABELS.get(kind, kind),
                driver=name,
                is_mock=any_mock and set(used) == {"mock"},
                partly_mock=any_mock and set(used) != {"mock"},
                drivers=used,
                mock_effect=MOCK_EFFECTS.get(kind) if any_mock else None,
                blocked_in_prod=kind == "einvoice" and any_mock and settings.app_env == "prod",
                available=available,
            )
        )
    return out


# ra lệnh bằng lời (i6)


@router.get("/commands", response_model=list[IntentOut], summary="Các việc giao được bằng lời")
async def list_intents(_: CurrentUser) -> list[IntentOut]:
    return [
        IntentOut(key=s.key, label=s.label, description=s.description, examples=s.examples) for s in INTENTS.values()
    ]


@router.post("/command", response_model=CommandOut, summary="Ra lệnh bằng lời (i6)")
async def command(body: CommandIn, user: CurrentUser, db: DbSession) -> dict:
    return await service.run_command(db, user, body.text, body.context)


routers = [auth_router, users_router, router, oauth_hooks]
