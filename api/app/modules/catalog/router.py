"""Route của catalog. `/api/store/catalog/**` công khai cho khách; `/api/desk/catalog/**` cho chị và người phụ."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core import ratelimit
from app.core.config import settings
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, NotFound
from app.core.pagination import Page, Paginated, paginate
from app.core.security import random_token
from app.modules.catalog import dossier as dossier_svc
from app.modules.catalog import drops as drop_svc
from app.modules.catalog import finds as find_svc
from app.modules.catalog import products as product_svc
from app.modules.catalog import public, stop_selling, tracking
from app.modules.catalog import reviews as review_svc
from app.modules.catalog.images import MAX_UPLOAD_BYTES
from app.modules.catalog.models import (
    Category,
    Drop,
    DropReminder,
    DropStatus,
    FindRequest,
    FindRequestStatus,
    FindRequestVote,
    ImageKind,
    Product,
    ProductStatus,
    Review,
    ReviewStatus,
)
from app.modules.catalog.products import image_set, primary_image
from app.modules.catalog.ratelimit import limit
from app.modules.catalog.schemas import (
    AboutOut,
    ArrivedIn,
    CategoryOut,
    DeskDrop,
    DeskFindRequest,
    DeskImageSet,
    DeskProduct,
    DeskProductRow,
    DeskReview,
    DossierOut,
    DropDetail,
    DropIn,
    DropItemOut,
    DropOut,
    DropPatch,
    DropsOverview,
    FindCreated,
    FindRequestIn,
    FindRequestOut,
    FindRequestsPage,
    FindStatusIn,
    FromCandidateIn,
    ImageOrderIn,
    ProductDetail,
    ProductOut,
    ProductPatch,
    ProductPipelineRow,
    PublicStatus,
    ReminderIn,
    ReminderOut,
    ResumeIn,
    ReviewInvite,
    ReviewReplyIn,
    RewriteIn,
    SalesOut,
    SelectableCandidate,
    SelectionTrailOut,
    ShelfOut,
    SitemapEntry,
    StopIn,
    StopPlanOut,
    StopRunOut,
    SupplierImageOption,
    SupplierImagesIn,
    VoiceIssue,
    VoteIn,
    VoteOut,
)
from app.modules.catalog.textutil import hash_key, matches_vi
from app.modules.control.models import ApprovalItem, ApprovalStatus
from app.modules.sourcing.models import Candidate, CandidateStage

store = APIRouter(prefix="/api/store/catalog", tags=["catalog (khách)"])
desk = APIRouter(prefix="/api/desk/catalog", tags=["catalog (desk)"])
routers = [store, desk]

DEVICE_COOKIE = "hc_dev"


def device_key(request: Request, response: Response) -> str:
    """Mã thiết bị ẩn danh (cookie httpOnly, 1 năm) → băm. Dùng cho «mình cũng cần» và chống gửi trùng."""
    raw = request.cookies.get(DEVICE_COOKIE)
    if not raw or len(raw) > 64:
        raw = random_token(16)
        response.set_cookie(
            DEVICE_COOKIE, raw, max_age=365 * 24 * 3600, httponly=True, samesite="lax", secure=settings.cookie_secure
        )
    return hash_key("device", raw)


def client_ip(request: Request) -> str:
    return ratelimit.client_ip(request)


# ==== khách =======================================================================================================


@store.get("/shelf", response_model=ShelfOut)
async def shelf(
    db: DbSession,
    nhom: Annotated[str | None, Query(max_length=140, description="slug nhóm hàng")] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> Any:
    return await public.shelf(db, category=nhom, q=q)


@store.get("/products/{slug}", response_model=ProductDetail)
async def product(slug: str, db: DbSession) -> Any:
    return await public.product_detail(db, await product_svc.get_by_slug(db, slug))


@store.get("/drops", response_model=DropsOverview)
async def drops_overview(db: DbSession) -> Any:
    return await public.drops_overview(db)


@store.get("/drops/{slug}", response_model=DropDetail)
async def drop_detail(slug: str, db: DbSession) -> Any:
    return await public.drop_detail(db, await drop_svc.get_by_slug(db, slug))


@store.post("/drops/{slug}/remind", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def drop_remind(slug: str, body: ReminderIn, request: Request, db: DbSession) -> Any:
    await limit(f"remind:{client_ip(request)}", 10, 600)
    d = await drop_svc.get_by_slug(db, slug)
    return {"added": await drop_svc.add_reminder(db, d, body.contact)}


@store.get("/about", response_model=AboutOut)
async def about(db: DbSession) -> Any:
    return await public.about(db)


async def _public_find(
    db: AsyncSession, fr: FindRequest, *, voted: bool = False, trying: int | None = None
) -> dict[str, Any]:
    if trying is None:
        trying = (await find_svc.trying_counts(db, [fr.brief_id])).get(fr.brief_id, 0) if fr.brief_id else 0
    slug = None
    if fr.product_id:
        p = await db.get(Product, fr.product_id)
        slug = p.slug if p and p.status == ProductStatus.PUBLISHED else None
    return {
        "slug": fr.public_slug,
        "title": fr.title,
        "description": fr.description,
        "budget_vnd": fr.budget_vnd,
        "vote_count": fr.vote_count,
        "vote_threshold": fr.vote_threshold,
        "status": find_svc.public_status(fr, trying),
        "voted": voted,
        "product_slug": slug,
        "created_at": fr.created_at,
    }


@store.get("/finds", response_model=FindRequestsPage)
async def finds(request: Request, db: DbSession) -> Any:
    rows = list(
        (
            await db.execute(
                select(FindRequest)
                .where(FindRequest.status.in_(find_svc.PUBLIC))
                .order_by(FindRequest.vote_count.desc(), FindRequest.created_at.desc())
                .limit(100)
            )
        ).scalars()
    )
    raw = request.cookies.get(DEVICE_COOKIE)
    voted: set[uuid.UUID] = set()
    if raw:
        key = hash_key("device", raw)
        voted = set(
            (
                await db.execute(
                    select(FindRequestVote.find_request_id).where(
                        FindRequestVote.voter_key == key, FindRequestVote.find_request_id.in_([r.id for r in rows])
                    )
                )
            ).scalars()
        )
    trying = await find_svc.trying_counts(db, [r.brief_id for r in rows if r.brief_id])
    items = [
        await _public_find(db, r, voted=r.id in voted, trying=trying.get(r.brief_id, 0) if r.brief_id else 0)
        for r in rows
    ]
    return {"items": items, "total": len(items), "threshold": await find_svc.threshold(db)}


@store.post("/finds", response_model=FindCreated, status_code=status.HTTP_201_CREATED)
async def create_find(body: FindRequestIn, request: Request, response: Response, db: DbSession) -> Any:
    if body.website:  # ô bẫy: người thật không điền
        raise BadRequest("Không gửi được yêu cầu này.", code="spam")
    await limit(f"find:{client_ip(request)}", 20, 3600)
    key = device_key(request, response)
    fr, dup = await find_svc.create(
        db, title=body.title, description=body.description, budget_vnd=body.budget_vnd,
        contact_name=body.contact_name, contact=body.contact, device_key=key,
    )  # fmt: skip
    await db.refresh(fr)
    return {"request": await _public_find(db, fr, voted=True), "duplicate": dup,
            "visible": fr.status in find_svc.PUBLIC}  # fmt: skip


@store.post("/finds/{slug}/vote", response_model=VoteOut)
async def vote(slug: str, request: Request, response: Response, db: DbSession, body: VoteIn | None = None) -> Any:
    await limit(f"vote:{client_ip(request)}", 60, 600)
    fr = await find_svc.get_public(db, slug)
    added = await find_svc.vote(db, fr, device_key(request, response), contact=body.contact if body else None)
    await db.refresh(fr)
    return {"request": await _public_find(db, fr, voted=True), "added": added}


async def _invite(db: AsyncSession, r: Review) -> dict[str, Any]:
    p = await db.get(Product, r.product_id)
    if p is None:
        raise NotFound("Món này không còn trên kệ.")
    img = primary_image(p)
    return {
        "status": r.status, "product_name": p.name, "product_slug": p.slug,
        "product_image": image_set(img) if img else None, "display_name": r.display_name,
        "rating": r.rating, "body": r.body, "choice_reason": r.choice_reason,
    }  # fmt: skip


@store.get("/reviews/{token}", response_model=ReviewInvite)
async def review_invite(token: str, db: DbSession) -> Any:
    return await _invite(db, await review_svc.get_by_token(db, token))


@store.post("/reviews/{token}", response_model=ReviewInvite)
async def submit_review(
    token: str,
    request: Request,
    db: DbSession,
    rating: Annotated[int, Form(ge=1, le=5)],
    body: Annotated[str | None, Form(max_length=2000)] = None,
    display_name: Annotated[str | None, Form(max_length=60)] = None,
    choice_reason: Annotated[str | None, Form(max_length=review_svc.MAX_REASON)] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
) -> Any:
    await limit(f"review:{client_ip(request)}", 10, 600)
    r = await review_svc.get_by_token(db, token)
    files = [f for f in (photos or []) if f.filename]
    # kiểm số lượng và cỡ TRƯỚC khi đọc vào bộ nhớ (route công khai: tệp khổng lồ không được làm sập máy chủ)
    if len(files) > review_svc.MAX_PHOTOS:
        raise BadRequest(f"Tối đa {review_svc.MAX_PHOTOS} ảnh.")
    if any((f.size or 0) > MAX_UPLOAD_BYTES for f in files):
        raise BadRequest("Ảnh lớn quá 15 MB, bạn chọn ảnh nhỏ hơn nhé.", code="image_too_large")
    blobs = [await f.read() for f in files]
    await review_svc.submit(db, r, rating=rating, body=body, display_name=display_name, photos=blobs,
                            choice_reason=choice_reason)  # fmt: skip
    return await _invite(db, r)


@store.get("/feed.xml", include_in_schema=False)
async def feed(db: DbSession) -> Response:
    return Response(await public.merchant_feed(db), media_type="application/xml; charset=utf-8")


@store.get("/sitemap", response_model=list[SitemapEntry])
async def sitemap(db: DbSession) -> Any:
    return await public.sitemap(db)


# ==== desk: sản phẩm ==============================================================================================


def _row(p: Product) -> dict[str, Any]:
    img = primary_image(p)
    return {
        "id": p.id, "slug": p.slug, "name": p.name, "status": p.status, "price_vnd": p.price_vnd,
        "selected_count": p.selected_count, "considered_count": p.considered_count,
        "image": image_set(img) if img else None, "approval_item_id": p.approval_item_id,
        "ai_generated": p.ai_generated, "review_count": p.review_count, "rating_avg": p.rating_avg,
        "updated_at": p.updated_at,
    }  # fmt: skip


async def _desk_product(db: AsyncSession, p: Product) -> DeskProduct:
    await db.refresh(p, ["images"])
    c = await db.get(Candidate, p.candidate_id) if p.candidate_id else None
    return DeskProduct(
        **ProductOut.model_validate(p).model_dump(),
        images=[
            DeskImageSet(**image_set(i), source="supplier" if i.kind == ImageKind.SUPPLIER else "own")
            for i in sorted(p.images, key=lambda i: i.position)
        ],
        candidate_title=c.title_vi if c else None,
        voice_issues=[VoiceIssue.model_validate(i) for i in product_svc.voice_issues(p)],
    )


@desk.get("/products", response_model=Paginated[DeskProductRow])
async def list_products(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    status_: Annotated[ProductStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> Any:
    stmt = select(Product).order_by(Product.updated_at.desc())
    if status_:
        stmt = stmt.where(Product.status == status_)
    if q:
        rows = [p for p in (await db.execute(stmt)).scalars() if matches_vi(f"{p.name} {p.subtitle or ''}", q)]
        sliced = rows[page.offset : page.offset + page.size]
        return {"items": [_row(p) for p in sliced], "total": len(rows), "page": page.page, "size": page.size,
                "pages": (len(rows) + page.size - 1) // page.size}  # fmt: skip
    return await paginate(db, stmt, page, _row)


@desk.get("/candidates/selectable", response_model=list[SelectableCandidate])
async def selectable(_: CurrentUser, db: DbSession) -> Any:
    """Ứng viên đã chọn mà chưa có sản phẩm (lưới an toàn khi lỡ sự kiện candidate.selected)."""
    have = select(Product.candidate_id).where(Product.candidate_id.is_not(None))
    rows = (
        await db.execute(
            select(Candidate)
            .where(Candidate.stage == CandidateStage.SELECTED, Candidate.id.not_in(have))
            .order_by(Candidate.stage_changed_at.desc().nulls_last())
            .limit(50)
        )
    ).scalars()
    return list(rows)


@desk.post("/products/from-candidate", response_model=DeskProduct, status_code=status.HTTP_201_CREATED)
async def from_candidate(body: FromCandidateIn, _: CurrentUser, db: DbSession) -> Any:
    c = await db.get(Candidate, body.candidate_id)
    if c is None or c.stage != CandidateStage.SELECTED:
        raise BadRequest("Chỉ ứng viên đã được chọn mới thành sản phẩm.", code="not_selected")
    p = await product_svc.draft_from_candidate(db, c.id)
    assert p is not None
    if not p.ai_generated:
        await product_svc.write_page(db, p)
    return await _desk_product(db, p)


@desk.get("/products/pipeline", response_model=list[ProductPipelineRow])
async def products_pipeline(_: CurrentUser, db: DbSession) -> Any:
    """Tình trạng hai chiều của mọi món (danh sách Sản phẩm): đã chọn ngày nào, thử bao lâu · nội dung x/6 →
    kênh đang bán → đơn."""
    return await tracking.pipeline_rows(db)


@desk.get("/categories", response_model=list[CategoryOut])
async def categories(_: CurrentUser, db: DbSession) -> Any:
    return list((await db.execute(select(Category).order_by(Category.position, Category.name))).scalars())


@desk.get("/products/{product_id}", response_model=DeskProduct)
async def get_product(product_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    return await _desk_product(db, await product_svc.get_product(db, product_id))


@desk.get("/products/{product_id}/dossier", response_model=DossierOut)
async def product_dossier(product_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    """Hồ sơ chọn (e2) — chỉ ở desk: website không hiện quá trình chọn."""
    return await dossier_svc.dossier_view(db, await product_svc.get_product(db, product_id))


@desk.get("/products/{product_id}/selection", response_model=SelectionTrailOut)
async def product_selection(product_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    """Hồ sơ chọn — dấu vết từng bước: đề săn hàng, thẩm định, mua mẫu, thử, quyết định, giá vốn (chỉ đọc)."""
    return await tracking.selection_trail(db, await product_svc.get_product(db, product_id))


@desk.get("/products/{product_id}/sales", response_model=SalesOut)
async def product_sales(product_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    """Hồ sơ bán: nội dung từng kênh → đã lên kênh nào → khách phản hồi và đặt (chỉ đọc)."""
    return await tracking.sales_view(db, await product_svc.get_product(db, product_id))


@desk.patch("/products/{product_id}", response_model=DeskProduct)
async def patch_product(product_id: uuid.UUID, body: ProductPatch, user: CurrentUser, db: DbSession) -> Any:
    p = await product_svc.get_product(db, product_id)
    data = body.model_dump(exclude_unset=True, mode="json")
    if data.get("category_id"):
        data["category_id"] = uuid.UUID(data["category_id"])
        if await db.get(Category, data["category_id"]) is None:
            raise BadRequest("Nhóm hàng không tồn tại.")
    if data.get("sale_mode"):
        data["sale_mode"] = body.sale_mode
    await product_svc.update_product(db, p, data, user)
    return await _desk_product(db, p)


@desk.post("/products/{product_id}/rewrite", response_model=DeskProduct)
async def rewrite(product_id: uuid.UUID, body: RewriteIn, _: CurrentUser, db: DbSession) -> Any:
    p = await product_svc.get_product(db, product_id)
    await product_svc.write_page(db, p, note=body.note)
    return await _desk_product(db, p)


@desk.post("/products/{product_id}/publish", response_model=DeskProduct)
async def publish_product(product_id: uuid.UUID, user: OwnerUser, db: DbSession) -> Any:
    p = await product_svc.get_product(db, product_id)
    await product_svc.owner_publish(db, p, user)
    return await _desk_product(db, p)


@desk.post("/products/{product_id}/unpublish", response_model=DeskProduct)
async def unpublish_product(product_id: uuid.UUID, user: OwnerUser, db: DbSession) -> Any:
    p = await product_svc.get_product(db, product_id)
    await product_svc.unpublish(db, p, user)
    return await _desk_product(db, p)


@desk.get("/products/{product_id}/stop-plan", response_model=StopPlanOut)
async def stop_plan(product_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    """«Ngừng bán»: mọi nơi món đang có (website, lịch đăng, bài đã đăng, sàn, đợt đang mở) + lần ngừng bán gần nhất."""
    return await stop_selling.plan(db, await product_svc.get_product(db, product_id))


@desk.post("/products/{product_id}/stop", response_model=StopRunOut)
async def stop_product(product_id: uuid.UUID, body: StopIn, user: OwnerUser, db: DbSession) -> Any:
    p = await product_svc.get_product(db, product_id)
    act = await stop_selling.stop(db, p, user, body.model_dump())
    await db.refresh(p)
    return {"product": await _desk_product(db, p), "steps": (act.result or {}).get("steps", []), "activity_id": act.id}


@desk.post("/products/{product_id}/resume", response_model=StopRunOut)
async def resume_product(product_id: uuid.UUID, user: OwnerUser, db: DbSession, body: ResumeIn | None = None) -> Any:
    p = await product_svc.get_product(db, product_id)
    steps = await stop_selling.resume(db, p, user, (body or ResumeIn()).model_dump()["overdue"])
    await db.refresh(p)
    return {"product": await _desk_product(db, p), "steps": steps}


@desk.post("/products/{product_id}/images", response_model=DeskProduct, status_code=status.HTTP_201_CREATED)
async def upload_image(
    product_id: uuid.UUID, _: CurrentUser, db: DbSession, file: Annotated[UploadFile, File()],
    alt: Annotated[str | None, Form(max_length=300)] = None,
) -> Any:  # fmt: skip
    p = await product_svc.get_product(db, product_id)
    data = await file.read()
    if not data:
        raise BadRequest("Tệp ảnh trống.")
    await product_svc.upload_image(db, p, data, alt=alt)
    return await _desk_product(db, p)


@desk.get("/products/{product_id}/supplier-images", response_model=list[SupplierImageOption])
async def supplier_images(product_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    """Ảnh nhà cung cấp trong hồ sơ ứng viên của món (chỉ desk) — để chị chọn dùng lại."""
    return await product_svc.supplier_image_options(db, await product_svc.get_product(db, product_id))


@desk.post("/products/{product_id}/supplier-images", response_model=DeskProduct, status_code=status.HTTP_201_CREATED)
async def use_supplier_images(product_id: uuid.UUID, body: SupplierImagesIn, _: CurrentUser, db: DbSession) -> Any:
    """Chị tích ảnh nhà cung cấp → chép thành ảnh sản phẩm, xử lý như ảnh chị tải lên."""
    p = await product_svc.get_product(db, product_id)
    await product_svc.import_supplier_images(db, p, body.urls)
    return await _desk_product(db, p)


@desk.put("/products/{product_id}/images/order", response_model=DeskProduct)
async def order_images(product_id: uuid.UUID, body: ImageOrderIn, _: CurrentUser, db: DbSession) -> Any:
    p = await product_svc.get_product(db, product_id)
    await product_svc.reorder_images(db, p, body.ids)
    return await _desk_product(db, p)


@desk.post("/products/{product_id}/images/{image_id}/primary", response_model=DeskProduct)
async def primary(product_id: uuid.UUID, image_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    p = await product_svc.get_product(db, product_id)
    await product_svc.set_primary(db, p, image_id)
    return await _desk_product(db, p)


@desk.delete("/products/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(product_id: uuid.UUID, image_id: uuid.UUID, _: CurrentUser, db: DbSession) -> None:
    p = await product_svc.get_product(db, product_id)
    await product_svc.delete_image(db, p, image_id)


# ==== desk: đợt ===================================================================================================


async def _desk_drop(db: AsyncSession, d: Drop) -> DeskDrop:
    await db.refresh(d, ["items"])
    reminders = (await db.execute(select(func.count()).where(DropReminder.drop_id == d.id))).scalar_one()
    names = dict(
        (
            await db.execute(select(Product.id, Product.name).where(Product.id.in_([i.product_id for i in d.items])))
        ).all()
    )
    return DeskDrop(
        **DropOut.model_validate(d).model_dump(),
        items=[DropItemOut.model_validate(i) for i in d.items],
        label=drop_svc.label(d),
        reminder_count=reminders,
        product_names={str(k): v for k, v in names.items()},
    )


@desk.get("/drops", response_model=Paginated[DeskDrop])
async def list_drops(
    _: CurrentUser, db: DbSession, page: Page, status_: Annotated[DropStatus | None, Query(alias="status")] = None
) -> Any:
    stmt = select(Drop).order_by(Drop.created_at.desc())
    if status_:
        stmt = stmt.where(Drop.status == status_)
    res = await paginate(db, stmt, page, lambda d: d)
    return {**res.model_dump(exclude={"items"}), "items": [await _desk_drop(db, d) for d in res.items]}


@desk.post("/drops", response_model=DeskDrop, status_code=status.HTTP_201_CREATED)
async def create_drop(body: DropIn, user: CurrentUser, db: DbSession) -> Any:
    data = body.model_dump()
    d = await drop_svc.create_drop(db, data, user)
    return await _desk_drop(db, d)


@desk.get("/drops/{drop_id}", response_model=DeskDrop)
async def get_drop(drop_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Any:
    return await _desk_drop(db, await drop_svc.get_drop(db, drop_id))


@desk.patch("/drops/{drop_id}", response_model=DeskDrop)
async def patch_drop(drop_id: uuid.UUID, body: DropPatch, user: CurrentUser, db: DbSession) -> Any:
    d = await drop_svc.get_drop(db, drop_id)
    data = body.model_dump(exclude_unset=True)
    await drop_svc.update_drop(db, d, data, user)
    return await _desk_drop(db, d)


@desk.post("/drops/{drop_id}/open", response_model=DeskDrop)
async def open_drop(drop_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Any:
    d = await drop_svc.get_drop(db, drop_id)
    await db.refresh(d, ["items"])
    await drop_svc.request_open(db, d, user)
    return await _desk_drop(db, d)


@desk.post("/drops/{drop_id}/close", response_model=DeskDrop)
async def close_drop(drop_id: uuid.UUID, user: OwnerUser, db: DbSession) -> Any:
    d = await drop_svc.get_drop(db, drop_id)
    await drop_svc.close_drop(db, d, reason="chị đóng", user=user)
    return await _desk_drop(db, d)


@desk.post("/drops/{drop_id}/arrived", response_model=DeskDrop)
async def arrived(drop_id: uuid.UUID, body: ArrivedIn, user: OwnerUser, db: DbSession) -> Any:
    d = await drop_svc.get_drop(db, drop_id)
    await drop_svc.mark_arrived(db, d, body.arrived_on, user)
    return await _desk_drop(db, d)


@desk.post("/drops/{drop_id}/cancel", response_model=DeskDrop)
async def cancel(drop_id: uuid.UUID, user: OwnerUser, db: DbSession) -> Any:
    d = await drop_svc.get_drop(db, drop_id)
    await drop_svc.cancel_drop(db, d, user)
    return await _desk_drop(db, d)


# ==== desk: đánh giá ==============================================================================================


async def _pending_item(db: AsyncSession, action: str, dedupe_key: str) -> ApprovalItem | None:
    return (
        await db.execute(
            select(ApprovalItem).where(
                ApprovalItem.action == action,
                ApprovalItem.dedupe_key == dedupe_key,
                ApprovalItem.status.in_((ApprovalStatus.PENDING, ApprovalStatus.FAILED)),
            )
        )
    ).scalar_one_or_none()


async def _desk_review(db: AsyncSession, r: Review) -> DeskReview:
    out = DeskReview.model_validate(r)
    p = await db.get(Product, r.product_id)
    out.product_name = p.name if p else None
    out.photo_urls = [review_svc.photo_url(ph, 400) for ph in r.photos]
    return out


@desk.get("/reviews", response_model=Paginated[DeskReview])
async def list_reviews(
    _: CurrentUser, db: DbSession, page: Page, status_: Annotated[ReviewStatus | None, Query(alias="status")] = None
) -> Any:
    stmt = (
        select(Review).where(Review.status != ReviewStatus.REQUESTED).order_by(Review.submitted_at.desc().nulls_last())
    )
    if status_:
        stmt = select(Review).where(Review.status == status_).order_by(Review.updated_at.desc())
    res = await paginate(db, stmt, page, lambda r: r)
    return {**res.model_dump(exclude={"items"}), "items": [await _desk_review(db, r) for r in res.items]}


@desk.post("/reviews/{review_id}/approve", response_model=DeskReview)
async def approve_review(review_id: uuid.UUID, user: OwnerUser, db: DbSession) -> Any:
    r = await review_svc.get_review(db, review_id)
    item = await _pending_item(db, "catalog.publish_review", f"review:{r.id}")
    if item is not None:
        item = await control.approve(db, item.id, user)
        if item.status == ApprovalStatus.FAILED:
            raise BadRequest(item.error or "Chưa hiện được đánh giá.")
        await db.refresh(r)
    elif r.status in (ReviewStatus.PENDING_REVIEW, ReviewStatus.HIDDEN, ReviewStatus.REJECTED):
        await review_svc.publish(db, r, mode="approved")
    return await _desk_review(db, r)


@desk.post("/reviews/{review_id}/reject", response_model=DeskReview)
async def reject_review(review_id: uuid.UUID, body: RewriteIn, user: OwnerUser, db: DbSession) -> Any:
    r = await review_svc.get_review(db, review_id)
    item = await _pending_item(db, "catalog.publish_review", f"review:{r.id}")
    if item is not None:
        await control.return_item(db, item.id, user, body.note or "Chị không hiện đánh giá này")
        await db.refresh(r)
    else:
        await review_svc.hide(
            db, r, ReviewStatus.HIDDEN if r.status == ReviewStatus.PUBLISHED else ReviewStatus.REJECTED
        )
    return await _desk_review(db, r)


@desk.patch("/reviews/{review_id}", response_model=DeskReview)
async def reply_review(review_id: uuid.UUID, body: ReviewReplyIn, user: OwnerUser, db: DbSession) -> Any:
    r = await review_svc.get_review(db, review_id)
    if "owner_reply" in body.model_fields_set:
        r.owner_reply = (body.owner_reply or "").strip() or None
        await control.audit(db, "catalog.review_replied", user=user, entity_type="reviews", entity_id=r.id,
                            summary="Chị trả lời đánh giá")  # fmt: skip
    if body.reason_public is not None and body.reason_public != r.reason_public:
        r.reason_public = body.reason_public
        await control.audit(db, "catalog.review_reason_visibility", user=user, entity_type="reviews", entity_id=r.id,
                            summary="Chị hiện lý do chọn" if r.reason_public else "Chị ẩn lý do chọn")  # fmt: skip
    await db.flush()
    return await _desk_review(db, r)


# ==== desk: nhờ tìm ===========================================================================================


async def _desk_find(db: AsyncSession, fr: FindRequest) -> DeskFindRequest:
    trying = (await find_svc.trying_counts(db, [fr.brief_id])).get(fr.brief_id, 0) if fr.brief_id else 0
    return DeskFindRequest(
        **FindRequestOut.model_validate(fr).model_dump(),
        public_status=PublicStatus(**find_svc.public_status(fr, trying)),
    )


@desk.get("/finds", response_model=Paginated[DeskFindRequest])
async def list_finds(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    status_: Annotated[FindRequestStatus | None, Query(alias="status")] = None,
) -> Any:
    stmt = select(FindRequest).order_by(FindRequest.vote_count.desc(), FindRequest.created_at.desc())
    if status_:
        stmt = stmt.where(FindRequest.status == status_)
    res = await paginate(db, stmt, page, lambda r: r)
    return {**res.model_dump(exclude={"items"}), "items": [await _desk_find(db, r) for r in res.items]}


@desk.post("/finds/{find_id}/approve", response_model=DeskFindRequest)
async def approve_find(find_id: uuid.UUID, user: OwnerUser, db: DbSession) -> Any:
    fr = await find_svc.get(db, find_id)
    item = await _pending_item(db, "catalog.publish_find_request", f"find:{fr.id}")
    if item is not None:
        item = await control.approve(db, item.id, user)
        if item.status == ApprovalStatus.FAILED:
            raise BadRequest(item.error or "Chưa hiện được.")
        await db.refresh(fr)
    elif fr.status in (FindRequestStatus.PENDING_REVIEW, FindRequestStatus.REJECTED):
        fr.status = FindRequestStatus.PENDING_REVIEW
        await find_svc.publish(db, fr, title=None, mode="approved", hide=False)
    return await _desk_find(db, fr)


@desk.post("/finds/{find_id}/status", response_model=DeskFindRequest)
async def find_status(find_id: uuid.UUID, body: FindStatusIn, user: OwnerUser, db: DbSession) -> Any:
    fr = await find_svc.get(db, find_id)
    await find_svc.set_status(db, fr, body.model_dump(mode="json"), user)
    return await _desk_find(db, fr)
