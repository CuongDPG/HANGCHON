"""Sản phẩm (e1) và ảnh sản phẩm (e6).

Vòng đời: ứng viên được chọn → `products` nháp (ảnh chụp hồ sơ chọn) → AI viết trang → chờ chị (`catalog.publish_product`)
→ đăng (`product.published`). Chị sửa mọi trường ở desk trước khi duyệt."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.errors import BadRequest, NotFound
from app.core.storage import get_storage, new_key
from app.core.timeutil import now_utc
from app.modules.catalog import images as img_lib
from app.modules.catalog.ai_tasks import FactIn, WritePageIn, WritePageOut
from app.modules.catalog.dossier import Snapshot, build_snapshot, overclaims, spec_pairs, unsupported_numbers
from app.modules.catalog.models import ImageKind, ImageStatus, Product, ProductImage, ProductStatus
from app.modules.catalog.textutil import seller_address_issues, unique_slug
from app.modules.control.models import ApprovalItem, ApprovalStatus, User
from app.modules.sourcing.models import Candidate

log = logging.getLogger("app.catalog")

EDITABLE_FIELDS = (
    "name", "subtitle", "short_description", "description", "specs", "faq", "price_vnd", "compare_at_price_vnd",
    "category_id", "sale_mode", "reason_selected", "not_satisfied", "trial_days", "weight_grams", "origin_country",
    "brand", "gtin", "seo_title", "seo_description", "feed_enabled", "is_consumable", "reorder_days",
)  # fmt: skip


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> Product:
    p = await db.get(Product, product_id)
    if p is None:
        raise NotFound("Không tìm thấy sản phẩm.")
    return p


async def get_by_slug(db: AsyncSession, slug: str, *, public: bool = True) -> Product:
    q = select(Product).where(Product.slug == slug)
    if public:
        q = q.where(Product.status == ProductStatus.PUBLISHED)
    p = (await db.execute(q)).scalar_one_or_none()
    if p is None:
        raise NotFound("Không tìm thấy món này trên kệ.")
    return p


def _apply_snapshot(p: Product, snap: Snapshot, *, content_too: bool) -> None:
    p.considered_count = snap.considered_count
    p.selected_count = snap.selected_count
    p.rejected_alternatives = snap.rejected_alternatives
    p.dossier = snap.dossier
    if content_too:
        p.trial_days = snap.trial_days
        p.reason_selected = snap.reason_selected
        p.not_satisfied = snap.not_satisfied


async def draft_from_candidate(
    db: AsyncSession, candidate_id: uuid.UUID, decision_id: uuid.UUID | None = None
) -> Product | None:
    """Tạo (hoặc làm mới) sản phẩm nháp từ ứng viên đã chọn. Chạy lại không sinh trùng (`candidate_id` duy nhất)."""
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        log.warning("candidate.selected: không thấy ứng viên %s", candidate_id)
        return None
    snap = await build_snapshot(db, candidate, decision_id)
    existing = (await db.execute(select(Product).where(Product.candidate_id == candidate.id))).scalar_one_or_none()
    if existing is not None:
        # đã đăng thì không đè lời chị đã duyệt, chỉ làm mới số liệu sàng lọc
        _apply_snapshot(
            existing, snap, content_too=existing.status in (ProductStatus.DRAFT, ProductStatus.PENDING_REVIEW)
        )
        await db.flush()
        return existing
    a = snap.assessment
    p = Product(
        candidate_id=candidate.id,
        category_id=candidate.category_id,
        slug=await unique_slug(db, Product, candidate.title_vi),
        name=candidate.title_vi[:200],
        short_description=(a.summary if a else None),
        specs=[{"label": k, "value": v, "source": ref} for k, v, ref in spec_pairs(candidate, a)][:14],
        status=ProductStatus.DRAFT,
        origin_country=snap.origin_country,
        weight_grams=candidate.weight_grams,
        price_vnd=(snap.price.approved_price_vnd or 0) if snap.price else 0,
        landed_cost_vnd=snap.price.landed_cost_vnd if snap.price else None,
        shipping_notes=_shipping_notes(a.safety if a else {}),
    )
    _apply_snapshot(p, snap, content_too=True)
    db.add(p)
    await db.flush()
    await control.audit(
        db, "catalog.product_drafted", entity_type="products", entity_id=p.id,
        summary=f"Tạo sản phẩm nháp từ ứng viên đã chọn: {p.name}", data={"candidate_id": str(candidate.id)},
    )  # fmt: skip
    return p


def _shipping_notes(safety: dict[str, Any]) -> list[str]:
    labels = {
        "has_battery": "Có pin",
        "liquid": "Có chất lỏng",
        "fragile": "Dễ vỡ",
        "food_contact": "Tiếp xúc thực phẩm",
    }
    return [lbl for k, lbl in labels.items() if safety.get(k) is True]


async def write_page(db: AsyncSession, product: Product, *, note: str | None = None) -> control.ProposeOutcome:
    """AI viết tên, mô tả, thông số, hỏi–đáp CHỈ từ dữ kiện hồ sơ; kiểm số liệu và lời nói quá; rồi đưa chị duyệt."""
    if product.candidate_id is None:
        raise BadRequest("Sản phẩm này không gắn với ứng viên nào nên AI không có hồ sơ để viết.")
    candidate = await db.get(Candidate, product.candidate_id)
    if candidate is None:
        raise BadRequest("Không còn hồ sơ ứng viên của sản phẩm này.")
    snap = await build_snapshot(db, candidate)
    facts = {f.ref: f for f in snap.facts}
    res = await ai.run(
        "catalog.write_product_page",
        WritePageIn(
            working_title=product.name or candidate.title_vi,
            facts=[FactIn(**f.as_dict()) for f in snap.facts],
            owner_note=note,
        ),
        WritePageOut,
    )
    out = res.output
    checks: dict[str, Any] = {"dropped_specs": [], "dropped_faq": [], "unsupported_numbers": [], "overclaims": []}
    specs = []
    for s in out.specs:
        src = facts.get(s.ref)
        if src is None or unsupported_numbers(s.value, [src.text]):
            checks["dropped_specs"].append(f"{s.label}: {s.value}")
            continue
        specs.append({"label": s.label, "value": s.value, "source": src.label})
    faq = []
    for f in out.faq:
        refs = [facts[r] for r in f.refs if r in facts]
        if not refs or unsupported_numbers(f.a, [r.text for r in refs]):
            checks["dropped_faq"].append(f.q)
            continue
        faq.append({"q": f.q, "a": f.a, "source": " · ".join(dict.fromkeys(r.label for r in refs))})
    all_text = [f.text for f in snap.facts]
    for field_name in ("name", "subtitle", "short_description", "description"):
        value = getattr(out, field_name)
        bad = unsupported_numbers(value, all_text)
        if bad:
            checks["unsupported_numbers"].append({"field": field_name, "numbers": sorted(bad)})
        checks["overclaims"] += overclaims(value)
    checks["overclaims"] = sorted(set(checks["overclaims"]))

    product.name = out.name.strip() or product.name
    product.subtitle = out.subtitle
    product.short_description = out.short_description
    product.description = out.description
    product.specs = specs or product.specs
    product.faq = faq
    product.seo_title = out.seo_title
    product.seo_description = out.seo_description
    product.ai_generated = True
    _apply_snapshot(product, snap, content_too=product.status in (ProductStatus.DRAFT, ProductStatus.PENDING_REVIEW))
    if product.status == ProductStatus.DRAFT:
        product.status = ProductStatus.PENDING_REVIEW
    await db.flush()
    checks["pronouns"] = [f"{i['field']}: «{i['quote']}» → gợi ý «{i['suggestion']}»" for i in voice_issues(product)]
    warnings = len(checks["dropped_specs"]) + len(checks["dropped_faq"]) + len(checks["unsupported_numbers"])
    warnings += len(checks["overclaims"]) + len(checks["pronouns"])
    outcome = await control.propose(
        "catalog.publish_product",
        f"Đăng trang sản phẩm: {product.name}",
        {"product_id": str(product.id)},
        {
            "name": product.name,
            "subtitle": product.subtitle,
            "price_vnd": product.price_vnd,
            "short_description": product.short_description,
            "reason_selected": product.reason_selected,
            "not_satisfied": product.not_satisfied,
            "faq_count": len(faq),
            "checks": checks,
            "href": f"/desk/san-pham/{product.id}",
        },
        db=db,
        summary=(
            "AI viết xong trang, "
            + (f"có {warnings} chỗ cần chị xem kỹ." if warnings else "không thấy chỗ lệch dữ liệu.")
        ),
        rationale="Viết từ hồ sơ thẩm định, ghi chú thử hàng và quyết định chọn; số liệu lạ và lời nói quá đã bị gạch ra.",
        ref_type="products",
        ref_id=product.id,
        ai_run_id=res.run_id,
        dedupe_key=f"product:{product.id}",
    )
    if outcome.status == "pending":
        product.approval_item_id = outcome.item_id
        await db.flush()
    return outcome


_VOICE_FIELDS = (
    ("name", "Tên"), ("subtitle", "Dòng phụ"), ("short_description", "Mô tả ngắn"), ("description", "Mô tả"),
    ("reason_selected", "Lý do chọn"), ("not_satisfied", "Điều chưa ưng"), ("seo_title", "Tiêu đề tìm kiếm"),
    ("seo_description", "Mô tả tìm kiếm"),
)  # fmt: skip


def voice_issues(product: Product) -> list[dict[str, str]]:
    """Chỗ trên trang (khách đọc) còn gọi người bán là «chị»: `path` (trường), `field` (nhãn), `quote`, `suggestion`.
    Lời trích trong ngoặc «…» (vd lời khách) và chữ như «chịu» không tính."""
    texts: list[tuple[str, str, str | None]] = [(k, label, getattr(product, k)) for k, label in _VOICE_FIELDS]
    for i, s in enumerate(product.specs or []):
        texts += [
            (f"specs.{i}.label", f"Thông số {i + 1}", s.get("label")),
            (f"specs.{i}.value", f"Thông số {i + 1}", s.get("value")),
        ]
    for i, f in enumerate(product.faq or []):
        texts += [
            (f"faq.{i}.q", f"Hỏi đáp {i + 1} (câu hỏi)", f.get("q")),
            (f"faq.{i}.a", f"Hỏi đáp {i + 1} (trả lời)", f.get("a")),
        ]
    out = []
    for path, label, text in texts:
        for hit in seller_address_issues(text if isinstance(text, str) else None):
            out.append({"path": path, "field": label, **hit})
    return out


def check_publishable(product: Product) -> None:
    if product.status == ProductStatus.STOPPED:
        raise BadRequest("Món này đang ngừng bán. Chị bấm «Mở bán lại» để đưa món lên lại mọi kênh.",
                         code="product_stopped")  # fmt: skip
    if not product.name.strip():
        raise BadRequest("Sản phẩm chưa có tên.")
    if product.price_vnd <= 0:
        raise BadRequest("Sản phẩm chưa có giá bán. Chị đặt giá trước khi đăng.", code="no_price")
    issues = voice_issues(product)
    if issues:
        first = issues[0]
        more = f" (và {len(issues) - 1} chỗ khác)" if len(issues) > 1 else ""
        raise BadRequest(
            f"Trang còn gọi người bán là «chị» ở {first['field'].lower()}: «{first['quote']}»{more}. Khách đọc trang "
            f"này nên người bán xưng «mình», gọi khách «bạn» — gợi ý: «{first['suggestion']}».",
            code="seller_address",
        )


async def publish(db: AsyncSession, product: Product, *, user: User | None = None) -> Product:
    check_publishable(product)
    first = product.status != ProductStatus.PUBLISHED
    product.status = ProductStatus.PUBLISHED
    product.published_at = product.published_at or now_utc()
    product.content_approved_at = now_utc()
    await db.flush()
    if first:
        await events.emit("product.published", {"product_id": str(product.id)}, db=db)
    return product


async def owner_publish(db: AsyncSession, product: Product, user: User) -> Product:
    """Chị bấm «Đăng»: có việc chờ thì duyệt việc đó (để có nhật ký), không thì đăng thẳng."""
    check_publishable(product)
    item = None
    if product.approval_item_id:
        item = await db.get(ApprovalItem, product.approval_item_id)
    if item is not None and item.status in (ApprovalStatus.PENDING, ApprovalStatus.FAILED):
        item = await control.approve(db, item.id, user)
        if item.status == ApprovalStatus.FAILED:
            raise BadRequest(item.error or "Chưa đăng được.")
        await db.refresh(product)
        return product
    await publish(db, product, user=user)
    await control.audit(db, "catalog.product_published", user=user, entity_type="products", entity_id=product.id,
                        summary=f"Đăng sản phẩm: {product.name}")  # fmt: skip
    return product


async def unpublish(db: AsyncSession, product: Product, user: User | None) -> Product:
    if product.status == ProductStatus.PUBLISHED:
        product.status = ProductStatus.PAUSED
        await control.audit(db, "catalog.product_paused", user=user, entity_type="products", entity_id=product.id,
                            summary=f"Tạm ẩn sản phẩm: {product.name}")  # fmt: skip
        await db.flush()
    return product


async def update_product(db: AsyncSession, product: Product, data: dict[str, Any], user: User) -> Product:
    for k, v in data.items():
        if k in EDITABLE_FIELDS:
            setattr(product, k, v)
    if data.get("slug"):
        product.slug = await unique_slug(db, Product, data["slug"], exclude_id=product.id)
    await control.audit(db, "catalog.product_edited", user=user, entity_type="products", entity_id=product.id,
                        summary=f"Sửa sản phẩm: {product.name}", data={"fields": sorted(data)})  # fmt: skip
    await db.flush()
    return product


async def apply_price(db: AsyncSession, candidate_id: uuid.UUID, price_vnd: int) -> Product | None:
    """`price.approved`: chị đã duyệt giá ở module supply → cập nhật giá bán (và giá vốn ảnh chụp)."""
    p = (await db.execute(select(Product).where(Product.candidate_id == candidate_id))).scalar_one_or_none()
    if p is None or price_vnd <= 0:
        return p
    if p.price_vnd != price_vnd:
        old = p.price_vnd
        p.price_vnd = int(price_vnd)
        from app.modules.catalog.dossier import approved_price

        prop = await approved_price(db, candidate_id)
        if prop is not None:
            p.landed_cost_vnd = prop.landed_cost_vnd
        await control.audit(db, "catalog.price_updated", entity_type="products", entity_id=p.id,
                            summary=f"Giá bán {p.name}: {old} → {price_vnd}", data={"from": old, "to": price_vnd})  # fmt: skip
        await db.flush()
    return p


# ---- ảnh (e6) ----------------------------------------------------------------------------------------------------


def image_url(img: ProductImage, size: int = 800, fmt: str = "jpg") -> str | None:
    key = img_lib.pick(img_lib.rendition_files(img.processing_ops), size, fmt)
    return get_storage().url(key) if key else None


def image_set(img: ProductImage) -> dict[str, Any]:
    files = img_lib.rendition_files(img.processing_ops)
    storage = get_storage()
    return {
        "id": str(img.id),
        "alt": img.alt,
        "is_primary": img.is_primary,
        "status": img.status.value,
        "src": image_url(img, 800),
        "src_large": image_url(img, 1600),
        "src_small": image_url(img, 400),
        "webp": {s: storage.url(v["webp"]) for s, v in files.items() if v.get("webp")},
    }


def primary_image(p: Product) -> ProductImage | None:
    ready = [i for i in p.images if img_lib.rendition_files(i.processing_ops)]
    return next((i for i in ready if i.is_primary), ready[0] if ready else None)


async def upload_image(
    db: AsyncSession,
    product: Product,
    data: bytes,
    *,
    alt: str | None = None,
    kind: ImageKind = ImageKind.OWNER_PHOTO,
    source_url: str | None = None,
) -> ProductImage:
    img_lib.open_image(data)  # kiểm tệp trước khi lưu
    storage = get_storage()
    key = new_key("private/products/originals", "jpg")
    await storage.put(key, data, "image/jpeg")
    position = (
        await db.execute(
            select(func.coalesce(func.max(ProductImage.position), -1)).where(ProductImage.product_id == product.id)
        )
    ).scalar_one() + 1
    has_primary = (
        await db.execute(
            select(func.count()).where(ProductImage.product_id == product.id, ProductImage.is_primary.is_(True))
        )
    ).scalar_one() > 0
    img = ProductImage(
        product_id=product.id, original_key=key, position=position, is_primary=not has_primary,
        alt=alt or product.name, status=ImageStatus.PROCESSING, kind=kind, source_url=source_url,
    )  # fmt: skip
    db.add(img)
    await db.flush()
    out = await control.propose(
        "catalog.process_image",
        f"Xử lý ảnh: {product.name}",
        {"image_id": str(img.id)},
        {"product": product.name},
        db=db,
        summary="Xoay đúng chiều, cân sáng nhẹ, làm sạch nền sáng (nếu nền đơn giản), cắt vuông giữ món ở giữa.",
        ref_type="product_images",
        ref_id=img.id,
        ai_generated=False,
    )
    if out.status in ("blocked", "failed"):
        await render_image(db, img, enhance=False)  # vẫn cần các cỡ để hiển thị, chỉ không chỉnh ảnh
    await db.refresh(product, ["images"])
    return img


# ---- ảnh nhà cung cấp chị chọn dùng lại (Hồ sơ bán) ------------------------------------------------------------
#
# Không có gì tự chép: chị tích từng ảnh trong hồ sơ ứng viên. Ảnh đi đúng đường của ảnh chị tải lên (gốc ở
# private/products/originals → `catalog.process_image` → các cỡ công khai không mang EXIF, tên tệp ngẫu nhiên, alt là
# tên món), nên website không lộ link/tên nhà cung cấp. Link gốc chỉ ghi ở `product_images.source_url` (desk).

MAX_SUPPLIER_PICK = 12


async def supplier_image_options(db: AsyncSession, product: Product) -> list[dict[str, Any]]:
    """Ảnh nhà cung cấp trong hồ sơ ứng viên của món (đọc bảng sourcing), kèm cờ đã dùng."""
    from app.modules.sourcing import gallery

    c = await db.get(Candidate, product.candidate_id) if product.candidate_id else None
    if c is None:
        return []
    await db.refresh(product, ["images"])
    used = {i.source_url for i in product.images if i.source_url}
    return [{**g, "used": g["source_url"] in used} for g in gallery.display(c)]


async def import_supplier_images(db: AsyncSession, product: Product, urls: list[str]) -> list[ProductImage]:
    """Chị tích ảnh nhà cung cấp → thành ảnh sản phẩm bình thường (`kind=supplier`, ghi link gốc)."""
    from app.modules.sourcing import gallery

    c = await db.get(Candidate, product.candidate_id) if product.candidate_id else None
    if c is None:
        raise BadRequest("Món này không gắn với ứng viên nào nên không có ảnh nhà cung cấp.", code="no_candidate")
    picked = list(dict.fromkeys(u for u in urls if u))[:MAX_SUPPLIER_PICK]
    if not picked:
        raise BadRequest("Chị chưa chọn ảnh nào.")
    allowed = set(gallery.source_urls(c))
    await db.refresh(product, ["images"])
    used = {i.source_url for i in product.images if i.source_url}
    out: list[ProductImage] = []
    for url in picked:
        if url not in allowed:
            raise BadRequest("Ảnh này không có trong hồ sơ ứng viên của món.", code="not_in_dossier")
        if url in used:
            continue
        got = await gallery.read_cached(c, url)
        if got is None:
            raise BadRequest(
                "Có ảnh chưa lưu về máy. Chị bấm «Lấy ảnh và chi tiết» ở hồ sơ ứng viên rồi chọn lại.",
                code="image_not_cached",
            )
        out.append(await upload_image(db, product, got[0], kind=ImageKind.SUPPLIER, source_url=url))
    await control.audit(db, "catalog.supplier_images_used", entity_type="products", entity_id=product.id,
                        summary=f"Dùng {len(out)} ảnh nhà cung cấp cho {product.name}",
                        data={"count": len(out)})  # fmt: skip
    return out


CLEAN_BG_SETTING = "catalog.image_clean_background"


async def render_image(db: AsyncSession, img: ProductImage, *, enhance: bool) -> ProductImage:
    data = await get_storage().get(img.original_key)
    clean_bg = enhance and bool(await control.get_setting(db, CLEAN_BG_SETTING))
    processed = img_lib.process_photo(data, enhance=enhance, clean_bg=clean_bg)
    files = await img_lib.store_renditions(f"public/products/{img.product_id}", processed)
    old = img_lib.rendition_files(img.processing_ops)
    img.processing_ops = [*processed.ops, {"op": "renditions", "files": files}]
    img.processed_key = img_lib.pick(files, 1600)
    img.width, img.height = processed.width, processed.height
    img.status = ImageStatus.PROCESSED
    img.ai_processed = enhance
    await db.flush()
    await _delete_files(old)
    return img


async def _delete_files(files: dict[str, dict[str, str]]) -> None:
    storage = get_storage()
    for entry in files.values():
        for key in entry.values():
            try:
                await storage.delete(key)
            except Exception:  # tệp cũ mất thì thôi
                log.warning("Không xoá được tệp %s", key)


async def get_image(db: AsyncSession, product: Product, image_id: uuid.UUID) -> ProductImage:
    img = await db.get(ProductImage, image_id)
    if img is None or img.product_id != product.id:
        raise NotFound("Không tìm thấy ảnh.")
    return img


async def reorder_images(db: AsyncSession, product: Product, ids: list[uuid.UUID]) -> Product:
    await db.refresh(product, ["images"])
    by_id = {i.id: i for i in product.images}
    if set(ids) != set(by_id):
        raise BadRequest("Danh sách ảnh không khớp, chị tải lại trang rồi thử lại.")
    for pos, iid in enumerate(ids):
        by_id[iid].position = pos
    await db.flush()
    await db.refresh(product, ["images"])
    return product


async def set_primary(db: AsyncSession, product: Product, image_id: uuid.UUID) -> Product:
    await db.refresh(product, ["images"])
    await get_image(db, product, image_id)
    for i in product.images:
        i.is_primary = i.id == image_id
    await db.flush()
    return product


async def delete_image(db: AsyncSession, product: Product, image_id: uuid.UUID) -> None:
    img = await get_image(db, product, image_id)
    files = img_lib.rendition_files(img.processing_ops)
    was_primary = img.is_primary
    await db.delete(img)
    await db.flush()
    await db.refresh(product, ["images"])
    if was_primary and product.images:
        product.images[0].is_primary = True
        await db.flush()
    await _delete_files(files)
    try:
        await get_storage().delete(img.original_key)
    except Exception:
        log.warning("Không xoá được ảnh gốc %s", img.original_key)
