"""Xưởng nội dung (f1) + soát lời (f5) + duyệt, xếp lịch."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core import events
from app.core.db import SessionLocal
from app.core.enums import Channel
from app.core.jobs import JOBS, job_context
from app.modules.content.models import CheckStatus, ContentDraft, DraftStatus, PostStatus, ScheduledPost
from app.modules.content.service import ACTION_PUBLISH
from app.modules.control.models import ApprovalItem, ApprovalStatus, AuditLog


async def _emit_published(product_id) -> None:
    async with SessionLocal() as db:
        await events.emit("product.published", {"product_id": str(product_id)}, db=db)
        await db.commit()


async def _sweep() -> int:
    return await JOBS["content.compose_pending"](job_context())


async def _drafts(product_id) -> list[ContentDraft]:
    async with SessionLocal() as db:
        q = select(ContentDraft).where(
            ContentDraft.product_id == product_id, ContentDraft.status != DraftStatus.ARCHIVED
        )
        return list((await db.execute(q.order_by(ContentDraft.created_at))).scalars())


async def _pending(action=ACTION_PUBLISH) -> list[ApprovalItem]:
    async with SessionLocal() as db:
        q = select(ApprovalItem).where(ApprovalItem.action == action, ApprovalItem.status == ApprovalStatus.PENDING)
        return list((await db.execute(q)).scalars())


async def test_product_published_creates_one_draft_per_channel(product_factory):
    p = await product_factory()
    await _emit_published(p.id)
    await _emit_published(p.id)  # lặp lại không sinh trùng
    ds = await _drafts(p.id)
    assert {d.channel for d in ds} == {
        Channel.FACEBOOK,
        Channel.INSTAGRAM,
        Channel.THREADS,
        Channel.TIKTOK,
        Channel.ZALO_OA,
    }
    assert all(d.status == DraftStatus.DRAFTING for d in ds)

    assert await _sweep() == 1
    ds = await _drafts(p.id)
    assert len(ds) == 5
    assert all(d.status == DraftStatus.PENDING_REVIEW for d in ds)
    bodies = {d.channel: d.body for d in ds}
    assert len(set(bodies.values())) == 5, "mỗi kênh một cách viết"
    assert "385.000đ" in bodies[Channel.FACEBOOK]
    ig = next(d for d in ds if d.channel == Channel.INSTAGRAM)
    assert ig.script and all("caption" in s for s in ig.script)  # thứ tự ảnh + chú thích
    tt = next(d for d in ds if d.channel == Channel.TIKTOK)
    assert 20 <= sum(s["seconds"] for s in tt.script) <= 30
    assert all(d.ai_generated and d.check_status == CheckStatus.PASSED for d in ds)
    # mỗi bản có một bài trên lịch (planned) và một việc chờ duyệt đăng, link mang mã bài
    async with SessionLocal() as db:
        posts = list((await db.execute(select(ScheduledPost))).scalars())
    assert len(posts) == 5 and all(x.status == PostStatus.PLANNED for x in posts)
    assert all(d.link_url and "?src=" in d.link_url for d in ds)
    assert len(await _pending()) == 5
    assert await _sweep() == 0  # đã soạn rồi


async def test_drop_opened_drafts(product_factory, drop_factory, owner_client):
    a = await product_factory()
    b = await product_factory(name="Hộp cơm inox 3 ngăn", price_vnd=245_000)
    d = await drop_factory([a, b])
    async with SessionLocal() as db:
        await events.emit("drop.opened", {"drop_id": str(d.id)}, db=db)
        await db.commit()
    await _sweep()
    r = await owner_client.get(f"/api/desk/content/studio/drop/{d.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert {x["channel"] for x in data["drafts"]} == {"facebook", "instagram", "zalo_oa"}
    fb = next(x for x in data["drafts"] if x["channel"] == "facebook")
    assert "245.000đ" in fb["body"] and "/dot/" in fb["link_url"]


async def test_studio_list_and_detail(product_factory, owner_client):
    p = await product_factory()
    r = await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})
    assert r.status_code == 200, r.text
    detail = r.json()
    assert len(detail["drafts"]) == 5 and detail["name"] == p.name
    assert detail["page_status"] == "published"  # thẻ «Website · trang sản phẩm» ở studio
    assert all(x["can_approve"] for x in detail["drafts"])
    assert all(x["approval_item_id_pending"] for x in detail["drafts"])
    lst = (await owner_client.get("/api/desk/content/studio")).json()
    row = next(i for i in lst["items"] if i["id"] == str(p.id))
    assert row["total"] == 5 and row["approved"] == 0 and row["pending"] == 5


async def test_studio_list_includes_selected_products_before_website(product_factory, owner_client):
    """Món vừa chọn (trang website còn nháp) đã có ở xưởng: Website là kênh đầu tiên; món lưu trữ thì không."""
    from app.modules.catalog.models import ProductStatus

    draft = await product_factory(name="Khay đá silicon", status=ProductStatus.PENDING_REVIEW)
    gone = await product_factory(name="Món đã lưu trữ", status=ProductStatus.ARCHIVED)
    items = (await owner_client.get("/api/desk/content/studio")).json()["items"]
    row = next(i for i in items if i["id"] == str(draft.id))
    assert row["status"] == "pending_review" and row["total"] == 0
    assert all(i["id"] != str(gone.id) for i in items)
    detail = (await owner_client.get(f"/api/desk/content/studio/product/{draft.id}")).json()
    assert detail["page_status"] == "pending_review" and detail["drafts"] == []


async def test_approve_schedules_through_queue(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    fb = next(x for x in detail["drafts"] if x["channel"] == "facebook")
    r = await owner_client.post(f"/api/desk/content/drafts/{fb['id']}/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled" and r.json()["post"]["status"] == "approved"
    async with SessionLocal() as db:
        item = await db.get(ApprovalItem, fb["approval_item_id_pending"])
        assert item.status == ApprovalStatus.APPROVED
        assert await db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "control.approved")) == 1


async def test_helper_cannot_approve(product_factory, owner_client, helper_client):
    p = await product_factory()
    detail = (await helper_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    d = detail["drafts"][0]
    r = await helper_client.post(f"/api/desk/content/drafts/{d['id']}/approve", json={})
    assert r.status_code == 403


async def test_unauthenticated(client):
    assert (await client.get("/api/desk/content/studio")).status_code == 401


async def test_failed_check_blocks_approval_until_fixed_or_overridden(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    fb = next(x for x in detail["drafts"] if x["channel"] == "facebook")
    body = fb["body"] + "\n\nĐây là bình giữ nhiệt tốt nhất, giá chỉ 350.000đ."
    r = await owner_client.patch(f"/api/desk/content/drafts/{fb['id']}", json={"body": body})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["check_status"] == "failed" and not d["can_approve"]
    chips = {f["key"]: f for f in d["check_findings"]}
    assert not chips["numbers"]["ok"] and "350.000đ" in chips["numbers"]["detail"]
    assert not chips["claims"]["ok"] and "tốt nhất" in chips["claims"]["detail"]
    assert chips["ai_label"]["ok"]
    assert d["approval_item_id_pending"] is None  # rút khỏi hàng chờ
    r = await owner_client.post(f"/api/desk/content/drafts/{fb['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "check_failed"

    # bỏ qua cần lý do
    r = await owner_client.post(f"/api/desk/content/drafts/{fb['id']}/override", json={"key": "claims", "reason": ""})
    assert r.status_code == 400
    r = await owner_client.post(
        f"/api/desk/content/drafts/{fb['id']}/override",
        json={"key": "claims", "reason": "Trích lời khách, đã xin phép"},
    )
    assert r.json()["check_status"] == "failed"  # còn mục số liệu
    # sửa số liệu cho đúng → còn mục đã bỏ qua → được duyệt
    r = await owner_client.patch(
        f"/api/desk/content/drafts/{fb['id']}", json={"body": body.replace("350.000đ", "385.000đ")}
    )
    d = r.json()
    assert d["check_status"] == "warnings" and d["can_approve"] and d["approval_item_id_pending"]
    r = await owner_client.post(f"/api/desk/content/drafts/{fb['id']}/approve", json={})
    assert r.status_code == 200, r.text
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "content.check_override")) == 1


async def test_rewrite_presets_make_new_version(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    fb = next(x for x in detail["drafts"] if x["channel"] == "facebook")
    r = await owner_client.post(f"/api/desk/content/drafts/{fb['id']}/rewrite", json={"preset": "shorter"})
    assert r.status_code == 200, r.text
    new = r.json()["draft"]
    assert r.json()["status"] == "applied"
    assert new["id"] != fb["id"] and new["version"] == 2 and new["parent_draft_id"] == fb["id"]
    assert len(new["body"]) < len(fb["body"])
    assert new["post"]["id"] == fb["post"]["id"]  # giữ chỗ trên lịch
    r = await owner_client.post(f"/api/desk/content/drafts/{new['id']}/rewrite", json={"preset": "warmer"})
    assert r.json()["draft"]["body"].startswith("Cả nhà ơi")
    r = await owner_client.post(f"/api/desk/content/drafts/{fb['id']}/rewrite", json={"preset": "price"})
    assert r.status_code == 409  # bản cũ đã archived
    r = await owner_client.post(f"/api/desk/content/drafts/{new['id']}/rewrite", json={"instruction": "  "})
    assert r.status_code == 409 or r.status_code == 400
    async with SessionLocal() as db:
        pending = list(
            (
                await db.execute(
                    select(ApprovalItem).where(
                        ApprovalItem.action == ACTION_PUBLISH, ApprovalItem.status == ApprovalStatus.PENDING
                    )
                )
            ).scalars()
        )
    assert len(pending) == 5  # mỗi kênh vẫn đúng một việc chờ


async def test_return_from_queue_rewrites(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    th = next(x for x in detail["drafts"] if x["channel"] == "threads")
    r = await owner_client.post(
        f"/api/desk/control/approvals/{th['approval_item_id_pending']}/return", json={"note": "nhắc thêm nắp tháo rời"}
    )
    assert r.status_code == 200, r.text
    detail = (await owner_client.get(f"/api/desk/content/studio/product/{p.id}")).json()
    th2 = next(x for x in detail["drafts"] if x["channel"] == "threads")
    assert th2["version"] == 2 and th2["feedback_note"] == "nhắc thêm nắp tháo rời"
    assert th2["approval_item_id_pending"]


async def test_auto_level_schedules_without_asking(product_factory, owner_client):
    r = await owner_client.patch(f"/api/desk/control/autonomy/{ACTION_PUBLISH}", json={"level": "auto"})
    assert r.status_code == 200, r.text
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    assert all(x["post"]["status"] == "approved" for x in detail["drafts"])
    assert await _pending() == []


async def test_approve_in_queue_with_edit_rechecks(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    z = next(x for x in detail["drafts"] if x["channel"] == "zalo_oa")
    r = await owner_client.post(
        f"/api/desk/control/approvals/{z['approval_item_id_pending']}/approve",
        json={"payload": {"body": "Cả nhà ơi, bình này chữa bệnh đau họng nhé, giá 385.000đ, ai cần nhắn mình."}},
    )
    assert r.json()["status"] == "failed"  # soát lại bằng luật: «chữa bệnh» → không cho duyệt
    r = await owner_client.post(
        f"/api/desk/control/approvals/{z['approval_item_id_pending']}/approve",
        json={
            "payload": {
                "body": "Cả nhà ơi, mình vừa lên kệ bình giữ nhiệt, giá 385.000đ, ai cần nhắn mình giữ suất nhé."
            }
        },
    )
    assert r.json()["status"] == "approved", r.text
