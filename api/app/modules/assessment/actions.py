"""Hành động AI của assessment: mức tự chủ + hàm thực thi.

b4 (chấm điểm) và b6 (an toàn) là «AI làm, chị duyệt»: AI ghi bản NHÁP (score_status=ai_draft, safety chưa
xác nhận) ngay trên hồ sơ, chị duyệt/sửa trên chính trang hồ sơ (POST confirm-score / confirm-safety). Vì vậy
action ghi nháp mặc định `auto` — việc chị duyệt nằm ở trạng thái của hồ sơ, không phải ở hàng chờ."""

from __future__ import annotations

import uuid

from app import control
from app.modules.assessment import service

GROUP = "Thẩm định"


def _run_id(ctx: control.ActionContext) -> uuid.UUID | None:
    rid = ctx.payload.get("ai_run_id")
    return uuid.UUID(rid) if rid else (ctx.item.ai_run_id if ctx.item else None)


control.register_action(
    "assessment.digest_reviews",
    "Đọc hộ đánh giá",
    GROUP,
    default="auto",
    description="Tóm tắt khen/chê lặp lại, tách riêng đánh giá 1–2 sao, dịch trích dẫn.",
)
control.register_action(
    "assessment.market_prices",
    "Tìm giá cùng món ở Việt Nam",
    GROUP,
    default="auto",
    description="Giá trên Shopee, TikTok Shop để biết còn chỗ cho mình không.",
)
control.register_action(
    "assessment.safety_check",
    "Soát an toàn và giấy tờ (bản nháp)",
    GROUP,
    default="auto",
    description="AI ghi nháp cảnh báo pin/chất lỏng/tiếp xúc thực phẩm/nhóm phải công bố; chị xác nhận trên hồ sơ.",
)
control.register_action(
    "assessment.risk_flags",
    "Cảnh báo hàng nhái, đánh giá ảo",
    GROUP,
    default="auto",
    description="So giá và ảnh giữa các shop cùng mẫu, phân bố đánh giá bất thường.",
)
control.register_action(
    "assessment.write_profile",
    "Viết hồ sơ thẩm định và chấm nháp",
    GROUP,
    default="auto",
    description="Tóm tắt, điểm mạnh/yếu, chấm nháp 7 tiêu chí kèm căn cứ; chị sửa điểm từng dòng rồi duyệt.",
)
control.register_action(
    "assessment.compare",
    "Lập bảng so sánh cạnh nhau",
    GROUP,
    default="auto",
    description="Xếp 2–5 ứng viên cùng đề theo tiêu chí, kèm kết luận.",
)


@control.handler("assessment.digest_reviews")
async def _digest(ctx: control.ActionContext) -> control.HandlerResult:
    row = service.save_digest_row(ctx.db, ctx.payload, _run_id(ctx))
    await ctx.db.flush()
    return control.HandlerResult(
        result={"review_digest_id": str(row.id)},
        undo={"review_digest_id": str(row.id)},
        summary=f"Đã đọc {row.reviews_read} đánh giá.",
        ref_type="candidates",
        ref_id=row.candidate_id,
    )


@control.undoer("assessment.digest_reviews")
async def _undo_digest(ctx: control.UndoContext) -> None:
    from app.modules.assessment.models import ReviewDigest

    row = await ctx.db.get(ReviewDigest, uuid.UUID(ctx.undo["review_digest_id"]))
    if row is not None:
        await ctx.db.delete(row)


@control.handler("assessment.market_prices")
async def _market(ctx: control.ActionContext) -> control.HandlerResult:
    n = service.save_market_rows(ctx.db, ctx.payload, _run_id(ctx))
    await ctx.db.flush()
    return control.HandlerResult(result={"count": n}, summary=f"Đã lưu {n} giá ở Việt Nam.")


@control.handler("assessment.safety_check")
async def _safety(ctx: control.ActionContext) -> control.HandlerResult:
    a = await service.get_assessment(ctx.db, uuid.UUID(ctx.payload["assessment_id"]))
    service.apply_safety(a, ctx.payload["safety"])
    return control.HandlerResult(
        result={"status": a.safety_status.value},
        summary=f"An toàn: {a.safety_status.value}",
        ref_type="assessments",
        ref_id=a.id,
    )


@control.handler("assessment.risk_flags")
async def _risk(ctx: control.ActionContext) -> control.HandlerResult:
    a = await service.get_assessment(ctx.db, uuid.UUID(ctx.payload["assessment_id"]))
    service.apply_risk(a, ctx.payload)
    return control.HandlerResult(
        result={"notes": len(ctx.payload["notes"])},
        summary=f"{len(ctx.payload['notes'])} cảnh báo.",
        ref_type="assessments",
        ref_id=a.id,
    )


@control.handler("assessment.write_profile")
async def _profile(ctx: control.ActionContext) -> control.HandlerResult:
    a = await service.get_assessment(ctx.db, uuid.UUID(ctx.payload["assessment_id"]))
    await service.apply_evaluation(ctx.db, a, ctx.payload, _run_id(ctx))
    return control.HandlerResult(
        result={"score_total": float(a.score_total) if a.score_total is not None else None},
        summary=f"Điểm nháp {float(a.score_total):.0f}/100." if a.score_total is not None else "Đã viết hồ sơ.",
        ref_type="assessments",
        ref_id=a.id,
    )


@control.handler("assessment.compare")
async def _compare(ctx: control.ActionContext) -> control.HandlerResult:
    comp = service.save_comparison(ctx.db, ctx.payload, _run_id(ctx))
    await ctx.db.flush()
    return control.HandlerResult(
        result={"comparison_id": str(comp.id), "href": f"/desk/san-hang/so-sanh/{comp.id}"},
        summary=comp.conclusion,
        ref_type="comparisons",
        ref_id=comp.id,
    )
