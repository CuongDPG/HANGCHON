"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

/* ================================================================================================================
 * Kiểu dữ liệu (khớp api/app/modules/orders/schemas.py)
 * ============================================================================================================== */

export type OrderStatus =
  | "draft"
  | "pending_payment"
  | "confirmed"
  | "awaiting_stock"
  | "ready_to_ship"
  | "shipping"
  | "delivered"
  | "completed"
  | "cancelled"
  | "returned";
export type PaymentMethod = "bank_transfer" | "cod" | "marketplace" | "cash";
export type PaymentState = "unpaid" | "partially_paid" | "paid" | "refunded" | "partially_refunded";
export type ShippingStatus =
  | "pending"
  | "created"
  | "picked_up"
  | "in_transit"
  | "out_for_delivery"
  | "delivered"
  | "failed_delivery"
  | "returning"
  | "returned"
  | "cancelled";
export type Channel = "web" | "facebook" | "instagram" | "threads" | "tiktok" | "zalo_oa" | "zalo_group" | "zalo" | "tiktok_shop" | "shopee" | "email" | "sms" | "phone" | "manual";
export type ReturnKind = "return" | "exchange" | "refund_only";
export type ReturnReason = "defect" | "wrong_item" | "damaged_in_shipping" | "not_as_described" | "changed_mind" | "other";
export type ReturnStatus = "requested" | "pending_decision" | "approved" | "rejected" | "awaiting_item" | "received" | "refunded" | "exchanged" | "closed";

export type CartLine = { product_id: string; variant_id?: string | null; drop_id?: string | null; quantity: number };
export type AddressFields = { address_line?: string | null; ward?: string | null; district?: string | null; province?: string | null };

export type DropBrief = { id: string; code: string; title: string; status: string; closes_at: string | null; expected_arrival_date: string | null };

export type QuoteLine = {
  product_id: string;
  variant_id: string | null;
  drop_id: string | null;
  drop_item_id: string | null;
  fulfillment_source: "drop" | "stock";
  name: string;
  variant_name: string | null;
  slug: string | null;
  image_url: string | null;
  unit_price_vnd: number;
  quantity: number;
  line_total_vnd: number;
  available: number | null;
  ok: boolean;
  problem: string | null;
};

export type Quote = {
  lines: QuoteLine[];
  subtotal_vnd: number;
  shipping_fee_vnd: number;
  shipping_estimated: boolean;
  total_vnd: number;
  deposit_required_vnd: number;
  drops: DropBrief[];
  delivery_hint: string | null;
  problems: string[];
  ok: boolean;
};

export type CheckoutInput = AddressFields & {
  items: CartLine[];
  name: string;
  phone: string;
  payment_method: "bank_transfer" | "cod";
  note?: string | null;
  client_ref?: string;
  marketing_opt_in?: boolean;
  src?: string;
  referral_code?: string;
};

export type PaymentInfo = {
  method: PaymentMethod;
  transfer_content: string | null;
  bank_code: string | null;
  account_no: string | null;
  account_name: string | null;
  amount_due_vnd: number;
  qr_url: string | null;
  qr_payload: string | null;
  due_at: string | null;
};

export type TimelineStep = { key: string; title: string; status: "done" | "current" | "todo"; at: string | null; meta: string | null };

export type PublicOrder = {
  code: string;
  token: string;
  status: OrderStatus;
  status_label: string;
  headline: string;
  channel: Channel;
  payment_method: PaymentMethod;
  payment_state: PaymentState;
  items: { name: string; variant_name: string | null; quantity: number; unit_price_vnd: number; line_total_vnd: number; image_url: string | null; slug: string | null }[];
  subtotal_vnd: number;
  shipping_fee_vnd: number;
  discount_vnd: number;
  total_vnd: number;
  paid_vnd: number;
  refunded_vnd: number;
  deposit_required_vnd: number;
  cod_amount_vnd: number;
  recipient_name: string;
  recipient_phone: string;
  address_line: string | null;
  ward: string | null;
  district: string | null;
  province: string | null;
  customer_note: string | null;
  placed_at: string;
  payment: PaymentInfo | null;
  drop: DropBrief | null;
  timeline: TimelineStep[];
  events: { title: string; detail: string | null; occurred_at: string }[];
  shipment: { carrier: string; tracking_code: string | null; status: ShippingStatus } | null;
  returns: { code: string; kind: ReturnKind; status: ReturnStatus; created_at: string }[];
  can_change_address: boolean;
  can_request_return: boolean;
  notify_hint: string | null;
  /** e8: món đã nhận chờ khách đánh giá (link một lần /danh-gia/<token>). */
  reviews: { name: string; token: string; status: string }[];
};

export type OrderListItem = {
  id: string;
  code: string;
  channel: Channel;
  status: OrderStatus;
  status_label: string;
  payment_method: PaymentMethod;
  payment_state: PaymentState;
  recipient_name: string;
  recipient_phone: string;
  province: string | null;
  total_vnd: number;
  paid_vnd: number;
  items_summary: string;
  item_count: number;
  placed_at: string;
  payment_due_at: string | null;
  drop_id: string | null;
  drop_code: string | null;
  ai_generated: boolean;
  tracking_code: string | null;
  missing_info: string[];
};

export type StatusGroup = "nhap" | "cho_thanh_toan" | "cho_hang" | "cho_giao" | "dang_giao" | "xong" | "huy" | "tat_ca";
export type OrderCounts = Record<Exclude<StatusGroup, "tat_ca">, number> & {
  tat_ca: number;
  new_today: number;
  payments_to_review: number;
  returns_open: number;
};

export type OrderEvent = { id: string; kind: string; status: OrderStatus | null; title: string; detail: string | null; visible_to_customer: boolean; actor: string; occurred_at: string };
export type OrderItem = { id: string; product_id: string | null; drop_item_id: string | null; fulfillment_source: "drop" | "stock"; name: string; variant_name: string | null; sku: string | null; quantity: number; unit_price_vnd: number; line_total_vnd: number };
export type Payment = {
  id: string;
  order_id: string | null;
  direction: "in" | "out";
  method: PaymentMethod;
  provider: string;
  status: "received" | "matched" | "needs_review" | "ignored" | "refunded" | "failed";
  amount_vnd: number;
  content: string | null;
  payer_name: string | null;
  received_at: string;
  match_method: string | null;
  note: string | null;
};
export type PaymentRow = Payment & { order_code: string | null };
export type Shipment = {
  id: string;
  carrier: string;
  service: string | null;
  tracking_code: string | null;
  status: ShippingStatus;
  fee_vnd: number;
  cod_amount_vnd: number;
  label_url: string | null;
  selection_reason: string | null;
  quotes: ShippingOption[];
  expected_delivery_at: string | null;
  created_at: string;
  events: { id: string; status: ShippingStatus; description: string; location: string | null; occurred_at: string }[];
};
export type Notification = { id: string; event: string; channel: string; recipient: string; body: string; status: "queued" | "sent" | "failed" | "skipped"; error: string | null; created_at: string };
export type ReturnRecord = {
  id: string;
  code: string;
  order_id: string;
  kind: ReturnKind;
  reason: ReturnReason;
  description: string | null;
  status: ReturnStatus;
  proposal: string | null;
  refund_amount_vnd: number;
  eligibility: { eligible?: boolean; summary?: string; checks?: { label: string; ok: boolean; note: string }[]; options?: { title: string; kind: string; refund_amount_vnd: number; description: string }[] };
  created_at: string;
};
export type ReturnRow = ReturnRecord & { order_code: string; recipient_name: string };

export type OrderDetail = Omit<PublicOrder, "items" | "events" | "timeline" | "payment" | "shipment" | "returns" | "token" | "headline" | "can_change_address" | "can_request_return" | "notify_hint" | "drop" | "reviews"> & {
  id: string;
  external_id: string | null;
  transfer_content: string | null;
  payment_due_at: string | null;
  internal_note: string | null;
  ai_generated: boolean;
  approval_item_id: string | null;
  cancel_reason: string | null;
  items: OrderItem[];
  events: OrderEvent[];
  payments: Payment[];
  shipments: Shipment[];
  notifications: Notification[];
  returns: ReturnRecord[];
  drop: DropBrief | null;
  customer: { id: string; name: string | null; phone: string | null; order_count: number; total_spent_vnd: number } | null;
  public_url: string;
  missing_info: string[];
  amount_due_vnd: number;
  can_cancel: boolean;
  can_ship: boolean;
  can_edit_address: boolean;
};

export type ShippingOption = { carrier: string; driver: string; service: string; service_name: string; fee_vnd: number; eta_days_min: number; eta_days_max: number };
export type ShipmentResult = { order_id: string; code: string; status: "applied" | "pending" | "blocked" | "failed" | "skipped"; shipment_id: string | null; tracking_code: string | null; fee_vnd: number | null; message: string | null };

export type DropOverview = {
  id: string;
  code: string;
  title: string;
  status: string;
  closes_at: string | null;
  expected_arrival_date: string | null;
  orders_total: number;
  orders_confirmed: number;
  orders_pending: number;
  revenue_vnd: number;
  slots_total: number | null;
  slots_taken: number;
  items: { drop_item_id: string; product_id: string; name: string; price_vnd: number; slots_total: number | null; quantity_confirmed: number; quantity_pending: number; min_total_to_order: number | null }[];
  inbound: { id: string; code: string | null; status: string; status_label: string; eta: string | null; last_note: string | null; last_at: string | null }[];
};

export type InventoryRow = { inventory_item_id: string; product_id: string; name: string; on_hand: number; reserved: number; pending_orders_qty: number; available: number; low_stock_threshold: number | null; low: boolean };
export type Listing = { id: string; marketplace: "tiktok_shop" | "shopee"; product_id: string; product_name: string; external_id: string | null; status: "pending" | "active" | "inactive" | "error"; price_vnd: number | null; synced_stock: number | null; last_synced_at: string | null; error: string | null };
export type SyncResult = { synced: number; created_orders: number; skipped: number; errors: string[] };
export type Templates = { templates: Record<string, string>; defaults: Record<string, string>; labels: Record<string, string>; placeholders: Record<string, string> };
export type LabelData = { order_id: string; code: string; recipient_name: string; recipient_phone: string; address: string; carrier: string; service: string | null; tracking_code: string | null; cod_amount_vnd: number; weight_grams: number | null; items_summary: string; note: string | null; label_url: string | null };

export type ManualOrderInput = AddressFields & {
  items: (CartLine & { unit_price_vnd?: number | null })[];
  name: string;
  phone: string;
  channel: Channel;
  payment_method: PaymentMethod;
  shipping_fee_vnd?: number | null;
  discount_vnd?: number;
  customer_note?: string | null;
  internal_note?: string | null;
  already_paid?: boolean;
};

/* ================================================================================================================
 * Nhãn tiếng Việt
 * ============================================================================================================== */

export const CHANNEL_LABELS: Record<string, string> = {
  web: "Website",
  facebook: "Facebook",
  instagram: "Instagram",
  threads: "Threads",
  tiktok: "TikTok",
  zalo_oa: "Zalo",
  zalo_group: "Nhóm Zalo",
  zalo: "Zalo",
  tiktok_shop: "TikTok Shop",
  shopee: "Shopee",
  email: "Email",
  sms: "SMS",
  phone: "Điện thoại",
  manual: "Chị tạo",
};

export const PAYMENT_LABELS: Record<PaymentMethod, string> = {
  bank_transfer: "Chuyển khoản",
  cod: "Trả khi nhận",
  marketplace: "Sàn thu hộ",
  cash: "Tiền mặt",
};

export const CARRIER_LABELS: Record<string, string> = { ghn: "GHN", ghtk: "GHTK", mock: "Giao thử", self: "Tự giao", viettel_post: "Viettel Post", other: "Khác" };

export const SHIPPING_LABELS: Record<ShippingStatus, string> = {
  pending: "Chưa tạo",
  created: "Chờ lấy hàng",
  picked_up: "Đã lấy hàng",
  in_transit: "Đang trung chuyển",
  out_for_delivery: "Đang giao",
  delivered: "Đã giao",
  failed_delivery: "Giao lỗi",
  returning: "Đang hoàn",
  returned: "Đã hoàn",
  cancelled: "Đã huỷ",
};

export const RETURN_REASON_LABELS: Record<ReturnReason, string> = {
  defect: "Hàng lỗi",
  wrong_item: "Giao sai món",
  damaged_in_shipping: "Vỡ, hỏng khi giao",
  not_as_described: "Khác mô tả",
  changed_mind: "Đổi ý",
  other: "Lý do khác",
};
export const RETURN_KIND_LABELS: Record<ReturnKind, string> = { return: "Trả hàng, hoàn tiền", exchange: "Đổi món", refund_only: "Chỉ hoàn tiền" };
export const RETURN_STATUS_LABELS: Record<ReturnStatus, string> = {
  requested: "Mới gửi",
  pending_decision: "Chờ chị quyết",
  approved: "Đã duyệt",
  rejected: "Không nhận",
  awaiting_item: "Chờ nhận hàng trả",
  received: "Đã nhận hàng trả",
  refunded: "Đã hoàn tiền",
  exchanged: "Đã đổi món",
  closed: "Đã đóng",
};

export const GROUPS: { value: StatusGroup; label: string }[] = [
  { value: "cho_thanh_toan", label: "Chờ thanh toán" },
  { value: "cho_hang", label: "Chờ hàng về" },
  { value: "cho_giao", label: "Chờ giao" },
  { value: "dang_giao", label: "Đang giao" },
  { value: "xong", label: "Xong" },
  { value: "huy", label: "Huỷ" },
  { value: "nhap", label: "Nháp" },
  { value: "tat_ca", label: "Tất cả" },
];

export function statusTone(status: OrderStatus): "neutral" | "accent" | "success" | "warning" | "danger" | "outline" {
  switch (status) {
    case "draft":
      return "outline";
    case "pending_payment":
      return "warning";
    case "shipping":
    case "ready_to_ship":
      return "accent";
    case "delivered":
    case "completed":
      return "success";
    case "cancelled":
    case "returned":
      return "danger";
    default:
      return "neutral";
  }
}

/* ================================================================================================================
 * Website (khách) — gọi thẳng, không cần đăng nhập
 * ============================================================================================================== */

export const storeOrdersApi = {
  quote: (body: { items: CartLine[]; payment_method?: "bank_transfer" | "cod" } & AddressFields) => api.post<Quote>("/api/store/orders/quote", body),
  checkout: (body: CheckoutInput) => api.post<PublicOrder>("/api/store/orders", body),
  lookup: (body: { phone: string; code: string }) => api.post<{ code: string; token: string }>("/api/store/orders/lookup", body),
  get: (code: string, t: string) => api.get<PublicOrder>(`/api/store/orders/${encodeURIComponent(code)}`, { query: { t } }),
  ask: (code: string, body: { t: string; message: string }) => api.post<PublicOrder>(`/api/store/orders/${encodeURIComponent(code)}/questions`, body),
  changeAddress: (code: string, body: { t: string; recipient_name?: string } & AddressFields) =>
    api.post<PublicOrder>(`/api/store/orders/${encodeURIComponent(code)}/address`, body),
  requestReturn: (code: string, body: { t: string; kind: ReturnKind; reason: ReturnReason; description?: string; order_item_index?: number | null }) =>
    api.post<PublicOrder>(`/api/store/orders/${encodeURIComponent(code)}/returns`, body),
  provinces: (q: string) => api.get<{ name: string; code: string | null }[]>("/api/store/orders/address-suggestions", { query: { q } }),
};

export const storeOrderKeys = {
  quote: (body: unknown) => ["store", "orders", "quote", body] as const,
  order: (code: string) => ["store", "orders", code] as const,
};

export function useQuote(body: { items: CartLine[]; payment_method?: "bank_transfer" | "cod" } & AddressFields, enabled = true) {
  return useQuery({
    queryKey: storeOrderKeys.quote(body),
    queryFn: () => storeOrdersApi.quote(body),
    enabled: enabled && body.items.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

/** Đơn của khách; đang chờ chuyển khoản thì tự hỏi lại mỗi 5 giây để thấy «đã nhận tiền». */
export function usePublicOrder(code: string, token: string | null) {
  return useQuery({
    queryKey: storeOrderKeys.order(code),
    queryFn: () => storeOrdersApi.get(code, token ?? ""),
    enabled: !!token,
    refetchInterval: (q) => (q.state.data?.status === "pending_payment" ? 5_000 : false),
    refetchIntervalInBackground: false,
  });
}

/* ================================================================================================================
 * Bàn làm việc (chị)
 * ============================================================================================================== */

const D = "/api/desk/orders";

export const ordersKeys = {
  all: ["desk", "orders"] as const,
  list: (q: object) => ["desk", "orders", "list", q] as const,
  counts: ["desk", "orders", "counts"] as const,
  detail: (id: string) => ["desk", "orders", "detail", id] as const,
  drops: ["desk", "orders", "drops"] as const,
  payments: (status?: string) => ["desk", "orders", "payments", status ?? "all"] as const,
  inventory: ["desk", "orders", "inventory"] as const,
  returns: ["desk", "orders", "returns"] as const,
  templates: ["desk", "orders", "templates"] as const,
  listings: ["desk", "orders", "listings"] as const,
  quotes: (id: string) => ["desk", "orders", "quotes", id] as const,
  labels: (ids: string[]) => ["desk", "orders", "labels", ids] as const,
};

export function useOrders(query: { nhom?: StatusGroup; q?: string; channel?: string; drop_id?: string; page?: number; size?: number }) {
  return useQuery({
    queryKey: ordersKeys.list(query),
    queryFn: () => api.get<Paginated<OrderListItem> & { page: number; pages: number }>(D, { query: { ...query, size: query.size ?? 30 } }),
    placeholderData: keepPreviousData,
  });
}

export function useOrderCounts() {
  return useQuery({ queryKey: ordersKeys.counts, queryFn: () => api.get<OrderCounts>(`${D}/counts`), refetchInterval: 60_000 });
}

export function useOrder(id: string) {
  return useQuery({ queryKey: ordersKeys.detail(id), queryFn: () => api.get<OrderDetail>(`${D}/${id}`) });
}

export function useDropOverviews() {
  return useQuery({ queryKey: ordersKeys.drops, queryFn: () => api.get<DropOverview[]>(`${D}/drops`) });
}

export function usePayments(status?: string) {
  return useQuery({ queryKey: ordersKeys.payments(status), queryFn: () => api.get<Paginated<PaymentRow>>(`${D}/payments`, { query: { status, size: 50 } }) });
}

export function useInventory() {
  return useQuery({ queryKey: ordersKeys.inventory, queryFn: () => api.get<InventoryRow[]>(`${D}/inventory`) });
}

export function useReturns() {
  return useQuery({ queryKey: ordersKeys.returns, queryFn: () => api.get<Paginated<ReturnRow>>(`${D}/returns`, { query: { size: 50 } }) });
}

export function useTemplates() {
  return useQuery({ queryKey: ordersKeys.templates, queryFn: () => api.get<Templates>(`${D}/templates`) });
}

export function useListings() {
  return useQuery({ queryKey: ordersKeys.listings, queryFn: () => api.get<Listing[]>(`${D}/marketplaces/listings`) });
}

export function useShippingQuotes(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ordersKeys.quotes(id),
    queryFn: () => api.get<{ options: ShippingOption[]; recommended: ShippingOption | null; reason: string }>(`${D}/${id}/shipping-quotes`),
    enabled,
    staleTime: 60_000,
  });
}

export function useLabels(ids: string[]) {
  return useQuery({ queryKey: ordersKeys.labels(ids), queryFn: () => api.get<LabelData[]>(`${D}/labels`, { query: { ids } }), enabled: ids.length > 0 });
}

function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ordersKeys.all }) });
}

export const useCreateOrder = () => useInvalidating((body: ManualOrderInput) => api.post<OrderDetail>(D, body));
export const usePatchOrder = (id: string) => useInvalidating((body: Partial<ManualOrderInput> & { recipient_name?: string; recipient_phone?: string }) => api.patch<OrderDetail>(`${D}/${id}`, body));
export const useCancelOrder = (id: string) => useInvalidating((body: { reason: string; notify_customer?: boolean }) => api.post<OrderDetail>(`${D}/${id}/cancel`, body));
export const useAddPayment = (id: string) => useInvalidating((body: { amount_vnd: number; method: "cash" | "bank_transfer"; note?: string }) => api.post<OrderDetail>(`${D}/${id}/payments`, body));
export const useConfirmDraft = (id: string) => useInvalidating((body: Record<string, unknown>) => api.post<OrderDetail>(`${D}/${id}/confirm-draft`, body));
export const useOpenReturn = (id: string) =>
  useInvalidating((body: { kind: ReturnKind; reason: ReturnReason; description?: string; order_item_id?: string | null }) => api.post<OrderDetail>(`${D}/${id}/returns`, body));
export const useCreateShipments = () =>
  useInvalidating((body: { order_ids: string[]; driver?: string; service?: string }) => api.post<{ results: ShipmentResult[] }>(`${D}/shipments`, body));
export const useSyncShipment = () => useInvalidating((id: string) => api.post<Shipment>(`${D}/shipments/${id}/sync`));
export const useCancelShipment = () => useInvalidating((id: string) => api.post<Shipment>(`${D}/shipments/${id}/cancel`));
export const useMatchPayment = () => useInvalidating(({ id, order_code }: { id: string; order_code: string }) => api.post<PaymentRow>(`${D}/payments/${id}/match`, { order_code }));
export const useIgnorePayment = () => useInvalidating((id: string) => api.post<PaymentRow>(`${D}/payments/${id}/ignore`));
export const useSimulateTransfer = () => useInvalidating((body: { amount_vnd: number; content: string }) => api.post<PaymentRow[]>(`${D}/payments/simulate`, body));
export const useReturnReceived = () => useInvalidating((id: string) => api.post<ReturnRecord>(`${D}/returns/${id}/received`));
export const useSaveTemplates = () => useInvalidating((templates: Record<string, string>) => api.put<Templates>(`${D}/templates`, { templates }));
export const useSyncProducts = () => useInvalidating((mk: string) => api.post<SyncResult>(`${D}/marketplaces/${mk}/sync-products`));
export const usePullOrders = () => useInvalidating((mk: string) => api.post<SyncResult>(`${D}/marketplaces/${mk}/pull-orders`));
export const useSimulateMarketplaceOrder = () =>
  useInvalidating(({ mk, product_id, quantity }: { mk: string; product_id: string; quantity: number }) => api.post<SyncResult>(`${D}/marketplaces/${mk}/simulate`, { product_id, quantity }));

export type SellableProduct = {
  product_id: string;
  name: string;
  slug: string;
  price_vnd: number;
  sale_mode: "drop" | "in_stock" | "both";
  image_url: string | null;
  stock_available: number | null;
  drops: { drop_id: string; code: string; status: string; price_vnd: number; available: number | null }[];
};

export function useSellable() {
  return useQuery({ queryKey: ["desk", "orders", "catalog"], queryFn: () => api.get<SellableProduct[]>(`${D}/catalog`) });
}
