"""Khai báo với control: hành động AI của bàn chọn, cài đặt, số liệu «Hôm nay»."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.modules.selection import service
from app.modules.selection.models import DraftStatus, SelectionDecision, TasteProfile
from app.modules.sourcing.models import Candidate, CandidateStage

GROUP = "Bàn chọn"

control.register_action(
    "selection.organize_note",
    "Sắp ghi chú thử hàng thành ý gọn",
    GROUP,
    default="auto",
    description="AI tách lời chị nói thành từng ý, gắn nhãn điểm tốt / chưa ưng / số đo, xếp vào đúng món.",
)
control.register_action(
    "selection.draft_reasons",
    "Soạn «Vì sao mình chọn» và «Điều mình chưa ưng»",
    GROUP,
    default="ask",
    customer_facing=True,
    description="AI soạn hai đoạn cho trang sản phẩm, chỉ từ ghi chú thử của chị. Chị sửa lời rồi chốt.",
)
control.register_action(
    "selection.update_taste",
    "Cập nhật gu chọn hàng của chị",
    GROUP,
    default="auto",
    description="AI tổng hợp điều chị hay chọn, hay loại để xếp hạng ứng viên cho giống mắt chị.",
)

control.register_action(
    "selection.suggest_sample",
    "Gợi ý mua mẫu món đạt ngưỡng điểm",
    GROUP,
    default="ask",
    description="Hồ sơ thẩm định đạt điểm đạt của khung chấm → hỏi chị có mua mẫu không. Duyệt = chuyển sang Mua mẫu.",
)

control.register_setting(
    service.TRIAL_DAYS_KEY, "Số ngày thử mỗi món", service.DEFAULT_TRIAL_DAYS, group=GROUP,
    description="Thanh tiến độ «ngày thử thứ n/14» trên bàn chọn.",
)  # fmt: skip


@control.handler("selection.organize_note")
async def _organize(ctx: control.ActionContext) -> control.HandlerResult:
    note = await service.apply_note_organization(ctx.db, ctx.payload)
    n = len(note.tags)
    return control.HandlerResult(
        result={"note_id": str(note.id), "points": n, "candidate_id": str(note.candidate_id or "")},
        summary=f"Sắp ghi chú thành {n} ý" + (" và xếp vào món" if ctx.payload.get("candidate_id") else ""),
        ref_type="trial_notes",
        ref_id=note.id,
    )


@control.handler("selection.draft_reasons")
async def _reasons(ctx: control.ActionContext) -> control.HandlerResult:
    d = await service.apply_reasons(
        ctx.db,
        uuid.UUID(ctx.payload["decision_id"]),
        list(ctx.payload.get("reason_selected") or []),
        list(ctx.payload.get("not_satisfied") or []),
    )
    return control.HandlerResult(
        result={"decision_id": str(d.id)},
        summary="Đã lưu «Vì sao mình chọn»",
        ref_type="selection_decisions",
        ref_id=d.id,
    )


@control.on_returned("selection.draft_reasons")
async def _reasons_returned(ctx: control.ReturnContext) -> None:
    d = await ctx.db.get(SelectionDecision, uuid.UUID(ctx.item.payload["decision_id"]))
    if d is not None and d.draft_status != DraftStatus.APPROVED:
        await service.draft_reasons(ctx.db, d, owner_request=ctx.note)


@control.handler("selection.update_taste")
async def _taste(ctx: control.ActionContext) -> control.HandlerResult:
    p, before = await service.apply_taste(ctx.db, ctx.payload)
    return control.HandlerResult(
        result={"profile_id": str(p.id), "version": p.version},
        undo={"profile_id": str(p.id), **before},
        summary=f"Gu của chị, bản {p.version}: {p.sample_count} mẫu",
        ref_type="taste_profiles",
        ref_id=p.id,
    )


@control.undoer("selection.update_taste")
async def _taste_undo(ctx: control.UndoContext) -> None:
    p = await ctx.db.get(TasteProfile, uuid.UUID(ctx.undo["profile_id"]))
    if p is not None:
        p.summary = ctx.undo.get("summary")
        p.weights = ctx.undo.get("weights") or {}
        p.version = (p.version or 1) + 1


@control.stat_provider("selection.board", order=30)
async def _stats(db: AsyncSession) -> list[control.Stat]:
    counts = dict(
        (
            await db.execute(
                select(Candidate.stage, func.count())
                .where(
                    Candidate.stage.in_([CandidateStage.SAMPLE, CandidateStage.TRIAL]), Candidate.is_archived.is_(False)
                )
                .group_by(Candidate.stage)
            )
        ).all()
    )
    return [
        control.Stat(
            key="selection.trial", label="Món đang thử", value=int(counts.get(CandidateStage.TRIAL, 0)),
            href="/desk/ban-chon?tab=trial", order=20,
        ),
        control.Stat(
            key="selection.sample", label="Đang mua mẫu", value=int(counts.get(CandidateStage.SAMPLE, 0)),
            href="/desk/ban-chon?tab=sample", order=21,
        ),
    ]  # fmt: skip


@control.handler("selection.suggest_sample")
async def _suggest_sample(ctx: control.ActionContext) -> control.HandlerResult:
    c, _ = await service.change_stage(ctx.db, uuid.UUID(ctx.payload["candidate_id"]), "sample", ctx.user)
    return control.HandlerResult(
        result={"candidate_id": str(c.id)}, summary=f"Chuyển «{c.title_vi}» sang Mua mẫu",
        ref_type="candidates", ref_id=c.id,
    )  # fmt: skip
