"""Nghiệp vụ nguồn cung và giá vốn (d1–d7).

Đặt hàng / trả tiền nhà cung cấp luôn chờ chị (`supply.place_order` khoá «Luôn hỏi chị»). Module khác nhận tin qua
sự kiện: `price.approved`, `inbound.arrived`, `expense.recorded` (ARCHITECTURE mục 10)."""

from __future__ import annotations

import logging
import secrets
import statistics
import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.enums import Language
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.money import format_vnd, margin_pct, to_vnd
from app.core.timeutil import local_today, now_utc, to_local
from app.integrations import get_driver
from app.integrations.base import IntegrationError
from app.modules.assessment.models import MarketPrice
from app.modules.catalog.models import Drop, DropItem, Product
from app.modules.control.models import User
from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.sourcing.models import Candidate
from app.modules.supply.ai_tasks import (
    ComposeOrderIn,
    ComposeOrderOut,
    InquiryAIIn,
    InquiryAIOut,
    MarketSample,
    OrderLineBrief,
    PriceIn,
    PriceOut,
    ReplyAIIn,
    ReplyAIOut,
)
from app.modules.supply.models import (
    CostSheet,
    DocumentKind,
    InboundShipment,
    InboundStatus,
    MessageDirection,
    POKind,
    POStatus,
    PriceProposal,
    ProposalStatus,
    ProvenanceDocument,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierChannel,
    SupplierMessage,
    SupplierMessageStatus,
)
from app.modules.supply.schemas import CostParams

log = logging.getLogger("app.supply")

# ---- d2: tham số giá vốn -------------------------------------------------------------------------------------------

COST_PARAMS_KEY = "supply.cost_params"
DEFAULT_COST_PARAMS: dict[str, Any] = {
    "fx_rates": {"CNY": 3650, "JPY": 172, "USD": 26000},
    "intl_vnd_per_kg": {"CN": 14000, "JP": 200000},
    "agent_fee_pct": 3,
    "domestic_shipping_vnd": 5000,
    "import_tax_pct": 0,
    "vat_pct": 10,
    "loss_pct": 2,
    "packaging_vnd": 2000,
    "target_margin_pct": 35,
}
CURRENCY_COUNTRY = {"CNY": "CN", "JPY": "JP"}
PCT = Decimal(100)


async def cost_params(db: AsyncSession) -> CostParams:
    raw = await control.get_setting(db, COST_PARAMS_KEY)
    merged = {**DEFAULT_COST_PARAMS, **(raw if isinstance(raw, dict) else {})}
    return CostParams.model_validate(merged)


def _d(v: Any) -> Decimal:
    return Decimal(str(v))


def _pct(base: int, pct: Decimal) -> int:
    return int((Decimal(base) * pct / PCT).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _fmt_num(v: Decimal | float | int) -> str:
    d = _d(v).normalize()
    s = f"{d:,f}" if d == d.to_integral() else f"{d:,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _vnd(v: int) -> str:
    return format_vnd(v, suffix="đ")


def compute_cost(inp: dict[str, Any], params: CostParams, *, use_overrides: bool) -> dict[str, Any]:
    """Giá gốc × tỷ giá + cước nội địa + phí mua hộ + cước quốc tế (cân nặng × đơn giá) + thuế NK + GTGT + đóng gói
    + phí khác + hao hụt. Trả các cột của `cost_sheets` (cho MỘT cái) và `breakdown` để hiển thị."""
    currency = str(inp.get("currency") or "CNY").upper()
    country = (inp.get("country") or CURRENCY_COUNTRY.get(currency) or "CN").upper()

    def pick(name: str, default: Any) -> Any:
        v = inp.get(name)
        return v if (use_overrides and v is not None) else default

    if currency == "VND":
        default_fx = Decimal(1)
    elif currency in params.fx_rates:
        default_fx = params.fx_rates[currency]
    else:
        raise BadRequest(f"Chưa có tỷ giá cho {currency}. Chị thêm ở cài đặt giá vốn.", code="missing_fx")
    fx = _d(pick("fx_rate", default_fx))
    per_kg = int(pick("intl_shipping_vnd_per_kg", params.intl_vnd_per_kg.get(country, params.intl_vnd_per_kg.get("CN", 0))))  # fmt: skip
    agent_pct = _d(pick("agent_fee_pct", params.agent_fee_pct))
    import_pct = _d(pick("import_tax_pct", params.import_tax_pct))
    vat_pct = _d(pick("vat_pct", params.vat_pct))
    loss_pct = _d(pick("loss_pct", params.loss_pct))
    amount = _d(inp["unit_price_amount"])
    weight = inp.get("weight_grams")
    domestic = int(inp["domestic_shipping_vnd"] if inp.get("domestic_shipping_vnd") is not None else params.domestic_shipping_vnd)  # fmt: skip
    packaging = int(inp["packaging_vnd"] if inp.get("packaging_vnd") is not None else params.packaging_vnd)
    other = int(inp.get("other_fees_vnd") or 0)

    unit_vnd = to_vnd(amount, fx)
    agent_fee = _pct(unit_vnd + domestic, agent_pct)
    intl = to_vnd(_d(weight or 0) / 1000 * per_kg) if weight else 0
    dutiable = unit_vnd + domestic + intl
    import_tax = _pct(dutiable, import_pct)
    vat = _pct(dutiable + import_tax, vat_pct)
    subtotal = unit_vnd + domestic + agent_fee + intl + import_tax + vat + packaging + other
    loss = _pct(subtotal, loss_pct)
    landed = subtotal + loss

    lines = [
        ("unit_price", "Giá gốc", unit_vnd, f"{_fmt_num(amount)} {currency} × {_fmt_num(fx)}"),
        ("domestic_shipping", "Cước nội địa bên bán", domestic, "chia cho mỗi cái"),
        ("agent_fee", "Phí mua hộ", agent_fee, f"{_fmt_num(agent_pct)}% × (giá gốc + cước nội địa)"),
        ("intl_shipping", "Cước quốc tế", intl,
         f"{_fmt_num(_d(weight or 0) / 1000)} kg × {_vnd(per_kg)}/kg" if weight else "chưa có cân nặng"),
        ("import_tax", "Thuế nhập khẩu", import_tax, f"{_fmt_num(import_pct)}% × {_vnd(dutiable)} (hàng + cước)"),
        ("vat", "Thuế GTGT", vat, f"{_fmt_num(vat_pct)}% × (giá tính thuế + thuế nhập khẩu)"),
        ("packaging", "Đóng gói", packaging, "mỗi cái"),
        ("other_fees", "Phí khác", other, "mỗi cái"),
        ("loss", "Hao hụt, đổi trả", loss, f"{_fmt_num(loss_pct)}% × {_vnd(subtotal)}"),
    ]  # fmt: skip
    breakdown = [
        {"key": k, "label": label, "amount_vnd": v, "formula": f}
        for k, label, v, f in lines
        if v or k in ("unit_price", "intl_shipping", "vat")
    ]
    return {
        "currency": currency,
        "fx_rate": fx,
        "unit_price_amount": amount,
        "unit_price_vnd": unit_vnd,
        "domestic_shipping_vnd": domestic,
        "agent_fee_pct": agent_pct,
        "agent_fee_vnd": agent_fee,
        "weight_grams": weight,
        "intl_shipping_vnd_per_kg": per_kg,
        "intl_shipping_vnd": intl,
        "import_tax_pct": import_pct,
        "vat_pct": vat_pct,
        "tax_vnd": import_tax + vat,
        "packaging_vnd": packaging,
        "other_fees_vnd": other,
        "loss_pct": loss_pct,
        "loss_vnd": loss,
        "landed_cost_vnd": landed,
        "breakdown": breakdown,
    }


def _sheet_inputs(s: CostSheet, country: str | None) -> dict[str, Any]:
    return {
        "unit_price_amount": s.unit_price_amount,
        "currency": s.currency,
        "weight_grams": s.weight_grams,
        "domestic_shipping_vnd": s.domestic_shipping_vnd,
        "packaging_vnd": s.packaging_vnd,
        "other_fees_vnd": s.other_fees_vnd,
        "country": country,
        "fx_rate": s.fx_rate,
        "intl_shipping_vnd_per_kg": s.intl_shipping_vnd_per_kg,
        "agent_fee_pct": s.agent_fee_pct,
        "import_tax_pct": s.import_tax_pct,
        "vat_pct": s.vat_pct,
        "loss_pct": s.loss_pct,
    }


async def supplier_country(db: AsyncSession, supplier_id: uuid.UUID | None) -> str | None:
    if not supplier_id:
        return None
    return await db.scalar(select(Supplier.country).where(Supplier.id == supplier_id))


async def current_sheet(
    db: AsyncSession, *, candidate_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None
) -> CostSheet | None:
    stmt = select(CostSheet).where(CostSheet.is_current.is_(True))
    if candidate_id:
        stmt = stmt.where(CostSheet.candidate_id == candidate_id)
    elif product_id:
        stmt = stmt.where(CostSheet.product_id == product_id)
    else:
        return None
    return await db.scalar(stmt.order_by(CostSheet.version.desc()).limit(1))


async def save_cost_sheet(db: AsyncSession, data: dict[str, Any]) -> CostSheet:
    if not data.get("candidate_id") and not data.get("product_id"):
        raise BadRequest("Bảng giá vốn cần gắn với một ứng viên hoặc sản phẩm.")
    if data.get("candidate_id") and await db.get(Candidate, data["candidate_id"]) is None:
        raise NotFound("Không tìm thấy ứng viên.")
    params = await cost_params(db)
    auto = bool(data.get("auto_update", True))
    country = data.get("country") or await supplier_country(db, data.get("supplier_id"))
    calc = compute_cost({**data, "country": country}, params, use_overrides=not auto)
    prev = await current_sheet(db, candidate_id=data.get("candidate_id"), product_id=data.get("product_id"))
    version = 1
    if prev is not None:
        prev.is_current = False
        version = prev.version + 1
    sheet = CostSheet(
        candidate_id=data.get("candidate_id"),
        product_id=data.get("product_id"),
        supplier_id=data.get("supplier_id"),
        is_current=True,
        version=version,
        auto_update=auto,
        moq=data.get("moq"),
        assumptions=data.get("assumptions"),
        fx_rate_at=now_utc(),
        recalculated_at=now_utc(),
        **calc,
    )
    db.add(sheet)
    await db.flush()
    return sheet


async def recalc_sheet(db: AsyncSession, s: CostSheet, params: CostParams | None = None) -> bool:
    """Tính lại một bảng theo tham số hiện hành (chỉ bảng `auto_update`). Trả True nếu giá vốn đổi."""
    if not s.auto_update:
        return False
    params = params or await cost_params(db)
    calc = compute_cost(_sheet_inputs(s, await supplier_country(db, s.supplier_id)), params, use_overrides=False)
    changed = calc["landed_cost_vnd"] != s.landed_cost_vnd
    for k, v in calc.items():
        setattr(s, k, v)
    s.fx_rate_at = now_utc()
    s.recalculated_at = now_utc()
    if changed:
        s.version += 1
    return changed


async def recalc_all(db: AsyncSession) -> int:
    params = await cost_params(db)
    sheets = (
        await db.execute(select(CostSheet).where(CostSheet.is_current.is_(True), CostSheet.auto_update.is_(True)))
    ).scalars()
    n = 0
    for s in sheets:
        if await recalc_sheet(db, s, params):
            n += 1
    await db.flush()
    return n


async def set_cost_params(db: AsyncSession, params: CostParams, user: User | None) -> int:
    await control.set_setting(db, COST_PARAMS_KEY, params.model_dump(mode="json"), user)
    return await recalc_all(db)


# ---- d1: sổ nhà cung cấp -------------------------------------------------------------------------------------------

ACTIVE_PO = (
    POStatus.APPROVED, POStatus.SENT, POStatus.CONFIRMED, POStatus.PAID, POStatus.PARTIALLY_RECEIVED, POStatus.RECEIVED,
)  # fmt: skip


def trust_label(s: Supplier) -> tuple[str, str]:
    if s.is_blocked:
        return "Đã chặn", "Chị đã chặn nhà cung cấp này."
    if s.trust_score is None:
        return "Chưa có lịch sử", "Chưa có đơn nào nhận hàng xong để chấm."
    label = "Tin được" if s.trust_score >= 80 else "Tạm ổn" if s.trust_score >= 60 else "Cần dè chừng"
    parts = [f"{s.order_count} đơn"]
    if s.on_time_rate is not None:
        parts.append(f"đúng hẹn {round(float(s.on_time_rate) * 100)}%")
    if s.defect_rate is not None:
        parts.append(f"lỗi {round(float(s.defect_rate) * 100, 1):g}%".replace(".", ","))
    return label, ", ".join(parts)


async def recompute_supplier(db: AsyncSession, supplier_id: uuid.UUID) -> Supplier | None:
    """Điểm uy tín từ lịch sử: 50% đúng hẹn + 50% ít lỗi (lỗi 20% trở lên = 0), co về 70 khi còn ít đơn."""
    s = await db.get(Supplier, supplier_id)
    if s is None:
        return None
    pos = list(
        (
            await db.execute(
                select(PurchaseOrder).where(
                    PurchaseOrder.supplier_id == supplier_id, PurchaseOrder.status.in_(ACTIVE_PO)
                )
            )
        ).scalars()
    )
    s.order_count = len(pos)
    s.last_order_at = max((p.approved_at or p.created_at for p in pos), default=None)
    done = [p for p in pos if p.received_at is not None]
    timed = [p for p in done if p.expected_at is not None]
    s.on_time_rate = (
        _d(round(sum(to_local(p.received_at).date() <= p.expected_at for p in timed) / len(timed), 4))  # type: ignore[arg-type,operator]
        if timed
        else None
    )
    received = sum(ln.received_qty for p in done for ln in p.lines)
    defects = sum(ln.defect_qty for p in done for ln in p.lines)
    s.defect_rate = _d(round(defects / received, 4)) if received else None
    leads = [(p.received_at - p.sent_at).total_seconds() / 86400 for p in done if p.sent_at and p.received_at]
    s.avg_lead_days = _d(round(statistics.mean(leads), 1)) if leads else None
    if not done:
        s.trust_score = None
    else:
        on_time = float(s.on_time_rate) if s.on_time_rate is not None else 0.7
        quality = max(0.0, 1 - float(s.defect_rate or 0) * 5)
        raw = 100 * (0.5 * on_time + 0.5 * quality)
        n = len(done)
        s.trust_score = round((n * raw + 2 * 70) / (n + 2))
    await db.flush()
    return s


# ---- d3: đề xuất giá bán -------------------------------------------------------------------------------------------


async def market_summary(db: AsyncSession, candidate_id: uuid.UUID) -> tuple[dict[str, int | None], list[MarketSample]]:
    rows = list(
        (
            await db.execute(
                select(MarketPrice)
                .where(MarketPrice.candidate_id == candidate_id)
                .order_by(MarketPrice.captured_at.desc())
                .limit(30)
            )
        ).scalars()
    )
    rows = [r for r in rows if r.match_confidence is None or r.match_confidence >= Decimal("0.5")]
    prices = sorted(r.price_vnd for r in rows if r.price_vnd > 0)
    stats: dict[str, int | None] = {"low": None, "median": None, "high": None}
    if prices:
        stats = {"low": prices[0], "median": int(statistics.median(prices)), "high": prices[-1]}
    samples = [
        MarketSample(
            platform=str(r.platform.value), shop_name=r.shop_name, price_vnd=r.price_vnd, sold_count=r.sold_count
        )
        for r in rows[:10]
    ]
    return stats, samples


async def propose_price(
    db: AsyncSession, candidate_id: uuid.UUID, target_margin_pct: Decimal | None = None
) -> PriceProposal:
    cand = await db.get(Candidate, candidate_id)
    if cand is None:
        raise NotFound("Không tìm thấy ứng viên.")
    sheet = await current_sheet(db, candidate_id=candidate_id)
    if sheet is None:
        raise BadRequest("Chưa có giá vốn về tay cho món này. Chị tính giá vốn trước nhé.", code="no_cost_sheet")
    params = await cost_params(db)
    target = _d(target_margin_pct if target_margin_pct is not None else params.target_margin_pct)
    stats, samples = await market_summary(db, candidate_id)
    res = await ai.run(
        "supply.propose_price",
        PriceIn(
            title=cand.title_vi, landed_cost_vnd=sheet.landed_cost_vnd, target_margin_pct=float(target),
            market_low_vnd=stats["low"], market_median_vnd=stats["median"], market_high_vnd=stats["high"],
            market=samples,
        ),
        PriceOut,
    )  # fmt: skip
    out = res.output
    old = list(
        (
            await db.execute(
                select(PriceProposal).where(
                    PriceProposal.candidate_id == candidate_id,
                    PriceProposal.status.in_([ProposalStatus.DRAFT, ProposalStatus.PENDING_REVIEW]),
                )
            )
        ).scalars()
    )
    for p in old:
        p.status = ProposalStatus.SUPERSEDED
    prop = PriceProposal(
        candidate_id=candidate_id,
        cost_sheet_id=sheet.id,
        status=ProposalStatus.PENDING_REVIEW,
        landed_cost_vnd=sheet.landed_cost_vnd,
        market_low_vnd=stats["low"],
        market_median_vnd=stats["median"],
        market_high_vnd=stats["high"],
        target_margin_pct=target,
        proposed_price_vnd=out.proposed_price_vnd,
        proposed_drop_price_vnd=out.proposed_drop_price_vnd,
        margin_pct=_d(margin_pct(out.proposed_price_vnd, sheet.landed_cost_vnd)),
        rationale=out.rationale,
        ai_run_id=res.run_id,
    )
    db.add(prop)
    await db.flush()
    warn = " Giá đề xuất thấp hơn giá vốn!" if out.proposed_price_vnd < sheet.landed_cost_vnd else ""
    outcome = await control.propose(
        "supply.set_price",
        f"Giá bán {cand.title_vi}: {_vnd(out.proposed_price_vnd)}",
        {"proposal_id": str(prop.id), "price_vnd": out.proposed_price_vnd},
        {
            "candidate": cand.title_vi,
            "landed_cost_vnd": sheet.landed_cost_vnd,
            "proposed_price_vnd": out.proposed_price_vnd,
            "proposed_drop_price_vnd": out.proposed_drop_price_vnd,
            "margin_pct": float(prop.margin_pct or 0),
            "market": stats,
        },
        db=db,
        summary=f"Giá vốn {_vnd(sheet.landed_cost_vnd)}, biên {float(prop.margin_pct or 0):g}%.{warn}",
        rationale=out.rationale,
        ref_type="price_proposals",
        ref_id=prop.id,
        ai_run_id=res.run_id,
        dedupe_key=f"price:{candidate_id}",
    )
    if outcome.status == "pending":
        prop.approval_item_id = outcome.item_id
    await db.flush()
    return prop


async def apply_price(db: AsyncSession, proposal_id: uuid.UUID, price_vnd: int) -> PriceProposal:
    p = await db.get(PriceProposal, proposal_id)
    if p is None:
        raise NotFound("Không tìm thấy đề xuất giá.")
    if p.status not in (ProposalStatus.DRAFT, ProposalStatus.PENDING_REVIEW):
        raise Conflict("Đề xuất giá này đã được xử lý.")
    if price_vnd <= 0:
        raise BadRequest("Giá bán phải lớn hơn 0.")
    p.status = ProposalStatus.APPROVED
    p.approved_price_vnd = int(price_vnd)
    p.margin_pct = _d(margin_pct(int(price_vnd), p.landed_cost_vnd))
    p.decided_at = now_utc()
    await db.flush()
    await events.emit(
        "price.approved",
        {
            "candidate_id": str(p.candidate_id) if p.candidate_id else None,
            "price_vnd": int(price_vnd),
            "price_proposal_id": str(p.id),
            "product_id": str(p.product_id) if p.product_id else None,
        },
        db=db,
    )
    return p


# ---- d5: đơn đặt mẫu, đặt lô ---------------------------------------------------------------------------------------


def po_code(kind: POKind) -> str:
    prefix = {POKind.SAMPLE: "MAU", POKind.BATCH: "LO", POKind.RESTOCK: "BS"}[kind]
    return f"{prefix}-{local_today():%y%m%d}-{secrets.token_hex(2).upper()}"


async def _supplier(db: AsyncSession, supplier_id: uuid.UUID | None) -> Supplier | None:
    if not supplier_id:
        return None
    s = await db.get(Supplier, supplier_id)
    if s is None:
        raise NotFound("Không tìm thấy nhà cung cấp.")
    return s


def _language_for(supplier: Supplier | None, currency: str) -> Language:
    if supplier is not None:
        return supplier.language
    return Language.JA if currency == "JPY" else Language.ZH


async def create_po(
    db: AsyncSession, data: dict[str, Any], *, ai_generated: bool = False, compose: bool = True
) -> PurchaseOrder:
    kind = POKind(data.get("kind") or POKind.SAMPLE)
    supplier = await _supplier(db, data.get("supplier_id"))
    agent = await _supplier(db, data.get("agent_supplier_id"))
    if supplier is not None and supplier.is_blocked:
        raise BadRequest(f"Chị đã chặn «{supplier.name}», không đặt hàng được.", code="supplier_blocked")
    currency = str(data.get("currency") or "CNY").upper()
    params = await cost_params(db)
    fx = _d(params.fx_rates.get(currency, 1)) if currency != "VND" else Decimal(1)
    po = PurchaseOrder(
        code=po_code(kind),
        kind=kind,
        status=POStatus.DRAFT,
        supplier_id=supplier.id if supplier else None,
        agent_supplier_id=agent.id if agent else None,
        drop_id=data.get("drop_id"),
        candidate_id=data.get("candidate_id"),
        currency=currency,
        fx_rate=fx,
        shipping_amount=_d(data.get("shipping_amount") or 0),
        fees_vnd=int(data.get("fees_vnd") or 0),
        expected_at=data.get("expected_at"),
        notes=data.get("notes"),
        ai_generated=ai_generated,
        message_language=Language.VI if agent else _language_for(supplier, currency),
    )
    for i, ln in enumerate(data["lines"]):
        qty = int(ln["quantity"])
        price = _d(ln["unit_price_amount"])
        unit_cost = None
        if ln.get("candidate_id"):
            sheet = await current_sheet(db, candidate_id=ln["candidate_id"])
            unit_cost = sheet.landed_cost_vnd if sheet else None
        po.lines.append(
            PurchaseOrderLine(
                position=i, candidate_id=ln.get("candidate_id"), product_id=ln.get("product_id"),
                description=ln["description"], source_url=ln.get("source_url"), variant_spec=ln.get("variant_spec") or {},
                quantity=qty, unit_price_amount=price, line_total_amount=price * qty, unit_cost_vnd=unit_cost,
            )
        )  # fmt: skip
    recompute_totals(po)
    db.add(po)
    await db.flush()
    if compose:
        await compose_po_message(db, po, supplier, agent)
    return po


def recompute_totals(po: PurchaseOrder) -> None:
    po.subtotal_amount = sum((ln.line_total_amount for ln in po.lines), Decimal(0))
    po.total_vnd = to_vnd(po.subtotal_amount + (po.shipping_amount or 0), po.fx_rate or 1) + (po.fees_vnd or 0)


async def compose_po_message(
    db: AsyncSession, po: PurchaseOrder, supplier: Supplier | None = None, agent: Supplier | None = None
) -> None:
    supplier = supplier or await _supplier(db, po.supplier_id)
    agent = agent or await _supplier(db, po.agent_supplier_id)
    lang = po.message_language or Language.ZH
    try:
        res = await ai.run(
            "supply.compose_order",
            ComposeOrderIn(
                supplier_name=(agent or supplier).name if (agent or supplier) else None,
                language=lang.value,
                kind=po.kind.value,
                via_agent=agent is not None,
                notes=po.notes,
                lines=[
                    OrderLineBrief(
                        description=ln.description, quantity=ln.quantity, unit_price_amount=float(ln.unit_price_amount),
                        currency=po.currency, source_url=ln.source_url,
                        variant=", ".join(f"{k}: {v}" for k, v in (ln.variant_spec or {}).items()) or None,
                    )
                    for ln in po.lines
                ],
            ),
            ComposeOrderOut,
        )  # fmt: skip
    except ai.AIError as e:
        log.warning("Chưa soạn được nội dung đơn %s: %s", po.code, e)
        return
    po.message_draft = res.output.message_original
    po.ai_generated = True
    vi = res.output.message_vi
    if vi and vi != po.message_draft:
        po.notes = (po.notes + "\n\n" if po.notes else "") + f"Bản dịch: {vi}"


async def po_preview(db: AsyncSession, po: PurchaseOrder) -> dict[str, Any]:
    supplier = await _supplier(db, po.supplier_id)
    return {
        "code": po.code,
        "kind": po.kind.value,
        "supplier": supplier.name if supplier else None,
        "currency": po.currency,
        "lines": [
            {"description": ln.description, "quantity": ln.quantity, "unit_price_amount": float(ln.unit_price_amount)}
            for ln in po.lines
        ],
        "subtotal_amount": float(po.subtotal_amount),
        "total_vnd": po.total_vnd,
        "message": po.message_draft,
    }


async def submit_po(db: AsyncSession, po: PurchaseOrder) -> PurchaseOrder:
    """Đưa đơn qua control.propose («Luôn hỏi chị»): đơn chuyển sang chờ chị duyệt."""
    if po.status not in (POStatus.DRAFT, POStatus.PENDING_APPROVAL):
        raise Conflict("Đơn này đã duyệt hoặc đã gửi rồi.", code="po_not_draft")
    if not po.lines:
        raise BadRequest("Đơn chưa có dòng hàng nào.")
    supplier = await _supplier(db, po.supplier_id)
    kind = "đặt mẫu" if po.kind == POKind.SAMPLE else "đặt lô"
    outcome = await control.propose(
        "supply.place_order",
        f"Duyệt {kind} {po.code}" + (f" · {supplier.name}" if supplier else ""),
        {"purchase_order_id": str(po.id), "message_draft": po.message_draft},
        await po_preview(db, po),
        db=db,
        summary=f"{sum(ln.quantity for ln in po.lines)} cái, khoảng {_vnd(po.total_vnd)}.",
        rationale=po.notes,
        ref_type="purchase_orders",
        ref_id=po.id,
        dedupe_key=f"po:{po.id}",
        ai_generated=po.ai_generated,
        priority=5,
    )
    if outcome.status == "pending":
        po.status = POStatus.PENDING_APPROVAL
        po.approval_item_id = outcome.item_id
    await db.flush()
    return po


async def apply_place_order(db: AsyncSession, payload: dict[str, Any]) -> PurchaseOrder:
    po = await get_po(db, uuid.UUID(payload["purchase_order_id"]))
    if po.status not in (POStatus.DRAFT, POStatus.PENDING_APPROVAL):
        raise Conflict("Đơn này đã được xử lý.")
    if payload.get("message_draft") is not None:
        po.message_draft = payload["message_draft"]
    po.status = POStatus.APPROVED
    po.approved_at = now_utc()
    await db.flush()
    return po


async def get_po(db: AsyncSession, po_id: uuid.UUID) -> PurchaseOrder:
    po = await db.get(PurchaseOrder, po_id)
    if po is None:
        raise NotFound("Không tìm thấy đơn đặt hàng.")
    return po


async def sample_order_for(
    db: AsyncSession, candidate_id: uuid.UUID, *, quantity: int = 1, supplier_id: uuid.UUID | None = None,
    ai_generated: bool = True, skip_if_exists: bool = False,
) -> PurchaseOrder | None:  # fmt: skip
    """AI soạn đơn mua mẫu từ ứng viên rồi đưa chị duyệt. `skip_if_exists` để người nghe sự kiện chạy lặp lại không trùng."""
    cand = await db.get(Candidate, candidate_id)
    if cand is None:
        raise NotFound("Không tìm thấy ứng viên.")
    if skip_if_exists:
        exists = await db.scalar(
            select(PurchaseOrder.id).where(
                PurchaseOrder.candidate_id == candidate_id,
                PurchaseOrder.kind == POKind.SAMPLE,
                PurchaseOrder.status != POStatus.CANCELLED,
            )
        )
        if exists:
            return None
    po = await create_po(
        db,
        {
            "kind": POKind.SAMPLE,
            "supplier_id": supplier_id or cand.supplier_id,
            "candidate_id": cand.id,
            "currency": cand.price_currency or "CNY",
            "notes": f"Mua mẫu để thử «{cand.title_vi}».",
            "lines": [
                {
                    "candidate_id": cand.id,
                    "description": cand.title_original or cand.title_vi,
                    "source_url": cand.source_url,
                    "quantity": quantity,
                    "unit_price_amount": cand.price_amount or 0,
                }
            ],
        },
        ai_generated=ai_generated,
    )
    return await submit_po(db, po)


BATCH_ORDER_STATUSES = (
    OrderStatus.CONFIRMED, OrderStatus.AWAITING_STOCK, OrderStatus.READY_TO_SHIP, OrderStatus.SHIPPING,
    OrderStatus.DELIVERED, OrderStatus.COMPLETED,
)  # fmt: skip


async def batch_orders_for_drop(db: AsyncSession, drop_id: uuid.UUID) -> list[PurchaseOrder]:
    """Nghe drop.closed: cộng số lượng các đơn đã chốt theo nhà cung cấp, soạn mỗi NCC một đơn đặt lô chờ chị duyệt.
    Chạy lặp lại không sinh trùng (bỏ qua NCC đã có đơn của đợt này)."""
    drop = await db.get(Drop, drop_id)
    if drop is None:
        return []
    rows = (
        await db.execute(
            select(DropItem.product_id, func.sum(OrderItem.quantity))
            .join(OrderItem, OrderItem.drop_item_id == DropItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(DropItem.drop_id == drop_id, Order.status.in_(BATCH_ORDER_STATUSES))
            .group_by(DropItem.product_id)
        )
    ).all()
    groups: dict[uuid.UUID | None, list[tuple[Candidate | None, Product, int]]] = {}
    for product_id, qty in rows:
        product = await db.get(Product, product_id)
        if product is None or not qty:
            continue
        cand = await db.get(Candidate, product.candidate_id) if product.candidate_id else None
        groups.setdefault(cand.supplier_id if cand else None, []).append((cand, product, int(qty)))
    created: list[PurchaseOrder] = []
    for supplier_id, items in groups.items():
        cond = PurchaseOrder.supplier_id.is_(None) if supplier_id is None else PurchaseOrder.supplier_id == supplier_id
        if await db.scalar(
            select(PurchaseOrder.id).where(
                PurchaseOrder.drop_id == drop_id, cond, PurchaseOrder.status != POStatus.CANCELLED
            )
        ):
            continue
        currency = next((c.price_currency for c, _, _ in items if c and c.price_currency), "CNY")
        po = await create_po(
            db,
            {
                "kind": POKind.BATCH,
                "supplier_id": supplier_id,
                "drop_id": drop_id,
                "currency": currency,
                "notes": f"Đặt lô cho đợt {drop.code}: {sum(q for _, _, q in items)} cái từ các đơn đã chốt.",
                "lines": [
                    {
                        "candidate_id": c.id if c else None,
                        "product_id": p.id,
                        "description": (c.title_original if c and c.title_original else p.name),
                        "source_url": c.source_url if c else None,
                        "quantity": q,
                        "unit_price_amount": (c.price_amount if c and c.price_amount else 0),
                    }
                    for c, p, q in items
                ],
            },
            ai_generated=True,
        )
        created.append(await submit_po(db, po))
    return created


async def set_po_status(
    db: AsyncSession, po: PurchaseOrder, to: str, user: User | None, note: str | None
) -> PurchaseOrder:
    if to == "sent":
        if po.status != POStatus.APPROVED:
            raise Conflict("Đơn cần được chị duyệt trước khi gửi.", code="po_not_approved")
        po.status = POStatus.SENT
        po.sent_at = now_utc()
        if not await db.scalar(select(InboundShipment.id).where(InboundShipment.purchase_order_id == po.id)):
            await create_inbound(db, {"purchase_order_id": po.id, "eta": po.expected_at}, source="system")
    elif to == "confirmed":
        if po.status != POStatus.SENT:
            raise Conflict("Chỉ đơn đã gửi mới xác nhận được.")
        po.status = POStatus.CONFIRMED
    elif to == "cancelled":
        if po.status in (POStatus.PARTIALLY_RECEIVED, POStatus.RECEIVED):
            raise Conflict("Hàng đã về, không huỷ đơn được.")
        po.status = POStatus.CANCELLED
        await control.cancel_pending(db, action="supply.place_order", ref_type="purchase_orders", ref_id=po.id)
    if note:
        po.notes = (po.notes + "\n" if po.notes else "") + note
    await control.audit(
        db, "supply.po_status", user=user, entity_type="purchase_orders", entity_id=po.id,
        summary=f"Đơn {po.code}: {to}", data={"note": note},
    )  # fmt: skip
    await db.flush()
    if po.supplier_id:
        await recompute_supplier(db, po.supplier_id)
    return po


EXPENSE_CATEGORY = {"deposit": None, "payment": None, "shipping": "shipping", "fee": "fees"}


async def record_payment(db: AsyncSession, po: PurchaseOrder, data: dict[str, Any], user: User | None) -> PurchaseOrder:
    """Chị ghi khoản đã trả cho đơn. Phát `expense.recorded` để module finance ghi sổ (supply không ghi bảng `expenses`)."""
    if po.status in (POStatus.DRAFT, POStatus.PENDING_APPROVAL, POStatus.CANCELLED):
        raise Conflict("Đơn chưa được duyệt nên chưa ghi trả tiền được.", code="po_not_approved")
    amount = int(data["amount_vnd"])
    kind = data.get("kind") or "payment"
    po.paid_vnd = (po.paid_vnd or 0) + amount
    if kind == "deposit":
        po.deposit_vnd = (po.deposit_vnd or 0) + amount
    if po.paid_vnd >= po.total_vnd and po.status in (POStatus.APPROVED, POStatus.SENT, POStatus.CONFIRMED):
        po.status = POStatus.PAID
    await db.flush()
    supplier = await _supplier(db, po.agent_supplier_id or po.supplier_id)
    ref = uuid.uuid4().hex[:12]  # mỗi lần ghi trả tiền một khoá riêng → finance chống ghi trùng theo source_key
    category = EXPENSE_CATEGORY.get(kind) or ("samples" if po.kind == POKind.SAMPLE else "goods")
    paid_on: date = data.get("paid_on") or local_today()
    label = {"deposit": "Đặt cọc", "payment": "Thanh toán", "shipping": "Cước", "fee": "Phí"}[kind]
    po.notes = (po.notes + "\n" if po.notes else "") + f"Đã trả {_vnd(amount)} ({label.lower()}) ngày {paid_on:%d/%m}"
    await events.emit(
        "expense.recorded",
        {
            "expense_id": None,
            "source": "supply",
            "source_key": f"po:{po.id}:pay:{ref}",
            "purchase_order_id": str(po.id),
            "amount_vnd": amount,
            "category": category,
            "incurred_on": paid_on.isoformat(),
            "description": f"{label} đơn {po.code}" + (f": {data['note']}" if data.get("note") else ""),
            "vendor": supplier.name if supplier else None,
        },
        db=db,
    )
    await control.audit(
        db, "supply.payment_recorded", user=user, entity_type="purchase_orders", entity_id=po.id,
        summary=f"{label} {_vnd(amount)} cho đơn {po.code}", data={"amount_vnd": amount, "kind": kind},
    )  # fmt: skip
    await db.flush()
    return po


async def receive_po(db: AsyncSession, po: PurchaseOrder, lines: list[dict[str, Any]]) -> PurchaseOrder:
    if po.status in (POStatus.DRAFT, POStatus.PENDING_APPROVAL, POStatus.CANCELLED):
        raise Conflict("Đơn chưa được duyệt, chưa nhận hàng được.")
    by_id = {ln.id: ln for ln in po.lines}
    for row in lines:
        ln = by_id.get(row["line_id"])
        if ln is None:
            raise BadRequest("Dòng hàng không thuộc đơn này.")
        if row.get("defect_qty", 0) > row["received_qty"]:
            raise BadRequest("Số lỗi không được lớn hơn số đã nhận.")
        ln.received_qty = row["received_qty"]
        ln.defect_qty = row.get("defect_qty", 0)
    full = all(ln.received_qty >= ln.quantity for ln in po.lines)
    po.status = POStatus.RECEIVED if full else POStatus.PARTIALLY_RECEIVED
    po.received_at = po.received_at or now_utc()
    await db.flush()
    if po.supplier_id:
        await recompute_supplier(db, po.supplier_id)
    return po


# ---- d7: lô hàng về ------------------------------------------------------------------------------------------------

INBOUND_ORDER = [
    InboundStatus.ORDERED, InboundStatus.SELLER_SHIPPED, InboundStatus.AT_AGENT_WAREHOUSE,
    InboundStatus.INTERNATIONAL_TRANSIT, InboundStatus.CUSTOMS, InboundStatus.DOMESTIC_TRANSIT, InboundStatus.DELIVERED,
]  # fmt: skip
INBOUND_LABELS = {
    InboundStatus.ORDERED: "Đã đặt",
    InboundStatus.SELLER_SHIPPED: "Bên bán đã gửi",
    InboundStatus.AT_AGENT_WAREHOUSE: "Về kho bên bán / kho mua hộ",
    InboundStatus.INTERNATIONAL_TRANSIT: "Đang về Việt Nam",
    InboundStatus.CUSTOMS: "Đang thông quan",
    InboundStatus.DOMESTIC_TRANSIT: "Đang giao về nhà",
    InboundStatus.DELIVERED: "Đã về nhà",
    InboundStatus.PROBLEM: "Có vấn đề",
}
# Trạng thái vận đơn của tích hợp `shipping` → mốc lô hàng về
TRACKING_MAP = {
    "picked_up": InboundStatus.SELLER_SHIPPED,
    "in_transit": InboundStatus.INTERNATIONAL_TRANSIT,
    "out_for_delivery": InboundStatus.DOMESTIC_TRANSIT,
    "delivered": InboundStatus.DELIVERED,
    "failed_delivery": InboundStatus.PROBLEM,
    "returning": InboundStatus.PROBLEM,
    "returned": InboundStatus.PROBLEM,
}


async def create_inbound(db: AsyncSession, data: dict[str, Any], *, source: str = "manual") -> InboundShipment:
    if data.get("purchase_order_id"):
        await get_po(db, data["purchase_order_id"])
    ship = InboundShipment(
        **{k: v for k, v in data.items() if v is not None},
        status=InboundStatus.ORDERED,
        milestones=[{"status": "ordered", "at": now_utc().isoformat(), "note": None, "source": source}],
    )
    db.add(ship)
    await db.flush()
    return ship


async def add_milestone(
    db: AsyncSession, ship: InboundShipment, status: InboundStatus, *, note: str | None = None,
    at: datetime | None = None, source: str = "manual",
) -> InboundShipment:  # fmt: skip
    """Thêm mốc. Lần đầu về tới nhà thì phát `inbound.arrived` (chỉ một lần cho mỗi lô)."""
    already = any(m.get("status") == InboundStatus.DELIVERED.value for m in ship.milestones)
    ship.milestones = [
        *ship.milestones,
        {"status": status.value, "at": (at or now_utc()).isoformat(), "note": note, "source": source},
    ]
    ship.status = status
    if status == InboundStatus.PROBLEM and note:
        ship.problem_note = note
    if status == InboundStatus.DELIVERED and not already:
        ship.received_at = at or now_utc()
        await db.flush()
        await events.emit("inbound.arrived", {"inbound_shipment_id": str(ship.id)}, db=db)
    await db.flush()
    return ship


async def sync_tracking(db: AsyncSession, ship: InboundShipment) -> int:
    """Cập nhật mốc từ tích hợp `shipping` (driver mặc định mock). Chỉ tiến lên, không lùi. Trả số mốc mới."""
    if not ship.tracking_code:
        raise BadRequest("Lô này chưa có mã vận đơn để theo dõi.", code="no_tracking")
    try:
        info = await get_driver("shipping").track(ship.tracking_code)
    except IntegrationError as e:
        raise BadRequest(f"Chưa tra được vận đơn: {e}", code="tracking_failed") from e
    seen = {m.get("status") for m in ship.milestones}
    rank = {s: i for i, s in enumerate(INBOUND_ORDER)}
    added = 0
    for ev in info.events:
        target = TRACKING_MAP.get(ev.status.value)
        if target is None or target.value in seen:
            continue
        if target != InboundStatus.PROBLEM and rank.get(target, 0) <= rank.get(ship.status, 0):
            continue
        await add_milestone(db, ship, target, note=ev.description, at=ev.occurred_at, source="shipping")
        seen.add(target.value)
        added += 1
    return added


# ---- d4: chứng từ nguồn gốc ----------------------------------------------------------------------------------------

REQUIRED_DOCS = {
    POKind.SAMPLE: [],
    POKind.BATCH: [DocumentKind.INVOICE, DocumentKind.ORIGINAL_LABEL],
    POKind.RESTOCK: [DocumentKind.INVOICE, DocumentKind.ORIGINAL_LABEL],
}
DOC_LABELS = {
    DocumentKind.INVOICE: "Hoá đơn mua",
    DocumentKind.CUSTOMS_DECLARATION: "Tờ khai hải quan",
    DocumentKind.ORIGINAL_LABEL: "Ảnh nhãn gốc",
    DocumentKind.PACKING_LIST: "Phiếu đóng gói",
    DocumentKind.PAYMENT_RECEIPT: "Biên nhận thanh toán",
    DocumentKind.CERTIFICATE: "Chứng nhận, công bố",
    DocumentKind.CONTRACT: "Hợp đồng",
    DocumentKind.OTHER: "Chứng từ khác",
}
DOC_CHECK_STATUSES = (
    POStatus.APPROVED, POStatus.SENT, POStatus.CONFIRMED, POStatus.PAID, POStatus.PARTIALLY_RECEIVED, POStatus.RECEIVED,
)  # fmt: skip


async def po_document_kinds(db: AsyncSession, po_ids: list[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
    if not po_ids:
        return {}
    out: dict[uuid.UUID, set[str]] = {i: set() for i in po_ids}
    for po_id, kind in await db.execute(
        select(ProvenanceDocument.purchase_order_id, ProvenanceDocument.kind).where(
            ProvenanceDocument.purchase_order_id.in_(po_ids)
        )
    ):
        out[po_id].add(kind.value)
    for po_id, kind in await db.execute(
        select(InboundShipment.purchase_order_id, ProvenanceDocument.kind)
        .join(ProvenanceDocument, ProvenanceDocument.inbound_shipment_id == InboundShipment.id)
        .where(InboundShipment.purchase_order_id.in_(po_ids))
    ):
        out[po_id].add(kind.value)
    return out


def missing_docs(po: PurchaseOrder, have: set[str]) -> list[str]:
    if po.status not in DOC_CHECK_STATUSES:
        return []
    return [k.value for k in REQUIRED_DOCS.get(po.kind, []) if k.value not in have]


async def document_warnings(db: AsyncSession) -> list[dict[str, Any]]:
    pos = list(
        (
            await db.execute(
                select(PurchaseOrder)
                .where(
                    PurchaseOrder.kind.in_([POKind.BATCH, POKind.RESTOCK]),
                    PurchaseOrder.status.in_(DOC_CHECK_STATUSES),
                )
                .order_by(PurchaseOrder.created_at.desc())
            )
        ).scalars()
    )
    kinds = await po_document_kinds(db, [p.id for p in pos])
    names = await supplier_names(db, {p.supplier_id for p in pos if p.supplier_id})
    out = []
    for p in pos:
        miss = missing_docs(p, kinds.get(p.id, set()))
        if miss:
            out.append(
                {
                    "purchase_order_id": p.id, "po_code": p.code, "kind": p.kind, "status": p.status,
                    "supplier_name": names.get(p.supplier_id) if p.supplier_id else None, "missing": miss,
                    "missing_labels": [DOC_LABELS[DocumentKind(m)] for m in miss],
                }
            )  # fmt: skip
    return out


async def supplier_names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict((await db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(ids)))).all())


# ---- d6: nhắn hỏi nhà cung cấp -------------------------------------------------------------------------------------


async def draft_inquiry(db: AsyncSession, supplier: Supplier, data: dict[str, Any]) -> SupplierMessage:
    cand = await db.get(Candidate, data["candidate_id"]) if data.get("candidate_id") else None
    lang = supplier.language if supplier.language in (Language.ZH, Language.JA) else Language.ZH
    res = await ai.run(
        "supply.compose_inquiry",
        InquiryAIIn(
            supplier_name=supplier.name, language=lang.value,
            product_title=cand.title_vi if cand else None, product_title_original=cand.title_original if cand else None,
            source_url=cand.source_url if cand else None, topics=list(data.get("topics") or []),
            quantity=data.get("quantity"), extra=data.get("extra"),
        ),
        InquiryAIOut,
    )  # fmt: skip
    msg = SupplierMessage(
        supplier_id=supplier.id,
        candidate_id=cand.id if cand else None,
        purchase_order_id=data.get("purchase_order_id"),
        direction=MessageDirection.OUTBOUND,
        language=lang,
        body_original=res.output.body_original,
        body_vi=res.output.body_vi,
        status=SupplierMessageStatus.PENDING_REVIEW,
        ai_generated=True,
        ai_run_id=res.run_id,
    )
    db.add(msg)
    await db.flush()
    outcome = await control.propose(
        "supply.send_supplier_message",
        f"Tin hỏi {supplier.name}" + (f" về {cand.title_vi}" if cand else ""),
        {"message_id": str(msg.id), "body_original": msg.body_original, "body_vi": msg.body_vi},
        {"supplier": supplier.name, "language": lang.value, "body_original": msg.body_original, "body_vi": msg.body_vi},
        db=db, ref_type="supplier_messages", ref_id=msg.id, ai_run_id=res.run_id, dedupe_key=f"msg:{msg.id}",
    )  # fmt: skip
    if outcome.status == "pending":
        msg.approval_item_id = outcome.item_id
    await db.flush()
    return msg


async def apply_message_approval(db: AsyncSession, payload: dict[str, Any]) -> SupplierMessage:
    msg = await get_message(db, uuid.UUID(payload["message_id"]))
    if msg.status not in (SupplierMessageStatus.DRAFT, SupplierMessageStatus.PENDING_REVIEW):
        raise Conflict("Tin này đã được xử lý.")
    if payload.get("body_original"):
        msg.body_original = payload["body_original"]
    if payload.get("body_vi") is not None:
        msg.body_vi = payload["body_vi"]
    msg.status = SupplierMessageStatus.APPROVED
    await db.flush()
    return msg


async def get_message(db: AsyncSession, msg_id: uuid.UUID) -> SupplierMessage:
    m = await db.get(SupplierMessage, msg_id)
    if m is None:
        raise NotFound("Không tìm thấy tin nhắn.")
    return m


async def mark_sent(db: AsyncSession, msg: SupplierMessage, channel: SupplierChannel) -> SupplierMessage:
    if msg.status != SupplierMessageStatus.APPROVED:
        raise Conflict("Tin cần được chị duyệt trước khi gửi.", code="message_not_approved")
    msg.status = SupplierMessageStatus.SENT
    msg.channel = channel
    msg.sent_at = now_utc()
    await db.flush()
    return msg


async def record_reply(db: AsyncSession, supplier: Supplier, data: dict[str, Any]) -> SupplierMessage:
    """Chị dán câu trả lời của nhà cung cấp → AI dịch và rút giá, số lượng tối thiểu, thời gian."""
    asked = await db.scalar(
        select(SupplierMessage.body_vi)
        .where(SupplierMessage.supplier_id == supplier.id, SupplierMessage.direction == MessageDirection.OUTBOUND)
        .order_by(SupplierMessage.created_at.desc())
        .limit(1)
    )
    msg = SupplierMessage(
        supplier_id=supplier.id,
        candidate_id=data.get("candidate_id"),
        purchase_order_id=data.get("purchase_order_id"),
        direction=MessageDirection.INBOUND,
        language=supplier.language,
        body_original=data["body_original"].strip(),
        status=SupplierMessageStatus.RECEIVED,
    )
    db.add(msg)
    await db.flush()
    res = await ai.run(
        "supply.read_reply",
        ReplyAIIn(language=supplier.language.value, body_original=msg.body_original, asked=asked),
        ReplyAIOut,
    )
    msg.ai_run_id = res.run_id
    await control.propose(
        "supply.read_supplier_reply",
        f"Dịch tin của {supplier.name}",
        {
            "message_id": str(msg.id),
            "body_vi": res.output.body_vi,
            "extracted": {**res.output.extracted.model_dump(), "summary": res.output.summary},
        },
        {"body_vi": res.output.body_vi, "summary": res.output.summary},
        db=db, ref_type="supplier_messages", ref_id=msg.id, ai_run_id=res.run_id, dedupe_key=f"reply:{msg.id}",
    )  # fmt: skip
    await db.flush()
    return msg


async def apply_reply(db: AsyncSession, payload: dict[str, Any]) -> SupplierMessage:
    msg = await get_message(db, uuid.UUID(payload["message_id"]))
    msg.body_vi = payload.get("body_vi")
    msg.extracted = payload.get("extracted") or {}
    await db.flush()
    return msg
