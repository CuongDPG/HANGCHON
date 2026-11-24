"""Dữ liệu mẫu cho nguồn cung (ví dụ, không phải dữ liệu thật). Chạy lại không sinh trùng.

uv run python -m app.seed && uv run python -m app.modules.supply.seed
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.enums import Language, SourcePlatform
from app.core.storage import get_storage, new_key
from app.core.timeutil import local_today, now_utc
from app.modules.control.models import User, UserRole
from app.modules.selection import seed as selection_seed
from app.modules.sourcing.models import Candidate
from app.modules.supply import service
from app.modules.supply.models import (
    DocumentKind,
    InboundShipment,
    InboundStatus,
    POKind,
    ProvenanceDocument,
    Supplier,
    SupplierChannel,
    SupplierKind,
)

log = logging.getLogger("app.supply.seed")

SUPPLIERS = [
    (
        "nghia-o",
        "Xưởng gia dụng Nghĩa Ô (ví dụ)",
        "义乌家居厂",
        SupplierKind.FACTORY,
        SourcePlatform.ALIBABA_1688,
        "CN",
        Language.ZH,
    ),
    ("go-moc", "Shop Gia Dụng Mộc (ví dụ)", "木木家居店", SupplierKind.SHOP, SourcePlatform.TAOBAO, "CN", Language.ZH),
    (
        "imabari",
        "Shop khăn Imabari (ví dụ)",
        "今治タオル工房",
        SupplierKind.SHOP,
        SourcePlatform.AMAZON_JP,
        "JP",
        Language.JA,
    ),
    (
        "bento",
        "Cửa hàng bento Osaka (ví dụ)",
        "大阪弁当箱店",
        SupplierKind.SHOP,
        SourcePlatform.RAKUTEN,
        "JP",
        Language.JA,
    ),
    ("mua-ho", "Mua hộ Quảng Châu – Hà Nội (ví dụ)", None, SupplierKind.PURCHASING_AGENT, None, "VN", Language.VI),
]
# ứng viên mẫu (khoá trong selection.seed) → nhà cung cấp
LINKS = {
    "gia-x": "nghia-o", "kep-inox": "nghia-o", "gia-bc": "nghia-o", "binh-tt": "nghia-o", "thot": "nghia-o",
    "gio-giat": "go-moc", "ke-cua": "go-moc", "moc-dan": "go-moc", "hop-nhua": "go-moc",
    "khan-be": "imabari", "hop-com-3": "bento",
}  # fmt: skip
SHEETS = {"gia-x": 10000, "kep-inox": 3000, "binh-tt": 4000, "khan-be": 0, "hop-com-3": 0, "gio-giat": 5000}

TINY_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def _owner(db: AsyncSession) -> User | None:
    return await db.scalar(select(User).where(User.role == UserRole.OWNER).limit(1))


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    await selection_seed.seed_demo(db)
    counts = {"suppliers": 0, "cost_sheets": 0, "purchase_orders": 0}
    if await db.scalar(select(Supplier.id).where(Supplier.external_shop_id.like("demo-sup-%")).limit(1)):
        return counts
    owner = await _owner(db)
    sups: dict[str, Supplier] = {}
    for key, name, orig, kind, platform, country, lang in SUPPLIERS:
        s = Supplier(
            name=name, name_original=orig, kind=kind, platform=platform, country=country, language=lang,
            external_shop_id=f"demo-sup-{key}", shop_url=f"https://example.com/shop/{key}",
            agent_fee_pct=Decimal("3") if kind == SupplierKind.PURCHASING_AGENT else None,
            notes="Dữ liệu mẫu." if kind != SupplierKind.PURCHASING_AGENT else "Gom hàng kho Quảng Châu, về Hà Nội 5–7 ngày.",
        )  # fmt: skip
        db.add(s)
        sups[key] = s
        counts["suppliers"] += 1
    await db.flush()
    cands = {
        c.source_external_id.removeprefix(f"{selection_seed.MARK}-"): c
        for c in (
            await db.execute(select(Candidate).where(Candidate.source_external_id.like(f"{selection_seed.MARK}-%")))
        ).scalars()
    }
    for ck, sk in LINKS.items():
        if ck in cands:
            cands[ck].supplier_id = sups[sk].id  # ứng viên mẫu do lát cắt này tạo
    await db.flush()

    for key, domestic in SHEETS.items():
        c = cands[key]
        await service.save_cost_sheet(
            db, {"candidate_id": c.id, "supplier_id": c.supplier_id, "unit_price_amount": c.price_amount,
                 "currency": c.price_currency, "weight_grams": c.weight_grams, "domestic_shipping_vnd": domestic,
                 "auto_update": True},
        )  # fmt: skip
        counts["cost_sheets"] += 1

    # d3: đề xuất giá
    approved = await service.propose_price(db, cands["kep-inox"].id)
    await service.propose_price(db, cands["binh-tt"].id)
    if owner and approved.approval_item_id:
        await control.approve(db, approved.approval_item_id, owner)

    # d5: đơn mua mẫu chờ duyệt (giỏ giặt) và đơn mẫu đã gửi (hộp cơm)
    await service.sample_order_for(db, cands["gio-giat"].id)
    counts["purchase_orders"] += 1
    po = await service.sample_order_for(db, cands["hop-com-3"].id, quantity=2)
    counts["purchase_orders"] += 1
    if owner and po and po.approval_item_id:
        await control.approve(db, po.approval_item_id, owner)
        po.expected_at = local_today() + timedelta(days=4)
        await service.set_po_status(db, po, "sent", owner, None)
        await service.record_payment(db, po, {"amount_vnd": po.total_vnd, "kind": "payment"}, owner)
        ship = await db.scalar(select(InboundShipment).where(InboundShipment.purchase_order_id == po.id))
        if ship:
            ship.carrier, ship.code, ship.eta = "Mua hộ (ví dụ)", "KIEN-JP-0412", local_today() + timedelta(days=4)
            ship.milestones = [{**ship.milestones[0], "at": (now_utc() - timedelta(days=6)).isoformat()}]
            for st, ago in ((InboundStatus.SELLER_SHIPPED, 5), (InboundStatus.AT_AGENT_WAREHOUSE, 3),
                            (InboundStatus.INTERNATIONAL_TRANSIT, 1)):  # fmt: skip
                await service.add_milestone(db, ship, st, note="Cập nhật mẫu", at=now_utc() - timedelta(days=ago))

    # đơn lô kẹp phơi đã về, có hoá đơn nhưng thiếu ảnh nhãn gốc → cảnh báo chứng từ
    lot = await service.create_po(
        db,
        {"kind": POKind.BATCH, "supplier_id": sups["nghia-o"].id, "agent_supplier_id": sups["mua-ho"].id,
         "candidate_id": cands["kep-inox"].id, "currency": "CNY", "expected_at": local_today() - timedelta(days=2),
         "notes": "Lô đầu cho đợt mở bán (dữ liệu mẫu).",
         "lines": [{"candidate_id": cands["kep-inox"].id, "description": "不锈钢晾衣夹20个", "quantity": 60,
                    "unit_price_amount": Decimal("16.5"), "source_url": cands["kep-inox"].source_url}]},
    )  # fmt: skip
    counts["purchase_orders"] += 1
    await service.submit_po(db, lot)
    if owner and lot.approval_item_id:
        await control.approve(db, lot.approval_item_id, owner)
        await service.set_po_status(db, lot, "sent", owner, None)
        lot.sent_at = now_utc() - timedelta(days=12)
        await service.record_payment(db, lot, {"amount_vnd": lot.total_vnd // 2, "kind": "deposit"}, owner)
        ship = await db.scalar(select(InboundShipment).where(InboundShipment.purchase_order_id == lot.id))
        if ship:
            ship.carrier, ship.code, ship.weight_kg = "Mua hộ (ví dụ)", "KIEN-CN-1180", Decimal("36.5")
            ship.milestones = [{**ship.milestones[0], "at": (now_utc() - timedelta(days=12)).isoformat()}]
            for st, ago in ((InboundStatus.AT_AGENT_WAREHOUSE, 9), (InboundStatus.INTERNATIONAL_TRANSIT, 7),
                            (InboundStatus.CUSTOMS, 5), (InboundStatus.DOMESTIC_TRANSIT, 4), (InboundStatus.DELIVERED, 3)):  # fmt: skip
                await service.add_milestone(db, ship, st, note="Cập nhật mẫu", at=now_utc() - timedelta(days=ago))
        await service.receive_po(db, lot, [{"line_id": lot.lines[0].id, "received_qty": 60, "defect_qty": 2}])
        lot.received_at = now_utc() - timedelta(days=3)
        await service.recompute_supplier(db, sups["nghia-o"].id)
        stored = await get_storage().put(new_key("private/provenance", "pdf"), TINY_PDF, "application/pdf")
        db.add(
            ProvenanceDocument(
                kind=DocumentKind.INVOICE, purchase_order_id=lot.id, supplier_id=sups["nghia-o"].id,
                storage_key=stored.key, filename="hoa-don-mau.pdf", content_type="application/pdf",
                size_bytes=stored.size, doc_number="HD-MAU-001", doc_date=local_today() - timedelta(days=12),
                amount=Decimal("990"), currency="CNY", uploaded_by_id=owner.id,
            )
        )  # fmt: skip

    # d6: hỏi giá xưởng Nghĩa Ô, đã gửi và có câu trả lời
    msg = await service.draft_inquiry(
        db,
        sups["nghia-o"],
        {"candidate_id": cands["gia-x"].id, "topics": ["price", "moq", "lead_time"], "quantity": 100},
    )
    if owner and msg.approval_item_id:
        await control.approve(db, msg.approval_item_id, owner)
        await service.mark_sent(db, msg, SupplierChannel.PLATFORM_CHAT)
        await service.record_reply(
            db,
            sups["nghia-o"],
            {"candidate_id": cands["gia-x"].id, "body_original": "亲，100件单价28元，50件起订，下单后3天发货。"},
        )
    await service.draft_inquiry(
        db, sups["imabari"], {"candidate_id": cands["khan-be"].id, "topics": ["price", "sample"]}
    )
    await db.flush()
    return counts


async def main() -> None:
    from app.core.db import SessionLocal
    from app.core.discovery import discover_modules

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    discover_modules()
    async with SessionLocal() as db:
        counts = await seed_demo(db)
        await db.commit()
    log.info("Dữ liệu mẫu bàn chọn + nguồn cung: %s", counts)


if __name__ == "__main__":
    asyncio.run(main())
