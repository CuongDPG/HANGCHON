"""Nghiệp vụ control: propose → (tự làm | chờ duyệt | chặn), duyệt / sửa rồi duyệt / trả lại, hoàn tác, mức tự chủ,
cài đặt, lưu vết, «Hôm nay», chi phí AI, lệnh bằng lời."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runner import BUDGET_SETTING_KEY, monthly_budget_vnd, monthly_spend_vnd
from app.core.db import SessionLocal
from app.core.enums import Actor
from app.core.errors import AppError, BadRequest, Conflict, Forbidden, NotFound
from app.core.timeutil import local_day_bounds_utc, local_month_bounds_utc, local_today, month_key, now_utc
from app.modules.control.models import (
    ActivityMode,
    AIActivity,
    AIRun,
    AIRunStatus,
    ApprovalItem,
    ApprovalStatus,
    AppSetting,
    AuditLog,
    AutonomyLevel,
    AutonomySetting,
    User,
    UserRole,
)
from app.modules.control.registry import (
    ACTIONS,
    INTENTS,
    SETTINGS,
    STAT_PROVIDERS,
    ActionContext,
    ActionSpec,
    CommandContext,
    CommandResult,
    HandlerResult,
    ReturnContext,
    Stat,
    UndoContext,
)

log = logging.getLogger("app.control")


# ---- lưu vết -----------------------------------------------------------------------------------------------------


async def audit(
    db: AsyncSession,
    action: str,
    *,
    user: User | None = None,
    actor: Actor | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    kind = actor or (Actor(user.role.value) if user else Actor.SYSTEM)
    row = AuditLog(
        actor_kind=kind,
        actor_user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary,
        data=data or {},
        ip=ip,
    )
    db.add(row)
    await db.flush()
    return row


# ---- mức tự chủ --------------------------------------------------------------------------------------------------


def get_spec(action: str) -> ActionSpec:
    spec = ACTIONS.get(action)
    if spec is None:
        raise NotFound(f"Không có hành động «{action}».")
    return spec


async def get_level(db: AsyncSession, action: str) -> AutonomyLevel:
    spec = get_spec(action)
    if spec.locked:
        return AutonomyLevel.LOCKED_ASK
    row = await db.get(AutonomySetting, action)
    return row.level if row else spec.default_level


# Gợi ý nới mức tự chủ (i3): xét HISTORY_WINDOW lần quyết gần nhất; duyệt liền SUGGEST_STREAK lần không sửa → gợi ý.
HISTORY_WINDOW = 20
SUGGEST_STREAK = 10


async def approval_history(db: AsyncSession) -> dict[str, dict[str, int]]:
    """Theo từng hành động: trong HISTORY_WINDOW lần chị quyết gần nhất có bao nhiêu lần duyệt / sửa / trả lại,
    và chuỗi duyệt liền (không sửa, không trả lại) tính từ lần gần nhất."""
    rn = func.row_number().over(partition_by=ApprovalItem.action, order_by=ApprovalItem.decided_at.desc()).label("rn")
    sub = (
        select(ApprovalItem.action, ApprovalItem.status, ApprovalItem.edited_payload, ApprovalItem.decided_at, rn)
        .where(
            ApprovalItem.status.in_([ApprovalStatus.APPROVED, ApprovalStatus.RETURNED]),
            ApprovalItem.decided_at.is_not(None),
        )
        .subquery()
    )
    rows = (
        await db.execute(
            select(sub.c.action, sub.c.status, sub.c.edited_payload)
            .where(sub.c.rn <= HISTORY_WINDOW)
            .order_by(sub.c.action, sub.c.decided_at.desc())
        )
    ).all()
    out: dict[str, dict[str, int]] = {}
    for action, st, edited in rows:
        h = out.setdefault(action, {"approved": 0, "edited": 0, "returned": 0, "streak": 0, "_open": 1})
        clean = st == ApprovalStatus.APPROVED and not edited
        if st == ApprovalStatus.APPROVED:
            h["approved"] += 1
            h["edited"] += 1 if edited else 0
        else:
            h["returned"] += 1
        if h["_open"] and clean:
            h["streak"] += 1
        else:
            h["_open"] = 0
    for h in out.values():
        h.pop("_open")
    return out


async def list_autonomy(db: AsyncSession) -> list[dict[str, Any]]:
    rows = {r.action: r for r in (await db.execute(select(AutonomySetting))).scalars()}
    history = await approval_history(db)
    empty = {"approved": 0, "edited": 0, "returned": 0, "streak": 0}
    out = []
    for spec in sorted(ACTIONS.values(), key=lambda s: (s.group, s.label)):
        row = rows.get(spec.key)
        level = AutonomyLevel.LOCKED_ASK if spec.locked else (row.level if row else spec.default_level)
        hist = history.get(spec.key, empty)
        out.append(
            {
                "history": hist,
                "suggest_auto": level == AutonomyLevel.ASK and hist["streak"] >= SUGGEST_STREAK,
                "action": spec.key,
                "label": spec.label,
                "group": spec.group,
                "description": spec.description,
                "module": spec.module,
                "level": level,
                "default_level": spec.default_level,
                "locked": spec.locked,
                "customer_facing": spec.customer_facing,
                "updated_at": row.updated_at if row else None,
            }
        )
    return out


async def set_level(db: AsyncSession, action: str, level: AutonomyLevel, user: User | None) -> AutonomyLevel:
    spec = get_spec(action)
    if spec.locked:
        raise Forbidden("Việc này luôn cần chị duyệt, không đổi được mức tự chủ.", code="autonomy_locked")
    if level == AutonomyLevel.LOCKED_ASK:
        raise BadRequest("Không đặt được mức «luôn hỏi» cho việc này; chọn «hỏi chị» nếu muốn duyệt.")
    row = await db.get(AutonomySetting, action)
    old = row.level if row else spec.default_level
    if row is None:
        # lần đầu đổi mức việc này mà chị bấm hai lần liền → hai yêu cầu cùng chèn dòng đầu: chèn-nếu-chưa-có (yêu cầu
        # sau chờ yêu cầu trước commit) rồi khoá dòng để cập nhật, thay vì vỡ khoá chính → 500
        await db.execute(
            pg_insert(AutonomySetting)
            .values(action=action, level=level)
            .on_conflict_do_nothing(index_elements=["action"])
        )
        row = await db.get(AutonomySetting, action, with_for_update=True, populate_existing=True)
        assert row is not None
    row.level = level
    row.updated_at = now_utc()
    row.updated_by_id = user.id if user else None
    await audit(
        db,
        "control.autonomy_changed",
        user=user,
        entity_type="autonomy",
        entity_id=action,
        summary=f"Đổi mức tự chủ «{spec.label}»: {old} → {level}",
        data={"from": str(old), "to": str(level)},
    )
    return level


# ---- propose -----------------------------------------------------------------------------------------------------


@dataclass
class ProposeOutcome:
    status: Literal["applied", "pending", "blocked", "failed"]
    level: AutonomyLevel
    item_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


def _normalize(res: HandlerResult | dict[str, Any] | None) -> HandlerResult:
    if isinstance(res, HandlerResult):
        return res
    return HandlerResult(result=res)


async def _execute(spec: ActionSpec, ctx: ActionContext) -> HandlerResult:
    if spec.handler is None:
        raise AppError(f"Chưa có hàm thực thi cho «{spec.label}».", code="no_handler")
    async with ctx.db.begin_nested():
        return _normalize(await spec.handler(ctx))


def _activity(
    spec: ActionSpec,
    *,
    title: str,
    mode: ActivityMode,
    payload: dict[str, Any],
    res: HandlerResult,
    summary: str | None,
    rationale: str | None,
    sources: list[Any] | None,
    ref_type: str | None,
    ref_id: uuid.UUID | None,
    ai_run_id: uuid.UUID | None,
    item_id: uuid.UUID | None = None,
) -> AIActivity:
    return AIActivity(
        action=spec.key,
        module=spec.module,
        title=title,
        summary=res.summary or summary,
        mode=mode,
        rationale=rationale,
        sources=sources or [],
        payload=payload,
        result=res.result,
        ref_type=res.ref_type or ref_type,
        ref_id=res.ref_id or ref_id,
        approval_item_id=item_id,
        ai_run_id=ai_run_id,
        undo_data=res.undo,
        undoable=res.undo is not None and spec.undo is not None,
    )


async def propose(
    action: str,
    title: str,
    payload: dict[str, Any],
    preview: dict[str, Any] | None = None,
    *,
    db: AsyncSession | None = None,
    summary: str | None = None,
    rationale: str | None = None,
    sources: list[Any] | None = None,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    ai_run_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    priority: int = 0,
    ai_generated: bool = True,
) -> ProposeOutcome:
    """Cửa chung cho mọi việc AI làm. Theo mức tự chủ của `action`:

    - auto → chạy handler ngay (trong savepoint), ghi ai_activity → "applied" (handler lỗi → "failed", không ghi gì)
    - ask / locked_ask → tạo approval_item → "pending" (cùng `dedupe_key` đang chờ thì cập nhật bản cũ)
    - off → "blocked", chỉ ghi audit_log

    `db` = phiên của nơi gọi (cùng giao dịch); bỏ trống thì tự mở phiên và commit."""
    if db is None:
        async with SessionLocal() as s:
            out = await propose(
                action, title, payload, preview, db=s, summary=summary, rationale=rationale, sources=sources,
                ref_type=ref_type, ref_id=ref_id, ai_run_id=ai_run_id, dedupe_key=dedupe_key, priority=priority,
                ai_generated=ai_generated,
            )  # fmt: skip
            await s.commit()
            return out

    spec = get_spec(action)
    level = await get_level(db, action)
    preview = preview or {}

    if level == AutonomyLevel.OFF:
        await audit(
            db, "control.blocked", actor=Actor.AI, entity_type="action", entity_id=action,
            summary=f"Bỏ qua (đang tắt): {title}", data={"payload": payload},
        )  # fmt: skip
        return ProposeOutcome(status="blocked", level=level)

    if level == AutonomyLevel.AUTO:
        ctx = ActionContext(
            db=db, action=action, payload=payload, preview=preview, mode="auto", ref_type=ref_type, ref_id=ref_id
        )
        try:
            res = await _execute(spec, ctx)
        except Exception as e:
            log.exception("AI tự làm «%s» lỗi", action)
            msg = e.message if isinstance(e, AppError) else str(e)
            await audit(
                db, "control.auto_failed", actor=Actor.AI, entity_type="action", entity_id=action,
                summary=f"AI tự làm lỗi: {title}", data={"error": msg[:2000]},
            )  # fmt: skip
            return ProposeOutcome(status="failed", level=level, error=msg)
        act = _activity(
            spec, title=title, mode=ActivityMode.AUTO, payload=payload, res=res, summary=summary,
            rationale=rationale, sources=sources, ref_type=ref_type, ref_id=ref_id, ai_run_id=ai_run_id,
        )  # fmt: skip
        db.add(act)
        await db.flush()
        return ProposeOutcome(status="applied", level=level, activity_id=act.id, result=res.result)

    # ask / locked_ask
    item: ApprovalItem | None = None
    if dedupe_key:
        item = (
            await db.execute(
                select(ApprovalItem).where(
                    ApprovalItem.action == action,
                    ApprovalItem.dedupe_key == dedupe_key,
                    ApprovalItem.status == ApprovalStatus.PENDING,
                )
            )
        ).scalar_one_or_none()
    if item is None:
        item = ApprovalItem(action=action, module=spec.module, dedupe_key=dedupe_key)
        db.add(item)
    item.title = title
    item.summary = summary
    item.payload = payload
    item.preview = preview
    item.rationale = rationale
    item.sources = sources or []
    item.ref_type = ref_type
    item.ref_id = ref_id
    item.ai_run_id = ai_run_id
    item.priority = priority
    item.ai_generated = ai_generated
    item.status = ApprovalStatus.PENDING
    await db.flush()
    return ProposeOutcome(status="pending", level=level, item_id=item.id)


# ---- hàng chờ duyệt ----------------------------------------------------------------------------------------------


async def get_item(db: AsyncSession, item_id: uuid.UUID) -> ApprovalItem:
    item = await db.get(ApprovalItem, item_id)
    if item is None:
        raise NotFound("Không tìm thấy việc chờ duyệt này.")
    return item


async def approve(
    db: AsyncSession,
    item_id: uuid.UUID,
    user: User,
    *,
    edited_payload: dict[str, Any] | None = None,
    note: str | None = None,
) -> ApprovalItem:
    """Duyệt (hoặc sửa rồi duyệt: `edited_payload` gộp nông vào payload). Handler lỗi → status failed, duyệt lại được."""
    item = await get_item(db, item_id)
    if item.status not in (ApprovalStatus.PENDING, ApprovalStatus.FAILED):
        raise Conflict("Việc này đã được xử lý rồi.", code="already_decided")
    spec = get_spec(item.action)
    payload = {**item.payload, **(edited_payload or {})}
    if edited_payload:
        item.edited_payload = edited_payload
    item.attempts += 1
    item.decided_at = now_utc()
    item.decided_by_id = user.id
    item.decision_note = note
    ctx = ActionContext(
        db=db, action=item.action, payload=payload, preview=item.preview, mode="approved", item=item, user=user,
        ref_type=item.ref_type, ref_id=item.ref_id,
    )  # fmt: skip
    try:
        res = await _execute(spec, ctx)
    except Exception as e:
        log.exception("Thực thi sau duyệt «%s» lỗi", item.action)
        item.status = ApprovalStatus.FAILED
        item.error = (e.message if isinstance(e, AppError) else str(e))[:2000]
        await audit(
            db, "control.approve_failed", user=user, entity_type="approval_item", entity_id=item.id,
            summary=f"Duyệt nhưng thực thi lỗi: {item.title}", data={"error": item.error},
        )  # fmt: skip
        await db.flush()
        return item
    item.status = ApprovalStatus.APPROVED
    item.result = res.result
    item.error = None
    db.add(
        _activity(
            spec,
            title=item.title,
            mode=ActivityMode.APPROVED,
            payload=payload,
            res=res,
            summary=item.summary,
            rationale=item.rationale,
            sources=item.sources,
            ref_type=item.ref_type,
            ref_id=item.ref_id,
            ai_run_id=item.ai_run_id,
            item_id=item.id,
        )
    )
    await audit(
        db, "control.approved", user=user, entity_type="approval_item", entity_id=item.id,
        summary=f"{'Sửa rồi duyệt' if edited_payload else 'Duyệt'}: {item.title}",
        data={"action": item.action, "edited": edited_payload or None, "note": note},
    )  # fmt: skip
    await db.flush()
    return item


async def return_item(db: AsyncSession, item_id: uuid.UUID, user: User, note: str) -> ApprovalItem:
    """Trả lại kèm lời nhắn. Module có `@control.on_returned` sẽ được gọi để soạn lại."""
    item = await get_item(db, item_id)
    if item.status not in (ApprovalStatus.PENDING, ApprovalStatus.FAILED):
        raise Conflict("Việc này đã được xử lý rồi.", code="already_decided")
    if not note.strip():
        raise BadRequest("Chị ghi vài chữ để AI biết cần sửa gì.")
    item.status = ApprovalStatus.RETURNED
    item.decision_note = note.strip()
    item.decided_at = now_utc()
    item.decided_by_id = user.id
    await db.flush()
    spec = get_spec(item.action)
    if spec.on_return:
        try:
            async with db.begin_nested():
                await spec.on_return(ReturnContext(db=db, item=item, note=item.decision_note, user=user))
        except Exception:
            log.exception("on_returned «%s» lỗi", item.action)
    await audit(
        db, "control.returned", user=user, entity_type="approval_item", entity_id=item.id,
        summary=f"Trả lại: {item.title}", data={"note": item.decision_note, "action": item.action},
    )  # fmt: skip
    return item


async def approve_many(
    db: AsyncSession, ids: list[uuid.UUID], user: User, *, note: str | None = None
) -> list[dict[str, Any]]:
    """Duyệt hàng loạt (i2): mỗi việc trong savepoint riêng; việc đã xử lý / không tìm thấy không làm hỏng việc khác."""
    results: list[dict[str, Any]] = []
    for item_id in dict.fromkeys(ids):
        try:
            async with db.begin_nested():
                item = await approve(db, item_id, user, note=note)
            results.append({"id": item_id, "status": item.status, "error": item.error})
        except AppError as e:
            results.append({"id": item_id, "status": None, "error": e.message})
    return results


async def pending_groups(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ApprovalItem.action, func.count())
            .where(ApprovalItem.status == ApprovalStatus.PENDING)
            .group_by(ApprovalItem.action)
            .order_by(func.count().desc())
        )
    ).all()
    out = []
    for action, n in rows:
        spec = ACTIONS.get(action)
        out.append(
            {
                "action": action,
                "label": spec.label if spec else action,
                "group": spec.group if spec else None,
                "locked": bool(spec and spec.locked),
                "count": int(n),
            }
        )
    return out


async def cancel_pending(
    db: AsyncSession,
    *,
    action: str,
    dedupe_key: str | None = None,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> int:
    """Huỷ các việc đang chờ không còn cần (vd đơn đã huỷ). Trả số việc đã huỷ."""
    q = select(ApprovalItem).where(ApprovalItem.action == action, ApprovalItem.status == ApprovalStatus.PENDING)
    if dedupe_key is not None:
        q = q.where(ApprovalItem.dedupe_key == dedupe_key)
    if ref_type is not None:
        q = q.where(ApprovalItem.ref_type == ref_type, ApprovalItem.ref_id == ref_id)
    items = list((await db.execute(q)).scalars())
    for it in items:
        it.status = ApprovalStatus.CANCELLED
        it.decided_at = now_utc()
    await db.flush()
    return len(items)


# ---- hoàn tác ----------------------------------------------------------------------------------------------------


async def undo(db: AsyncSession, activity_id: uuid.UUID, user: User) -> AIActivity:
    act = await db.get(AIActivity, activity_id)
    if act is None:
        raise NotFound("Không tìm thấy việc trong nhật ký.")
    if act.undone_at is not None:
        raise Conflict("Việc này đã được hoàn tác.", code="already_undone")
    spec = ACTIONS.get(act.action)
    if not act.undoable or act.undo_data is None or spec is None or spec.undo is None:
        raise BadRequest("Việc này không hoàn tác được.", code="not_undoable")
    try:
        async with db.begin_nested():
            await spec.undo(UndoContext(db=db, activity=act, undo=act.undo_data, user=user))
    except AppError:
        raise
    except Exception as e:
        log.exception("Hoàn tác «%s» lỗi", act.action)
        raise AppError(f"Không hoàn tác được: {e}", code="undo_failed") from e
    act.undone_at = now_utc()
    act.undone_by_id = user.id
    await audit(
        db, "control.undone", user=user, entity_type="ai_activity", entity_id=act.id,
        summary=f"Hoàn tác: {act.title}", data={"action": act.action},
    )  # fmt: skip
    await db.flush()
    return act


# ---- cài đặt -----------------------------------------------------------------------------------------------------


async def get_setting(db: AsyncSession, key: str, default: Any = None) -> Any:
    row = await db.get(AppSetting, key)
    if row is not None:
        return row.value
    spec = SETTINGS.get(key)
    return spec.default if spec and default is None else default


async def set_setting(db: AsyncSession, key: str, value: Any, user: User | None = None) -> AppSetting:
    row = await db.get(AppSetting, key)
    old = row.value if row else None
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    row.value = value
    row.updated_at = now_utc()
    row.updated_by_id = user.id if user else None
    await audit(
        db, "control.setting_changed", user=user, entity_type="app_setting", entity_id=key,
        summary=f"Đổi cài đặt {key}", data={"from": old, "to": value},
    )  # fmt: skip
    await db.flush()
    return row


async def list_settings(db: AsyncSession) -> list[dict[str, Any]]:
    from app.integrations.channel_config import PREFIX as CHANNEL_PREFIX
    from app.integrations.source_config import PREFIX as SOURCE_PREFIX
    from app.integrations.source_profiles import PREFIX as PROFILE_PREFIX

    # tài khoản kênh / nguồn hàng (có khoá mã hoá) và cấu hình nâng cao nguồn (có kiểm riêng) đọc/ghi qua
    # /control/channels, /control/sources
    rows = {
        r.key: r
        for r in (await db.execute(select(AppSetting))).scalars()
        if not r.key.startswith((CHANNEL_PREFIX, SOURCE_PREFIX, PROFILE_PREFIX))
    }
    keys = sorted(set(SETTINGS) | set(rows))
    out = []
    for k in keys:
        spec, row = SETTINGS.get(k), rows.get(k)
        out.append(
            {
                "key": k,
                "label": spec.label if spec else k,
                "group": spec.group if spec else "Khác",
                "description": spec.description if spec else "",
                "default": spec.default if spec else None,
                "value": row.value if row else (spec.default if spec else None),
                "is_default": row is None,
                "updated_at": row.updated_at if row else None,
            }
        )
    return out


# ---- chi phí AI --------------------------------------------------------------------------------------------------


def _task_label(task: str) -> str:
    from app.ai.registry import TASKS

    spec = TASKS.get(task)
    return (spec.description if spec and spec.description else "") or task


async def ai_costs(db: AsyncSession, key: str | None = None) -> dict[str, Any]:
    key = key or month_key()
    start, end = local_month_bounds_utc(key)
    in_month = (AIRun.created_at >= start, AIRun.created_at < end)
    by_task = (
        await db.execute(
            select(
                AIRun.task,
                func.count(),
                func.coalesce(func.sum(AIRun.cost_vnd), 0),
                func.coalesce(func.sum(AIRun.input_tokens), 0),
                func.coalesce(func.sum(AIRun.output_tokens), 0),
            )
            .where(*in_month)
            .group_by(AIRun.task)
            .order_by(func.sum(AIRun.cost_vnd).desc())
        )
    ).all()
    day = func.date(func.timezone("Asia/Ho_Chi_Minh", AIRun.created_at))
    by_day = (
        await db.execute(
            select(day, func.count(), func.coalesce(func.sum(AIRun.cost_vnd), 0))
            .where(*in_month)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    status_counts = dict(
        (await db.execute(select(AIRun.status, func.count()).where(*in_month).group_by(AIRun.status))).all()
    )
    spent = sum(int(r[2]) for r in by_task)
    budget = await monthly_budget_vnd()
    return {
        "month": key,
        "spent_vnd": spent,
        "budget_vnd": budget,
        "remaining_vnd": max(budget - spent, 0),
        "used_pct": round(spent * 100 / budget, 1) if budget > 0 else 0.0,
        "run_count": sum(int(r[1]) for r in by_task),
        "error_count": int(status_counts.get(AIRunStatus.ERROR, 0)) + int(status_counts.get(AIRunStatus.REFUSED, 0)),
        "blocked_count": int(status_counts.get(AIRunStatus.BLOCKED, 0)),
        "by_task": [
            {
                "task": t,
                "label": _task_label(t),
                "runs": int(n),
                "cost_vnd": int(c),
                "input_tokens": int(i),
                "output_tokens": int(o),
            }
            for t, n, c, i, o in by_task
        ],
        "by_day": [{"date": d, "runs": int(n), "cost_vnd": int(c)} for d, n, c in by_day],
    }


async def set_budget(db: AsyncSession, budget_vnd: int, user: User | None) -> int:
    if budget_vnd < 0:
        raise BadRequest("Trần chi phí không được âm.")
    await set_setting(db, BUDGET_SETTING_KEY, budget_vnd, user)
    return budget_vnd


# ---- «Hôm nay» ---------------------------------------------------------------------------------------------------


async def collect_stats(db: AsyncSession) -> list[Stat]:
    stats: list[Stat] = []
    for p in sorted(STAT_PROVIDERS.values(), key=lambda p: p.order):
        try:
            async with db.begin_nested():
                res = await p.fn(db)
        except Exception:
            log.exception("Stat provider «%s» lỗi", p.key)
            continue
        stats += res if isinstance(res, list) else [res]
    return sorted(stats, key=lambda s: s.order)


async def today(db: AsyncSession, *, limit: int = 10) -> dict[str, Any]:
    start, end = local_day_bounds_utc()
    pending_q = select(ApprovalItem).where(ApprovalItem.status == ApprovalStatus.PENDING)
    pending_total = (await db.execute(select(func.count()).select_from(pending_q.subquery()))).scalar_one()
    pending = (
        await db.execute(pending_q.order_by(ApprovalItem.priority.desc(), ApprovalItem.created_at.asc()).limit(limit))
    ).scalars()
    done_q = select(AIActivity).where(AIActivity.created_at >= start, AIActivity.created_at < end)
    done_total = (await db.execute(select(func.count()).select_from(done_q.subquery()))).scalar_one()
    done = (await db.execute(done_q.order_by(AIActivity.created_at.desc()).limit(limit))).scalars()
    auto_rows = (
        await db.execute(
            select(AIActivity.action, func.count())
            .where(AIActivity.created_at >= start, AIActivity.created_at < end, AIActivity.mode == ActivityMode.AUTO)
            .group_by(AIActivity.action)
            .order_by(func.count().desc())
        )
    ).all()
    groups = [{"action": a, "label": ACTIONS[a].label if a in ACTIONS else a, "count": int(n)} for a, n in auto_rows]
    spent, budget = await monthly_spend_vnd(), await monthly_budget_vnd()
    return {
        "date": local_today(),
        "pending": {"total": pending_total, "items": list(pending)},
        "ai_done": {
            "total": done_total,
            "items": list(done),
            "auto_total": sum(g["count"] for g in groups),
            "groups": groups,
        },
        "stats": await collect_stats(db),
        "ai_cost": {
            "month": month_key(),
            "spent_vnd": spent,
            "budget_vnd": budget,
            "used_pct": round(spent * 100 / budget, 1) if budget > 0 else 0.0,
        },
    }


# ---- lệnh bằng lời (i6) ------------------------------------------------------------------------------------------


async def run_command(db: AsyncSession, user: User, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    from app import ai
    from app.modules.control.ai_tasks import ClassifyCommandIn, ClassifyCommandOut, IntentOption

    text = text.strip()
    if not text:
        raise BadRequest("Chị nói hoặc gõ một câu để giao việc.")
    options = [
        IntentOption(
            key=s.key,
            label=s.label,
            description=s.description,
            params_schema=s.params.model_json_schema() if s.params else None,
            examples=s.examples,
        )
        for s in INTENTS.values()
    ]
    base: dict[str, Any] = {"text": text, "intent": None, "label": None, "href": None, "data": None}
    if not options:
        return {**base, "status": "unknown", "message": "Chưa có việc nào giao được bằng lời."}
    res = await ai.run(
        "control.classify_command",
        ClassifyCommandIn(text=text, context=context or {}, intents=options),
        ClassifyCommandOut,
        tier="fast",
    )
    out = res.output
    spec = INTENTS.get(out.intent or "")
    if spec is None or out.confidence < 0.5:
        msg = out.clarification or "Em chưa hiểu ý chị. Chị nói rõ hơn việc cần làm được không?"
        await audit(
            db, "control.command", user=user, summary=text, data={"status": "unknown", "ai_run_id": str(res.run_id)}
        )
        return {**base, "status": "unknown", "message": msg}
    try:
        params = spec.params.model_validate_json(out.params_json or "{}") if spec.params else None
    except ValidationError:
        msg = out.clarification or f"Em cần thêm thông tin để «{spec.label}». Chị nói rõ hơn được không?"
        return {**base, "status": "needs_clarification", "intent": spec.key, "label": spec.label, "message": msg}
    try:
        async with db.begin_nested():
            result: CommandResult = await spec.fn(
                CommandContext(db=db, user=user, text=text, context=context or {}), params
            )
    except AppError as e:
        return {**base, "status": "failed", "intent": spec.key, "label": spec.label, "message": e.message}
    await audit(
        db, "control.command", user=user, entity_type="intent", entity_id=spec.key, summary=text,
        data={"status": result.status, "params": params.model_dump(mode="json") if params else None,
              "ai_run_id": str(res.run_id)},
    )  # fmt: skip
    return {
        **base,
        "status": result.status,
        "intent": spec.key,
        "label": spec.label,
        "message": result.message,
        "href": result.href,
        "data": result.data,
    }


# ---- người dùng --------------------------------------------------------------------------------------------------


async def ensure_owner(db: AsyncSession, email: str, password: str, name: str = "Chị") -> User | None:
    """Tạo tài khoản chị nếu email chưa có. Không đổi mật khẩu tài khoản đã tồn tại."""
    from app.core.security import hash_password

    email = email.strip().lower()
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        return existing
    user = User(email=email, name=name, password_hash=hash_password(password), role=UserRole.OWNER)
    db.add(user)
    await db.flush()
    await audit(db, "control.owner_created", entity_type="user", entity_id=user.id, summary=f"Tạo tài khoản {email}")
    return user
