"""Theo dõi một sản phẩm ở desk theo hai chiều.

- **Hồ sơ chọn** (ngược về quá trình chọn): đề săn hàng + nguồn, hồ sơ thẩm định + điểm + an toàn, đơn đặt mẫu,
  những ngày thử + ghi chú thử, quyết định chọn, giá vốn về tay. Phần dải số sàng lọc / món đã loại vẫn ở
  `dossier.dossier_view` (dùng chung với Bàn chọn).
- **Hồ sơ bán** (xuôi theo đường bán): nội dung từng kênh đã sẵn chưa → đã lên kênh nào → khách phản hồi và đặt
  ra sao (số liệu bài, hộp thư, trợ lý web, nhờ tìm, nhắc mua lại, đơn, tồn, đánh giá).

CHỈ ĐỌC bảng của sourcing / assessment / selection / supply / content / orders / inbox / assistant / crm
(ARCHITECTURE mục 10), không ghi gì. Số liệu bài đăng lấy từ driver `mock` thì gắn cờ `simulated` để màn hình nói
thật là số giả lập; sàn chưa nối thật cũng vậy."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import Channel
from app.integrations.social import driver_name_for
from app.modules.assessment.models import Assessment
from app.modules.assistant.models import AssistantConversation, ConversationStatus
from app.modules.catalog.models import (
    Drop,
    DropItem,
    DropReminder,
    DropStatus,
    FindRequest,
    InventoryItem,
    Product,
    ProductStatus,
    Review,
    ReviewStatus,
)
from app.modules.content.models import ContentDraft, DraftStatus, PostMetric, PostStatus, ScheduledPost
from app.modules.control.models import User
from app.modules.crm.models import ReminderStatus, ReorderReminder
from app.modules.inbox.models import Thread, ThreadStatus
from app.modules.orders.models import (
    RELEASED_STATUSES,
    ListingStatus,
    MarketplaceListing,
    Order,
    OrderItem,
    OrderStatus,
)
from app.modules.selection.models import Decision, NoteAuthor, SelectionDecision, TrialNote
from app.modules.sourcing.models import Candidate, SourcingBrief
from app.modules.supply.models import CostSheet, POKind, PriceProposal, ProposalStatus, PurchaseOrder

# Kênh mạng xã hội theo thứ tự xưởng nội dung (Website đứng đầu, tính riêng).
SOCIAL_CHANNELS: list[tuple[Channel, str]] = [
    (Channel.FACEBOOK, "Facebook"),
    (Channel.INSTAGRAM, "Instagram"),
    (Channel.THREADS, "Threads"),
    (Channel.TIKTOK, "TikTok"),
    (Channel.ZALO_OA, "Zalo"),
]
CONTENT_TOTAL = 1 + len(SOCIAL_CHANNELS)

CONTENT_STATE_LABELS = {"none": "Chưa soạn", "drafting": "Đang soạn", "pending": "Chờ duyệt", "approved": "Đã duyệt"}

POST_STATUS_LABELS = {
    PostStatus.PLANNED: "Đã xếp lịch, chờ chị duyệt",
    PostStatus.APPROVED: "Hẹn giờ đăng",
    PostStatus.PUBLISHING: "Đang đăng",
    PostStatus.PUBLISHED: "Đã đăng",
    PostStatus.DRAFT_PUSHED: "Nháp TikTok, chờ chị bấm đăng",
    PostStatus.FAILED: "Đăng lỗi",
    PostStatus.CANCELLED: "Đã huỷ",
}

ORDER_STATUS_LABELS = {
    OrderStatus.DRAFT: "Đơn nháp",
    OrderStatus.PENDING_PAYMENT: "Chờ chuyển khoản",
    OrderStatus.CONFIRMED: "Đã xác nhận",
    OrderStatus.AWAITING_STOCK: "Chờ hàng về",
    OrderStatus.READY_TO_SHIP: "Chờ giao",
    OrderStatus.SHIPPING: "Đang giao",
    OrderStatus.DELIVERED: "Đã giao",
    OrderStatus.COMPLETED: "Hoàn tất",
    OrderStatus.CANCELLED: "Đã huỷ",
    OrderStatus.RETURNED: "Đã hoàn về",
}

CHANNEL_LABELS = {
    Channel.WEB: "Website",
    Channel.FACEBOOK: "Facebook",
    Channel.INSTAGRAM: "Instagram",
    Channel.THREADS: "Threads",
    Channel.TIKTOK: "TikTok",
    Channel.ZALO_OA: "Zalo OA",
    Channel.ZALO_GROUP: "Nhóm Zalo",
    Channel.ZALO: "Zalo",
    Channel.TIKTOK_SHOP: "TikTok Shop",
    Channel.SHOPEE: "Shopee",
    Channel.EMAIL: "Email",
    Channel.SMS: "SMS",
    Channel.PHONE: "Điện thoại",
    Channel.MANUAL: "Chị nhập tay",
}

LISTING_STATUS_LABELS = {
    ListingStatus.PENDING: "Đang đưa lên",
    ListingStatus.ACTIVE: "Đang bán",
    ListingStatus.INACTIVE: "Ngừng bán",
    ListingStatus.ERROR: "Lỗi đồng bộ",
}

DROP_STATUS_LABELS = {
    DropStatus.DRAFT: "Nháp",
    DropStatus.PENDING_REVIEW: "Chờ chị duyệt",
    DropStatus.SCHEDULED: "Sắp mở",
    DropStatus.OPEN: "Đang nhận đặt",
    DropStatus.CLOSED: "Đã chốt",
    DropStatus.SOURCING: "Đang đặt nguồn",
    DropStatus.ARRIVING: "Hàng đang về",
    DropStatus.FULFILLING: "Đang giao khách",
    DropStatus.COMPLETED: "Xong",
}

PLATFORM_LABELS = {
    "1688": "1688", "taobao": "Taobao", "tmall": "Tmall", "pinduoduo": "Pinduoduo", "rakuten": "Rakuten",
    "amazon_jp": "Amazon Nhật", "amazon": "Amazon", "xiaohongshu": "Tiểu Hồng Thư", "cosme": "@cosme",
    "tiktok_shop_vn": "TikTok Shop", "shopee_vn": "Shopee", "lazada_vn": "Lazada", "tiki": "Tiki",
    "web": "Trang web", "offline": "Ngoài đời", "other": "Nguồn khác",
}  # fmt: skip

ORIGIN_LABELS = {
    "brief_scan": "AI quét theo đề", "link": "Chị dán link", "image": "Tìm bằng ảnh", "trend": "Radar xu hướng",
    "demand": "Khách hỏi nhiều", "manual": "Chị tự thêm",
}  # fmt: skip

PO_STATUS_LABELS = {
    "draft": "Nháp", "pending_approval": "Chờ chị duyệt", "approved": "Đã duyệt", "sent": "Đã gửi",
    "confirmed": "Bên bán xác nhận", "paid": "Đã trả tiền", "partially_received": "Về một phần",
    "received": "Đã nhận", "cancelled": "Đã huỷ",
}  # fmt: skip

SAFETY_LABELS = {"unchecked": "Chưa kiểm", "ok": "Ổn", "warning": "Cần lưu ý", "blocked": "Không nên bán"}
RISK_LABELS = {"unknown": "Chưa rõ", "low": "Thấp", "medium": "Vừa", "high": "Cao"}

# đơn «còn sống»: không tính đơn nháp AI tạo từ tin nhắn (chưa thành đơn) và đơn đã huỷ / hoàn về
_NOT_LIVE = (OrderStatus.DRAFT, *RELEASED_STATUSES)


def _dec(v: Any) -> float | None:
    return float(v) if v is not None else None


def _label(labels: dict[Any, str], v: Any) -> str:
    return labels.get(v, labels.get(getattr(v, "value", v), str(getattr(v, "value", v))))


# ==== Hồ sơ chọn ===================================================================================================


async def selection_trail(db: AsyncSession, p: Product) -> dict[str, Any]:
    c = await db.get(Candidate, p.candidate_id) if p.candidate_id else None
    if c is None:
        return {"candidate_id": None, "hunt": None, "assessment": None, "samples": [], "trial": None,
                "decision": None, "cost": _cost(p, None, None)}  # fmt: skip
    brief = await db.get(SourcingBrief, c.brief_id) if c.brief_id else None
    a = (await db.execute(select(Assessment).where(Assessment.candidate_id == c.id))).scalar_one_or_none()
    decision = (
        await db.execute(
            select(SelectionDecision)
            .where(SelectionDecision.candidate_id == c.id, SelectionDecision.decision == Decision.SELECTED)
            .order_by(SelectionDecision.decided_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    decider = await db.get(User, decision.decided_by_id) if decision and decision.decided_by_id else None
    pos = list(
        (
            await db.execute(
                select(PurchaseOrder)
                .where(PurchaseOrder.candidate_id == c.id, PurchaseOrder.kind == POKind.SAMPLE)
                .order_by(PurchaseOrder.created_at)
            )
        ).scalars()
    )
    notes = list(
        (
            await db.execute(select(TrialNote).where(TrialNote.candidate_id == c.id).order_by(TrialNote.recorded_at))
        ).scalars()
    )
    sheet = (
        await db.execute(
            select(CostSheet)
            .where(CostSheet.candidate_id == c.id, CostSheet.is_current.is_(True))
            .order_by(CostSheet.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    proposal = (
        await db.execute(
            select(PriceProposal)
            .where(PriceProposal.candidate_id == c.id, PriceProposal.status == ProposalStatus.APPROVED)
            .order_by(PriceProposal.decided_at.desc().nulls_last(), PriceProposal.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    hunt = {
        "brief_id": brief.id if brief else None,
        "brief_title": brief.title if brief else None,
        "brief_text": brief.raw_text if brief else None,
        "brief_created_at": brief.created_at if brief else None,
        "price_max_vnd": brief.price_max_vnd if brief else None,
        "origin": _label(ORIGIN_LABELS, c.origin),
        "platform": _label(PLATFORM_LABELS, c.source_platform),
        "source_url": c.source_url,
        "seller_name": c.seller_name,
        "title_original": c.title_original,
        "source_price_vnd": c.price_vnd_estimate,
        "source_rating": _dec(c.rating),
        "source_review_count": c.review_count,
        "found_at": c.created_at,
    }
    assessment = None
    if a is not None:
        assessment = {
            "status": a.status.value,
            "summary": a.summary,
            "score_total": _dec(a.score_total),
            "score_confirmed": a.score_confirmed_at is not None,
            "ai_score": c.ai_score,
            "scores": [
                {
                    "label": s.criterion_label,
                    "score": _dec(s.owner_score if s.owner_score is not None else s.ai_score),
                    "weight": _dec(s.weight),
                }
                for s in a.scores
            ],
            "strengths": [str(x) for x in (a.strengths or [])][:4],
            "weaknesses": [str(x) for x in (a.weaknesses or [])][:4],
            "safety_status": a.safety_status.value,
            "safety_label": _label(SAFETY_LABELS, a.safety_status),
            "safety_notes": str((a.safety or {}).get("notes") or "") or None,
            "counterfeit_risk": _label(RISK_LABELS, a.counterfeit_risk),
            "fake_review_risk": _label(RISK_LABELS, a.fake_review_risk),
            "generated_at": a.generated_at,
        }
    samples = [
        {"id": po.id, "code": po.code, "status": po.status.value, "status_label": _label(PO_STATUS_LABELS, po.status),
         "total_vnd": po.total_vnd, "sent_at": po.sent_at, "received_at": po.received_at}
        for po in pos
    ]  # fmt: skip
    trial = None
    if notes or (decision and decision.trial_days):
        trial = {
            "trial_days": decision.trial_days if decision else p.trial_days,
            "started_at": decision.trial_started_at if decision else None,
            "ended_at": decision.trial_ended_at if decision else None,
            "note_count": len(notes),
            "tester_count": len({n.tester_invite_id or n.author_name for n in notes if n.author == NoteAuthor.TESTER}),
            "notes": [
                {
                    "text": n.text,
                    "recorded_at": n.recorded_at,
                    "trial_day": n.trial_day,
                    "kind": n.kind.value,
                    "author": n.author_name if n.author == NoteAuthor.TESTER else None,
                    "sentiment": n.sentiment,
                }
                for n in notes[-5:][::-1]
                if n.text
            ],
        }
    decided = None
    if decision is not None:
        decided = {
            "decided_at": decision.decided_at,
            "decided_by": decider.name if decider else None,
            "reason_selected": decision.reason_selected or decision.draft_reason_selected,
            "not_satisfied": decision.not_satisfied or decision.draft_not_satisfied,
            "wording_pending": decision.draft_status.value == "pending_review",
        }
    return {
        "candidate_id": c.id,
        "hunt": hunt,
        "assessment": assessment,
        "samples": samples,
        "trial": trial,
        "decision": decided,
        "cost": _cost(p, sheet, proposal),
    }


def _cost(p: Product, sheet: CostSheet | None, proposal: PriceProposal | None) -> dict[str, Any]:
    landed = sheet.landed_cost_vnd if sheet else p.landed_cost_vnd
    margin = round((p.price_vnd - landed) * 100 / p.price_vnd, 1) if landed and p.price_vnd else None
    return {
        "landed_cost_vnd": landed,
        "breakdown": [
            {"label": str(b.get("label")), "amount_vnd": int(b.get("amount_vnd") or 0)}
            for b in (sheet.breakdown if sheet else [])
            if isinstance(b, dict) and b.get("label")
        ],
        "price_vnd": p.price_vnd,
        "margin_pct": margin,
        "proposed_price_vnd": proposal.proposed_price_vnd if proposal else None,
        "approved_at": proposal.decided_at if proposal else None,
    }


# ==== Hồ sơ bán ====================================================================================================


def _draft_state(d: ContentDraft | None) -> str:
    if d is None:
        return "none"
    if d.status in (DraftStatus.APPROVED, DraftStatus.SCHEDULED, DraftStatus.PUBLISHED):
        return "approved"
    if d.status == DraftStatus.PENDING_REVIEW:
        return "pending"
    return "drafting"  # đang soạn, hoặc chị trả lại và AI đang soạn lại


def _page_state(p: Product) -> str:
    if p.status in (ProductStatus.PUBLISHED, ProductStatus.PAUSED) or p.content_approved_at:
        return "approved"
    if p.status == ProductStatus.PENDING_REVIEW:
        return "pending"
    return "drafting"


async def _current_drafts(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[Channel, ContentDraft]]:
    rows = (
        await db.execute(
            select(ContentDraft)
            .where(
                ContentDraft.product_id.in_(ids),
                ContentDraft.drop_id.is_(None),
                ContentDraft.status != DraftStatus.ARCHIVED,
            )
            .order_by(ContentDraft.created_at)
        )
    ).scalars()
    out: dict[uuid.UUID, dict[Channel, ContentDraft]] = defaultdict(dict)
    for d in rows:
        if d.product_id:
            out[d.product_id][d.channel] = d  # bản mới nhất mỗi kênh
    return out


def _store_url(p: Product) -> str:
    return f"{settings.web_base_url.rstrip('/')}/san-pham/{p.slug}"


async def sales_view(db: AsyncSession, p: Product) -> dict[str, Any]:
    drafts = (await _current_drafts(db, [p.id])).get(p.id, {})
    page_state = _page_state(p)
    channels = []
    for ch, label in SOCIAL_CHANNELS:
        d = drafts.get(ch)
        st = _draft_state(d)
        channels.append({"channel": ch.value, "label": label, "state": st,
                         "state_label": CONTENT_STATE_LABELS[st], "updated_at": d.updated_at if d else None})  # fmt: skip
    ready = (page_state == "approved") + sum(c["state"] == "approved" for c in channels)

    posts = list(
        (
            await db.execute(
                select(ScheduledPost)
                .where(ScheduledPost.product_id == p.id, ScheduledPost.status != PostStatus.CANCELLED)
                .order_by(ScheduledPost.scheduled_at.desc())
            )
        ).scalars()
    )
    metrics = await _latest_metrics(db, [x.id for x in posts])
    post_rows = []
    for x in posts:
        m = metrics.get(x.id)
        post_rows.append(
            {
                "id": x.id, "channel": x.channel.value, "label": _label(CHANNEL_LABELS, x.channel),
                "status": x.status.value, "status_label": _label(POST_STATUS_LABELS, x.status),
                "scheduled_at": x.scheduled_at, "published_at": x.published_at, "url": x.external_url,
                "simulated": driver_name_for(x.channel) == "mock",
                "metrics": _metric_dict(m) if m else None,
            }
        )  # fmt: skip

    listings = list(
        (await db.execute(select(MarketplaceListing).where(MarketplaceListing.product_id == p.id))).scalars()
    )
    drop_rows = (
        await db.execute(
            select(Drop, DropItem)
            .join(DropItem, DropItem.drop_id == Drop.id)
            .where(DropItem.product_id == p.id, Drop.status != DropStatus.DRAFT)
            .order_by(Drop.opens_at.desc().nulls_last(), Drop.created_at.desc())
            .limit(6)
        )
    ).all()
    drop_ids = [d.id for d, _ in drop_rows]
    reminder_counts: dict[uuid.UUID, int] = dict(
        (
            await db.execute(
                select(DropReminder.drop_id, func.count())
                .where(DropReminder.drop_id.in_(drop_ids))
                .group_by(DropReminder.drop_id)
            )
        ).all()
    ) if drop_ids else {}  # fmt: skip

    live = {
        "website": {
            "status": p.status.value,
            "published": p.status == ProductStatus.PUBLISHED,
            "published_at": p.published_at,
            "url": _store_url(p) if p.status == ProductStatus.PUBLISHED else None,
        },
        "posts": post_rows,
        "drops": [
            {
                "id": d.id,
                "code": d.code,
                "title": d.title,
                "status": d.status.value,
                "status_label": _label(DROP_STATUS_LABELS, d.status),
                "opens_at": d.opens_at,
                "closes_at": d.closes_at,
                "slots_total": it.slots_total,
                "slots_reserved": it.slots_reserved,
                "price_vnd": it.price_vnd,
                "reminders": reminder_counts.get(d.id, 0),
            }
            for d, it in drop_rows
        ],
        "marketplaces": [
            {
                "marketplace": li.marketplace.value,
                "label": _label(CHANNEL_LABELS, li.marketplace),
                "status": li.status.value,
                "status_label": _label(LISTING_STATUS_LABELS, li.status),
                "external_id": li.external_id,
                "price_vnd": li.price_vnd,
                "synced_stock": li.synced_stock,
                "last_synced_at": li.last_synced_at,
            }
            for li in listings
        ],
        "marketplaces_simulated": settings.marketplaces_driver == "mock",
        "channels_live": _live_labels(p, posts, listings),
    }
    return {
        "product_id": p.id,
        "content": {
            "website": {
                "state": page_state,
                "state_label": CONTENT_STATE_LABELS[page_state],
                "status": p.status.value,
                "updated_at": p.updated_at,
            },
            "channels": channels,
            "ready": ready,
            "total": CONTENT_TOTAL,
        },
        "live": live,
        "customers": await _customers(db, p, post_rows),
    }


def _live_labels(p: Product, posts: list[ScheduledPost], listings: list[MarketplaceListing]) -> list[str]:
    out: list[str] = ["Website"] if p.status == ProductStatus.PUBLISHED else []
    for ch, label in SOCIAL_CHANNELS:
        if any(x.channel == ch and x.status == PostStatus.PUBLISHED for x in posts):
            out.append(label)
    out += [_label(CHANNEL_LABELS, li.marketplace) for li in listings if li.status == ListingStatus.ACTIVE]
    return out


async def _latest_metrics(db: AsyncSession, post_ids: list[uuid.UUID]) -> dict[uuid.UUID, PostMetric]:
    if not post_ids:
        return {}
    sub = (
        select(PostMetric.scheduled_post_id, func.max(PostMetric.captured_at).label("at"))
        .where(PostMetric.scheduled_post_id.in_(post_ids))
        .group_by(PostMetric.scheduled_post_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(PostMetric).join(
                sub, (PostMetric.scheduled_post_id == sub.c.scheduled_post_id) & (PostMetric.captured_at == sub.c.at)
            )
        )
    ).scalars()
    return {m.scheduled_post_id: m for m in rows}


def _metric_dict(m: PostMetric) -> dict[str, Any]:
    return {
        "captured_at": m.captured_at, "reach": m.reach, "clicks": m.clicks,
        "interactions": m.likes + m.comments + m.shares + m.saves, "messages": m.messages_started,
        "orders": m.orders_attributed, "revenue_vnd": m.revenue_attributed_vnd,
    }  # fmt: skip


async def _customers(db: AsyncSession, p: Product, post_rows: list[dict[str, Any]]) -> dict[str, Any]:
    # --- số liệu bài đăng (bản đo mới nhất của từng bài) ---
    measured = [r for r in post_rows if r["metrics"]]
    totals = {k: sum(r["metrics"][k] for r in measured) for k in ("reach", "clicks", "interactions", "messages")}
    post_signals = {
        "measured_posts": len(measured),
        **totals,
        "orders_from_posts": sum(r["metrics"]["orders"] for r in measured),
        "revenue_from_posts_vnd": sum(r["metrics"]["revenue_vnd"] for r in measured),
        "simulated": any(r["simulated"] for r in measured),
        "last_captured_at": max((r["metrics"]["captured_at"] for r in measured), default=None),
    }

    # --- hộp thư: hội thoại đang hỏi về món này ---
    threads = list(
        (
            await db.execute(
                select(Thread)
                .where(Thread.product_id == p.id, Thread.status != ThreadStatus.SPAM)
                .order_by(Thread.last_message_at.desc().nulls_last())
            )
        ).scalars()
    )
    inbox = {
        "threads": len(threads),
        "needs_owner": sum(t.needs_owner or t.status == ThreadStatus.NEEDS_OWNER for t in threads),
        "recent": [
            {
                "id": t.id,
                "channel": t.channel.value,
                "channel_label": _label(CHANNEL_LABELS, t.channel),
                "name": t.participant_name,
                "snippet": t.snippet,
                "last_message_at": t.last_message_at,
            }
            for t in threads[:3]
        ],
    }
    conv = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(AssistantConversation.status == ConversationStatus.HANDED_OFF),
                func.coalesce(func.sum(AssistantConversation.message_count), 0),
            ).where(AssistantConversation.product_id == p.id)
        )
    ).one()
    assistant = {"conversations": conv[0], "handed_off": conv[1], "messages": int(conv[2])}

    finds = list((await db.execute(select(FindRequest).where(FindRequest.product_id == p.id))).scalars())
    reminder_rows = (
        await db.execute(
            select(ReorderReminder.status, func.count())
            .where(ReorderReminder.product_id == p.id)
            .group_by(ReorderReminder.status)
        )
    ).all()
    by_reminder = {s.value: n for s, n in reminder_rows}
    reorder = {
        "scheduled": by_reminder.get(ReminderStatus.SCHEDULED.value, 0)
        + by_reminder.get(ReminderStatus.PENDING_REVIEW.value, 0),
        "sent": by_reminder.get(ReminderStatus.SENT.value, 0),
        "converted": by_reminder.get(ReminderStatus.CONVERTED.value, 0),
    }

    return {
        "posts": post_signals,
        "inbox": inbox,
        "assistant": assistant,
        "finds": [{"title": f.title, "votes": f.vote_count, "status": f.status.value} for f in finds],
        "reorder": reorder,
        "orders": await _orders(db, p.id),
        "stock": await _stock(db, p),
        "reviews": await _reviews(db, p),
    }


async def _orders(db: AsyncSession, product_id: uuid.UUID) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(Order, OrderItem)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.product_id == product_id)
            .order_by(Order.placed_at.desc())
        )
    ).all()
    per_order: dict[uuid.UUID, dict[str, Any]] = {}
    for o, it in rows:
        r = per_order.setdefault(o.id, {"order": o, "qty": 0, "total": 0})
        r["qty"] += it.quantity
        r["total"] += it.line_total_vnd
    live = [r for r in per_order.values() if r["order"].status not in _NOT_LIVE]
    by_status = Counter(r["order"].status for r in per_order.values())
    by_channel = Counter(r["order"].channel for r in live)
    buyers = Counter(r["order"].customer_id for r in live if r["order"].customer_id)
    return {
        "count": len(live),
        "units": sum(r["qty"] for r in live),
        "revenue_vnd": sum(r["total"] for r in live if r["order"].paid_at is not None),
        "unpaid_vnd": sum(r["total"] for r in live if r["order"].paid_at is None),
        "customers": len(buyers),
        "repeat_buyers": sum(1 for n in buyers.values() if n >= 2),
        "drafts": by_status.get(OrderStatus.DRAFT, 0),
        "cancelled": sum(by_status.get(s, 0) for s in RELEASED_STATUSES),
        "by_status": [
            {"status": s.value, "label": ORDER_STATUS_LABELS[s], "count": by_status[s]}
            for s in OrderStatus
            if by_status.get(s)
        ],
        "by_channel": [
            {"channel": ch.value, "label": _label(CHANNEL_LABELS, ch), "count": n} for ch, n in by_channel.most_common()
        ],
        "recent": [
            {
                "id": r["order"].id,
                "code": r["order"].code,
                "status": r["order"].status.value,
                "status_label": ORDER_STATUS_LABELS[r["order"].status],
                "placed_at": r["order"].placed_at,
                "channel_label": _label(CHANNEL_LABELS, r["order"].channel),
                "quantity": r["qty"],
                "amount_vnd": r["total"],
                "name": r["order"].recipient_name,
            }
            for r in list(per_order.values())[:5]
        ],
    }


async def _stock(db: AsyncSession, p: Product) -> dict[str, Any]:
    items = list((await db.execute(select(InventoryItem).where(InventoryItem.product_id == p.id))).scalars())
    if not items:
        return {"sale_mode": p.sale_mode.value, "tracked": False, "on_hand": 0, "reserved": 0, "available": 0,
                "low": False}  # fmt: skip
    on_hand, reserved = sum(i.on_hand for i in items), sum(i.reserved for i in items)
    low = any(i.low_stock_threshold is not None and i.available <= i.low_stock_threshold for i in items)
    return {"sale_mode": p.sale_mode.value, "tracked": True, "on_hand": on_hand, "reserved": reserved,
            "available": on_hand - reserved, "low": low}  # fmt: skip


async def _reviews(db: AsyncSession, p: Product) -> dict[str, Any]:
    rows = dict(
        (
            await db.execute(
                select(Review.status, func.count()).where(Review.product_id == p.id).group_by(Review.status)
            )
        ).all()
    )
    return {
        "published": rows.get(ReviewStatus.PUBLISHED, 0),
        "rating_avg": p.rating_avg,
        "waiting_owner": rows.get(ReviewStatus.PENDING_REVIEW, 0) + rows.get(ReviewStatus.SUBMITTED, 0),
        "requested": rows.get(ReviewStatus.REQUESTED, 0),
    }


# ==== danh sách: tình trạng hai chiều từng món =====================================================================


async def pipeline_rows(db: AsyncSession) -> list[dict[str, Any]]:
    products = list((await db.execute(select(Product).where(Product.status != ProductStatus.ARCHIVED))).scalars())
    ids = [p.id for p in products]
    if not ids:
        return []
    cids = [p.candidate_id for p in products if p.candidate_id]
    decided: dict[uuid.UUID, datetime] = dict(
        (
            await db.execute(
                select(SelectionDecision.candidate_id, func.max(SelectionDecision.decided_at))
                .where(SelectionDecision.candidate_id.in_(cids), SelectionDecision.decision == Decision.SELECTED)
                .group_by(SelectionDecision.candidate_id)
            )
        ).all()
    ) if cids else {}  # fmt: skip
    drafts = await _current_drafts(db, ids)
    published_posts = (
        await db.execute(
            select(ScheduledPost.product_id, ScheduledPost.channel)
            .where(ScheduledPost.product_id.in_(ids), ScheduledPost.status == PostStatus.PUBLISHED)
            .distinct()
        )
    ).all()
    live_social: dict[uuid.UUID, set[Channel]] = defaultdict(set)
    for pid, ch in published_posts:
        live_social[pid].add(ch)
    active_listings: dict[uuid.UUID, set[Channel]] = defaultdict(set)
    for pid, mk in (
        await db.execute(
            select(MarketplaceListing.product_id, MarketplaceListing.marketplace).where(
                MarketplaceListing.product_id.in_(ids), MarketplaceListing.status == ListingStatus.ACTIVE
            )
        )
    ).all():
        active_listings[pid].add(mk)
    order_rows = (
        await db.execute(
            select(
                OrderItem.product_id,
                func.count(func.distinct(Order.id)),
                func.coalesce(func.sum(OrderItem.quantity), 0),
                func.coalesce(func.sum(OrderItem.line_total_vnd).filter(Order.paid_at.is_not(None)), 0),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.product_id.in_(ids), Order.status.not_in(_NOT_LIVE))
            .group_by(OrderItem.product_id)
        )
    ).all()
    orders = {pid: (int(n), int(u), int(rev)) for pid, n, u, rev in order_rows}

    out = []
    for p in products:
        ds = drafts.get(p.id, {})
        ready = (_page_state(p) == "approved") + sum(
            _draft_state(ds.get(ch)) == "approved" for ch, _ in SOCIAL_CHANNELS
        )
        live = ["Website"] if p.status == ProductStatus.PUBLISHED else []
        live += [label for ch, label in SOCIAL_CHANNELS if ch in live_social.get(p.id, set())]
        live += [_label(CHANNEL_LABELS, mk) for mk in sorted(active_listings.get(p.id, set()))]
        n, units, revenue = orders.get(p.id, (0, 0, 0))
        out.append(
            {
                "product_id": p.id,
                "chosen_at": decided.get(p.candidate_id) if p.candidate_id else None,
                "trial_days": p.trial_days,
                "content_ready": ready,
                "content_total": CONTENT_TOTAL,
                "channels_live": live,
                "orders": n,
                "units": units,
                "revenue_vnd": revenue,
            }
        )
    return out
