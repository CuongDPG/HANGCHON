"use client";

import { Download, RefreshCw, Upload } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DateTime,
  EmptyState,
  Input,
  InlineSelect,
  LevelTag,
  Money,
  notifySuccess,
  PageHeader,
  SkeletonList,
  Textarea,
} from "@/components/ui";
import {
  RETURN_KIND_LABELS,
  RETURN_REASON_LABELS,
  RETURN_STATUS_LABELS,
  useIgnorePayment,
  useListings,
  useMatchPayment,
  useOrderCounts,
  usePayments,
  usePullOrders,
  useReturnReceived,
  useReturns,
  useSaveTemplates,
  useSellable,
  useSimulateMarketplaceOrder,
  useSimulateTransfer,
  useSyncProducts,
  useTemplates,
  type FailedNotification,
  type NotifyChannel,
  type PaymentRow,
} from "@/lib/api/orders";
import { ORDER_SETTINGS, orderSections } from "@/lib/desk-sections";
import { InventoryTab } from "./inventory-tab";

type Tab = "tien" | "doi-tra" | "ton" | "san" | "mau-tin";

/**
 * Vận hành đơn hàng — bốn mục tầng 1 của khu Đơn hàng (?tab=): khoản tiền cần xem (g2), đổi trả (g7), tồn kho nhỏ (g8), sàn (g9);
 * mẫu tin (g5) là trang cấu hình (nút bánh răng).
 */
export function OperationsScreen() {
  const params = useSearchParams();
  const c = useOrderCounts().data;
  const raw = params.get("tab");
  const tab: Tab = raw === "doi-tra" || raw === "ton" || raw === "san" || raw === "mau-tin" ? raw : "tien";
  return (
    <div className="flex flex-col gap-4">
      {tab === "mau-tin" ? (
        <PageHeader title="Mẫu tin" backHref="/desk/don-hang" />
      ) : (
        <PageHeader sections={orderSections(c)} active={tab} settings={ORDER_SETTINGS} />
      )}
      {tab === "tien" ? <PaymentsTab /> : tab === "doi-tra" ? <ReturnsTab /> : tab === "ton" ? <InventoryTab /> : tab === "san" ? <MarketplaceTab /> : <TemplatesTab />}
    </div>
  );
}

function PaymentsTab() {
  const review = usePayments("needs_review");
  const recent = usePayments();
  const sim = useSimulateTransfer();
  const [amount, setAmount] = useState("");
  const [content, setContent] = useState("");
  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-2">
        <h2 className="flex items-center gap-2 font-sans text-[15px] font-semibold">
          Cần chị xem <LevelTag level="review" />
        </h2>
        {review.isPending ? (
          <SkeletonList rows={2} />
        ) : review.isError ? (
          <EmptyState tone="error" title="Chưa tải được" description={review.error.message} />
        ) : review.data.items.length === 0 ? (
          <p className="text-[14px] text-ink-2">Không có khoản nào lệch. Tiền chuyển đúng nội dung được khớp tự động.</p>
        ) : (
          review.data.items.map((p) => <ReviewRow key={p.id} p={p} />)
        )}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-sans text-[15px] font-semibold">Tiền vào gần đây</h2>
        {recent.data?.items.length ? (
          <Card flush>
            <ul className="divide-y divide-line">
              {recent.data.items.slice(0, 20).map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2 text-[14px]">
                  <span className="min-w-0">
                    <span className="block truncate">{p.content || "(không nội dung)"}</span>
                    <span className="text-[12.5px] text-ink-2">
                      <DateTime value={p.received_at} format="dateTime" /> · {p.order_code ?? "chưa khớp"} · {PROVIDER[p.provider] ?? "Chuyển khoản"}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-0.5">
                    <Money value={p.direction === "out" ? -p.amount_vnd : p.amount_vnd} className="font-semibold" />
                    <Badge tone={p.status === "matched" ? "success" : p.status === "needs_review" ? "warning" : "neutral"}>{STATUS[p.status] ?? p.status}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        ) : (
          <p className="text-[14px] text-ink-2">Chưa có khoản nào.</p>
        )}
      </section>
      <Card tone="soft" className="flex flex-col gap-3">
        <CardHeader title="Chạy thử: giả lập khách chuyển khoản" aside={<Badge tone="outline">chỉ khi dùng thanh toán giả</Badge>} />
        <div className="grid grid-cols-1 gap-2 md:grid-cols-[10rem_1fr_auto]">
          <Input aria-label="Số tiền" placeholder="Số tiền" inputMode="numeric" trailing="đ" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <Input aria-label="Nội dung chuyển khoản" placeholder="Nội dung, vd HC 48213" value={content} onChange={(e) => setContent(e.target.value)} />
          <Button
            variant="secondary"
            loading={sim.isPending}
            disabled={!amount}
            onClick={() => sim.mutate({ amount_vnd: Number(amount.replace(/\D/g, "")), content }, { onSuccess: (r) => notifySuccess(r[0]?.order_code ? `Đã khớp vào ${r[0].order_code}` : "Đã nhận, chưa khớp đơn") })}
          >
            Gửi
          </Button>
        </div>
      </Card>
    </div>
  );
}

/** Nguồn tiền vào, gọi bằng lời thường (không lộ tên tích hợp như «mock», «sepay»). */
const PROVIDER: Record<string, string> = {
  manual: "Chị ghi tay",
  cod: "Thu hộ khi giao",
  tiktok_shop: "TikTok Shop",
  shopee: "Shopee",
};

const STATUS: Record<string, string> = { matched: "Đã khớp", needs_review: "Cần xem", ignored: "Bỏ qua", received: "Mới về", refunded: "Hoàn", failed: "Lỗi" };

function ReviewRow({ p }: { p: PaymentRow }) {
  const match = useMatchPayment();
  const ignore = useIgnorePayment();
  const [code, setCode] = useState(p.order_code ?? "");
  return (
    <Card tone="danger" className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <Money value={p.amount_vnd} className="text-[18px] font-bold" />
        <DateTime value={p.received_at} format="dateTime" className="text-[13px] text-ink-2" />
      </div>
      <p className="text-[14px]">
        Nội dung: <b>{p.content || "(trống)"}</b>
        {p.payer_name ? ` · ${p.payer_name}` : ""}
      </p>
      {p.order_code ? (
        <p className="text-[13px] text-ink-2">
          Đang gắn với <Link href={`/desk/don-hang?q=${encodeURIComponent(p.order_code)}`} className="text-accent">{p.order_code}</Link> (thiếu/thừa tiền hoặc đơn đã huỷ)
        </p>
      ) : null}
      <div className="flex flex-wrap items-end gap-2">
        <Input wrapperClassName="w-36" aria-label="Mã đơn" placeholder="HC-48213" value={code} onChange={(e) => setCode(e.target.value)} />
        <Button size="sm" disabled={code.trim().length < 3} loading={match.isPending} onClick={() => match.mutate({ id: p.id, order_code: code }, { onSuccess: () => notifySuccess("Đã khớp") })}>
          {p.order_code && code === p.order_code ? "Nhận đủ, xác nhận đơn" : "Khớp vào đơn"}
        </Button>
        {!p.order_code ? (
          <Button size="sm" variant="ghost" loading={ignore.isPending} onClick={() => ignore.mutate(p.id)}>
            Không phải tiền đơn
          </Button>
        ) : null}
      </div>
      <p className="text-[12.5px] text-ink-2">Việc này cũng có ở «Chờ duyệt» kèm đề xuất của AI.</p>
    </Card>
  );
}

function ReturnsTab() {
  const q = useReturns();
  const received = useReturnReceived();
  if (q.isPending) return <SkeletonList rows={2} />;
  if (q.isError) return <EmptyState tone="error" title="Chưa tải được" description={q.error.message} />;
  if (!q.data.items.length) return <EmptyState title="Không có yêu cầu đổi trả nào đang mở" description="Khách gửi từ trang theo dõi đơn, hoặc chị mở trong chi tiết đơn." />;
  return (
    <div className="flex flex-col gap-2">
      {q.data.items.map((r) => (
        <Card key={r.id} className="flex flex-col gap-1.5 text-[14px]">
          <div className="flex items-center justify-between gap-2">
            <Link href={`/desk/don-hang/${r.order_id}`} className="font-semibold">
              {r.code} · {r.order_code} · {r.recipient_name}
            </Link>
            <Badge tone={r.status === "pending_decision" ? "warning" : "neutral"}>{RETURN_STATUS_LABELS[r.status]}</Badge>
          </div>
          <p className="text-ink-2">
            {RETURN_KIND_LABELS[r.kind]} · {RETURN_REASON_LABELS[r.reason]}
            {r.description ? ` · «${r.description}»` : ""}
          </p>
          {r.eligibility.summary ? <p>{r.eligibility.summary}</p> : null}
          {r.status === "pending_decision" ? (
            <Link href="/desk/duyet" className="text-accent">
              Quyết ở hàng chờ duyệt →
            </Link>
          ) : r.status === "awaiting_item" ? (
            <Button size="sm" className="self-start" loading={received.isPending} onClick={() => received.mutate(r.id)}>
              Đã nhận lại hàng · hoàn <Money value={r.refund_amount_vnd} />
            </Button>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

function MarketplaceTab() {
  const listings = useListings();
  const sync = useSyncProducts();
  const pull = usePullOrders();
  const sim = useSimulateMarketplaceOrder();
  const sellable = useSellable();
  const stock = (sellable.data ?? []).filter((p) => p.stock_available !== null);
  const [simProduct, setSimProduct] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-4">
      {(["shopee", "tiktok_shop"] as const).map((mk) => {
        const rows = (listings.data ?? []).filter((l) => l.marketplace === mk);
        return (
          <Card key={mk} className="flex flex-col gap-3">
            <CardHeader title={mk === "shopee" ? "Shopee" : "TikTok Shop"} aside={<LevelTag level="auto" />} />
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" icon={<Upload className="size-4" />} loading={sync.isPending && sync.variables === mk} onClick={() => sync.mutate(mk, { onSuccess: (r) => notifySuccess(`Đã đồng bộ ${r.synced} món${r.errors.length ? `, ${r.errors.length} lỗi` : ""}`) })}>
                Đẩy món + tồn lên sàn
              </Button>
              <Button size="sm" variant="secondary" icon={<Download className="size-4" />} loading={pull.isPending && pull.variables === mk} onClick={() => pull.mutate(mk, { onSuccess: (r) => notifySuccess(`Kéo về ${r.created_orders} đơn mới`) })}>
                Kéo đơn về
              </Button>
            </div>
            {rows.length ? (
              <ul className="flex flex-col gap-1 text-[14px]">
                {rows.map((l) => (
                  <li key={l.id} className="flex justify-between gap-2">
                    <span className="min-w-0 truncate">{l.product_name}</span>
                    <span className="shrink-0 text-ink-2">
                      tồn {l.synced_stock ?? "—"} · {l.status === "error" ? <span className="text-seal">{l.error}</span> : l.status === "active" ? "đang bán" : "tạm ẩn"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[14px] text-ink-2">Chưa đẩy món nào lên sàn này.</p>
            )}
            {stock.length ? (
              <div className="flex flex-wrap items-end gap-2 border-t border-line pt-3">
                <InlineSelect className="min-w-48 flex-1" label="Chạy thử: giả lập khách đặt trên sàn" value={simProduct} placeholder="Chọn món" onChange={setSimProduct} options={stock.map((p) => ({ value: p.product_id, label: p.name }))} />
                <Button size="sm" variant="ghost" icon={<RefreshCw className="size-4" />} disabled={!simProduct} loading={sim.isPending} onClick={() => simProduct && sim.mutate({ mk, product_id: simProduct, quantity: 1 }, { onSuccess: (r) => notifySuccess(`Kéo về ${r.created_orders} đơn`) })}>
                  Giả lập đơn
                </Button>
              </div>
            ) : null}
          </Card>
        );
      })}
      <p className="text-[13px] text-ink-2">Đơn sàn vào chung danh sách đơn, không sinh trùng. Tự kéo đơn mỗi 30 phút.</p>
    </div>
  );
}

function TemplatesTab() {
  const q = useTemplates();
  const save = useSaveTemplates();
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  if (q.isPending) return <SkeletonList rows={3} />;
  if (q.isError) return <EmptyState tone="error" title="Chưa tải được" description={q.error.message} />;
  const values = draft ?? q.data.templates;
  return (
    <div className="flex flex-col gap-3">
      <DeliveryStatus channels={q.data.channels} failed={q.data.failed} />
      <p className="text-[14px] text-ink-2">
        Mỗi mốc gửi khách một tin, không gửi trùng. Chèn thông tin bằng ngoặc nhọn, vd <code>{"{ma_don}"}</code>.
      </p>
      {Object.keys(q.data.defaults).map((k) => (
        <Textarea
          key={k}
          label={q.data.labels[k] ?? k}
          rows={3}
          value={values[k] ?? ""}
          onChange={(e) => setDraft({ ...values, [k]: e.target.value })}
          hint={values[k] === q.data.defaults[k] ? "Câu mặc định" : "Chị đã sửa — xoá trắng để dùng lại câu mặc định"}
        />
      ))}
      <details className="text-[13px] text-ink-2">
        <summary className="cursor-pointer text-accent">Các ô chèn được</summary>
        <ul className="mt-2 grid gap-1 md:grid-cols-2">
          {Object.entries(q.data.placeholders).map(([k, v]) => (
            <li key={k}>
              <code className="text-ink">{`{${k}}`}</code> — {v}
            </li>
          ))}
        </ul>
      </details>
      <Button className="self-end" disabled={!draft} loading={save.isPending} onClick={() => draft && save.mutate(draft, { onSuccess: () => (setDraft(null), notifySuccess("Đã lưu mẫu tin")) })}>
        Lưu mẫu tin
      </Button>
    </div>
  );
}

/** g5: kênh báo tin đang bật (chính / dự phòng, đủ cấu hình chưa) và các tin gửi lỗi gần đây. */
function DeliveryStatus({ channels, failed }: { channels: NotifyChannel[]; failed: FailedNotification[] }) {
  return (
    <Card className="flex flex-col gap-3">
      <CardHeader title="Kênh báo tin" />
      <ul className="flex flex-col gap-2">
        {channels.map((c) => (
          <li key={c.channel} className="flex flex-col gap-0.5">
            <div className="flex flex-wrap items-center gap-2 text-[14px]">
              <b>{c.label}</b>
              <Badge tone="outline">{c.role === "primary" ? "kênh chính" : "dự phòng"}</Badge>
              <Badge tone={c.ready ? "success" : "warning"}>{c.ready ? `đang gửi qua ${c.driver}` : c.driver}</Badge>
            </div>
            {c.note ? <p className="text-[13px] text-ink-2">{c.note}</p> : null}
          </li>
        ))}
      </ul>
      <p className="text-[12.5px] text-ink-2">Đổi kênh chính / dự phòng trong Cài đặt (nhóm Đơn hàng); nhà cung cấp gửi tin do người vận hành cấu hình.</p>
      {failed.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="font-sans text-[14px] font-semibold">Tin gửi lỗi gần đây</h3>
          <ul className="flex flex-col gap-2">
            {failed.map((f) => (
              <li key={f.id} className="rounded-md bg-seal-wash p-2 text-[13px]">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span>
                    <b>{f.event_label}</b>
                    {f.order_code && f.order_id ? (
                      <>
                        {" · "}
                        <Link href={`/desk/don-hang/${f.order_id}`} className="text-accent">{f.order_code}</Link>
                      </>
                    ) : null}
                  </span>
                  <DateTime value={f.created_at} format="dateTime" className="text-ink-2" />
                </div>
                <p className="text-ink-2">{f.error || "Lỗi không rõ"}</p>
                <p className="text-ink-2">{f.will_retry ? `Sẽ tự gửi lại (đã thử ${f.attempts} lần)` : "Không gửi lại tự động"}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-[13px] text-ink-2">Chưa có tin nào gửi lỗi.</p>
      )}
    </Card>
  );
}
