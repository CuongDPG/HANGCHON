"""API nguồn cung và giá vốn (d1–d7): `/api/desk/supply/**`."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from sqlalchemy import func, or_, select

from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.pagination import Page, Paginated, paginate
from app.core.storage import get_storage, new_key
from app.modules.selection.service import file_url
from app.modules.sourcing.models import Candidate
from app.modules.supply import service
from app.modules.supply.models import (
    CostSheet,
    DocumentKind,
    InboundShipment,
    POKind,
    POStatus,
    PriceProposal,
    ProvenanceDocument,
    PurchaseOrder,
    Supplier,
    SupplierKind,
    SupplierMessage,
)
from app.modules.supply.schemas import (
    CostParams,
    CostParamsOut,
    CostPreview,
    CostSheetIn,
    CostSheetOut,
    CostSheetView,
    DocumentView,
    DocumentWarning,
    InboundIn,
    InboundUpdate,
    InboundView,
    InquiryIn,
    MessageSentIn,
    MilestoneIn,
    PaymentIn,
    POStatusIn,
    PriceProposalIn,
    PriceProposalView,
    PurchaseOrderIn,
    PurchaseOrderUpdate,
    PurchaseOrderView,
    ReceiveIn,
    ReplyIn,
    SampleOrderIn,
    SupplierIn,
    SupplierMessageOut,
    SupplierUpdate,
    SupplierView,
)

router = APIRouter(prefix="/api/desk/supply", tags=["supply"])

MAX_DOC_BYTES = 20 * 1024 * 1024
DOC_TYPES = ("image/", "application/pdf")


def _fields(model: type, obj: Any) -> dict[str, Any]:
    return {c: getattr(obj, c) for c in model.model_fields if hasattr(obj, c)}  # type: ignore[attr-defined]


# ---- d2: tham số + bảng giá vốn ------------------------------------------------------------------------------------


@router.get("/settings", response_model=CostParamsOut, summary="Tham số giá vốn về tay (d2)")
async def get_params(_: CurrentUser, db: DbSession) -> CostParamsOut:
    return CostParamsOut(**(await service.cost_params(db)).model_dump())


@router.patch("/settings", response_model=CostParamsOut, summary="Đổi tham số → tính lại các bảng giá vốn tự cập nhật")
async def update_params(body: CostParams, user: OwnerUser, db: DbSession) -> CostParamsOut:
    n = await service.set_cost_params(db, body, user)
    return CostParamsOut(**body.model_dump(), recalculated=n)


@router.post("/cost-sheets/preview", response_model=CostPreview, summary="Tính thử, không lưu")
async def preview_cost(body: CostSheetIn, _: CurrentUser, db: DbSession) -> dict:
    country = body.country or await service.supplier_country(db, body.supplier_id)
    calc = service.compute_cost(
        {**body.model_dump(), "country": country}, await service.cost_params(db), use_overrides=not body.auto_update
    )
    return {"landed_cost_vnd": calc["landed_cost_vnd"], "breakdown": calc["breakdown"]}


@router.get("/cost-sheets", response_model=Paginated[CostSheetView], summary="Các bảng giá vốn hiện hành")
async def list_cost_sheets(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    candidate_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> Paginated[CostSheetView]:
    stmt = select(CostSheet).where(CostSheet.is_current.is_(True)).order_by(CostSheet.updated_at.desc())
    if candidate_id:
        stmt = stmt.where(CostSheet.candidate_id == candidate_id)
    if product_id:
        stmt = stmt.where(CostSheet.product_id == product_id)
    result = await paginate(db, stmt, page)
    ids = [s.candidate_id for s in result.items if s.candidate_id]
    info: dict[uuid.UUID, tuple[str, str]] = {}
    if ids:
        rows = await db.execute(select(Candidate.id, Candidate.title_vi, Candidate.stage).where(Candidate.id.in_(ids)))
        info = {i: (t, st.value) for i, t, st in rows}
    result.items = [
        CostSheetView.model_validate(
            {
                **_fields(CostSheetView, s),
                "candidate_title": info.get(s.candidate_id, (None, None))[0],
                "candidate_stage": info.get(s.candidate_id, (None, None))[1],
            }
        )
        for s in result.items
    ]
    return result  # type: ignore[return-value]


@router.get("/cost-sheets/current", response_model=CostSheetOut | None, summary="Bảng giá vốn hiện hành của một món")
async def current_cost_sheet(
    _: CurrentUser, db: DbSession, candidate_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None
) -> CostSheet | None:
    if not candidate_id and not product_id:
        raise BadRequest("Cần candidate_id hoặc product_id.")
    return await service.current_sheet(db, candidate_id=candidate_id, product_id=product_id)


@router.post("/cost-sheets", response_model=CostSheetOut, status_code=status.HTTP_201_CREATED)
async def create_cost_sheet(body: CostSheetIn, _: CurrentUser, db: DbSession) -> CostSheet:
    return await service.save_cost_sheet(db, body.model_dump())


@router.post("/cost-sheets/{sheet_id}/recalculate", response_model=CostSheetOut)
async def recalc_cost_sheet(sheet_id: uuid.UUID, _: CurrentUser, db: DbSession) -> CostSheet:
    s = await db.get(CostSheet, sheet_id)
    if s is None:
        raise NotFound("Không tìm thấy bảng giá vốn.")
    if not s.auto_update:
        raise BadRequest("Bảng này dùng tham số riêng, không tự tính lại.", code="manual_sheet")
    await service.recalc_sheet(db, s)
    await db.flush()
    return s


# ---- d3: đề xuất giá bán -------------------------------------------------------------------------------------------


async def proposal_view(db: DbSession, p: PriceProposal) -> PriceProposalView:
    n = 0
    if p.candidate_id:
        _, samples = await service.market_summary(db, p.candidate_id)
        n = len(samples)
    return PriceProposalView.model_validate({**_fields(PriceProposalView, p), "market_samples": n})


@router.get("/price-proposals", response_model=list[PriceProposalView], summary="Đề xuất giá bán (d3)")
async def list_proposals(_: CurrentUser, db: DbSession, candidate_id: uuid.UUID) -> list[PriceProposalView]:
    rows = (
        await db.execute(
            select(PriceProposal)
            .where(PriceProposal.candidate_id == candidate_id)
            .order_by(PriceProposal.created_at.desc())
            .limit(20)
        )
    ).scalars()
    return [await proposal_view(db, p) for p in rows]


@router.post("/price-proposals", response_model=PriceProposalView, status_code=status.HTTP_201_CREATED)
async def create_proposal(body: PriceProposalIn, _: CurrentUser, db: DbSession) -> PriceProposalView:
    p = await service.propose_price(db, body.candidate_id, body.target_margin_pct)
    return await proposal_view(db, p)


# ---- d1: nhà cung cấp ----------------------------------------------------------------------------------------------


async def supplier_view(db: DbSession, s: Supplier) -> SupplierView:
    label, basis = service.trust_label(s)
    open_orders = await db.scalar(
        select(func.count()).where(
            or_(PurchaseOrder.supplier_id == s.id, PurchaseOrder.agent_supplier_id == s.id),
            PurchaseOrder.status.not_in([POStatus.RECEIVED, POStatus.CANCELLED]),
        )
    )
    return SupplierView.model_validate(
        {**_fields(SupplierView, s), "trust_label": label, "trust_basis": basis, "open_orders": int(open_orders or 0)}
    )


async def _get_supplier(db: DbSession, supplier_id: uuid.UUID) -> Supplier:
    s = await db.get(Supplier, supplier_id)
    if s is None:
        raise NotFound("Không tìm thấy nhà cung cấp.")
    return s


@router.get("/suppliers", response_model=Paginated[SupplierView], summary="Sổ nhà cung cấp (d1)")
async def list_suppliers(
    _: CurrentUser, db: DbSession, page: Page, q: str | None = None, kind: SupplierKind | None = None
) -> Paginated[SupplierView]:
    stmt = select(Supplier).order_by(Supplier.is_blocked, Supplier.trust_score.desc().nulls_last(), Supplier.name)
    if q:
        stmt = stmt.where(or_(Supplier.name.ilike(f"%{q}%"), Supplier.name_original.ilike(f"%{q}%")))
    if kind:
        stmt = stmt.where(Supplier.kind == kind)
    result = await paginate(db, stmt, page)
    result.items = [await supplier_view(db, s) for s in result.items]
    return result  # type: ignore[return-value]


@router.post("/suppliers", response_model=SupplierView, status_code=status.HTTP_201_CREATED)
async def create_supplier(body: SupplierIn, _: CurrentUser, db: DbSession) -> SupplierView:
    data = body.model_dump()
    data["country"] = data["country"].upper() if data.get("country") else None
    s = Supplier(**data)
    db.add(s)
    await db.flush()
    return await supplier_view(db, s)


@router.get("/suppliers/{supplier_id}", response_model=SupplierView)
async def get_supplier(supplier_id: uuid.UUID, _: CurrentUser, db: DbSession) -> SupplierView:
    return await supplier_view(db, await _get_supplier(db, supplier_id))


@router.patch("/suppliers/{supplier_id}", response_model=SupplierView)
async def update_supplier(supplier_id: uuid.UUID, body: SupplierUpdate, _: CurrentUser, db: DbSession) -> SupplierView:
    s = await _get_supplier(db, supplier_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v.upper() if k == "country" and v else v)
    await db.flush()
    return await supplier_view(db, s)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(supplier_id: uuid.UUID, _: OwnerUser, db: DbSession) -> None:
    s = await _get_supplier(db, supplier_id)
    used = await db.scalar(
        select(func.count()).where(or_(PurchaseOrder.supplier_id == s.id, PurchaseOrder.agent_supplier_id == s.id))
    )
    if used:
        raise Conflict("Nhà cung cấp đã có đơn đặt hàng; chị chặn thay vì xoá để giữ lịch sử.", code="supplier_in_use")
    await db.delete(s)


@router.post("/suppliers/{supplier_id}/recompute", response_model=SupplierView, summary="Tính lại điểm uy tín")
async def recompute_supplier(supplier_id: uuid.UUID, _: CurrentUser, db: DbSession) -> SupplierView:
    await _get_supplier(db, supplier_id)
    s = await service.recompute_supplier(db, supplier_id)
    return await supplier_view(db, s)  # type: ignore[arg-type]


# ---- d6: tin nhắn nhà cung cấp -------------------------------------------------------------------------------------


@router.get("/suppliers/{supplier_id}/messages", response_model=list[SupplierMessageOut])
async def list_messages(supplier_id: uuid.UUID, _: CurrentUser, db: DbSession) -> list[SupplierMessage]:
    await _get_supplier(db, supplier_id)
    rows = (
        await db.execute(
            select(SupplierMessage)
            .where(SupplierMessage.supplier_id == supplier_id)
            .order_by(SupplierMessage.created_at)
            .limit(200)
        )
    ).scalars()
    return list(rows)


@router.post(
    "/suppliers/{supplier_id}/messages/inquiry", response_model=SupplierMessageOut, status_code=status.HTTP_201_CREATED,
    summary="AI soạn tin hỏi (d6)",
)  # fmt: skip
async def draft_inquiry(supplier_id: uuid.UUID, body: InquiryIn, _: CurrentUser, db: DbSession) -> SupplierMessage:
    s = await _get_supplier(db, supplier_id)
    if body.candidate_id and await db.get(Candidate, body.candidate_id) is None:
        raise NotFound("Không tìm thấy ứng viên.")
    return await service.draft_inquiry(db, s, body.model_dump())


@router.post(
    "/suppliers/{supplier_id}/messages/reply", response_model=SupplierMessageOut, status_code=status.HTTP_201_CREATED,
    summary="Dán câu trả lời: AI dịch và rút thông tin (d6)",
)  # fmt: skip
async def record_reply(supplier_id: uuid.UUID, body: ReplyIn, _: CurrentUser, db: DbSession) -> SupplierMessage:
    s = await _get_supplier(db, supplier_id)
    return await service.record_reply(db, s, body.model_dump())


@router.post("/messages/{message_id}/sent", response_model=SupplierMessageOut, summary="Chị đã gửi tin")
async def mark_message_sent(message_id: uuid.UUID, body: MessageSentIn, _: CurrentUser, db: DbSession) -> Any:
    return await service.mark_sent(db, await service.get_message(db, message_id), body.channel)


# ---- d5: đơn đặt mẫu, đặt lô ---------------------------------------------------------------------------------------


async def po_view(db: DbSession, po: PurchaseOrder) -> PurchaseOrderView:
    names = await service.supplier_names(db, {i for i in (po.supplier_id, po.agent_supplier_id) if i})
    title = (
        await db.scalar(select(Candidate.title_vi).where(Candidate.id == po.candidate_id)) if po.candidate_id else None
    )
    ships = list(
        (await db.execute(select(InboundShipment).where(InboundShipment.purchase_order_id == po.id))).scalars()
    )
    kinds = (await service.po_document_kinds(db, [po.id])).get(po.id, set())
    return PurchaseOrderView.model_validate(
        {
            **_fields(PurchaseOrderView, po),
            "lines": list(po.lines),
            "supplier_name": names.get(po.supplier_id) if po.supplier_id else None,
            "agent_name": names.get(po.agent_supplier_id) if po.agent_supplier_id else None,
            "candidate_title": title,
            "inbound": [
                {"id": s.id, "status": s.status, "tracking_code": s.tracking_code, "eta": s.eta} for s in ships
            ],
            "document_kinds": sorted(kinds),
            "missing_documents": service.missing_docs(po, kinds),
        }
    )


@router.get("/purchase-orders", response_model=Paginated[PurchaseOrderView], summary="Đơn đặt mẫu, đặt lô (d5)")
async def list_pos(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    state: Annotated[list[POStatus] | None, Query()] = None,
    kind: POKind | None = None,
    supplier_id: uuid.UUID | None = None,
    candidate_id: uuid.UUID | None = None,
    open_only: bool = False,
) -> Paginated[PurchaseOrderView]:
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    if state:
        stmt = stmt.where(PurchaseOrder.status.in_(state))
    if kind:
        stmt = stmt.where(PurchaseOrder.kind == kind)
    if supplier_id:
        stmt = stmt.where(or_(PurchaseOrder.supplier_id == supplier_id, PurchaseOrder.agent_supplier_id == supplier_id))
    if candidate_id:
        stmt = stmt.where(PurchaseOrder.candidate_id == candidate_id)
    if open_only:
        stmt = stmt.where(PurchaseOrder.status.not_in([POStatus.RECEIVED, POStatus.CANCELLED]))
    result = await paginate(db, stmt, page)
    result.items = [await po_view(db, po) for po in result.items]
    return result  # type: ignore[return-value]


@router.post("/purchase-orders/sample", response_model=PurchaseOrderView, status_code=status.HTTP_201_CREATED)
async def create_sample_order(body: SampleOrderIn, _: CurrentUser, db: DbSession) -> PurchaseOrderView:
    po = await service.sample_order_for(
        db, body.candidate_id, quantity=body.quantity, supplier_id=body.supplier_id, ai_generated=True
    )
    return await po_view(db, po)  # type: ignore[arg-type]


@router.post("/purchase-orders", response_model=PurchaseOrderView, status_code=status.HTTP_201_CREATED)
async def create_order(body: PurchaseOrderIn, _: CurrentUser, db: DbSession) -> PurchaseOrderView:
    po = await service.create_po(db, body.model_dump())
    po = await service.submit_po(db, po)
    return await po_view(db, po)


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderView)
async def get_order(po_id: uuid.UUID, _: CurrentUser, db: DbSession) -> PurchaseOrderView:
    return await po_view(db, await service.get_po(db, po_id))


@router.patch("/purchase-orders/{po_id}", response_model=PurchaseOrderView, summary="Sửa đơn nháp (chị trả lại)")
async def update_order(po_id: uuid.UUID, body: PurchaseOrderUpdate, _: CurrentUser, db: DbSession) -> PurchaseOrderView:
    po = await service.get_po(db, po_id)
    data = body.model_dump(exclude_unset=True)
    if po.status not in (POStatus.DRAFT, POStatus.PENDING_APPROVAL) and set(data) - {"notes", "expected_at"}:
        raise Conflict("Đơn đã duyệt; chỉ sửa được ghi chú và ngày dự kiến.", code="po_locked")
    for k, v in data.items():
        setattr(po, k, v)
    service.recompute_totals(po)
    await db.flush()
    return await po_view(db, po)


@router.post("/purchase-orders/{po_id}/submit", response_model=PurchaseOrderView, summary="Gửi chị duyệt lại")
async def submit_order(po_id: uuid.UUID, _: CurrentUser, db: DbSession) -> PurchaseOrderView:
    po = await service.submit_po(db, await service.get_po(db, po_id))
    return await po_view(db, po)


@router.post("/purchase-orders/{po_id}/compose", response_model=PurchaseOrderView, summary="AI soạn lại nội dung đơn")
async def compose_order(po_id: uuid.UUID, _: CurrentUser, db: DbSession) -> PurchaseOrderView:
    po = await service.get_po(db, po_id)
    if po.status not in (POStatus.DRAFT, POStatus.PENDING_APPROVAL):
        raise Conflict("Đơn đã duyệt, không soạn lại được.", code="po_locked")
    await service.compose_po_message(db, po)
    if po.status == POStatus.PENDING_APPROVAL:
        await service.submit_po(db, po)
    return await po_view(db, po)


@router.post("/purchase-orders/{po_id}/status", response_model=PurchaseOrderView, summary="Đã gửi / NCC xác nhận / huỷ")
async def set_order_status(po_id: uuid.UUID, body: POStatusIn, user: CurrentUser, db: DbSession) -> PurchaseOrderView:
    po = await service.set_po_status(db, await service.get_po(db, po_id), body.to, user, body.note)
    return await po_view(db, po)


@router.post("/purchase-orders/{po_id}/payments", response_model=PurchaseOrderView, summary="Ghi khoản đã trả")
async def record_payment(po_id: uuid.UUID, body: PaymentIn, user: OwnerUser, db: DbSession) -> PurchaseOrderView:
    po = await service.record_payment(db, await service.get_po(db, po_id), body.model_dump(), user)
    return await po_view(db, po)


@router.post("/purchase-orders/{po_id}/receive", response_model=PurchaseOrderView, summary="Đếm hàng nhận, hàng lỗi")
async def receive_order(po_id: uuid.UUID, body: ReceiveIn, _: CurrentUser, db: DbSession) -> PurchaseOrderView:
    po = await service.receive_po(db, await service.get_po(db, po_id), [ln.model_dump() for ln in body.lines])
    return await po_view(db, po)


# ---- d7: lô hàng về ------------------------------------------------------------------------------------------------


async def inbound_view(db: DbSession, s: InboundShipment) -> InboundView:
    po = await db.get(PurchaseOrder, s.purchase_order_id) if s.purchase_order_id else None
    name = None
    if po and po.supplier_id:
        name = (await service.supplier_names(db, {po.supplier_id})).get(po.supplier_id)
    kinds = (await service.po_document_kinds(db, [po.id])).get(po.id, set()) if po else set()
    own = (
        await db.execute(select(ProvenanceDocument.kind).where(ProvenanceDocument.inbound_shipment_id == s.id))
    ).scalars()
    kinds |= {k.value for k in own}
    return InboundView.model_validate(
        {
            **_fields(InboundView, s),
            "po_code": po.code if po else None,
            "supplier_name": name,
            "document_kinds": sorted(kinds),
            "missing_documents": service.missing_docs(po, kinds) if po else [],
        }
    )


async def _get_inbound(db: DbSession, inbound_id: uuid.UUID) -> InboundShipment:
    s = await db.get(InboundShipment, inbound_id)
    if s is None:
        raise NotFound("Không tìm thấy lô hàng.")
    return s


@router.get("/inbound", response_model=Paginated[InboundView], summary="Lô hàng về (d7)")
async def list_inbound(_: CurrentUser, db: DbSession, page: Page, active_only: bool = False) -> Paginated[InboundView]:
    stmt = select(InboundShipment).order_by(InboundShipment.received_at.desc().nulls_first(), InboundShipment.eta)
    if active_only:
        stmt = stmt.where(InboundShipment.received_at.is_(None))
    result = await paginate(db, stmt, page)
    result.items = [await inbound_view(db, s) for s in result.items]
    return result  # type: ignore[return-value]


@router.post("/inbound", response_model=InboundView, status_code=status.HTTP_201_CREATED)
async def create_inbound(body: InboundIn, _: CurrentUser, db: DbSession) -> InboundView:
    return await inbound_view(db, await service.create_inbound(db, body.model_dump()))


@router.get("/inbound/{inbound_id}", response_model=InboundView)
async def get_inbound(inbound_id: uuid.UUID, _: CurrentUser, db: DbSession) -> InboundView:
    return await inbound_view(db, await _get_inbound(db, inbound_id))


@router.patch("/inbound/{inbound_id}", response_model=InboundView)
async def update_inbound(inbound_id: uuid.UUID, body: InboundUpdate, _: CurrentUser, db: DbSession) -> InboundView:
    s = await _get_inbound(db, inbound_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush()
    return await inbound_view(db, s)


@router.post("/inbound/{inbound_id}/milestones", response_model=InboundView, summary="Cập nhật mốc bằng tay")
async def add_milestone(inbound_id: uuid.UUID, body: MilestoneIn, _: CurrentUser, db: DbSession) -> InboundView:
    s = await service.add_milestone(db, await _get_inbound(db, inbound_id), body.status, note=body.note, at=body.at)
    return await inbound_view(db, s)


@router.post("/inbound/{inbound_id}/sync", response_model=InboundView, summary="Cập nhật mốc từ hãng vận chuyển")
async def sync_inbound(inbound_id: uuid.UUID, _: CurrentUser, db: DbSession) -> InboundView:
    s = await _get_inbound(db, inbound_id)
    await service.sync_tracking(db, s)
    return await inbound_view(db, s)


# ---- d4: chứng từ nguồn gốc ----------------------------------------------------------------------------------------


def document_view(d: ProvenanceDocument) -> DocumentView:
    return DocumentView.model_validate({**_fields(DocumentView, d), "url": file_url(d.storage_key)})


@router.get("/documents/warnings", response_model=list[DocumentWarning], summary="Lô thiếu chứng từ (d4)")
async def document_warnings(_: CurrentUser, db: DbSession) -> list[dict]:
    return await service.document_warnings(db)


@router.get("/documents", response_model=list[DocumentView], summary="Chứng từ nguồn gốc (d4)")
async def list_documents(
    _: CurrentUser,
    db: DbSession,
    purchase_order_id: uuid.UUID | None = None,
    inbound_shipment_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[DocumentView]:
    stmt = select(ProvenanceDocument).order_by(ProvenanceDocument.created_at.desc())
    if purchase_order_id:
        ship_ids = select(InboundShipment.id).where(InboundShipment.purchase_order_id == purchase_order_id)
        stmt = stmt.where(
            or_(
                ProvenanceDocument.purchase_order_id == purchase_order_id,
                ProvenanceDocument.inbound_shipment_id.in_(ship_ids),
            )
        )
    if inbound_shipment_id:
        stmt = stmt.where(ProvenanceDocument.inbound_shipment_id == inbound_shipment_id)
    if product_id:
        stmt = stmt.where(ProvenanceDocument.product_id == product_id)
    if supplier_id:
        stmt = stmt.where(ProvenanceDocument.supplier_id == supplier_id)
    return [document_view(d) for d in (await db.execute(stmt.limit(200))).scalars()]


@router.post("/documents", response_model=DocumentView, status_code=status.HTTP_201_CREATED, summary="Tải chứng từ")
async def upload_document(
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    kind: Annotated[DocumentKind, Form()],
    purchase_order_id: Annotated[uuid.UUID | None, Form()] = None,
    inbound_shipment_id: Annotated[uuid.UUID | None, Form()] = None,
    product_id: Annotated[uuid.UUID | None, Form()] = None,
    supplier_id: Annotated[uuid.UUID | None, Form()] = None,
    doc_number: Annotated[str | None, Form(max_length=100)] = None,
    doc_date: Annotated[date | None, Form()] = None,
    amount: Annotated[Decimal | None, Form(ge=0)] = None,
    currency: Annotated[str | None, Form(min_length=3, max_length=3)] = None,
    notes: Annotated[str | None, Form(max_length=2000)] = None,
) -> DocumentView:
    if not any((purchase_order_id, inbound_shipment_id, product_id, supplier_id)):
        raise BadRequest("Chứng từ cần gắn với một đơn, một lô hàng, một sản phẩm hoặc một nhà cung cấp.")
    if purchase_order_id:
        po = await service.get_po(db, purchase_order_id)
        supplier_id = supplier_id or po.supplier_id
    if inbound_shipment_id:
        await _get_inbound(db, inbound_shipment_id)
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if not ctype.startswith(DOC_TYPES):
        raise BadRequest("Chứng từ cần là ảnh hoặc PDF.", code="bad_file_type")
    data = await file.read()
    if not data:
        raise BadRequest("Tệp trống.", code="empty_file")
    if len(data) > MAX_DOC_BYTES:
        raise BadRequest("Tệp quá lớn (tối đa 20 MB).", code="file_too_large")
    ext = "pdf" if ctype == "application/pdf" else (ctype.split("/", 1)[1].replace("jpeg", "jpg") or "bin")
    stored = await get_storage().put(new_key("private/provenance", ext), data, ctype)
    doc = ProvenanceDocument(
        kind=kind, purchase_order_id=purchase_order_id, inbound_shipment_id=inbound_shipment_id, product_id=product_id,
        supplier_id=supplier_id, storage_key=stored.key, filename=(file.filename or f"chung-tu.{ext}")[:255],
        content_type=ctype, size_bytes=len(data), doc_number=doc_number, doc_date=doc_date, amount=amount,
        currency=currency.upper() if currency else None, notes=notes, uploaded_by_id=user.id,
    )  # fmt: skip
    db.add(doc)
    await db.flush()
    return document_view(doc)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, _: OwnerUser, db: DbSession) -> None:
    d = await db.get(ProvenanceDocument, document_id)
    if d is None:
        raise NotFound("Không tìm thấy chứng từ.")
    key = d.storage_key
    await db.delete(d)
    await db.flush()
    try:
        await get_storage().delete(key)
    except Exception:  # tệp đã mất trước đó: bỏ qua
        pass
