"""Hành động AI của sourcing (mức tự chủ + hàm thực thi), lệnh bằng lời, số liệu «Hôm nay», cài đặt tỷ giá."""

from __future__ import annotations

import uuid
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app import control
from app.core.errors import NotFound
from app.core.timeutil import now_utc
from app.modules.sourcing import service
from app.modules.sourcing.ai_io import BriefParse
from app.modules.sourcing.estimate import DEFAULT_FX, FX_SETTING_KEY
from app.modules.sourcing.models import BriefStatus, Candidate, DemandSignal, DemandStatus, SourcingBrief

GROUP = "Săn hàng"

control.register_action(
    "sourcing.interpret_brief",
    "Hiểu đề tìm hàng",
    GROUP,
    default="auto",
    description="AI chuyển lời chị dặn thành tiêu chí; chị vẫn xem «AI hiểu là» trước khi tìm.",
)
control.register_action(
    "sourcing.save_candidates",
    "Lưu ứng viên AI tìm được",
    GROUP,
    default="auto",
    description="Kết quả quét nhiều nguồn, tìm bằng ảnh, săn theo lịch: AI lọc, gom cùng mẫu và xếp hạng.",
)
control.register_action(
    "sourcing.import_link",
    "Lấy hồ sơ từ link chị dán",
    GROUP,
    default="auto",
    description="Đọc trang sản phẩm, dịch sang tiếng Việt, tạo ứng viên.",
)
control.register_action(
    "sourcing.save_trends",
    "Lưu tín hiệu xu hướng mỗi sáng",
    GROUP,
    default="auto",
    description="Radar Tiểu Hồng Thư, @cosme, TikTok Shop Việt Nam kèm lý do đáng xem.",
)
control.register_action(
    "sourcing.record_demand",
    "Ghi nhu cầu khách",
    GROUP,
    default="auto",
    description="Gom câu hỏi, lời nhờ tìm của khách thành danh sách nhu cầu.",
)
control.register_action(
    "sourcing.scheduled_alert",
    "Báo ứng viên mới đạt ngưỡng (săn theo lịch)",
    GROUP,
    default="ask",
    description="Đề đã lưu chạy lại hằng tuần; chỉ báo chị khi có ứng viên mới đạt ngưỡng điểm.",
)
control.register_action(
    "sourcing.suggest_demand_brief",
    "Đề xuất mở đề tìm khi đủ người cùng cần",
    GROUP,
    default="ask",
    description="Trang Nhờ chị tìm đủ người bấm «cùng cần»: duyệt để AI mở đề tìm món đó.",
)

control.register_setting(
    FX_SETTING_KEY,
    "Tỷ giá ước tính giá vốn",
    DEFAULT_FX,
    group=GROUP,
    description="VND cho 1 đơn vị ngoại tệ, dùng để ước tính sơ bộ giá về tay khi chưa có bảng giá vốn.",
)


@control.handler("sourcing.interpret_brief")
async def _interpret(ctx: control.ActionContext) -> control.HandlerResult:
    brief = await service.get_brief(ctx.db, uuid.UUID(ctx.payload["brief_id"]))
    parse = BriefParse.model_validate(ctx.payload["parse"])
    service.apply_parse(brief, parse, await service._categories(ctx.db))
    if ctx.payload.get("ai_run_id"):
        brief.ai_run_id = uuid.UUID(ctx.payload["ai_run_id"])
    return control.HandlerResult(
        result={"brief_id": str(brief.id)},
        summary=parse.interpretation,
        ref_type="sourcing_briefs",
        ref_id=brief.id,
    )


@control.handler("sourcing.save_candidates")
async def _save_candidates(ctx: control.ActionContext) -> control.HandlerResult:
    res = await service.save_candidates(ctx.db, ctx.payload["run_id"], ctx.payload["candidates"])
    return control.HandlerResult(
        result=res,
        undo={"candidate_ids": res["new_ids"]},
        summary=f"Đã lưu {res['new_count']} ứng viên mới.",
        ref_type="sourcing_briefs",
        ref_id=uuid.UUID(ctx.payload["brief_id"]),
    )


@control.undoer("sourcing.save_candidates")
async def _undo_candidates(ctx: control.UndoContext) -> None:
    await service.undo_candidates(ctx.db, ctx.undo.get("candidate_ids", []))


@control.handler("sourcing.import_link")
async def _import(ctx: control.ActionContext) -> control.HandlerResult:
    res = await service.save_imported(ctx.db, ctx.payload["run_id"], ctx.payload["candidate"])
    cid = uuid.UUID(res["candidate_ids"][0])
    return control.HandlerResult(
        result=res,
        undo={"candidate_ids": res["new_ids"]},
        summary="Đã tạo ứng viên từ link." if res["created"] else "Đã cập nhật ứng viên có sẵn.",
        ref_type="candidates",
        ref_id=cid,
    )


@control.undoer("sourcing.import_link")
async def _undo_import(ctx: control.UndoContext) -> None:
    await service.undo_candidates(ctx.db, ctx.undo.get("candidate_ids", []))


@control.handler("sourcing.save_trends")
async def _save_trends(ctx: control.ActionContext) -> control.HandlerResult:
    p = ctx.payload
    res = await service.save_trends(ctx.db, p["run_id"], p["detected_on"], p["signals"])
    return control.HandlerResult(result=res, summary=f"{len(res['trend_ids'])} tín hiệu đáng xem.")


@control.handler("sourcing.record_demand")
async def _record_demand(ctx: control.ActionContext) -> control.HandlerResult:
    res = await service.save_demand(ctx.db, ctx.payload)
    return control.HandlerResult(
        result=res,
        summary=f"{ctx.payload['title']}: {res['ask_count']} người đã hỏi.",
        ref_type="demand_signals",
        ref_id=uuid.UUID(res["signal_id"]),
    )


@control.handler("sourcing.scheduled_alert")
async def _alert_seen(ctx: control.ActionContext) -> control.HandlerResult:
    n = len(ctx.payload.get("candidate_ids", []))
    return control.HandlerResult(
        result={"href": f"/desk/san-hang/de/{ctx.payload['brief_id']}"}, summary=f"Chị đã xem {n} ứng viên mới."
    )


@control.handler("sourcing.suggest_demand_brief")
async def _demand_brief(ctx: control.ActionContext) -> control.HandlerResult:
    signal = await ctx.db.get(DemandSignal, uuid.UUID(ctx.payload["signal_id"]))
    if signal is None:
        raise NotFound("Nhu cầu này không còn nữa.")
    brief = await service.brief_from_demand(ctx.db, signal, ctx.user.id if ctx.user else None)
    return control.HandlerResult(
        result={"brief_id": str(brief.id), "href": f"/desk/san-hang/de/{brief.id}"},
        summary=f"Đã mở đề tìm «{brief.title}».",
        ref_type="sourcing_briefs",
        ref_id=brief.id,
    )


# ---- lệnh bằng lời (i6) ------------------------------------------------------------------------------------------


class NewBriefParams(BaseModel):
    text: str = Field(description="Tiêu chí tìm hàng, nguyên văn lời chị")


@control.intent(
    "sourcing.new_brief",
    "Tạo đề săn hàng",
    "Chị dặn tiêu chí tìm một món mới",
    params=NewBriefParams,
    examples=["tìm giúp chị giá phơi gấp gọn inox dưới 300k", "săn bình giữ nhiệt hàng Nhật đánh giá tốt"],
)
async def _new_brief(ctx: control.CommandContext, params: NewBriefParams | None) -> control.CommandResult:
    text = (params.text if params else "") or ctx.text
    brief = await service.create_brief(ctx.db, text, user_id=ctx.user.id if ctx.user else None)
    return control.CommandResult(
        message=f"Em đã ghi đề «{brief.title}». {brief.interpretation or ''} Chị xem lại rồi bấm Tìm nhé.".strip(),
        href=f"/desk/san-hang/de/{brief.id}",
        data={"brief_id": str(brief.id)},
    )


# ---- «Hôm nay» ---------------------------------------------------------------------------------------------------


@control.stat_provider("sourcing.week", order=40)
async def _stats(db) -> list[control.Stat]:
    since = now_utc() - timedelta(days=7)
    new = (await db.execute(select(func.count()).where(Candidate.created_at >= since))).scalar_one()
    demand = (await db.execute(select(func.count()).where(DemandSignal.status == DemandStatus.OPEN))).scalar_one()
    briefs = (await db.execute(select(func.count()).where(SourcingBrief.status == BriefStatus.ACTIVE))).scalar_one()
    return [
        control.Stat(
            key="sourcing.new_candidates", label="Ứng viên mới 7 ngày", value=int(new), href="/desk/san-hang", order=40
        ),
        control.Stat(
            key="sourcing.active_briefs", label="Đề đang chạy", value=int(briefs), href="/desk/san-hang", order=41
        ),
        control.Stat(
            key="sourcing.open_demand",
            label="Nhu cầu khách",
            value=int(demand),
            href="/desk/san-hang?tab=khach-hoi",
            order=42,
        ),
    ]
