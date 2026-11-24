"""Dựng video ngắn (f6) + Kịch bản livestream (f8)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.enums import Actor, Channel
from app.core.storage import get_storage
from app.core.timeutil import now_utc
from app.modules.content.models import ContentDraft, LivestreamScript, MediaAsset
from app.modules.content.service import ACTION_LIVE, ACTION_VIDEO
from app.modules.control.models import ApprovalItem, ApprovalStatus
from app.modules.inbox.models import Direction, Message, Thread, ThreadKind

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _clip(seconds: int = 6, audio: bool = False) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "c.mp4"
        args = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=24:duration={seconds}"]
        if audio:
            args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(out)]
        subprocess.run(args, check=True, capture_output=True)
        return out.read_bytes()


async def _upload(client, data: bytes, product_id, note: str, name="clip.mp4", ctype="video/mp4"):
    return await client.post(
        "/api/desk/content/media",
        files={"file": (name, data, ctype)},
        data={"product_id": str(product_id), "note": note},
    )


async def test_upload_rejects_non_video(product_factory, owner_client):
    p = await product_factory()
    r = await _upload(owner_client, b"hello", p.id, "x", name="a.txt", ctype="text/plain")
    assert r.status_code == 400


@pytest.mark.skipif(not HAS_FFMPEG, reason="máy không có ffmpeg")
async def test_video_plan_render_and_approve(product_factory, owner_client):
    p = await product_factory()
    await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})
    clips = []
    for i, note in enumerate(["Rót trà nóng vào bình", "Tháo nắp, rửa", "Cầm bình ra ngoài trời"]):
        r = await _upload(owner_client, _clip(6, audio=i == 0), p.id, note)
        assert r.status_code == 201, r.text
        assert r.json()["duration_seconds"] == 6 and r.json()["purpose"] == "trial_clip"
        clips.append(r.json()["id"])
    r = await owner_client.post(
        "/api/desk/content/videos", json={"product_id": str(p.id), "clip_ids": clips, "target_seconds": 24}
    )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    v = (await owner_client.get(f"/api/desk/content/videos/{vid}")).json()  # job nền đã chạy (JOBS_EAGER)
    assert v["status"] == "pending_review", v["edit_spec"].get("render_note")
    assert v["edit_spec"]["render"] == "done" and v["width"] == 720 and v["height"] == 1280
    assert v["ai_generated"] and len(v["edit_spec"]["segments"]) == 3 and v["edit_spec"]["music"]["mood"]
    assert 10 <= v["duration_seconds"] <= 30
    assert await get_storage().exists(v["storage_key"])

    r = await owner_client.post(f"/api/desk/content/videos/{vid}/approve")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["status"] == "approved" and v["storage_key"].startswith("public/")
    async with SessionLocal() as db:
        tt = await db.scalar(select(ContentDraft).where(ContentDraft.channel == Channel.TIKTOK))
    assert tt.media_asset_ids == [vid]
    detail = (await owner_client.get(f"/api/desk/content/studio/product/{p.id}")).json()
    assert next(d for d in detail["drafts"] if d["channel"] == "tiktok")["video_url"]


async def test_video_without_ffmpeg_exports_plan(product_factory, owner_client, monkeypatch):
    monkeypatch.setattr(settings, "content_ffmpeg", False)
    p = await product_factory()
    async with SessionLocal() as db:
        a = MediaAsset(
            kind="video",
            purpose="trial_clip",
            status="ready",
            storage_key="private/x.mp4",
            content_type="video/mp4",
            duration_seconds=10,
            product_id=p.id,
            transcript="Đổ nước sôi",
        )
        db.add(a)
        await db.commit()
    r = await owner_client.post("/api/desk/content/videos", json={"product_id": str(p.id), "clip_ids": [str(a.id)]})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "pending_review" and v["edit_spec"]["render"] == "unavailable"
    assert "ffmpeg" in v["edit_spec"]["render_note"]
    async with SessionLocal() as db:
        item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == ACTION_VIDEO))
    assert item.status == ApprovalStatus.PENDING


async def test_livestream_from_drop_with_customer_questions(product_factory, drop_factory, owner_client, helper_client):
    a = await product_factory()
    b = await product_factory(name="Hộp cơm inox 3 ngăn", price_vnd=245_000)
    d = await drop_factory([a, b])
    async with SessionLocal() as db:
        t = Thread(channel=Channel.FACEBOOK, kind=ThreadKind.COMMENT, external_thread_id="t1", product_id=a.id)
        db.add(t)
        await db.flush()
        for i, body in enumerate(["Bình này giá bao nhiêu vậy chị?", "ok", "Bình này giá bao nhiêu vậy chị?"]):
            db.add(
                Message(
                    thread_id=t.id,
                    direction=Direction.INBOUND,
                    sender=Actor.CUSTOMER,
                    body=body,
                    sent_at=now_utc(),
                    external_message_id=f"m{i}",
                )
            )
        await db.commit()
    r = await helper_client.post("/api/desk/content/livestreams", json={"drop_id": str(d.id), "minutes": 30})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "pending_review" and s["drop_title"] == d.title
    assert [i["name"] for i in s["items"]] == [a.name, b.name]
    asked = [f for f in s["faq"] if f["source"] == "khach_hoi"]
    assert len(asked) == 1 and "385.000đ" in asked[0]["a"]
    assert sum(x["minutes"] for x in s["outline"]) >= 20

    r = await helper_client.post(f"/api/desk/content/livestreams/{s['id']}/approve")
    assert r.status_code == 403
    r = await owner_client.patch(f"/api/desk/content/livestreams/{s['id']}", json={"notes": "Nhớ cầm bình lên"})
    assert r.json()["notes"] == "Nhớ cầm bình lên"
    r = await owner_client.post(f"/api/desk/content/livestreams/{s['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    r = await owner_client.post(f"/api/desk/content/livestreams/{s['id']}/used")
    assert r.json()["status"] == "used"


async def test_livestream_return_regenerates(product_factory, owner_client):
    a = await product_factory()
    r = await owner_client.post("/api/desk/content/livestreams", json={"product_ids": [str(a.id)]})
    s = r.json()
    async with SessionLocal() as db:
        item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == ACTION_LIVE))
    r = await owner_client.post(
        f"/api/desk/control/approvals/{item.id}/return", json={"note": "thêm phần trả lời phí giao"}
    )
    assert r.status_code == 200
    async with SessionLocal() as db:
        row = await db.get(LivestreamScript, s["id"])
        new_item = await db.scalar(
            select(ApprovalItem).where(
                ApprovalItem.action == ACTION_LIVE, ApprovalItem.status == ApprovalStatus.PENDING
            )
        )
    assert row.notes == "thêm phần trả lời phí giao" and new_item is not None


async def test_livestream_needs_products(owner_client):
    r = await owner_client.post("/api/desk/content/livestreams", json={})
    assert r.status_code == 400
