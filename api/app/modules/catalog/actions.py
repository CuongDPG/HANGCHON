"""Khai báo của catalog với control: hành động (mức tự chủ), handler, hoàn tác, trả lại, cài đặt, số liệu «Hôm nay».

Mức mặc định theo hướng thận trọng: mọi thứ khách nhìn thấy `ask`; xử lý ảnh (nội bộ, hoàn tác được) `auto`."""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from unidecode import unidecode

from app import control
from app.core.errors import Forbidden, NotFound
from app.modules.catalog import drops as drop_svc
from app.modules.catalog import finds as find_svc
from app.modules.catalog import products as product_svc
from app.modules.catalog import reviews as review_svc
from app.modules.catalog import stop_selling
from app.modules.catalog.models import (
    Drop,
    DropStatus,
    FindRequest,
    FindRequestStatus,
    ProductImage,
    ProductStatus,
    Review,
    ReviewStatus,
)
from app.modules.catalog.models import Product as ProductModel
from app.modules.catalog.public import DEFAULTS as STORE_DEFAULTS
from app.modules.control.models import UserRole

GROUP = "Website"

control.register_action(
    "catalog.publish_product", "Đăng trang sản phẩm lên website", GROUP, default="ask", customer_facing=True,
    description="AI viết trang từ hồ sơ chọn; chị sửa lời rồi duyệt thì món lên kệ.",
)  # fmt: skip
control.register_action(
    "catalog.process_image", "Xử lý ảnh sản phẩm (xoay, cân sáng, làm sạch nền, cắt vuông)", GROUP, default="auto",
    description="Chỉ chỉnh ảnh thật chị chụp, không tạo ảnh giả. Hoàn tác được: quay về ảnh chỉ cắt vuông.",
)  # fmt: skip
control.register_action(
    "catalog.open_drop", "Mở đợt bán", GROUP, default="ask", customer_facing=True,
    description="Đợt gom đơn có hạn chót, số suất, ngày hàng về dự kiến.",
)  # fmt: skip
control.register_action(
    "catalog.send_drop_reminders", "Nhắn khách đã bấm «Nhắc mình» khi đợt mở", GROUP, default="ask",
    customer_facing=True,
)  # fmt: skip
control.register_action(
    "catalog.send_review_request", "Nhắn khách xin đánh giá sau khi nhận hàng", GROUP, default="ask",
    customer_facing=True,
)  # fmt: skip
control.register_action(
    "catalog.publish_review", "Hiện đánh giá của khách", GROUP, default="ask", customer_facing=True,
    description="AI lọc spam, thô tục, lộ thông tin cá nhân; chê thật lòng vẫn được hiện.",
)  # fmt: skip
control.register_action(
    "catalog.publish_find_request", "Hiện lời Nhờ tìm của khách", GROUP, default="ask", customer_facing=True,
)  # fmt: skip

control.register_setting(product_svc.CLEAN_BG_SETTING, "Làm sạch nền ảnh sản phẩm", True, group="Website",
                         description="Nền sáng, đều màu (trắng, xám nhạt) được đưa về trắng. Nền phức tạp giữ nguyên. "
                         "Tắt thì ảnh mới chỉ xoay, cân sáng, cắt vuông.")  # fmt: skip
control.register_setting(find_svc.THRESHOLD_SETTING, "Số người cùng cần để mở tìm", find_svc.DEFAULT_THRESHOLD,
                         group="Website", description="Đủ số người bấm «mình cũng cần» thì chị mở đề săn hàng.")  # fmt: skip
for _key, _label in (("store.picker_name", "Tên người chọn (trang Về người chọn)"),
                     ("store.picker_intro", "Lời giới thiệu của người chọn"),
                     ("store.not_selling", "«Mình không bán»"), ("store.ai_help", "«AI giúp mình việc gì»")):  # fmt: skip
    control.register_setting(_key, _label, STORE_DEFAULTS[_key], group="Cửa hàng")


def _uuid(ctx: control.ActionContext, key: str) -> uuid.UUID:
    return uuid.UUID(str(ctx.payload[key]))


# ---- trang sản phẩm ----------------------------------------------------------------------------------------------


@control.handler("catalog.publish_product")
async def _publish_product(ctx: control.ActionContext) -> control.HandlerResult:
    p = await product_svc.get_product(ctx.db, _uuid(ctx, "product_id"))
    before = p.status.value
    await product_svc.publish(ctx.db, p, user=ctx.user)
    return control.HandlerResult(
        result={"product_id": str(p.id), "slug": p.slug}, undo={"product_id": str(p.id), "status": before},
        summary=f"Đã đăng «{p.name}» lên kệ", ref_type="products", ref_id=p.id,
    )  # fmt: skip


@control.undoer("catalog.publish_product")
async def _unpublish_product(ctx: control.UndoContext) -> None:
    p = await product_svc.get_product(ctx.db, uuid.UUID(ctx.undo["product_id"]))
    p.status = ProductStatus.PAUSED
    await ctx.db.flush()


control.register_action(
    stop_selling.ACTION, "Ngừng bán một món trên mọi kênh", GROUP, default="ask", customer_facing=True,
    description="Chị bấm «Ngừng bán»: gỡ khỏi website, huỷ lịch đăng, ẩn/xoá bài đã đăng, ngừng bán trên sàn. Chị tự "
    "bấm thì làm ngay; hoàn tác = «Mở bán lại».",
)  # fmt: skip


@control.handler(stop_selling.ACTION)
async def _stop_selling(ctx: control.ActionContext) -> control.HandlerResult:
    return await stop_selling.apply_stop(ctx)


@control.undoer(stop_selling.ACTION)
async def _resume_selling(ctx: control.UndoContext) -> None:
    await stop_selling.undo_stop(ctx)


@control.on_returned("catalog.publish_product")
async def _rewrite_product(ctx: control.ReturnContext) -> None:
    p = await ctx.db.get(ProductModel, uuid.UUID(str(ctx.item.payload["product_id"])))
    if p is not None and p.status != ProductStatus.PUBLISHED:
        await product_svc.write_page(ctx.db, p, note=ctx.note)


# ---- ảnh ---------------------------------------------------------------------------------------------------------


@control.handler("catalog.process_image")
async def _process_image(ctx: control.ActionContext) -> control.HandlerResult:
    img = await ctx.db.get(ProductImage, _uuid(ctx, "image_id"))
    if img is None:
        raise NotFound("Ảnh đã bị xoá.")
    await product_svc.render_image(ctx.db, img, enhance=True)
    labels = {"exif_transpose": "xoay đúng chiều", "autocontrast": "cân tương phản", "brightness": "cân sáng",
              "clean_background": "làm sạch nền", "crop": "cắt vuông"}  # fmt: skip
    ops = ", ".join(labels.get(o["op"], o["op"]) for o in img.processing_ops if o.get("op") != "renditions")
    return control.HandlerResult(
        result={"image_id": str(img.id)}, undo={"image_id": str(img.id)}, summary=f"Đã xử lý ảnh: {ops}",
        ref_type="product_images", ref_id=img.id,
    )  # fmt: skip


@control.undoer("catalog.process_image")
async def _undo_image(ctx: control.UndoContext) -> None:
    img = await ctx.db.get(ProductImage, uuid.UUID(ctx.undo["image_id"]))
    if img is not None:
        await product_svc.render_image(ctx.db, img, enhance=False)


# ---- đợt ---------------------------------------------------------------------------------------------------------


@control.handler("catalog.open_drop")
async def _open_drop(ctx: control.ActionContext) -> control.HandlerResult:
    d = await drop_svc.get_drop(ctx.db, _uuid(ctx, "drop_id"))
    await drop_svc.apply_open(ctx.db, d)
    word = "Đã hẹn giờ mở" if d.status == DropStatus.SCHEDULED else "Đã mở"
    return control.HandlerResult(result={"drop_id": str(d.id), "status": d.status.value},
                                 summary=f"{word} {drop_svc.label(d)}", ref_type="drops", ref_id=d.id)  # fmt: skip


@control.on_returned("catalog.open_drop")
async def _open_returned(ctx: control.ReturnContext) -> None:
    d = await ctx.db.get(Drop, uuid.UUID(str(ctx.item.payload["drop_id"])))
    if d is not None and d.status == DropStatus.PENDING_REVIEW:
        d.status = DropStatus.DRAFT
        await ctx.db.flush()


@control.handler("catalog.send_drop_reminders")
async def _send_reminders(ctx: control.ActionContext) -> control.HandlerResult:
    d = await drop_svc.get_drop(ctx.db, _uuid(ctx, "drop_id"))
    n = await drop_svc.send_reminders(ctx.db, d)
    return control.HandlerResult(result={"sent": n}, summary=f"Đã nhắn {n} khách: {drop_svc.label(d)} đã mở",
                                 ref_type="drops", ref_id=d.id)  # fmt: skip


# ---- đánh giá ----------------------------------------------------------------------------------------------------


@control.handler("catalog.send_review_request")
async def _send_review_request(ctx: control.ActionContext) -> control.HandlerResult:
    res = await review_svc.send_request(ctx.payload)
    return control.HandlerResult(result=res, summary="Đã nhắn khách xin đánh giá")


@control.handler("catalog.publish_review")
async def _publish_review(ctx: control.ActionContext) -> control.HandlerResult:
    r = await review_svc.get_review(ctx.db, _uuid(ctx, "review_id"))
    await review_svc.publish(ctx.db, r, mode=ctx.mode)
    shown = r.status == ReviewStatus.PUBLISHED
    return control.HandlerResult(
        result={"review_id": str(r.id), "status": r.status.value}, undo={"review_id": str(r.id)} if shown else None,
        summary="Đã hiện đánh giá" if shown else "AI giữ lại đánh giá bị gắn cờ (không tự hiện)",
        ref_type="reviews", ref_id=r.id,
    )  # fmt: skip


@control.undoer("catalog.publish_review")
async def _hide_review(ctx: control.UndoContext) -> None:
    r = await ctx.db.get(Review, uuid.UUID(ctx.undo["review_id"]))
    if r is not None:
        await review_svc.hide(ctx.db, r)


@control.on_returned("catalog.publish_review")
async def _reject_review(ctx: control.ReturnContext) -> None:
    r = await ctx.db.get(Review, uuid.UUID(str(ctx.item.payload["review_id"])))
    if r is not None:
        await review_svc.hide(ctx.db, r, ReviewStatus.REJECTED)


# ---- nhờ tìm -----------------------------------------------------------------------------------------------------


@control.handler("catalog.publish_find_request")
async def _publish_find(ctx: control.ActionContext) -> control.HandlerResult:
    fr = await find_svc.get(ctx.db, _uuid(ctx, "find_request_id"))
    await find_svc.publish(ctx.db, fr, title=ctx.payload.get("title"), mode=ctx.mode,
                           hide=ctx.preview.get("recommend") == "hide")  # fmt: skip
    shown = fr.status != FindRequestStatus.REJECTED
    return control.HandlerResult(
        result={"find_request_id": str(fr.id), "status": fr.status.value},
        undo={"find_request_id": str(fr.id)} if shown else None,
        summary="Đã hiện lời nhờ tìm" if shown else "AI không tự hiện lời nhờ tìm bị gắn cờ",
        ref_type="find_requests", ref_id=fr.id,
    )  # fmt: skip


@control.undoer("catalog.publish_find_request")
async def _hide_find(ctx: control.UndoContext) -> None:
    fr = await ctx.db.get(FindRequest, uuid.UUID(ctx.undo["find_request_id"]))
    if fr is not None:
        fr.status = FindRequestStatus.REJECTED
        await ctx.db.flush()


@control.on_returned("catalog.publish_find_request")
async def _reject_find(ctx: control.ReturnContext) -> None:
    fr = await ctx.db.get(FindRequest, uuid.UUID(str(ctx.item.payload["find_request_id"])))
    if fr is not None and fr.status == FindRequestStatus.PENDING_REVIEW:
        fr.status = FindRequestStatus.REJECTED
        fr.moderation_note = ctx.note
        await ctx.db.flush()


# ---- «Hôm nay» ---------------------------------------------------------------------------------------------------


@control.stat_provider("catalog.overview", order=40)
async def _stats(db: AsyncSession) -> list[control.Stat]:
    async def n(q):  # type: ignore[no-untyped-def]
        return (await db.execute(q)).scalar_one()

    on_shelf = await n(select(func.count()).where(ProductModel.status == ProductStatus.PUBLISHED))
    open_drops = await n(select(func.count()).where(Drop.status == DropStatus.OPEN))
    reviews = await n(select(func.count()).where(Review.status == ReviewStatus.PENDING_REVIEW))
    finds = await n(select(func.count()).where(FindRequest.status == FindRequestStatus.THRESHOLD_REACHED))
    return [
        control.Stat(key="catalog.on_shelf", label="Món trên kệ", value=on_shelf, href="/desk/san-pham", order=40),
        control.Stat(
            key="catalog.open_drops", label="Đợt đang mở", value=open_drops, href="/desk/san-pham/dot", order=41
        ),
        control.Stat(
            key="catalog.pending_reviews",
            label="Đánh giá chờ duyệt",
            value=reviews,
            href="/desk/san-pham/danh-gia",
            order=42,
        ),
        control.Stat(
            key="catalog.find_threshold", label="Nhờ tìm đủ người", value=finds, href="/desk/san-pham/nho-tim", order=43
        ),
    ]


# ---- lệnh bằng lời (i6): mở / đóng đợt mua chung ------------------------------------------------------------------

control.register_action(
    "catalog.close_drop", "Đóng đợt bán sớm", GROUP, default="ask", customer_facing=True,
    description="Chị bảo AI đóng đợt trước hạn chót: khách không đặt thêm được, đơn của đợt được chốt.",
)  # fmt: skip


@control.handler("catalog.close_drop")
async def _close_drop(ctx: control.ActionContext) -> control.HandlerResult:
    d = await drop_svc.get_drop(ctx.db, _uuid(ctx, "drop_id"))
    await drop_svc.close_drop(ctx.db, d, reason="chị bảo đóng bằng lời", user=ctx.user)
    return control.HandlerResult(result={"drop_id": str(d.id), "status": d.status.value},
                                 summary=f"Đã đóng {drop_svc.label(d)}", ref_type="drops", ref_id=d.id)  # fmt: skip


class DropParams(BaseModel):
    drop: str | None = Field(default=None, description="Số đợt (vd «12» trong «đợt 12») hoặc tên đợt, đúng như chị nói")


async def _find_drop(ctx: control.CommandContext, params: DropParams | None, statuses: tuple[DropStatus, ...]):
    """Đợt khớp lời chị trong các trạng thái cho phép: «đợt 12» → mã D12, không thì so tên đợt."""
    rows = list((await ctx.db.execute(select(Drop).where(Drop.status.in_(statuses)))).scalars())
    query = (params.drop if params and params.drop else None) or ctx.text
    m = re.search(r"\b(?:dot|d)\s*(\d+)\b", unidecode(query).lower()) or re.fullmatch(r"\s*(\d+)\s*", query)
    if m:
        hit = [d for d in rows if d.code == f"D{m.group(1)}"]
        if hit:
            return hit
    ids = control.match_names(query, [(d.id, d.title) for d in rows])
    if not ids and len(rows) == 1 and not m:
        return rows  # chỉ có một đợt hợp lệ và chị không nói rõ đợt nào
    return [d for d in rows if d.id in ids]


def _ask_drop(found: list[Drop], what: str) -> control.CommandResult:
    if not found:
        msg = f"Em không thấy đợt nào {what} được. Chị nói số đợt (vd «đợt 12») hoặc tên đợt nhé."
    else:
        msg = "Chị muốn đợt nào: " + "; ".join(f"{drop_svc.label(d)} «{d.title}»" for d in found[:4]) + "?"
    return control.CommandResult(message=msg, status="needs_clarification", href="/desk/san-pham/dot")


@control.intent(
    "catalog.open_drop",
    "Mở đợt mua chung",
    "Mở một đợt đang soạn cho khách đặt. Đợt mở được đưa vào hàng chờ để chị xem lại trước khi khách thấy.",
    params=DropParams,
    examples=["mở đợt 12", "mở đợt mua chung đồ bếp gọn"],
)
async def _open_drop_cmd(ctx: control.CommandContext, params: DropParams | None) -> control.CommandResult:
    found = await _find_drop(ctx, params, drop_svc.OPENABLE)
    if len(found) != 1:
        return _ask_drop(found, "đang soạn để mở")
    d = found[0]
    # Như nút «Mở đợt» nhưng không tự duyệt thay chị: lời nói có thể bị hiểu nhầm đợt, nên để chị xem lại.
    await drop_svc._validate_openable(ctx.db, d)
    out = await control.propose(
        "catalog.open_drop", f"Mở {drop_svc.label(d)}: {d.title}", {"drop_id": str(d.id)},
        {"title": d.title, "closes_at": d.closes_at.isoformat() if d.closes_at else None, "items": len(d.items),
         "slots": sum(i.slots_total or 0 for i in d.items)},
        db=ctx.db, summary=f"Chị bảo mở bằng lời: «{ctx.text}»", ref_type="drops", ref_id=d.id,
        dedupe_key=f"drop:{d.id}", ai_generated=False,
    )  # fmt: skip
    if out.status == "pending":
        d.approval_item_id = out.item_id
        d.status = DropStatus.PENDING_REVIEW
        await ctx.db.flush()
    return control.CommandResult.from_outcome(
        out, href=f"/desk/san-pham/dot/{d.id}", data={"drop_id": str(d.id)},
        done=f"Đã mở {drop_svc.label(d)} «{d.title}».",
        pending=f"Em đã đưa việc mở {drop_svc.label(d)} «{d.title}» vào hàng chờ, chị duyệt là đợt mở.",
    )  # fmt: skip


@control.intent(
    "catalog.close_drop",
    "Đóng đợt mua chung",
    "Đóng sớm một đợt đang mở (trước hạn chót). Đi qua hàng chờ theo mức tự chủ của «Đóng đợt bán sớm».",
    params=DropParams,
    examples=["dừng nhận đơn đợt 11", "đóng đợt 11", "đóng đợt mua chung đồ bếp gọn"],
)
async def _close_drop_cmd(ctx: control.CommandContext, params: DropParams | None) -> control.CommandResult:
    if ctx.user is None or ctx.user.role != UserRole.OWNER:  # cùng quyền với nút «Đóng đợt»
        raise Forbidden("Chỉ chị (chủ cửa hàng) đóng được đợt.")
    found = await _find_drop(ctx, params, (DropStatus.OPEN, DropStatus.SCHEDULED))
    if len(found) != 1:
        return _ask_drop(found, "đang mở để đóng")
    d = found[0]
    out = await control.propose(
        "catalog.close_drop", f"Đóng sớm {drop_svc.label(d)}: {d.title}", {"drop_id": str(d.id)},
        {"title": d.title, "closes_at": d.closes_at.isoformat() if d.closes_at else None},
        db=ctx.db, summary=f"Chị bảo đóng bằng lời: «{ctx.text}»", ref_type="drops", ref_id=d.id,
        dedupe_key=f"drop-close:{d.id}", ai_generated=False,
    )  # fmt: skip
    return control.CommandResult.from_outcome(
        out, href=f"/desk/san-pham/dot/{d.id}", data={"drop_id": str(d.id)},
        done=f"Đã đóng {drop_svc.label(d)} «{d.title}».",
        pending=f"Em đã đưa việc đóng {drop_svc.label(d)} «{d.title}» vào hàng chờ, chị duyệt là đợt đóng.",
    )  # fmt: skip
