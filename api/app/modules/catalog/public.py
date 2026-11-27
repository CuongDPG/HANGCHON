"""Dữ liệu công khai cho website (e1, e2, e3, e10): kệ hàng, trang sản phẩm, đợt, về người chọn,
nguồn cấp sản phẩm Google Merchant, sơ đồ trang. Quá trình chọn (dải số sàng lọc, món đã loại) không ra website:
hồ sơ chọn chỉ ở desk (`dossier.dossier_view`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.config import settings
from app.modules.catalog import drops as drop_svc
from app.modules.catalog.dossier import COUNTRY_LABELS
from app.modules.catalog.models import (
    Category,
    Drop,
    DropItem,
    DropStatus,
    InventoryItem,
    Product,
    ProductStatus,
    Review,
    ReviewStatus,
)
from app.modules.catalog.products import image_set, primary_image
from app.modules.catalog.reviews import photo_url
from app.modules.catalog.textutil import matches_vi
from app.modules.selection.models import NoteAuthor, PrincipleKind, SelectionPrinciple, TrialNote

DEFAULTS = {
    "store.name": "Hàng Chọn",
    "store.tagline": "Đồ gia dụng nhỏ, chọn từng món",
    "store.picker_name": "Người chọn hàng",
    "store.picker_intro": "Mình không bán nhiều. Món nào ở đây mình cũng đã mua bằng tiền của mình và dùng thử "
    "trước khi đưa lên kệ.",
    "store.not_selling": "Món mình chưa thử. Món không rõ nguồn gốc. Món phải nói quá mới bán được.",
    "store.ai_help": "AI giúp mình tìm hàng ở nhiều nơi, đọc hàng nghìn đánh giá, soạn bài và trả lời câu hỏi "
    "thường gặp. Quyết định chọn món nào là của mình.",
}


async def setting(db: AsyncSession, key: str) -> Any:
    v = await control.get_setting(db, key)
    return v if v not in (None, "") else DEFAULTS.get(key)


def proof_line(p: Product) -> str | None:
    """«Thử 3 tuần · Nhật» — bằng chứng đã thử, đứng ở chỗ sàn khác đặt số sao."""
    parts = []
    if p.trial_days:
        weeks = round(p.trial_days / 7)
        parts.append(f"Thử {weeks} tuần" if p.trial_days >= 14 and weeks else f"Thử {p.trial_days} ngày")
    if p.origin_country:
        parts.append(COUNTRY_LABELS.get(p.origin_country, p.origin_country))
    return " · ".join(parts) or None


async def _open_drop_items(db: AsyncSession, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[Drop, DropItem]]:
    if not product_ids:
        return {}
    rows = (
        await db.execute(
            select(DropItem, Drop)
            .join(Drop, Drop.id == DropItem.drop_id)
            .where(DropItem.product_id.in_(product_ids), Drop.status == DropStatus.OPEN)
            .order_by(Drop.closes_at)
        )
    ).all()
    out: dict[uuid.UUID, tuple[Drop, DropItem]] = {}
    for item, drop in rows:
        out.setdefault(item.product_id, (drop, item))
    return out


async def _stock(db: AsyncSession, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    rows = (
        await db.execute(
            select(InventoryItem.product_id, func.sum(InventoryItem.on_hand - InventoryItem.reserved))
            .where(InventoryItem.product_id.in_(product_ids))
            .group_by(InventoryItem.product_id)
        )
    ).all()
    return {r[0]: max(0, int(r[1] or 0)) for r in rows}


def slots_left(item: DropItem) -> int | None:
    return None if item.slots_total is None else max(0, item.slots_total - item.slots_reserved)


def _drop_brief(drop: Drop, item: DropItem) -> dict[str, Any]:
    return {
        "id": drop.id,
        "slug": drop.slug,
        "label": drop_svc.label(drop),
        "title": drop.title,
        "closes_at": drop.closes_at,
        "expected_arrival_date": drop.expected_arrival_date,
        "price_vnd": item.price_vnd,
        "slots_total": item.slots_total,
        "slots_left": slots_left(item),
        "max_per_order": item.max_per_order,
    }


def _card(
    p: Product, cats: dict[uuid.UUID, Category], drop: tuple[Drop, DropItem] | None, stock: int
) -> dict[str, Any]:
    img = primary_image(p)
    cat = cats.get(p.category_id) if p.category_id else None
    drop_info = _drop_brief(*drop) if drop else None
    in_drop = bool(drop_info and (drop_info["slots_left"] is None or drop_info["slots_left"] > 0))
    return {
        "id": str(p.id),
        "slug": p.slug,
        "name": p.name,
        "subtitle": p.subtitle,
        "price_vnd": drop_info["price_vnd"] if drop_info else p.price_vnd,
        "list_price_vnd": p.price_vnd,
        "compare_at_price_vnd": p.compare_at_price_vnd,
        "image": image_set(img) if img else None,
        "trial_days": p.trial_days,
        "origin": COUNTRY_LABELS.get(p.origin_country or "", p.origin_country),
        "proof": proof_line(p),
        "category": {"slug": cat.slug, "name": cat.name} if cat else None,
        "rating_avg": p.rating_avg,
        "review_count": p.review_count,
        "drop": drop_info,
        "stock": stock,
        "available": in_drop or stock > 0,
    }


async def _categories(db: AsyncSession) -> dict[uuid.UUID, Category]:
    return {c.id: c for c in (await db.execute(select(Category))).scalars()}


async def shelf(db: AsyncSession, *, category: str | None = None, q: str | None = None) -> dict[str, Any]:
    products = list(
        (
            await db.execute(
                select(Product)
                .where(Product.status == ProductStatus.PUBLISHED)
                .order_by(Product.published_at.desc().nulls_last(), Product.created_at.desc())
            )
        ).scalars()
    )
    cats = await _categories(db)
    ids = [p.id for p in products]
    drops, stock = await _open_drop_items(db, ids), await _stock(db, ids)
    counts: dict[uuid.UUID, int] = {}
    for p in products:
        if p.category_id:
            counts[p.category_id] = counts.get(p.category_id, 0) + 1
    chips = [
        {"slug": c.slug, "name": c.name, "count": counts[c.id]}
        for c in sorted(cats.values(), key=lambda c: (c.position, c.name))
        if counts.get(c.id) and c.is_active
    ]
    filtered = products
    if category:
        cat_ids = {c.id for c in cats.values() if c.slug == category}
        filtered = [p for p in filtered if p.category_id in cat_ids]
    if q and q.strip():

        def hay(p: Product) -> str:
            cat = cats.get(p.category_id) if p.category_id else None
            specs = " ".join(f"{s.get('label', '')} {s.get('value', '')}" for s in p.specs if isinstance(s, dict))
            return " ".join(filter(None, [p.name, p.subtitle, p.short_description, cat.name if cat else "", specs]))

        filtered = [p for p in filtered if matches_vi(hay(p), q)]
    return {
        "total": len(products),
        "chips": chips,
        "items": [_card(p, cats, drops.get(p.id), stock.get(p.id, 0)) for p in filtered],
        "query": q or None,
        "category": category,
    }


def bullets(text: str | None) -> list[str]:
    if not text:
        return []
    lines = [ln.strip().lstrip("-•*").strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


async def published_reviews(db: AsyncSession, product_id: uuid.UUID, limit: int = 12) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Review)
            .where(Review.product_id == product_id, Review.status == ReviewStatus.PUBLISHED)
            .order_by(Review.published_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "id": str(r.id),
            "display_name": r.display_name or "Khách",
            "rating": r.rating,
            "body": r.body,
            "photos": [{"src": photo_url(ph, 800), "thumb": photo_url(ph, 400)} for ph in r.photos],
            "published_at": r.published_at,
            "owner_reply": r.owner_reply,
        }
        for r in rows
    ]


async def customer_reasons(db: AsyncSession, product_id: uuid.UUID, limit: int = 5) -> list[dict[str, Any]]:
    """«Vì sao khách chọn»: chỉ đánh giá chị đã duyệt (published) và lý do chưa bị chị ẩn."""
    rows = await db.execute(
        select(Review.display_name, Review.choice_reason)
        .where(
            Review.product_id == product_id,
            Review.status == ReviewStatus.PUBLISHED,
            Review.reason_public.is_(True),
            Review.choice_reason.is_not(None),
        )
        .order_by(Review.published_at.desc())
        .limit(limit)
    )
    return [{"display_name": name or "Khách", "text": text} for name, text in rows if text and text.strip()]


async def public_trial_notes(db: AsyncSession, p: Product, limit: int = 6) -> list[dict[str, Any]]:
    """«Ghi chú dùng thử» (đọc bảng selection): chỉ ghi chú của chị mà chị đã tích «Đưa lên website». Lời là bản chị
    sửa cho website; ảnh chỉ là bản sao công khai chị tích kèm (đã bỏ EXIF), không bao giờ ảnh gốc."""
    if not p.candidate_id:
        return []
    rows = (
        await db.execute(
            select(TrialNote)
            .where(
                TrialNote.candidate_id == p.candidate_id,
                TrialNote.is_public.is_(True),
                TrialNote.author == NoteAuthor.OWNER,
            )
            .order_by(TrialNote.recorded_at)
            .limit(limit)
        )
    ).scalars()
    out = []
    for n in rows:
        text = (n.public_text or "").strip()
        photos = [{"src": photo_url(ph, 800), "thumb": photo_url(ph, 400)} for ph in n.public_photos]
        if text or photos:
            out.append({"text": text or None, "day": n.trial_day, "photos": photos})
    return out


async def product_detail(db: AsyncSession, p: Product) -> dict[str, Any]:
    cats = await _categories(db)
    drops, stock = await _open_drop_items(db, [p.id]), await _stock(db, [p.id])
    card = _card(p, cats, drops.get(p.id), stock.get(p.id, 0))
    ready = [i for i in p.images if image_set(i)["src"]]
    ready.sort(key=lambda i: (not i.is_primary, i.position))
    return {
        **card,
        "short_description": p.short_description,
        "description": p.description,
        "specs": p.specs,
        "faq": p.faq,
        "reason_selected": bullets(p.reason_selected),
        "not_satisfied": p.not_satisfied,
        "images": [image_set(i) for i in ready],
        "weight_grams": p.weight_grams,
        "brand": p.brand,
        "gtin": p.gtin,
        "shipping_notes": p.shipping_notes,
        "sale_mode": p.sale_mode.value,
        "seo_title": p.seo_title,
        "seo_description": p.seo_description,
        "published_at": p.published_at,
        "updated_at": p.updated_at,
        "ai_generated": p.ai_generated,
        "reviews": await published_reviews(db, p.id),
        "customer_reasons": await customer_reasons(db, p.id),
        "trial_notes": await public_trial_notes(db, p),
        "url": f"{settings.web_base_url.rstrip('/')}/san-pham/{p.slug}",
        # tên người chọn cho nhãn «… trả lời» (chưa đặt thì là tên trung tính mặc định)
        "picker_name": await setting(db, "store.picker_name"),
    }


async def _drop_stats(db: AsyncSession, drop_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Số đơn và điểm đánh giá của từng đợt (đọc bảng orders, chỉ đọc)."""
    from app.modules.orders.models import Order, OrderStatus

    if not drop_ids:
        return {}
    orders = dict(
        (
            await db.execute(
                select(Order.drop_id, func.count())
                .where(Order.drop_id.in_(drop_ids), Order.status.not_in((OrderStatus.CANCELLED, OrderStatus.DRAFT)))
                .group_by(Order.drop_id)
            )
        ).all()
    )
    ratings = {
        r[0]: (r[1], r[2])
        for r in (
            await db.execute(
                select(Order.drop_id, func.avg(Review.rating), func.count(Review.id))
                .join(Review, Review.order_id == Order.id)
                .where(Order.drop_id.in_(drop_ids), Review.status == ReviewStatus.PUBLISHED)
                .group_by(Order.drop_id)
            )
        ).all()
    }
    out = {}
    for did in drop_ids:
        avg, n = ratings.get(did, (None, 0))
        out[did] = {"order_count": int(orders.get(did, 0)), "rating_avg": round(float(avg), 1) if avg else None,
                    "review_count": int(n)}  # fmt: skip
    return out


async def _drop_summary(db: AsyncSession, d: Drop, stats: dict[str, Any]) -> dict[str, Any]:
    products = {
        p.id: p
        for p in (await db.execute(select(Product).where(Product.id.in_([i.product_id for i in d.items])))).scalars()
    }
    first = next((products.get(i.product_id) for i in d.items if products.get(i.product_id)), None)
    cover = primary_image(first) if first else None
    limited = [i for i in d.items if i.slots_total is not None]
    return {
        "id": str(d.id),
        "slug": d.slug,
        "code": d.code,
        "label": drop_svc.label(d),
        "title": d.title,
        "description": d.description,
        "status": d.status.value,
        "opens_at": d.opens_at,
        "closes_at": d.closes_at,
        "expected_arrival_date": d.expected_arrival_date,
        "actual_arrival_date": d.actual_arrival_date,
        "item_count": len(d.items),
        "slots_total": sum(i.slots_total or 0 for i in limited) if limited else None,
        "slots_reserved": sum(i.slots_reserved for i in d.items),
        "cover": image_set(cover) if cover else None,
        "product_names": [products[i.product_id].name for i in d.items if i.product_id in products][:6],
        **stats,
    }


async def drops_overview(db: AsyncSession) -> dict[str, Any]:
    rows = list(
        (
            await db.execute(select(Drop).where(Drop.status.in_(drop_svc.PUBLIC)).order_by(Drop.closes_at.desc()))
        ).scalars()
    )
    stats = await _drop_stats(db, [d.id for d in rows])
    groups: dict[str, list[dict[str, Any]]] = {"open": [], "upcoming": [], "arrived": [], "closed": []}
    for d in rows:
        s = await _drop_summary(db, d, stats.get(d.id, {}))
        if d.status == DropStatus.OPEN:
            groups["open"].append(s)
        elif d.status == DropStatus.SCHEDULED:
            groups["upcoming"].append(s)
        elif d.status in drop_svc.ARRIVED:
            groups["arrived"].append(s)
        else:
            groups["closed"].append(s)
    far = datetime.max.replace(tzinfo=UTC)
    groups["open"].sort(key=lambda s: s["closes_at"] or far)
    groups["upcoming"].sort(key=lambda s: s["opens_at"] or far)
    return groups


async def drop_detail(db: AsyncSession, d: Drop) -> dict[str, Any]:
    stats = (await _drop_stats(db, [d.id])).get(d.id, {})
    summary = await _drop_summary(db, d, stats)
    cats = await _categories(db)
    products = {
        p.id: p
        for p in (
            await db.execute(
                select(Product).where(
                    Product.id.in_([i.product_id for i in d.items]), Product.status == ProductStatus.PUBLISHED
                )
            )
        ).scalars()
    }
    items = []
    for it in d.items:
        p = products.get(it.product_id)
        if p is None:
            continue
        card = _card(p, cats, (d, it) if d.status == DropStatus.OPEN else None, 0)
        card["price_vnd"] = it.price_vnd
        items.append(
            {**card, "slots_total": it.slots_total, "slots_left": slots_left(it), "max_per_order": it.max_per_order}
        )
    return {**summary, "deposit_pct": d.deposit_pct, "items": items}


async def about(db: AsyncSession) -> dict[str, Any]:
    principles = list(
        (
            await db.execute(
                select(SelectionPrinciple)
                .where(SelectionPrinciple.is_active.is_(True), SelectionPrinciple.category_id.is_(None))
                .order_by(SelectionPrinciple.priority, SelectionPrinciple.created_at)
            )
        ).scalars()
    )
    how = [p.text for p in principles if p.kind in (PrincipleKind.MUST, PrincipleKind.PREFER, PrincipleKind.AVOID)]
    never = [p.text for p in principles if p.kind == PrincipleKind.MUST_NOT]
    return {
        "store_name": await setting(db, "store.name"),
        "tagline": await setting(db, "store.tagline"),
        "picker_name": await setting(db, "store.picker_name"),
        "intro": await setting(db, "store.picker_intro"),
        "not_selling": await setting(db, "store.not_selling"),
        "not_selling_rules": never,
        "ai_help": await setting(db, "store.ai_help"),
        "how_we_choose": how,
    }


def _availability(card: dict[str, Any]) -> str:
    if card["stock"] > 0:
        return "in_stock"
    if card["available"]:
        return "preorder"
    return "out_of_stock"


async def merchant_feed(db: AsyncSession) -> str:
    """Nguồn cấp Google Merchant (RSS 2.0 + không gian tên g:)."""
    data = await shelf(db)
    base = settings.web_base_url.rstrip("/")
    store_name = await setting(db, "store.name")
    products = {
        str(p.id): p
        for p in (
            await db.execute(
                select(Product).where(Product.status == ProductStatus.PUBLISHED, Product.feed_enabled.is_(True))
            )
        ).scalars()
    }
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">',
        "<channel>",
        f"<title>{escape(str(store_name))}</title>",
        f"<link>{escape(base)}</link>",
        f"<description>{escape(str(await setting(db, 'store.tagline')))}</description>",
    ]
    for card in data["items"]:
        p = products.get(card["id"])
        if p is None:
            continue
        desc = p.short_description or p.subtitle or p.name
        avail = _availability(card)
        lines = [
            "<item>",
            f"<g:id>{escape(p.sku or str(p.id))}</g:id>",
            f"<g:title>{escape(p.name)}</g:title>",
            f"<g:description>{escape(desc)}</g:description>",
            f"<g:link>{escape(f'{base}/san-pham/{p.slug}')}</g:link>",
            f"<g:price>{card['list_price_vnd']} VND</g:price>",
            f"<g:availability>{avail}</g:availability>",
            "<g:condition>new</g:condition>",
        ]
        if card["drop"] and card["price_vnd"] != card["list_price_vnd"]:
            lines.append(f"<g:sale_price>{card['price_vnd']} VND</g:sale_price>")
        if avail == "preorder" and card["drop"] and card["drop"]["expected_arrival_date"]:
            lines.append(
                f"<g:availability_date>{card['drop']['expected_arrival_date']}T00:00+07:00</g:availability_date>"
            )
        if card["image"] and card["image"]["src_large"]:
            lines.append(f"<g:image_link>{escape(card['image']['src_large'])}</g:image_link>")
        if p.brand:
            lines.append(f"<g:brand>{escape(p.brand)}</g:brand>")
        if p.gtin:
            lines.append(f"<g:gtin>{escape(p.gtin)}</g:gtin>")
        if not (p.brand and p.gtin):
            lines.append("<g:identifier_exists>no</g:identifier_exists>")
        if card["category"]:
            lines.append(f"<g:product_type>{escape(card['category']['name'])}</g:product_type>")
        if p.weight_grams:
            lines.append(f"<g:shipping_weight>{p.weight_grams} g</g:shipping_weight>")
        lines.append("</item>")
        out += lines
    out += ["</channel>", "</rss>"]
    return "\n".join(out)


async def sitemap(db: AsyncSession) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slug, updated in (
        await db.execute(select(Product.slug, Product.updated_at).where(Product.status == ProductStatus.PUBLISHED))
    ).all():
        rows.append({"path": f"/san-pham/{slug}", "lastmod": updated, "priority": 0.8})
    for slug, updated in (
        await db.execute(select(Drop.slug, Drop.updated_at).where(Drop.status.in_(drop_svc.PUBLIC)))
    ).all():
        rows.append({"path": f"/dot/{slug}", "lastmod": updated, "priority": 0.6})
    return rows
