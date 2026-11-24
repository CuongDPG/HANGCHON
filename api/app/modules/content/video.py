"""Dựng video ngắn (f6): clip chị quay khi thử hàng → AI lập kế hoạch dựng → có `ffmpeg` thì cắt-ghép-chèn phụ đề ra
file 9:16 thật (job nền), không có thì xuất kế hoạch dựng và báo rõ → chị xem trước, duyệt.

Phụ đề vẽ bằng Pillow thành ảnh trong suốt rồi `overlay` (không phụ thuộc bộ lọc drawtext/libass của ffmpeg)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core.enums import Channel
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.storage import get_storage, new_key
from app.modules.content import facts
from app.modules.content.ai_io import ClipFacts, VideoPlanIn, VideoPlanOut
from app.modules.content.models import (
    ContentDraft,
    DraftStatus,
    MediaAsset,
    MediaKind,
    MediaPurpose,
    MediaStatus,
)
from app.modules.content.service import ACTION_VIDEO, ACTION_VIDEO_PLAN
from app.modules.control.models import User

log = logging.getLogger("app.content.video")

MAX_CLIP_BYTES = 200 * 1024 * 1024
VIDEO_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm", "video/x-m4v": "m4v"}
W, H = 720, 1280  # 9:16
FONT_CANDIDATES = [
    os.environ.get("CONTENT_FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def ffmpeg_available() -> bool:
    if os.environ.get("CONTENT_FFMPEG", "1") == "0":
        return False
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


async def _run(*args: str, limit_s: float = 300) -> bytes:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        async with asyncio.timeout(limit_s):
            out, err = await proc.communicate()
    except TimeoutError:
        proc.kill()
        raise RuntimeError(f"{args[0]} chạy quá {int(limit_s)} giây") from None
    if proc.returncode != 0:
        raise RuntimeError(f"{args[0]} lỗi: {err.decode(errors='ignore')[-500:]}")
    return out


async def probe(path: str) -> dict[str, Any]:
    out = await _run(
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path, limit_s=60
    )
    data = json.loads(out or b"{}")
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "duration": float(data.get("format", {}).get("duration") or v.get("duration") or 0),
        "width": v.get("width"),
        "height": v.get("height"),
        "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


# ---- tải clip ----------------------------------------------------------------------------------------------------


async def upload_clip(
    db: AsyncSession,
    *,
    data: bytes,
    content_type: str,
    filename: str | None,
    product_id: uuid.UUID | None,
    note: str | None,
    user: User,
) -> MediaAsset:
    ctype = (content_type or "").split(";")[0].strip().lower()
    ext = VIDEO_TYPES.get(ctype) or (Path(filename or "").suffix.lstrip(".").lower() or None)
    if ext not in VIDEO_TYPES.values():
        raise BadRequest("Chỉ nhận clip video (mp4, mov, webm).")
    if not data:
        raise BadRequest("Tệp trống.")
    if len(data) > MAX_CLIP_BYTES:
        raise BadRequest("Clip lớn quá 200 MB, chị cắt ngắn bớt nhé.")
    if product_id and await facts.get_product(db, product_id) is None:
        raise NotFound("Không tìm thấy sản phẩm.")
    key = new_key("private/content/clips", ext)
    await get_storage().put(key, data, ctype or f"video/{ext}")
    meta: dict[str, Any] = {}
    if ffmpeg_available():
        with tempfile.NamedTemporaryFile(suffix=f".{ext}") as f:
            f.write(data)
            f.flush()
            try:
                meta = await probe(f.name)
            except RuntimeError as e:
                log.warning("Không đọc được clip: %s", e)
    asset = MediaAsset(
        kind=MediaKind.VIDEO,
        purpose=MediaPurpose.TRIAL_CLIP,
        status=MediaStatus.READY,
        storage_key=key,
        content_type=ctype or f"video/{ext}",
        size_bytes=len(data),
        width=meta.get("width"),
        height=meta.get("height"),
        duration_seconds=round(meta["duration"]) if meta.get("duration") else None,
        product_id=product_id,
        transcript=(note or "").strip() or None,
        edit_spec={"has_audio": meta.get("has_audio"), "filename": filename},
        uploaded_by_id=user.id,
    )
    db.add(asset)
    await db.flush()
    return asset


# ---- kế hoạch dựng -----------------------------------------------------------------------------------------------


async def plan_video(
    db: AsyncSession,
    *,
    product_id: uuid.UUID | None,
    clip_ids: list[uuid.UUID],
    notes: str | None,
    target_seconds: int,
    user: User | None,
) -> MediaAsset:
    if not clip_ids:
        raise BadRequest("Chị chọn ít nhất một clip.")
    clips = list((await db.execute(select(MediaAsset).where(MediaAsset.id.in_(clip_ids)))).scalars())
    by_id = {c.id: c for c in clips}
    ordered = [by_id[i] for i in clip_ids if i in by_id and by_id[i].purpose == MediaPurpose.TRIAL_CLIP]
    if not ordered:
        raise NotFound("Không tìm thấy clip đã chọn.")
    product = await facts.get_product(db, product_id) if product_id else None
    res = await ai.run(
        "content.plan_video",
        VideoPlanIn(
            product=facts.product_facts(product) if product else None,
            clips=[
                ClipFacts(index=i, duration_seconds=float(c.duration_seconds or 8), note=c.transcript)
                for i, c in enumerate(ordered)
            ],
            target_seconds=max(20, min(30, target_seconds)),
            notes=notes,
        ),
        VideoPlanOut,
    )
    plan = res.output
    segments = []
    for s in plan.segments:
        if not (0 <= s.clip_index < len(ordered)):
            continue
        clip = ordered[s.clip_index]
        dur = float(clip.duration_seconds or 8)
        start = max(0.0, min(s.start, dur - 0.5))
        end = max(start + 0.5, min(s.end, dur))
        segments.append(
            {"clip_id": str(clip.id), "start": round(start, 2), "end": round(end, 2), "caption": s.caption[:80]}
        )
    if not segments:
        raise ai.AIOutputInvalid("AI chưa chọn được đoạn nào từ các clip.")
    can_render = ffmpeg_available()
    spec = {
        "summary": plan.summary,
        "segments": segments,
        "music": plan.music.model_dump(),
        "cover_text": plan.cover_text,
        "clip_ids": [str(c.id) for c in ordered],
        "target_seconds": target_seconds,
        "notes": notes,
        "render": "queued" if can_render else "unavailable",
        "render_note": None
        if can_render
        else "Máy chủ chưa có ffmpeg nên chưa dựng ra file; đây là kế hoạch dựng để chị dựng trong CapCut/TikTok.",
        "total_seconds": round(sum(s["end"] - s["start"] for s in segments), 1),
    }
    out = await control.propose(
        ACTION_VIDEO_PLAN,
        f"Lập kế hoạch dựng video {spec['total_seconds']:.0f} giây" + (f": {product.name}" if product else ""),
        {
            "product_id": str(product.id) if product else None,
            "parent_asset_id": str(ordered[0].id),
            "edit_spec": spec,
            "ai_run_id": str(res.run_id),
            "user_id": str(user.id) if user else None,
        },
        preview={"summary": plan.summary, "segments": len(segments)},
        db=db,
        rationale="Chọn đoạn từ ghi chú từng clip, theo mạch: lý do xem → dùng thật → chưa ưng → giá.",
        ref_type="products" if product else None,
        ref_id=product.id if product else None,
        ai_run_id=res.run_id,
    )
    if out.status != "applied" or not out.result:
        raise Conflict("Việc dựng video đang chờ chị duyệt hoặc đang tắt ở Mức tự chủ.", code="not_applied")
    asset = await db.get(MediaAsset, uuid.UUID(out.result["asset_id"]))
    assert asset is not None
    return asset


async def apply_plan(db: AsyncSession, payload: dict[str, Any]) -> control.HandlerResult:
    spec = payload["edit_spec"]
    asset = MediaAsset(
        kind=MediaKind.VIDEO,
        purpose=MediaPurpose.EDITED_VIDEO,
        status=MediaStatus.PROCESSING if spec.get("render") == "queued" else MediaStatus.PENDING_REVIEW,
        storage_key="",
        content_type="video/mp4",
        product_id=uuid.UUID(payload["product_id"]) if payload.get("product_id") else None,
        parent_asset_id=uuid.UUID(payload["parent_asset_id"]),
        edit_spec=spec,
        duration_seconds=round(spec.get("total_seconds") or 0) or None,
        ai_generated=True,
        uploaded_by_id=uuid.UUID(payload["user_id"]) if payload.get("user_id") else None,
    )
    db.add(asset)
    await db.flush()
    if asset.status == MediaStatus.PENDING_REVIEW:
        await propose_review(db, asset)
    return control.HandlerResult(
        result={"asset_id": str(asset.id)}, summary=spec.get("summary"), ref_type="media_assets", ref_id=asset.id
    )


async def propose_review(db: AsyncSession, asset: MediaAsset) -> None:
    spec = asset.edit_spec
    rendered = spec.get("render") == "done"
    out = await control.propose(
        ACTION_VIDEO,
        ("Video dựng xong, chờ chị xem" if rendered else "Kế hoạch dựng video, chờ chị xem")
        + f" ({spec.get('total_seconds', 0):.0f} giây)",
        {"asset_id": str(asset.id)},
        preview={
            "summary": spec.get("summary"),
            "rendered": rendered,
            "storage_key": asset.storage_key or None,
            "segments": spec.get("segments"),
            "music": spec.get("music"),
        },
        db=db,
        summary=spec.get("render_note") or spec.get("summary"),
        ref_type="media_assets",
        ref_id=asset.id,
        dedupe_key=f"video:{asset.id}",
    )
    if out.item_id:
        asset.approval_item_id = out.item_id
        await db.flush()


# ---- dựng bằng ffmpeg --------------------------------------------------------------------------------------------


def _font(size: int) -> Any:
    from PIL import ImageFont

    for p in FONT_CANDIDATES:
        if p and Path(p).is_file():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def caption_png(text: str, path: str) -> None:
    """Ảnh phụ đề trong suốt 720×1280: dải nền tối mờ ở 1/4 dưới, chữ trắng căn giữa, tự xuống dòng."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _font(46)
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) > W - 120 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    lines = lines[:3]
    lh = 60
    box_h = lh * len(lines) + 40
    top = int(H * 0.72)
    draw.rounded_rectangle((40, top, W - 40, top + box_h), radius=8, fill=(28, 29, 34, 170))
    for i, line in enumerate(lines):
        tw = draw.textlength(line, font=font)
        draw.text(((W - tw) / 2, top + 20 + i * lh), line, font=font, fill=(255, 255, 255, 255))
    img.save(path)


async def render(asset: MediaAsset, clips: dict[str, MediaAsset]) -> tuple[bytes, float]:
    storage = get_storage()
    spec = asset.edit_spec
    with tempfile.TemporaryDirectory(prefix="hangchon-video-") as tmp:
        src: dict[str, tuple[str, bool]] = {}
        for cid, clip in clips.items():
            ext = Path(clip.storage_key).suffix or ".mp4"
            p = os.path.join(tmp, f"src-{cid}{ext}")
            blob = await storage.get(clip.storage_key)
            await asyncio.to_thread(Path(p).write_bytes, blob)
            src[cid] = (p, (await probe(p))["has_audio"])
        parts = []
        for i, seg in enumerate(spec["segments"]):
            path, has_audio = src[seg["clip_id"]]
            cap = os.path.join(tmp, f"cap-{i}.png")
            caption_png(seg["caption"], cap)
            out = os.path.join(tmp, f"part-{i}.mp4")
            dur = max(0.5, float(seg["end"]) - float(seg["start"]))
            vf = (
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30[v];"
                "[v][1:v]overlay=0:0[vo]"
            )
            args = ["ffmpeg", "-y", "-ss", str(seg["start"]), "-t", f"{dur:.2f}", "-i", path, "-i", cap]
            if not has_audio:
                args += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            args += [
                "-filter_complex",
                vf,
                "-map",
                "[vo]",
                "-map",
                "0:a" if has_audio else "2:a",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-shortest",
                out,
            ]
            await _run(*args)
            parts.append(out)
        lst = os.path.join(tmp, "list.txt")
        await asyncio.to_thread(Path(lst).write_text, "".join(f"file '{p}'\n" for p in parts))
        final = os.path.join(tmp, "final.mp4")
        await _run(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", final
        )
        meta = await probe(final)
        return await asyncio.to_thread(Path(final).read_bytes), meta["duration"]


async def render_job(db: AsyncSession, asset_id: uuid.UUID) -> MediaAsset | None:
    asset = await db.get(MediaAsset, asset_id)
    if asset is None or asset.status != MediaStatus.PROCESSING:
        return asset
    spec = dict(asset.edit_spec)
    ids = [uuid.UUID(s["clip_id"]) for s in spec.get("segments", [])]
    clips = {str(c.id): c for c in (await db.execute(select(MediaAsset).where(MediaAsset.id.in_(ids)))).scalars()}
    try:
        if not ffmpeg_available():
            raise RuntimeError("Máy chủ không có ffmpeg")
        data, duration = await render(asset, clips)
    except Exception as e:
        log.warning("Dựng video %s lỗi: %s", asset.id, e)
        spec.update(render="failed", render_note=f"Chưa dựng được file: {str(e)[:300]}. Kế hoạch dựng vẫn dùng được.")
        asset.edit_spec = spec
        asset.status = MediaStatus.PENDING_REVIEW
        await db.flush()
        await propose_review(db, asset)
        return asset
    key = new_key("private/content/videos", "mp4")
    await get_storage().put(key, data, "video/mp4")
    asset.storage_key = key
    asset.size_bytes = len(data)
    asset.duration_seconds = round(duration)
    asset.width, asset.height = W, H
    spec.update(render="done", render_note=None)
    asset.edit_spec = spec
    asset.status = MediaStatus.PENDING_REVIEW
    await db.flush()
    await propose_review(db, asset)
    return asset


async def apply_approve(db: AsyncSession, payload: dict[str, Any]) -> control.HandlerResult:
    """Chị duyệt video: chuyển file sang khu công khai (để mạng xã hội kéo về) và gắn vào bản TikTok của sản phẩm."""
    asset = await db.get(MediaAsset, uuid.UUID(payload["asset_id"]))
    if asset is None or asset.status != MediaStatus.PENDING_REVIEW:
        raise Conflict("Video này không còn chờ duyệt.", code="not_pending")
    attached = None
    if asset.storage_key and asset.edit_spec.get("render") == "done":
        storage = get_storage()
        pub = new_key("public/content/videos", "mp4")
        await storage.put(pub, await storage.get(asset.storage_key), "video/mp4")
        old = asset.storage_key
        asset.storage_key = pub
        await storage.delete(old)
        if asset.product_id:
            draft = await db.scalar(
                select(ContentDraft)
                .where(
                    ContentDraft.product_id == asset.product_id,
                    ContentDraft.drop_id.is_(None),
                    ContentDraft.channel == Channel.TIKTOK,
                    ContentDraft.status.not_in((DraftStatus.ARCHIVED, DraftStatus.PUBLISHED)),
                )
                .order_by(ContentDraft.created_at.desc())
                .limit(1)
            )
            if draft is not None:
                draft.media_asset_ids = [str(asset.id)]
                attached = str(draft.id)
    asset.status = MediaStatus.APPROVED
    await db.flush()
    return control.HandlerResult(
        result={"asset_id": str(asset.id), "attached_draft_id": attached},
        summary="Đã duyệt video" + (" và gắn vào bản TikTok" if attached else ""),
        ref_type="media_assets",
        ref_id=asset.id,
    )
