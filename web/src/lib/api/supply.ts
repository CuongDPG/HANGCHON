"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

/** Nguồn cung và giá vốn (d1–d7) — khớp `/api/desk/supply/**`. Số thập phân từ API là chuỗi (Decimal). */

type Dec = string | number;
export const num = (v: Dec | null | undefined): number => (v === null || v === undefined || v === "" ? 0 : Number(v));

export type SupplierKind = "factory" | "shop" | "trading" | "purchasing_agent" | "forwarder" | "local_wholesaler";
export const SUPPLIER_KIND_LABELS: Record<SupplierKind, string> = {
  factory: "Xưởng",
  shop: "Shop trên sàn",
  trading: "Công ty thương mại",
  purchasing_agent: "Đơn vị mua hộ",
  forwarder: "Vận chuyển, gom hàng",
  local_wholesaler: "Sỉ trong nước",
};
export const LANGUAGE_LABELS: Record<string, string> = { zh: "Tiếng Trung", ja: "Tiếng Nhật", vi: "Tiếng Việt", en: "Tiếng Anh" };

export type Supplier = {
  id: string;
  name: string;
  name_original: string | null;
  kind: SupplierKind;
  platform: string | null;
  shop_url: string | null;
  country: string | null;
  language: string;
  contact: Record<string, unknown>;
  trust_score: number | null;
  order_count: number;
  defect_rate: Dec | null;
  on_time_rate: Dec | null;
  avg_lead_days: Dec | null;
  agent_fee_pct: Dec | null;
  notes: string | null;
  is_blocked: boolean;
  trust_label: string;
  trust_basis: string;
  open_orders: number;
};
export type SupplierInput = {
  name: string;
  name_original?: string | null;
  kind: SupplierKind;
  country?: string | null;
  language: string;
  shop_url?: string | null;
  notes?: string | null;
  is_blocked?: boolean;
};

export type CostParams = {
  fx_rates: Record<string, Dec>;
  intl_vnd_per_kg: Record<string, number>;
  agent_fee_pct: Dec;
  domestic_shipping_vnd: number;
  import_tax_pct: Dec;
  vat_pct: Dec;
  loss_pct: Dec;
  packaging_vnd: number;
  target_margin_pct: Dec;
  recalculated?: number;
};

export type CostLine = { key: string; label: string; amount_vnd: number; formula: string };
export type CostSheet = {
  id: string;
  candidate_id: string | null;
  supplier_id: string | null;
  version: number;
  auto_update: boolean;
  unit_price_amount: Dec;
  currency: string;
  fx_rate: Dec;
  weight_grams: number | null;
  domestic_shipping_vnd: number;
  packaging_vnd: number;
  other_fees_vnd: number;
  landed_cost_vnd: number;
  breakdown: CostLine[];
  recalculated_at: string | null;
  candidate_title?: string | null;
  candidate_stage?: string | null;
};
export type CostInput = {
  candidate_id?: string;
  supplier_id?: string | null;
  unit_price_amount: string;
  currency: string;
  weight_grams?: number | null;
  domestic_shipping_vnd?: number | null;
  packaging_vnd?: number | null;
  other_fees_vnd?: number;
  auto_update: boolean;
  fx_rate?: string | null;
  vat_pct?: string | null;
  import_tax_pct?: string | null;
  agent_fee_pct?: string | null;
  loss_pct?: string | null;
  intl_shipping_vnd_per_kg?: number | null;
};

export type PriceProposal = {
  id: string;
  candidate_id: string | null;
  status: "draft" | "pending_review" | "approved" | "rejected" | "superseded";
  landed_cost_vnd: number;
  market_low_vnd: number | null;
  market_median_vnd: number | null;
  market_high_vnd: number | null;
  target_margin_pct: Dec | null;
  proposed_price_vnd: number;
  proposed_drop_price_vnd: number | null;
  margin_pct: Dec | null;
  rationale: string | null;
  approved_price_vnd: number | null;
  approval_item_id: string | null;
  created_at: string;
  market_samples: number;
};

export type POStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "sent"
  | "confirmed"
  | "paid"
  | "partially_received"
  | "received"
  | "cancelled";
export const PO_STATUS_LABELS: Record<POStatus, string> = {
  draft: "Nháp",
  pending_approval: "Chờ chị duyệt",
  approved: "Đã duyệt, chờ gửi",
  sent: "Đã gửi",
  confirmed: "Bên bán đã nhận",
  paid: "Đã trả tiền",
  partially_received: "Nhận một phần",
  received: "Đã nhận đủ",
  cancelled: "Đã huỷ",
};
export const PO_KIND_LABELS = { sample: "Đặt mẫu", batch: "Đặt lô", restock: "Bổ sung hàng" } as const;

export type POLine = {
  id: string;
  candidate_id: string | null;
  product_id: string | null;
  description: string;
  source_url: string | null;
  quantity: number;
  unit_price_amount: Dec;
  line_total_amount: Dec;
  unit_cost_vnd: number | null;
  received_qty: number;
  defect_qty: number;
};
export type InboundStatus =
  | "ordered"
  | "seller_shipped"
  | "at_agent_warehouse"
  | "international_transit"
  | "customs"
  | "domestic_transit"
  | "delivered"
  | "problem";
export const INBOUND_FLOW: InboundStatus[] = [
  "ordered",
  "seller_shipped",
  "at_agent_warehouse",
  "international_transit",
  "customs",
  "domestic_transit",
  "delivered",
];
export const INBOUND_LABELS: Record<InboundStatus, string> = {
  ordered: "Đã đặt",
  seller_shipped: "Bên bán đã gửi",
  at_agent_warehouse: "Về kho bên bán / kho mua hộ",
  international_transit: "Đang về Việt Nam",
  customs: "Đang thông quan",
  domestic_transit: "Đang giao về nhà",
  delivered: "Đã về nhà",
  problem: "Có vấn đề",
};

export type PurchaseOrder = {
  id: string;
  code: string;
  kind: keyof typeof PO_KIND_LABELS;
  status: POStatus;
  supplier_id: string | null;
  agent_supplier_id: string | null;
  candidate_id: string | null;
  drop_id: string | null;
  currency: string;
  fx_rate: Dec | null;
  subtotal_amount: Dec;
  shipping_amount: Dec;
  fees_vnd: number;
  total_vnd: number;
  deposit_vnd: number;
  paid_vnd: number;
  message_draft: string | null;
  message_language: string | null;
  approval_item_id: string | null;
  approved_at: string | null;
  sent_at: string | null;
  expected_at: string | null;
  received_at: string | null;
  ai_generated: boolean;
  notes: string | null;
  created_at: string;
  lines: POLine[];
  supplier_name: string | null;
  agent_name: string | null;
  candidate_title: string | null;
  inbound: { id: string; status: InboundStatus; tracking_code: string | null; eta: string | null }[];
  document_kinds: string[];
  missing_documents: string[];
};

export type Milestone = { status: InboundStatus; at: string; note: string | null; source: string };
export type Inbound = {
  id: string;
  purchase_order_id: string | null;
  code: string | null;
  carrier: string | null;
  tracking_code: string | null;
  status: InboundStatus;
  milestones: Milestone[];
  eta: string | null;
  weight_kg: Dec | null;
  received_at: string | null;
  problem_note: string | null;
  po_code: string | null;
  supplier_name: string | null;
  document_kinds: string[];
  missing_documents: string[];
};

export type DocumentKind =
  | "invoice"
  | "customs_declaration"
  | "original_label"
  | "packing_list"
  | "payment_receipt"
  | "certificate"
  | "contract"
  | "other";
export const DOC_LABELS: Record<DocumentKind, string> = {
  invoice: "Hoá đơn mua",
  customs_declaration: "Tờ khai hải quan",
  original_label: "Ảnh nhãn gốc",
  packing_list: "Phiếu đóng gói",
  payment_receipt: "Biên nhận thanh toán",
  certificate: "Chứng nhận, công bố",
  contract: "Hợp đồng",
  other: "Chứng từ khác",
};
/** Phần AI đọc từ chứng từ (d4). `status`: reading (đang đọc) · read · pending (chờ chị duyệt) · failed · unreadable · off. */
export type DocExtract = {
  status?: "reading" | "read" | "pending" | "failed" | "unreadable" | "off";
  note?: string;
  readable?: boolean;
  edited?: boolean;
  source?: "image" | "pdf_text";
  product_name?: string | null;
  product_name_vi?: string | null;
  manufacturer?: string | null;
  origin_country?: string | null;
  lot_number?: string | null;
  production_date?: string | null;
  expiry_date?: string | null;
  doc_number?: string | null;
  doc_date?: string | null;
  amount?: number | null;
  currency?: string | null;
  certifications?: string[];
  summary?: string | null;
};
export type ExtractField = "product_name" | "product_name_vi" | "manufacturer" | "origin_country" | "lot_number" | "production_date" | "expiry_date";
export const EXTRACT_LABELS: Record<ExtractField, string> = {
  product_name: "Tên hàng trên chứng từ",
  product_name_vi: "Tên hàng (tiếng Việt)",
  manufacturer: "Nhà sản xuất",
  origin_country: "Xuất xứ",
  lot_number: "Số lô",
  production_date: "Ngày sản xuất",
  expiry_date: "Hạn dùng",
};
export type ProvenanceDoc = {
  id: string;
  kind: DocumentKind;
  purchase_order_id: string | null;
  inbound_shipment_id: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  doc_number: string | null;
  doc_date: string | null;
  amount: string | null;
  currency: string | null;
  notes: string | null;
  extracted: DocExtract;
  created_at: string;
  url: string | null;
};
export type DocPatch = {
  doc_number?: string | null;
  doc_date?: string | null;
  extracted?: Partial<Record<ExtractField, string | null>> & { certifications?: string[]; summary?: string | null };
};
export type DocWarning = {
  purchase_order_id: string;
  po_code: string;
  kind: string;
  status: POStatus;
  supplier_name: string | null;
  missing: DocumentKind[];
  missing_labels: string[];
};

export type SupplierMessage = {
  id: string;
  supplier_id: string;
  candidate_id: string | null;
  direction: "outbound" | "inbound";
  channel: string;
  language: string;
  body_original: string;
  body_vi: string | null;
  status: "draft" | "pending_review" | "approved" | "sent" | "received" | "failed";
  extracted: {
    unit_price?: number | null;
    currency?: string | null;
    moq?: number | null;
    lead_days?: number | null;
    shipping_note?: string | null;
    sample_available?: boolean | null;
    summary?: string;
  };
  approval_item_id: string | null;
  created_at: string;
};
export type InquiryTopic = "price" | "moq" | "lead_time" | "shipping" | "sample";
export const TOPIC_LABELS: Record<InquiryTopic, string> = {
  price: "Giá theo số lượng",
  moq: "Số lượng tối thiểu",
  lead_time: "Thời gian gửi hàng",
  shipping: "Phí gửi",
  sample: "Mua mẫu",
};

const S = "/api/desk/supply";

export const supplyKeys = {
  all: ["supply"] as const,
  suppliers: (q: object) => ["supply", "suppliers", q] as const,
  supplier: (id: string) => ["supply", "supplier", id] as const,
  messages: (id: string) => ["supply", "messages", id] as const,
  params: ["supply", "params"] as const,
  sheets: ["supply", "sheets"] as const,
  sheet: (candidateId: string) => ["supply", "sheet", candidateId] as const,
  proposals: (candidateId: string) => ["supply", "proposals", candidateId] as const,
  pos: (q: object) => ["supply", "pos", q] as const,
  po: (id: string) => ["supply", "po", id] as const,
  inboundList: (q: object) => ["supply", "inbound", q] as const,
  inbound: (id: string) => ["supply", "inbound-one", id] as const,
  docs: (q: object) => ["supply", "docs", q] as const,
  warnings: ["supply", "warnings"] as const,
};

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: supplyKeys.all });
    qc.invalidateQueries({ queryKey: ["selection"] });
  };
}

/* ---------- d1 ---------- */

export function useSuppliers(q: { q?: string; kind?: SupplierKind } = {}) {
  return useQuery({
    queryKey: supplyKeys.suppliers(q),
    queryFn: () => api.get<Paginated<Supplier>>(`${S}/suppliers`, { query: { ...q, size: 100 } }),
  });
}

export function useSupplier(id: string) {
  return useQuery({ queryKey: supplyKeys.supplier(id), queryFn: () => api.get<Supplier>(`${S}/suppliers/${id}`) });
}

export function useSaveSupplier() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: SupplierInput & { id?: string }) =>
      id ? api.patch<Supplier>(`${S}/suppliers/${id}`, body) : api.post<Supplier>(`${S}/suppliers`, body),
    onSuccess: invalidate,
  });
}

/* ---------- d2 ---------- */

export function useCostParams() {
  return useQuery({ queryKey: supplyKeys.params, queryFn: () => api.get<CostParams>(`${S}/settings`) });
}

export function useSaveCostParams() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (body: CostParams) => api.patch<CostParams>(`${S}/settings`, body), onSuccess: invalidate });
}

export function useCostSheets() {
  return useQuery({
    queryKey: supplyKeys.sheets,
    queryFn: () => api.get<Paginated<CostSheet>>(`${S}/cost-sheets`, { query: { size: 100 } }),
  });
}

export function useCurrentSheet(candidateId: string) {
  return useQuery({
    queryKey: supplyKeys.sheet(candidateId),
    queryFn: () => api.get<CostSheet | null>(`${S}/cost-sheets/current`, { query: { candidate_id: candidateId } }),
  });
}

export function previewCost(body: CostInput) {
  return api.post<{ landed_cost_vnd: number; breakdown: CostLine[] }>(`${S}/cost-sheets/preview`, body);
}

export function useSaveCostSheet() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (body: CostInput) => api.post<CostSheet>(`${S}/cost-sheets`, body), onSuccess: invalidate });
}

/* ---------- d3 ---------- */

export function usePriceProposals(candidateId: string) {
  return useQuery({
    queryKey: supplyKeys.proposals(candidateId),
    queryFn: () => api.get<PriceProposal[]>(`${S}/price-proposals`, { query: { candidate_id: candidateId } }),
  });
}

export function useProposePrice() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { candidate_id: string; target_margin_pct?: number }) => api.post<PriceProposal>(`${S}/price-proposals`, body),
    onSuccess: invalidate,
  });
}

/* ---------- duyệt / trả lại qua hàng chờ của control ---------- */

export function useApproveItem() {
  const invalidate = useInvalidate();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload?: Record<string, unknown> }) =>
      api.post<{ status: string; error: string | null }>(`/api/desk/control/approvals/${id}/approve`, payload ? { payload } : {}),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["control"] });
    },
  });
}

export function useReturnItem() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => api.post(`/api/desk/control/approvals/${id}/return`, { note }),
    onSuccess: invalidate,
  });
}

/* ---------- d5 ---------- */

export function usePurchaseOrders(q: { open_only?: boolean; candidate_id?: string; supplier_id?: string } = {}) {
  return useQuery({
    queryKey: supplyKeys.pos(q),
    queryFn: () => api.get<Paginated<PurchaseOrder>>(`${S}/purchase-orders`, { query: { ...q, size: 100 } }),
  });
}

export function usePurchaseOrder(id: string) {
  return useQuery({ queryKey: supplyKeys.po(id), queryFn: () => api.get<PurchaseOrder>(`${S}/purchase-orders/${id}`) });
}

export function useSampleOrder() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { candidate_id: string; quantity?: number }) => api.post<PurchaseOrder>(`${S}/purchase-orders/sample`, body),
    onSuccess: invalidate,
  });
}

export function usePOAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: string; action: "submit" | "compose" | "status" | "payments" | "receive"; body?: unknown }) =>
      api.post<PurchaseOrder>(`${S}/purchase-orders/${id}/${action}`, body),
    onSuccess: invalidate,
  });
}

export function useUpdatePO() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; message_draft?: string; notes?: string; expected_at?: string | null }) =>
      api.patch<PurchaseOrder>(`${S}/purchase-orders/${id}`, body),
    onSuccess: invalidate,
  });
}

/* ---------- d7 ---------- */

export function useInboundList(q: { active_only?: boolean } = {}) {
  return useQuery({
    queryKey: supplyKeys.inboundList(q),
    queryFn: () => api.get<Paginated<Inbound>>(`${S}/inbound`, { query: { ...q, size: 100 } }),
  });
}

export function useInbound(id: string) {
  return useQuery({ queryKey: supplyKeys.inbound(id), queryFn: () => api.get<Inbound>(`${S}/inbound/${id}`) });
}

export function useInboundAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: string; action: "milestones" | "sync"; body?: unknown }) =>
      api.post<Inbound>(`${S}/inbound/${id}/${action}`, body),
    onSuccess: invalidate,
  });
}

export function useUpdateInbound() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; tracking_code?: string | null; carrier?: string | null; eta?: string | null }) =>
      api.patch<Inbound>(`${S}/inbound/${id}`, body),
    onSuccess: invalidate,
  });
}

/* ---------- d4 ---------- */

export function useDocuments(q: { purchase_order_id?: string; inbound_shipment_id?: string }) {
  return useQuery({
    queryKey: supplyKeys.docs(q),
    queryFn: () => api.get<ProvenanceDoc[]>(`${S}/documents`, { query: q }),
    // AI đang đọc chứng từ (việc nền) → hỏi lại vài giây một lần cho tới khi xong
    refetchInterval: (query) => (query.state.data?.some((d) => d.extracted?.status === "reading") ? 3000 : false),
  });
}

export function useEditDocument() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: DocPatch & { id: string }) => api.patch<ProvenanceDoc>(`${S}/documents/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useRereadDocument() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => api.post<ProvenanceDoc>(`${S}/documents/${id}/read`), onSuccess: invalidate });
}

export function useDocWarnings() {
  return useQuery({ queryKey: supplyKeys.warnings, queryFn: () => api.get<DocWarning[]>(`${S}/documents/warnings`) });
}

export function useUploadDocument() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (input: { file: File; kind: DocumentKind; purchase_order_id?: string; inbound_shipment_id?: string; doc_number?: string }) => {
      const fd = new FormData();
      fd.append("file", input.file);
      fd.append("kind", input.kind);
      if (input.purchase_order_id) fd.append("purchase_order_id", input.purchase_order_id);
      if (input.inbound_shipment_id) fd.append("inbound_shipment_id", input.inbound_shipment_id);
      if (input.doc_number) fd.append("doc_number", input.doc_number);
      return api.post<ProvenanceDoc>(`${S}/documents`, fd);
    },
    onSuccess: invalidate,
  });
}

export function useDeleteDocument() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => api.delete(`${S}/documents/${id}`), onSuccess: invalidate });
}

/* ---------- d6 ---------- */

export function useSupplierMessages(supplierId: string) {
  return useQuery({
    queryKey: supplyKeys.messages(supplierId),
    queryFn: () => api.get<SupplierMessage[]>(`${S}/suppliers/${supplierId}/messages`),
  });
}

export function useDraftInquiry(supplierId: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { candidate_id?: string | null; topics: InquiryTopic[]; quantity?: number | null; extra?: string }) =>
      api.post<SupplierMessage>(`${S}/suppliers/${supplierId}/messages/inquiry`, body),
    onSuccess: invalidate,
  });
}

export function useRecordReply(supplierId: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { body_original: string }) => api.post<SupplierMessage>(`${S}/suppliers/${supplierId}/messages/reply`, body),
    onSuccess: invalidate,
  });
}

export function useMarkSent() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => api.post<SupplierMessage>(`${S}/messages/${id}/sent`, {}),
    onSuccess: invalidate,
  });
}
