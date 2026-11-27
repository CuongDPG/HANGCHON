"use client";

import { Download, FileText, Paperclip, Plus, Receipt, RotateCw, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { ApprovalSheet } from "@/components/control/approval-sheet";
import {
  Badge,
  Button,
  Card,
  DateTime,
  EmptyState,
  IconButton,
  InlineSelect,
  Money,
  PageHeader,
  SectionLabel,
  SkeletonList,
  StatTile,
  Toolbar,
  buttonClasses,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import {
  EXPENSE_CATEGORY_LABELS,
  LEDGER_KIND_LABELS,
  fileUrl,
  ledgerExportUrl,
  useDeleteExpense,
  useExpenses,
  useInvoiceCandidates,
  useInvoices,
  useLedger,
  useLedgerSummary,
  type ExpenseCategory,
  type InvoiceCandidate,
  type InvoiceStatus,
  type LedgerEntry,
} from "@/lib/api/finance";
import { formatDate, formatVndCompact } from "@/lib/format";
import { BOOKS_SECTIONS } from "@/lib/desk-sections";
import { useUrlParam } from "@/lib/use-url-param";
import { ExpenseSheet } from "./expense-sheet";
import { InvoiceSheet } from "./invoice-sheet";
import { periodOptions } from "./period";

type Tab = "so" | "chi-phi" | "hoa-don";

/** Sổ sách (k1, k5): sổ doanh thu/chi phí theo kỳ + bảng kê CSV, chi phí nhập tay, hoá đơn điện tử. */
const noopSubscribe = () => () => {};

export function BooksScreen() {
  const params = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = raw === "chi-phi" || raw === "hoa-don" ? raw : "so";
  const periods = periodOptions();
  const [period, setPeriod] = useUrlParam<string>("ky", periods[0].value, periods.map((p) => p.value));
  const { user } = useSession();
  // lúc hydrate dùng đúng như máy chủ (chưa biết phiên), tránh lệch HTML khi phiên về trước khi khối này hydrate
  const hydrated = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const owner = hydrated && isOwner(user);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        sections={BOOKS_SECTIONS}
        active={tab}
        actions={
          tab === "so" && owner ? (
            <a href={ledgerExportUrl(period)} download className={buttonClasses({ variant: "secondary", size: "sm" })}>
              <Download className="size-4" aria-hidden />
              Tải CSV
            </a>
          ) : null
        }
      />
      {tab !== "hoa-don" ? <Toolbar end={<InlineSelect aria-label="Kỳ" appearance="inline" value={period} onChange={setPeriod} options={periods} />} /> : null}
      {tab === "so" ? <LedgerTab key={period} period={period} /> : tab === "chi-phi" ? <ExpensesTab key={period} period={period} /> : <InvoicesTab />}
    </div>
  );
}

function ErrorBlock({ message, retry }: { message: string; retry: () => void }) {
  return (
    <EmptyState
      tone="error"
      title="Chưa tải được"
      description={message}
      action={
        <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={retry}>
          Thử lại
        </Button>
      }
    />
  );
}

/* ---------- sổ ---------- */

function LedgerTab({ period }: { period: string }) {
  const [page, setPage] = useState(1);
  const summary = useLedgerSummary(period);
  const ledger = useLedger({ period, page });
  const t = summary.data?.totals;
  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        <StatTile value={t ? formatVndCompact(t.net_revenue_vnd) : "…"} label="doanh thu thuần" hint={t?.refund_vnd ? `đã trừ ${formatVndCompact(t.refund_vnd)} hoàn` : undefined} />
        <StatTile value={t ? formatVndCompact(t.expense_vnd) : "…"} label="chi phí" />
        <StatTile value={t ? formatVndCompact(t.net_revenue_vnd - t.expense_vnd) : "…"} label="còn lại" />
      </div>
      {summary.data && summary.data.by_month.length > 1 ? (
        <Card flush className="px-4 py-2">
          <ul className="divide-y divide-line text-[14px]">
            {summary.data.by_month.map((m) => (
              <li key={m.period} className="flex items-baseline justify-between gap-3 py-2">
                <span className="text-ink-2">Tháng {Number(m.period.slice(5))}/{m.period.slice(0, 4)}</span>
                <span className="tabular-nums">
                  +{formatVndCompact(m.net_revenue_vnd)} · −{formatVndCompact(m.expense_vnd)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      <SectionLabel>{summary.data?.label ?? "Các dòng sổ"}</SectionLabel>
      {ledger.isPending ? (
        <SkeletonList rows={4} />
      ) : ledger.error ? (
        <ErrorBlock message={ledger.error.message} retry={() => ledger.refetch()} />
      ) : !ledger.data.items.length ? (
        <EmptyState
          icon={<FileText />}
          title="Kỳ này chưa có dòng sổ nào"
          description="Đơn đã thanh toán tự vào sổ doanh thu; chi phí chị ghi ở thẻ Chi phí."
        />
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
            {ledger.data.items.map((e) => (
              <LedgerRow key={e.id} e={e} />
            ))}
          </ul>
          <Pager page={ledger.data.page} pages={ledger.data.pages} onPage={setPage} />
        </>
      )}
    </>
  );
}

function LedgerRow({ e }: { e: LedgerEntry }) {
  const inflow = e.direction === "in";
  const cat = e.category && e.category in EXPENSE_CATEGORY_LABELS ? EXPENSE_CATEGORY_LABELS[e.category as ExpenseCategory] : null;
  return (
    <li className="flex items-start justify-between gap-3 p-3.5">
      <div className="min-w-0">
        <p className="text-[15px] leading-snug [overflow-wrap:anywhere]">{e.description}</p>
        <p className="mt-0.5 text-[13px] text-ink-2">
          {formatDate(e.entry_date)} · {LEDGER_KIND_LABELS[e.kind]}
          {e.kind === "expense" && cat ? ` · ${cat}` : ""}
          {e.document_no && !e.description.includes(e.document_no) ? ` · ${e.document_no}` : ""}
          {e.source === "manual" ? " · nhập tay" : ""}
        </p>
        {e.notes ? <p className="text-[12.5px] text-ink-3">{e.notes}</p> : null}
      </div>
      <span className={inflow ? "shrink-0 font-semibold text-auto tabular-nums" : "shrink-0 font-semibold tabular-nums"}>
        {inflow ? "+" : "−"}
        <Money value={e.amount_vnd} />
      </span>
    </li>
  );
}

/* ---------- chi phí ---------- */

function ExpensesTab({ period }: { period: string }) {
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const list = useExpenses({ period, page });
  const summary = useLedgerSummary(period);
  const del = useDeleteExpense();
  const confirm = useConfirm();
  const { user } = useSession();
  const owner = isOwner(user);

  async function remove(id: string, description: string) {
    const ok = await confirm({ title: "Xoá khoản chi này?", message: `«${description}» sẽ bị gỡ khỏi sổ.`, confirmLabel: "Xoá", tone: "danger" });
    if (!ok) return;
    await del.mutateAsync(id);
    notifySuccess("Đã xoá khoản chi");
  }

  return (
    <>
      <Button icon={<Plus className="size-4" />} onClick={() => setAdding(true)} className="self-start">
        Ghi khoản chi
      </Button>
      {summary.data?.expenses_by_category.length ? (
        <Card flush className="px-4 py-2">
          <ul className="divide-y divide-line text-[14px]">
            {summary.data.expenses_by_category.map((c) => (
              <li key={c.category} className="flex items-baseline justify-between gap-3 py-2">
                <span className="text-ink-2">
                  {EXPENSE_CATEGORY_LABELS[c.category as ExpenseCategory] ?? c.category} · {c.count}
                </span>
                <Money value={c.amount_vnd} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {list.isPending ? (
        <SkeletonList rows={3} />
      ) : list.error ? (
        <ErrorBlock message={list.error.message} retry={() => list.refetch()} />
      ) : !list.data.items.length ? (
        <EmptyState icon={<Receipt />} title="Kỳ này chưa ghi khoản chi nào" description="Ghi tiền mua mẫu, đóng gói, cước giao, quảng cáo… kèm ảnh chứng từ." />
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
            {list.data.items.map((x) => (
              <li key={x.id} className="flex items-start gap-3 p-3.5">
                <div className="min-w-0 flex-1">
                  <p className="text-[15px] leading-snug [overflow-wrap:anywhere]">{x.description}</p>
                  <p className="mt-0.5 text-[13px] text-ink-2">
                    {formatDate(x.incurred_on)} · {EXPENSE_CATEGORY_LABELS[x.category]}
                    {x.vendor ? ` · ${x.vendor}` : ""}
                  </p>
                  {x.receipt_storage_key ? (
                    <a href={fileUrl(x.receipt_storage_key)} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-[13px] font-semibold text-accent">
                      <Paperclip className="size-3.5" aria-hidden /> Xem chứng từ
                    </a>
                  ) : (
                    <p className="mt-1 text-[12.5px] text-ink-3">Chưa có ảnh chứng từ</p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="font-semibold tabular-nums">
                    <Money value={x.amount_vnd} />
                  </span>
                  {owner ? <IconButton label="Xoá khoản chi" icon={<Trash2 />} size="sm" onClick={() => remove(x.id, x.description)} /> : null}
                </div>
              </li>
            ))}
          </ul>
          <Pager page={list.data.page} pages={list.data.pages} onPage={setPage} />
        </>
      )}
      <ExpenseSheet open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

/* ---------- hoá đơn ---------- */

const INVOICE_STATUS: Record<InvoiceStatus, { label: string; tone: "neutral" | "success" | "warning" | "danger" | "outline" }> = {
  draft: { label: "Nháp", tone: "neutral" },
  issuing: { label: "Đang phát hành", tone: "warning" },
  issued: { label: "Đã phát hành", tone: "success" },
  failed: { label: "Lỗi", tone: "danger" },
  cancelled: { label: "Đã huỷ", tone: "outline" },
  replaced: { label: "Đã thay thế", tone: "outline" },
};

function InvoicesTab() {
  const candidates = useInvoiceCandidates();
  const invoices = useInvoices();
  const { user } = useSession();
  const owner = isOwner(user);
  const [order, setOrder] = useState<InvoiceCandidate | null>(null);
  const [approvalId, setApprovalId] = useState<string | null>(null);

  return (
    <>
      <section className="flex flex-col gap-2" aria-label="Đơn chờ xuất hoá đơn">
        <SectionLabel>Đơn đã thanh toán, chưa có hoá đơn</SectionLabel>
        {candidates.isPending ? (
          <SkeletonList rows={2} />
        ) : candidates.error ? (
          <ErrorBlock message={candidates.error.message} retry={() => candidates.refetch()} />
        ) : !candidates.data.length ? (
          <p className="text-[14px] text-ink-2">Không có đơn nào đang chờ xuất hoá đơn.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
            {candidates.data.map((c) => (
              <li key={c.order_id} className="flex items-center gap-3 p-3.5">
                <div className="min-w-0 flex-1">
                  <p className="text-[15px] font-semibold">{c.code}</p>
                  <p className="text-[13px] text-ink-2">
                    {c.recipient_name}
                    {c.paid_at ? (
                      <>
                        {" "}
                        · trả <DateTime value={c.paid_at} format="relative" />
                      </>
                    ) : null}
                    {c.invoice_status ? ` · ${INVOICE_STATUS[c.invoice_status].label.toLowerCase()}` : ""}
                  </p>
                </div>
                <span className="shrink-0 text-[15px] tabular-nums">
                  <Money value={c.total_vnd} />
                </span>
                {owner ? (
                  <Button size="sm" variant="secondary" onClick={() => setOrder(c)}>
                    Soạn
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-2" aria-label="Hoá đơn đã soạn">
        <SectionLabel>Hoá đơn</SectionLabel>
        {invoices.isPending ? (
          <SkeletonList rows={2} />
        ) : invoices.error ? (
          <ErrorBlock message={invoices.error.message} retry={() => invoices.refetch()} />
        ) : !invoices.data.items.length ? (
          <EmptyState icon={<FileText />} title="Chưa có hoá đơn nào" description="Soạn hoá đơn cho đơn đã thanh toán; chị duyệt rồi mới phát hành." />
        ) : (
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
            {invoices.data.items.map((inv) => {
              const waiting = inv.status === "draft" && inv.approval_status === "pending";
              const failed = inv.approval_status === "failed";
              const st = failed && inv.status === "draft" ? INVOICE_STATUS.failed : INVOICE_STATUS[inv.status];
              const pdf = typeof inv.raw.pdf_url === "string" ? inv.raw.pdf_url : null;
              return (
                <li key={inv.id} className="flex flex-col gap-1 p-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[15px] font-semibold">
                        {inv.number ? `${inv.series}-${inv.number}` : `Đơn ${inv.reference}`}
                      </p>
                      <p className="text-[13px] text-ink-2 [overflow-wrap:anywhere]">
                        {inv.buyer_name}
                        {inv.buyer_tax_code ? ` · MST ${inv.buyer_tax_code}` : ""} · đơn {inv.reference}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Money value={inv.total_vnd} />
                      <Badge tone={waiting ? "warning" : st.tone}>{waiting ? "Chờ duyệt" : st.label}</Badge>
                    </div>
                  </div>
                  {inv.lookup_code ? <p className="text-[13px] text-ink-2">Mã tra cứu: {inv.lookup_code}</p> : null}
                  {failed && inv.approval_error ? <p className="text-[13px] text-seal">{inv.approval_error}</p> : null}
                  <div className="flex flex-wrap gap-3 text-[14px] font-semibold">
                    {(waiting || failed) && inv.approval_item_id ? (
                      <button type="button" className="text-accent" onClick={() => setApprovalId(inv.approval_item_id)}>
                        {failed ? "Duyệt lại →" : "Xem và duyệt →"}
                      </button>
                    ) : null}
                    {pdf ? (
                      <a href={pdf} target="_blank" rel="noreferrer" className="text-accent">
                        Bản PDF →
                      </a>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <InvoiceSheet order={order} onClose={() => setOrder(null)} onPending={setApprovalId} />
      <ApprovalSheet itemId={approvalId} open={!!approvalId} onClose={() => setApprovalId(null)} />
    </>
  );
}

function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <nav aria-label="Trang" className="flex items-center justify-between gap-3">
      <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Trước
      </Button>
      <span className="text-[13px] text-ink-2">
        Trang {page}/{pages}
      </span>
      <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Sau →
      </Button>
    </nav>
  );
}
