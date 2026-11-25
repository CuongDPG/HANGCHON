"""Khai báo của catalog với control: hành động (mức tự chủ), handler, hoàn tác, trả lại, cài đặt, số liệu «Hôm nay».

Mức mặc định theo hướng thận trọng: mọi thứ khách nhìn thấy `ask`; xử lý ảnh (nội bộ, hoàn tác được) `auto`."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.errors import NotFound
from app.modules.catalog import drops as drop_svc
from app.modules.catalog import finds as find_svc
from app.modules.catalog import products as product_svc
from app.modules.catalog import reviews as review_svc
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
