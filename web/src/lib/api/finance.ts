"use client";

/** API sổ sách (backend `app/modules/finance`): sổ doanh thu/chi phí, chi phí, hoá đơn điện tử, báo cáo tuần, sao lưu. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, buildUrl, type Paginated } from "./client";

export type LedgerKind = "revenue" | "refund" | "cost_of_goods" | "shipping" | "payment_fee" | "marketplace_fee" | "expense" | "adjustment";
export type ExpenseCategory = "goods" | "samples" | "shipping" | "packaging" | "ads" | "ai" | "software" | "fees" | "tax" | "other";

export type LedgerEntry = {
  id: string;
  entry_date: string;
  kind: LedgerKind;
  direction: "in" | "out";
  amount_vnd: number;
  description: string;
  category: string | null;
  document_no: string | null;
  source: "auto" | "manual";
  order_id: string | null;
  expense_id: string | null;
  invoice_id: string | null;
  period: string;
  notes: string | null;
  created_at: string;
};

export type LedgerTotals = { revenue_vnd: number; refund_vnd: number; net_revenue_vnd: number; expense_vnd: number; entry_count: number };

export type LedgerSummary = {
  period: string;
  label: string;
  date_from: string;
  date_to: string;
  totals: LedgerTotals;
  by_month: (LedgerTotals & { period: string })[];
  expenses_by_category: { category: string; amount_vnd: number; count: number }[];
};

export type Expense = {
  id: string;
  incurred_on: string;
  category: ExpenseCategory;
  amount_vnd: number;
  description: string;
  vendor: string | null;
  receipt_storage_key: string | null;
  payment_method: string | null;
  is_deductible: boolean;
  created_at: string;
};

export type InvoiceStatus = "draft" | "issuing" | "issued" | "failed" | "cancelled" | "replaced";

export type Invoice = {
  id: string;
  order_id: string | null;
  reference: string;
  provider: string;
  status: InvoiceStatus;
  series: string | null;
  number: string | null;
  lookup_code: string | null;
  buyer_name: string;
  buyer_tax_code: string | null;
  buyer_address: string | null;
  buyer_email: string | null;
  lines: { name: string; quantity: number; unit_price_vnd: number; unit?: string }[];
  total_vnd: number;
  issued_at: string | null;
  raw: Record<string, unknown>;
  error: string | null;
  updated_at: string;
  approval_item_id: string | null;
  approval_status: string | null;
  approval_error: string | null;
};

export type InvoiceCandidate = { order_id: string; code: string; recipient_name: string; total_vnd: number; paid_at: string | null; invoice_status: InvoiceStatus | null };

export type ProductMargin = { product_id: string | null; name: string; orders: number; qty: number; revenue_vnd: number; cost_vnd: number | null; margin_pct: number | null };
export type TopPost = { scheduled_post_id: string; title: string; channel: string; orders: number; revenue_vnd: number; url: string | null };

export type WeeklyReport = {
  id: string;
  week_start: string;
  week_end: string;
  status: "generating" | "ready" | "failed";
  revenue_vnd: number;
  cogs_vnd: number;
  gross_profit_vnd: number;
  expenses_vnd: number;
  order_count: number;
  customer_count: number;
  returning_customer_count: number;
  ai_cost_vnd: number;
  product_margins: ProductMargin[];
  top_posts: TopPost[];
  metrics: {
    gross_margin_pct?: number | null;
    returning_order_pct?: number | null;
    cogs_missing_items?: number;
    review_minutes?: number;
    review_decisions?: number;
    iso_week?: number;
    insight_status?: string;
    insight_error?: string;
  } & Record<string, unknown>;
  summary: string | null;
  highlights: string[];
  generated_at: string | null;
};

export type Backup = {
  id: string;
  kind: string;
  status: "running" | "succeeded" | "failed";
  trigger: "schedule" | "manual";
  storage_key: string | null;
  size_bytes: number | null;
  checksum: string | null;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  offsite_driver: string | null;
  offsite_key: string | null;
  offsite_at: string | null;
  offsite_error: string | null;
  verified_at: string | null;
  verify_ok: boolean | null;
  verify_note: string | null;
};

export type BackupConfig = {
  pg_dump: string | null;
  keep: number;
  schedule: string;
  last_success_at: string | null;
  last_success_id: string | null;
  /** lỗi của lần hỏng gần nhất (chỉ khi xảy ra sau lần thành công cuối) */
  last_error: string | null;
  last_error_at: string | null;
  storage_driver: string;
  /** kho ngoài máy chủ; null = chưa cấu hình */
  offsite_driver: string | null;
  last_offsite_at: string | null;
  offsite_error: string | null;
};

export const EXPENSE_CATEGORY_LABELS: Record<ExpenseCategory, string> = {
  goods: "Mua hàng",
  samples: "Mua mẫu",
  shipping: "Vận chuyển",
  packaging: "Đóng gói",
  ads: "Quảng cáo",
  ai: "Chi phí AI",
  software: "Phần mềm",
  fees: "Phí, lệ phí",
  tax: "Thuế",
  other: "Khác",
};

export const LEDGER_KIND_LABELS: Record<LedgerKind, string> = {
  revenue: "Doanh thu",
  refund: "Hoàn tiền",
  cost_of_goods: "Giá vốn",
  shipping: "Vận chuyển",
  payment_fee: "Phí thanh toán",
  marketplace_fee: "Phí sàn",
  expense: "Chi phí",
  adjustment: "Điều chỉnh",
};

const BASE = "/api/desk/finance";

export const financeKeys = {
  all: ["finance"] as const,
  summary: (period: string) => ["finance", "summary", period] as const,
  ledger: (q: object) => ["finance", "ledger", q] as const,
  expenses: (q: object) => ["finance", "expenses", q] as const,
  invoices: (q: object) => ["finance", "invoices", q] as const,
  candidates: () => ["finance", "invoice-candidates"] as const,
  reports: () => ["finance", "reports"] as const,
  backups: () => ["finance", "backups"] as const,
  backupConfig: () => ["finance", "backup-config"] as const,
};

/* ---------- sổ (k1) ---------- */

export function useLedgerSummary(period: string) {
  return useQuery({
    queryKey: financeKeys.summary(period),
    queryFn: () => api.get<LedgerSummary>(`${BASE}/ledger/summary`, { query: { period } }),
    placeholderData: keepPreviousData,
  });
}

export function useLedger(query: { period: string; kind?: LedgerKind; page?: number }) {
  return useQuery({
    queryKey: financeKeys.ledger(query),
    queryFn: () => api.get<Paginated<LedgerEntry>>(`${BASE}/ledger`, { query: { ...query, size: 30 } }),
    placeholderData: keepPreviousData,
  });
}

/** Đường dẫn tải bảng kê CSV (cùng origin, cookie đi kèm). */
export function ledgerExportUrl(period: string): string {
  return buildUrl(`${BASE}/ledger/export.csv`, { period });
}

/* ---------- chi phí ---------- */

export function useExpenses(query: { period: string; page?: number }) {
  return useQuery({
    queryKey: financeKeys.expenses(query),
    queryFn: () => api.get<Paginated<Expense>>(`${BASE}/expenses`, { query: { ...query, size: 30 } }),
    placeholderData: keepPreviousData,
  });
}

export type ExpenseInput = {
  incurred_on: string;
  category: ExpenseCategory;
  amount_vnd: number;
  description: string;
  vendor?: string;
  receipt?: File | null;
};

export function useCreateExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ExpenseInput) => {
      const fd = new FormData();
      fd.set("incurred_on", input.incurred_on);
      fd.set("category", input.category);
      fd.set("amount_vnd", String(input.amount_vnd));
      fd.set("description", input.description);
      if (input.vendor) fd.set("vendor", input.vendor);
      if (input.receipt) fd.set("receipt", input.receipt);
      return api.post<Expense>(`${BASE}/expenses`, fd);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: financeKeys.all }),
  });
}

export function useDeleteExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`${BASE}/expenses/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: financeKeys.all }),
  });
}

/** Ảnh chứng từ: khoá `private/...` phục vụ qua /api/files (cần đăng nhập). */
export function fileUrl(key: string): string {
  return `/api/files/${key}`;
}

/* ---------- hoá đơn (k5) ---------- */

export function useInvoices(query: { status?: InvoiceStatus; page?: number } = {}) {
  return useQuery({
    queryKey: financeKeys.invoices(query),
    queryFn: () => api.get<Paginated<Invoice>>(`${BASE}/invoices`, { query: { ...query, size: 30 } }),
  });
}

export function useInvoiceCandidates() {
  return useQuery({ queryKey: financeKeys.candidates(), queryFn: () => api.get<InvoiceCandidate[]>(`${BASE}/invoices/candidates`) });
}

export type InvoiceProposeResult = { invoice: Invoice; outcome: "applied" | "pending" | "blocked" | "failed"; approval_item_id: string | null; error: string | null };

export function usePrepareInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { order_id: string; buyer_name?: string; buyer_tax_code?: string; buyer_email?: string; buyer_address?: string }) =>
      api.post<InvoiceProposeResult>(`${BASE}/invoices`, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: financeKeys.all });
      void qc.invalidateQueries({ queryKey: ["control"] });
    },
  });
}

/* ---------- báo cáo tuần (i5) ---------- */

export function useReports() {
  return useQuery({
    queryKey: financeKeys.reports(),
    queryFn: () => api.get<Paginated<WeeklyReport>>(`${BASE}/reports`, { query: { size: 26 } }),
  });
}

export function useGenerateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (week_start?: string) => api.post<WeeklyReport>(`${BASE}/reports/generate`, { week_start: week_start ?? null }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: financeKeys.reports() });
      void qc.invalidateQueries({ queryKey: ["control"] });
    },
  });
}

/* ---------- sao lưu (k4) ---------- */

export function useBackups(enabled: boolean) {
  return useQuery({
    queryKey: financeKeys.backups(),
    queryFn: () => api.get<Paginated<Backup>>(`${BASE}/backups`, { query: { size: 30 } }),
    enabled,
  });
}

export function useBackupConfig(enabled: boolean) {
  return useQuery({ queryKey: financeKeys.backupConfig(), queryFn: () => api.get<BackupConfig>(`${BASE}/backups/config`), enabled });
}

export function useRunBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Backup>(`${BASE}/backups`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: financeKeys.backups() });
      void qc.invalidateQueries({ queryKey: financeKeys.backupConfig() });
    },
  });
}

export function useVerifyBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Backup>(`${BASE}/backups/${id}/verify`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: financeKeys.backups() }),
  });
}

export function backupDownloadUrl(id: string): string {
  return `${BASE}/backups/${id}/download`;
}
