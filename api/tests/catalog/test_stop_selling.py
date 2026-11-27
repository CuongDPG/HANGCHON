"""«Ngừng bán trên mọi kênh» và «Mở bán lại» (driver mock): từng loại kênh, lỗi một phần, xoá hẳn chỉ khi chị chọn,
mở bán lại khôi phục đúng thứ đã làm, việc nền không đưa món đã ngừng lên lại."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.enums import Channel
from app.core.jobs import JOBS, job_context
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.modules.catalog.models import Product, ProductStatus, SaleMode
from app.modules.content.models import ContentDraft, DraftFormat, DraftStatus, PostStatus, ScheduledPost
from app.modules.control.models import AIActivity, ApprovalItem, ApprovalStatus, AuditLog
from app.modules.orders.models import ListingStatus, MarketplaceListing
from tests.content.conftest import make_drop, make_product

BASE = "/api/desk/catalog/products"
FORMATS = {Channel.INSTAGRAM: DraftFormat.CAROUSEL, Channel.TIKTOK: DraftFormat.VIDEO_SCRIPT,
           Channel.ZALO_OA: DraftFormat.ZALO_MESSAGE}  # fmt: skip


async def _post(product: Product, channel: Channel, status: PostStatus, *, ext: str | None = None) -> uuid.UUID:
    async with SessionLocal() as db:
        d = ContentDraft(product_id=product.id, channel=channel, format=FORMATS.get(channel, DraftFormat.POST),
                         status=DraftStatus.SCHEDULED, body="Bài thử")  # fmt: skip
        db.add(d)
        await db.flush()
        live = status in (PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED)
        p = ScheduledPost(
            draft_id=d.id, channel=channel, product_id=product.id, status=status,
            scheduled_at=now_utc() + (timedelta(hours=-2) if live else timedelta(hours=5)),
            published_at=now_utc() if status == PostStatus.PUBLISHED else None,
            external_post_id=ext, external_url=f"https://mock.hangchon.local/{channel.value}/posts/{ext}" if ext else None,
        )  # fmt: skip
        db.add(p)
        await db.commit()
        return p.id


async def _listing(product: Product, mk: Channel, ext: str) -> uuid.UUID:
    async with SessionLocal() as db:
        li = MarketplaceListing(marketplace=mk, product_id=product.id, external_id=ext, status=ListingStatus.ACTIVE,
                                synced_stock=4)  # fmt: skip
        db.add(li)
        await db.commit()
        return li.id


@pytest.fixture
async def setup() -> dict:
    p = await make_product()
    ids = {
        "scheduled": await _post(p, Channel.FACEBOOK, PostStatus.APPROVED),
        "facebook": await _post(p, Channel.FACEBOOK, PostStatus.PUBLISHED, ext="fb_1"),
        "instagram": await _post(p, Channel.INSTAGRAM, PostStatus.PUBLISHED, ext="ig_1"),
        "threads": await _post(p, Channel.THREADS, PostStatus.PUBLISHED, ext="th_1"),
        "zalo": await _post(p, Channel.ZALO_OA, PostStatus.PUBLISHED, ext="za_1"),
        "tiktok": await _post(p, Channel.TIKTOK, PostStatus.DRAFT_PUSHED, ext="tt_1"),
        "shopee": await _listing(p, Channel.SHOPEE, "123"),
        "tts": await _listing(p, Channel.TIKTOK_SHOP, "p1:s1"),
    }
    drop = await make_drop([p])
    return {"product": p, "ids": ids, "drop": drop}


def _all_ticked(ids: dict, *, delete: bool = False, manual: tuple[str, ...] = ("zalo",)) -> dict:
    return {
        "cancel_post_ids": [str(ids["scheduled"])],
        "remove_posts": [
            {"id": str(ids[k]), "manual_done": k in manual}
            for k in ("facebook", "instagram", "threads", "zalo", "tiktok")
        ],
        "listing_ids": [str(ids["shopee"]), str(ids["tts"])],
        "delete_posts": delete,
    }


def _by_id(steps: list[dict]) -> dict[str, dict]:
    return {s["id"]: s for s in steps if s["id"]}


async def _post_status(pid: uuid.UUID) -> PostStatus:
    async with SessionLocal() as db:
        return (await db.get(ScheduledPost, pid)).status


async def test_plan_lists_every_channel_with_capabilities(owner_client: httpx.AsyncClient, setup) -> None:
    p, ids = setup["product"], setup["ids"]
    r = await owner_client.get(f"{BASE}/{p.id}/stop-plan")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["can_stop"] and plan["website_published"] and plan["last_stop"] is None
    assert [x["id"] for x in plan["scheduled_posts"]] == [str(ids["scheduled"])]
    caps = {x["channel"]: (x["can_hide"], x["can_delete"]) for x in plan["posts"]}
    assert caps == {"facebook": (True, True), "instagram": (False, True), "threads": (False, True),
                    "zalo_oa": (False, False), "tiktok": (False, False)}  # fmt: skip
    assert {x["marketplace"]: x["auto"] for x in plan["listings"]} == {"shopee": True, "tiktok_shop": True}
    assert [d["id"] for d in plan["drops"]] == [str(setup["drop"].id)]


async def test_stop_every_channel_hides_and_records_one_log_entry(owner_client: httpx.AsyncClient, setup) -> None:
    p, ids = setup["product"], setup["ids"]
    r = await owner_client.post(f"{BASE}/{p.id}/stop", json=_all_ticked(ids))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["product"]["status"] == "stopped" and out["activity_id"]
    steps = _by_id(out["steps"])
    assert out["steps"][0]["kind"] == "website" and out["steps"][0]["status"] == "done"
    assert steps[str(ids["scheduled"])]["status"] == "done"
    assert steps[str(ids["facebook"])]["status"] == "done" and "ẩn" in steps[str(ids["facebook"])]["detail"]
    assert steps[str(ids["instagram"])]["status"] == "needs_manual"  # chỉ xoá hẳn được, chị chưa chọn
    assert steps[str(ids["threads"])]["status"] == "needs_manual"
    assert steps[str(ids["zalo"])]["status"] == "done"  # chị tích «đã gỡ tay»
    assert steps[str(ids["tiktok"])]["status"] == "needs_manual"
    assert steps[str(ids["shopee"])]["status"] == "done" and steps[str(ids["tts"])]["status"] == "done"
    assert steps[str(setup["drop"].id)]["status"] == "needs_manual"  # đợt không tự đóng

    social, market = get_driver("social", "mock"), get_driver("marketplaces", "mock")
    assert social.hidden == {"fb_1"} and social.deleted == set()  # không xoá hẳn gì khi chị không chọn
    assert market.deactivated == {"123", "p1:s1"}
    assert await _post_status(ids["scheduled"]) == PostStatus.CANCELLED
    assert await _post_status(ids["facebook"]) == PostStatus.HIDDEN
    assert await _post_status(ids["instagram"]) == PostStatus.PUBLISHED
    assert await _post_status(ids["zalo"]) == PostStatus.REMOVED
    async with SessionLocal() as db:
        items = list(
            (await db.execute(select(ApprovalItem).where(ApprovalItem.action == "catalog.stop_selling"))).scalars()
        )
        acts = list((await db.execute(select(AIActivity).where(AIActivity.action == "catalog.stop_selling"))).scalars())
        li = await db.get(MarketplaceListing, ids["shopee"])
        audits = set((await db.execute(select(AuditLog.action))).scalars())
    assert len(items) == 1 and items[0].status == ApprovalStatus.APPROVED and not items[0].ai_generated
    assert len(acts) == 1 and acts[0].undoable and acts[0].undo_data["hidden_post_ids"] == [str(ids["facebook"])]
    assert li.status == ListingStatus.INACTIVE and li.data["stop"]["outcome"] == "deactivated"
    assert {"catalog.product_stopped", "content.post_hidden", "content.post_cancelled",
            "content.post_removed_manually", "orders.listing_deactivated", "control.approved"} <= audits  # fmt: skip

    again = await owner_client.post(f"{BASE}/{p.id}/stop", json=_all_ticked(ids))
    assert again.status_code == 400  # đã ngừng bán rồi


async def test_delete_only_when_chosen(owner_client: httpx.AsyncClient, setup) -> None:
    p, ids = setup["product"], setup["ids"]
    r = await owner_client.post(f"{BASE}/{p.id}/stop", json=_all_ticked(ids, delete=True, manual=()))
    assert r.status_code == 200, r.text
    steps = _by_id(r.json()["steps"])
    for k in ("facebook", "instagram", "threads"):
        assert steps[str(ids[k])]["status"] == "done" and "xoá hẳn" in steps[str(ids[k])]["detail"].lower()
        assert await _post_status(ids[k]) == PostStatus.REMOVED
    assert steps[str(ids["zalo"])]["status"] == "needs_manual"  # Zalo không gỡ tự động, chị chưa tích «đã gỡ tay»
    social = get_driver("social", "mock")
    assert social.deleted == {"fb_1", "ig_1", "th_1"} and social.hidden == set()

    # mở bán lại: bài đã xoá hẳn không quay lại, chỉ báo chị lên lịch bài mới
    back = await owner_client.post(f"{BASE}/{p.id}/resume")
    assert back.status_code == 200, back.text
    rs = _by_id(back.json()["steps"])
    assert (
        rs[str(ids["facebook"])]["status"] == "info" and "/desk/noi-dung/san-pham/" in rs[str(ids["facebook"])]["url"]
    )
    assert await _post_status(ids["facebook"]) == PostStatus.REMOVED


async def test_partial_failure_keeps_going_and_reports_reason(owner_client: httpx.AsyncClient, setup) -> None:
    p, ids = setup["product"], setup["ids"]
    get_driver("social", "mock").fail_remove.add("fb_1")
    get_driver("marketplaces", "mock").fail.add("123")
    r = await owner_client.post(f"{BASE}/{p.id}/stop", json=_all_ticked(ids))
    assert r.status_code == 200, r.text
    out = r.json()
    steps = _by_id(out["steps"])
    assert out["product"]["status"] == "stopped"
    assert steps[str(ids["facebook"])]["status"] == "failed" and "giả lập" in steps[str(ids["facebook"])]["detail"]
    assert steps[str(ids["shopee"])]["status"] == "failed" and steps[str(ids["tts"])]["status"] == "done"
    assert steps[str(ids["scheduled"])]["status"] == "done"
    assert await _post_status(ids["facebook"]) == PostStatus.PUBLISHED
    async with SessionLocal() as db:
        li = await db.get(MarketplaceListing, ids["shopee"])
        act = (await db.execute(select(AIActivity).where(AIActivity.action == "catalog.stop_selling"))).scalar_one()
    assert li.status == ListingStatus.ACTIVE and li.data["stop"]["outcome"] == "failed"
    assert act.undo_data["listing_ids"] == [str(ids["tts"])] and act.undo_data["hidden_post_ids"] == []


async def test_unticked_items_are_kept(owner_client: httpx.AsyncClient, setup) -> None:
    p, ids = setup["product"], setup["ids"]
    r = await owner_client.post(f"{BASE}/{p.id}/stop", json={"remove_posts": [{"id": str(ids["facebook"])}]})
    assert r.status_code == 200, r.text
    steps = _by_id(r.json()["steps"])
    assert steps[str(ids["scheduled"])]["status"] == "skipped" and steps[str(ids["shopee"])]["status"] == "skipped"
    assert await _post_status(ids["scheduled"]) == PostStatus.APPROVED
    assert get_driver("marketplaces", "mock").deactivated == set()


async def test_resume_restores_exactly_what_was_done(owner_client: httpx.AsyncClient, setup) -> None:
    p, ids = setup["product"], setup["ids"]
    assert (await owner_client.post(f"{BASE}/{p.id}/stop", json=_all_ticked(ids))).status_code == 200
    plan = (await owner_client.get(f"{BASE}/{p.id}/stop-plan")).json()
    assert not plan["can_stop"] and plan["last_stop"]["undoable"] and plan["last_stop"]["hidden_posts"] == 1

    r = await owner_client.post(f"{BASE}/{p.id}/resume")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["product"]["status"] == "published"
    steps = _by_id(out["steps"])
    assert steps[str(ids["facebook"])]["status"] == "done"
    assert steps[str(ids["shopee"])]["status"] == "done" and steps[str(ids["tts"])]["status"] == "done"
    assert steps[str(ids["zalo"])]["status"] == "info"  # gỡ tay: không tự hiện lại
    assert await _post_status(ids["facebook"]) == PostStatus.PUBLISHED
    assert await _post_status(ids["scheduled"]) == PostStatus.CANCELLED  # lịch đã huỷ không tự đặt lại
    assert get_driver("social", "mock").hidden == set()
    assert get_driver("marketplaces", "mock").deactivated == set()
    async with SessionLocal() as db:
        act = (await db.execute(select(AIActivity).where(AIActivity.action == "catalog.stop_selling"))).scalar_one()
        li = await db.get(MarketplaceListing, ids["tts"])
    assert act.undone_at is not None and li.data["stop"]["restored_at"]
    assert (await owner_client.post(f"{BASE}/{p.id}/resume")).status_code == 400  # không còn ngừng bán

    # ngừng bán lần hai vẫn chạy (lần ngừng mới, mã mới)
    again = await owner_client.post(f"{BASE}/{p.id}/stop", json=_all_ticked(ids, manual=()))
    assert again.status_code == 200, again.text
    assert _by_id(again.json()["steps"])[str(ids["facebook"])]["status"] == "done"


async def test_resume_keeps_paused_if_page_was_paused(owner_client: httpx.AsyncClient) -> None:
    p = await make_product(status=ProductStatus.PAUSED)
    assert (await owner_client.post(f"{BASE}/{p.id}/stop", json={})).status_code == 200
    r = await owner_client.post(f"{BASE}/{p.id}/resume")
    assert r.status_code == 200 and r.json()["product"]["status"] == "paused"


async def test_stopped_product_is_not_republished_by_jobs(owner_client: httpx.AsyncClient, setup) -> None:
    p, ids = setup["product"], setup["ids"]
    async with SessionLocal() as db:
        prod = await db.get(Product, p.id)
        prod.sale_mode = SaleMode.BOTH
        post = await db.get(ScheduledPost, ids["scheduled"])
        post.scheduled_at = now_utc() - timedelta(minutes=1)
        await db.commit()
    # chị bỏ tích lịch đăng: bài vẫn nằm trên lịch nhưng không được đăng khi món đang ngừng bán
    r = await owner_client.post(f"{BASE}/{p.id}/stop", json={"listing_ids": [str(ids["shopee"])]})
    assert r.status_code == 200, r.text
    published_before = len(get_driver("social", "mock").published)
    assert await JOBS["content.publish_due"](job_context()) == 0
    assert len(get_driver("social", "mock").published) == published_before
    assert await _post_status(ids["scheduled"]) == PostStatus.APPROVED
    now = await owner_client.post(f"/api/desk/content/posts/{ids['scheduled']}/publish-now")
    assert now.status_code == 409

    sync = await owner_client.post("/api/desk/orders/marketplaces/shopee/sync-products")
    assert sync.status_code == 200 and sync.json()["synced"] == 0
    async with SessionLocal() as db:
        li = await db.get(MarketplaceListing, ids["shopee"])
        assert li.status == ListingStatus.INACTIVE  # đồng bộ không bật lại

    pub = await owner_client.post(f"{BASE}/{p.id}/publish")
    assert pub.status_code == 400 and "ngừng bán" in pub.json()["detail"]
    store = await owner_client.get(f"/api/store/catalog/products/{p.slug}")
    assert store.status_code == 404


async def test_only_owner_and_only_selling_products(helper_client: httpx.AsyncClient, owner_client, setup) -> None:
    p = setup["product"]
    assert (await helper_client.post(f"{BASE}/{p.id}/stop", json={})).status_code == 403
    assert (await helper_client.get(f"{BASE}/{p.id}/stop-plan")).status_code == 200
    draft = await make_product(status=ProductStatus.DRAFT)
    assert (await owner_client.post(f"{BASE}/{draft.id}/stop", json={})).status_code == 400


async def test_stop_follows_autonomy_off(owner_client: httpx.AsyncClient, setup) -> None:
    p = setup["product"]
    r = await owner_client.patch("/api/desk/control/autonomy/catalog.stop_selling", json={"level": "off"})
    assert r.status_code == 200, r.text
    assert (await owner_client.post(f"{BASE}/{p.id}/stop", json={})).status_code == 400
    async with SessionLocal() as db:
        assert (await db.get(Product, p.id)).status == ProductStatus.PUBLISHED
        assert await db.scalar(select(func.count(AIActivity.id))) == 0


async def test_stop_cancels_drafts_awaiting_approval_and_blocks_approve(owner_client: httpx.AsyncClient) -> None:
    """Bài chờ duyệt luôn bị huỷ khi ngừng bán (kể cả chị không tích); duyệt / xếp lịch bị chặn khi món đang ngừng."""
    from app.core.errors import Conflict
    from app.modules.content.service import apply_publish_approval

    p = await make_product()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    drafts = detail["drafts"]
    assert drafts and all(d["approval_item_id_pending"] for d in drafts)
    async with SessionLocal() as db:
        waiting = list((await db.execute(select(ScheduledPost).where(ScheduledPost.product_id == p.id))).scalars())
    assert waiting and all(x.status == PostStatus.PLANNED for x in waiting)

    r = await owner_client.post(f"{BASE}/{p.id}/stop", json={})
    assert r.status_code == 200, r.text
    steps = _by_id(r.json()["steps"])
    for x in waiting:
        s = steps[str(x.id)]
        assert s["status"] == "done" and s["label"].startswith("Bài chờ duyệt"), s
    async with SessionLocal() as db:
        for x in waiting:
            post = await db.get(ScheduledPost, x.id)
            assert post.status == PostStatus.CANCELLED and post.removal["outcome"] == "cancelled"
        items = list(
            (await db.execute(select(ApprovalItem).where(ApprovalItem.action == "content.publish_post"))).scalars()
        )
        assert items and all(i.status == ApprovalStatus.CANCELLED for i in items)

    fb = next(d for d in drafts if d["channel"] == "facebook")
    a = await owner_client.post(f"/api/desk/content/drafts/{fb['id']}/approve", json={})
    assert a.status_code == 409 and "ngừng bán" in a.json()["detail"] and "Chị" in a.json()["detail"]
    async with SessionLocal() as db:
        assert (
            await db.scalar(
                select(func.count(ScheduledPost.id)).where(
                    ScheduledPost.product_id == p.id, ScheduledPost.status != PostStatus.CANCELLED
                )
            )
            == 0
        )  # không xếp lịch bài mới
        # việc duyệt còn sót trong hàng chờ (bài vẫn chờ) cũng không xếp lịch được
        stray = ScheduledPost(draft_id=uuid.UUID(fb["id"]), channel=Channel.FACEBOOK, product_id=p.id,
                              status=PostStatus.PLANNED, scheduled_at=now_utc() + timedelta(hours=3))  # fmt: skip
        db.add(stray)
        await db.flush()
        with pytest.raises(Conflict, match="ngừng bán"):
            await apply_publish_approval(db, {"draft_id": fb["id"], "scheduled_post_id": str(stray.id)}, None)
        assert stray.status == PostStatus.PLANNED


async def test_resume_asks_before_posting_overdue(owner_client: httpx.AsyncClient) -> None:
    """Mở bán lại: bài giữ lại đã quá giờ không tự đăng — theo chị chọn (đăng ngay / hẹn lại / bỏ); bài còn hạn giữ lịch."""
    p = await make_product()
    ids = {k: await _post(p, Channel.FACEBOOK, PostStatus.APPROVED) for k in ("now", "later", "drop", "none", "future")}
    async with SessionLocal() as db:
        for k in ("now", "later", "drop", "none"):
            (await db.get(ScheduledPost, ids[k])).scheduled_at = now_utc() - timedelta(hours=1)
        future_at = (await db.get(ScheduledPost, ids["future"])).scheduled_at
        await db.commit()
    assert (await owner_client.post(f"{BASE}/{p.id}/stop", json={})).status_code == 200  # chị giữ lại các lịch

    plan = (await owner_client.get(f"{BASE}/{p.id}/stop-plan")).json()
    assert {x["id"] for x in plan["overdue_posts"]} == {str(ids[k]) for k in ("now", "later", "drop", "none")}

    late = (now_utc() + timedelta(days=1)).replace(microsecond=0)
    choices = [
        {"id": str(ids["now"]), "action": "now"},
        {"id": str(ids["later"]), "action": "reschedule", "scheduled_at": late.isoformat()},
        {"id": str(ids["drop"]), "action": "drop"},
    ]
    past = [
        {"id": str(ids["later"]), "action": "reschedule", "scheduled_at": (now_utc() - timedelta(hours=1)).isoformat()}
    ]
    bad = await owner_client.post(f"{BASE}/{p.id}/resume", json={"overdue": past})
    assert bad.status_code == 400 and "sau bây giờ" in bad.json()["detail"]
    async with SessionLocal() as db:
        assert (await db.get(Product, p.id)).status == ProductStatus.STOPPED

    r = await owner_client.post(f"{BASE}/{p.id}/resume", json={"overdue": choices})
    assert r.status_code == 200, r.text
    assert r.json()["product"]["status"] == "published"
    steps = _by_id(r.json()["steps"])
    assert steps[str(ids["now"])]["status"] == "done" and "Đăng ngay" in steps[str(ids["now"])]["detail"]
    assert steps[str(ids["later"])]["status"] == "done" and "hẹn lại" in steps[str(ids["later"])]["detail"]
    assert steps[str(ids["drop"])]["status"] == "done"
    assert steps[str(ids["none"])]["status"] == "info"  # chị chưa chọn: không tự đăng
    assert str(ids["future"]) not in steps
    async with SessionLocal() as db:
        rows = {k: await db.get(ScheduledPost, v) for k, v in ids.items()}
    assert rows["now"].status == PostStatus.APPROVED and rows["now"].scheduled_at <= now_utc()
    assert rows["later"].status == PostStatus.APPROVED and rows["later"].scheduled_at == late
    assert rows["drop"].status == PostStatus.CANCELLED and rows["none"].status == PostStatus.CANCELLED
    assert rows["future"].status == PostStatus.APPROVED and rows["future"].scheduled_at == future_at

    social = get_driver("social", "mock")
    before = len(social.published)
    assert await JOBS["content.publish_due"](job_context()) == 1  # chỉ bài chị chọn «Đăng ngay»
    assert len(social.published) == before + 1
    assert await _post_status(ids["now"]) == PostStatus.PUBLISHED


async def test_resume_from_log_without_choices_does_not_post_overdue(owner_client: httpx.AsyncClient) -> None:
    """Hoàn tác từ Nhật ký AI (không có lựa chọn): bài quá giờ huỷ lịch, không đăng."""
    p = await make_product()
    pid = await _post(p, Channel.FACEBOOK, PostStatus.APPROVED)
    async with SessionLocal() as db:
        (await db.get(ScheduledPost, pid)).scheduled_at = now_utc() - timedelta(hours=1)
        await db.commit()
    r = await owner_client.post(f"{BASE}/{p.id}/stop", json={})
    assert r.status_code == 200, r.text
    undo = await owner_client.post(f"/api/desk/control/activity/{r.json()['activity_id']}/undo")
    assert undo.status_code in (200, 201), undo.text
    assert await _post_status(pid) == PostStatus.CANCELLED
    assert await JOBS["content.publish_due"](job_context()) == 0
