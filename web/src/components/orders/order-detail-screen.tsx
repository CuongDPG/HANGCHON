"use client";

import { Bot, Copy, ExternalLink, PackageCheck, Printer, RefreshCw, RotateCcw, Truck, Wallet, X } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  CardHeader,
  DataList,
  DateTime,
  EmptyState,
  Input,
  InlineSelect,
  LevelTag,
  Money,
  notifySuccess,
  PageHeader,
  Sheet,
  Skeleton,
  Switch,
  Textarea,
  Timeline,
  useConfirm,
} from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import {
  CARRIER_LABELS,
  CHANNEL_LABELS,
  PAYMENT_LABELS,
  RETURN_KIND_LABELS,
  RETURN_REASON_LABELS,
  RETURN_STATUS_LABELS,
  SHIPPING_LABELS,
  statusTone,
  useAddPayment,
  useCancelOrder,
  useCancelShipment,
  useConfirmDraft,
  useCreateShipments,
  useOpenReturn,
  useOrder,
  usePatchOrder,
  useReturnReceived,
  useShippingQuotes,
  useSyncShipment,
  type OrderDetail,
  type PaymentMethod,
  type ReturnKind,
  type ReturnReason,
} from "@/lib/api/orders";

const NOTIFY_STATUS: Record<string, string> = { queued: "Đang gửi", sent: "Đã gửi", failed: "Lỗi", skipped: "Bỏ qua" };

export function OrderDetailScreen() {
  const { id } = useParams<{ id: string }>();
  const q = useOrder(id);
  if (q.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader loading backHref="/desk/don-hang" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (q.isError) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được đơn" backHref="/desk/don-hang" />
        <EmptyState tone="error" title="Chưa tải được đơn" description={q.error.message} action={<Button onClick={() => q.refetch()}>Thử lại</Button>} />
      </div>
    );
  }
  return <Detail order={q.data} />;
}

function Detail({ order: o }: { order: OrderDetail }) {
  const { user } = useSession();
  const isOwner = user?.role === "owner";
  const [sheet, setSheet] = useState<null | "pay" | "edit" | "cancel" | "return">(null);
  const address = [o.address_line, o.ward, o.district, o.province].filter(Boolean).join(", ");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow={`${CHANNEL_LABELS[o.channel] ?? o.channel} · ${PAYMENT_LABELS[o.payment_method]}`}
        title={o.code}
        backHref="/desk/don-hang"
        badge={<Badge tone={statusTone(o.status)}>{o.status_label}</Badge>}
      />
      {o.status === "draft" ? <DraftCard order={o} /> : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="flex flex-col gap-3">
          <CardHeader title="Món và tiền" aside={o.drop ? <Badge tone="accent">{o.drop.code}</Badge> : null} />
          <ul className="flex flex-col gap-1.5 text-[15px]">
            {o.items.map((i) => (
              <li key={i.id} className="flex justify-between gap-3">
                <span className="min-w-0">
                  {i.name} <span className="text-ink-2">× {i.quantity}</span>
                  {i.product_id ? null : <span className="text-seal"> (chưa khớp sản phẩm)</span>}
                </span>
                <Money value={i.line_total_vnd} />
              </li>
            ))}
          </ul>
          <DataList
            items={[
              { label: "Tạm tính", value: <Money value={o.subtotal_vnd} /> },
              { label: "Phí giao", value: <Money value={o.shipping_fee_vnd} /> },
              ...(o.discount_vnd ? [{ label: "Giảm", value: <Money value={-o.discount_vnd} /> }] : []),
              { label: "Tổng", value: <Money value={o.total_vnd} />, strong: true },
              { label: "Đã nhận", value: <Money value={o.paid_vnd} /> },
              ...(o.refunded_vnd ? [{ label: "Đã hoàn", value: <Money value={o.refunded_vnd} /> }] : []),
              ...(o.cod_amount_vnd ? [{ label: "Thu khi giao", value: <Money value={o.cod_amount_vnd} /> }] : []),
              ...(o.amount_due_vnd ? [{ label: "Còn chờ chuyển", value: <Money value={o.amount_due_vnd} className="text-review" /> }] : []),
            ]}
          />
          {o.transfer_content ? <p className="text-[13px] text-ink-2">Nội dung chuyển khoản: <b className="text-ink">{o.transfer_content}</b></p> : null}
          {o.payments.length ? (
            <ul className="flex flex-col gap-1 border-t border-line pt-2 text-[13px]">
              {o.payments.map((p) => (
                <li key={p.id} className="flex justify-between gap-2">
                  <span className="min-w-0 truncate text-ink-2">
                    <DateTime value={p.received_at} format="dateTime" /> · {p.direction === "out" ? "Hoàn" : p.provider} {p.content ? `· ${p.content}` : ""}
                  </span>
                  <Money value={p.direction === "out" ? -p.amount_vnd : p.amount_vnd} className={p.status === "needs_review" ? "text-review" : ""} />
                </li>
              ))}
            </ul>
          ) : null}
          {isOwner && o.status !== "draft" && o.status !== "cancelled" && o.payment_state !== "paid" ? (
            <Button variant="secondary" size="sm" icon={<Wallet className="size-4" />} onClick={() => setSheet("pay")} className="self-start">
              Ghi nhận tiền nhận tay
            </Button>
          ) : null}
        </Card>

        <Card className="flex flex-col gap-2 text-[15px]">
          <CardHeader
            title="Người nhận"
            aside={o.can_edit_address ? <Button variant="ghost" size="sm" onClick={() => setSheet("edit")}>Sửa</Button> : null}
          />
          <p>
            {o.recipient_name} · <a href={`tel:${o.recipient_phone}`} className="text-accent">{o.recipient_phone}</a>
          </p>
          <p className="text-ink-2">{address || "Chưa có địa chỉ"}</p>
          {o.customer_note ? <p className="rounded-md bg-soft px-3 py-2 text-[14px]">Khách dặn: {o.customer_note}</p> : null}
          {o.internal_note ? <p className="rounded-md bg-review-wash px-3 py-2 text-[14px] whitespace-pre-line">Ghi chú: {o.internal_note}</p> : null}
          {o.customer ? <p className="text-[13px] text-ink-2">Khách đã đặt {o.customer.order_count} đơn · đã chi <Money value={o.customer.total_spent_vnd} /></p> : null}
          <div className="mt-1 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<Copy className="size-4" />}
              onClick={async () => {
                await navigator.clipboard.writeText(o.public_url).catch(() => undefined);
                notifySuccess("Đã chép link theo dõi đơn");
              }}
            >
              Chép link cho khách
            </Button>
            <ButtonLink href={o.public_url} target="_blank" variant="ghost" size="sm" icon={<ExternalLink className="size-4" />}>
              Xem như khách
            </ButtonLink>
          </div>
        </Card>
      </div>

      {o.status !== "draft" ? <ShippingCard order={o} /> : null}
      <ReturnsCard order={o} onOpen={() => setSheet("return")} isOwner={isOwner} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Hành trình đơn" />
          <Timeline
            items={o.events.slice(0, 15).map((e, i) => ({
              title: e.title,
              status: i === 0 ? "current" : "done",
              meta: (
                <>
                  <DateTime value={e.occurred_at} format="dateTime" />
                  {e.visible_to_customer ? "" : " · nội bộ"}
                </>
              ),
              description: e.detail,
            }))}
          />
        </Card>
        <Card>
          <CardHeader title="Tin đã báo khách" aside={<LevelTag level="auto" />} />
          {o.notifications.length ? (
            <ul className="flex flex-col gap-3">
              {o.notifications.map((n) => (
                <li key={n.id} className="text-[14px]">
                  <div className="flex items-center justify-between gap-2 text-[12.5px] text-ink-2">
                    <span>
                      <DateTime value={n.created_at} format="dateTime" /> · {n.channel}
                    </span>
                    <Badge tone={n.status === "sent" ? "success" : n.status === "failed" ? "danger" : "neutral"}>{NOTIFY_STATUS[n.status]}</Badge>
                  </div>
                  <p className="mt-0.5 [text-wrap:pretty]">{n.body}</p>
                  {n.error ? <p className="text-[12.5px] text-seal">{n.error}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[14px] text-ink-2">Chưa gửi tin nào.</p>
          )}
        </Card>
      </div>

      {isOwner && o.can_cancel ? (
        <div className="flex justify-end">
          <Button variant="ghost" className="text-seal" icon={<X className="size-4" />} onClick={() => setSheet("cancel")}>
            Huỷ đơn
          </Button>
        </div>
      ) : null}

      <PaySheet open={sheet === "pay"} onClose={() => setSheet(null)} order={o} />
      <EditSheet open={sheet === "edit"} onClose={() => setSheet(null)} order={o} />
      <CancelSheet open={sheet === "cancel"} onClose={() => setSheet(null)} order={o} />
      <ReturnSheet open={sheet === "return"} onClose={() => setSheet(null)} order={o} />
    </div>
  );
}

function DraftCard({ order: o }: { order: OrderDetail }) {
  const confirm = useConfirmDraft(o.id);
  const [f, setF] = useState({
    recipient_name: o.recipient_name === "Chưa rõ" ? "" : o.recipient_name,
    recipient_phone: o.recipient_phone,
    address_line: o.address_line ?? "",
    province: o.province ?? "",
    payment_method: o.payment_method as PaymentMethod,
  });
  return (
    <Card tone="accent" className="flex flex-col gap-3">
      <CardHeader title={<span className="inline-flex items-center gap-1.5"><Bot className="size-4 text-accent" aria-hidden /> Đơn nháp AI soạn từ tin nhắn</span>} aside={<LevelTag level="review" />} />
      {o.missing_info.length ? <p className="text-[14px] text-seal">Còn thiếu: {o.missing_info.join(", ")}. Chị điền nốt rồi chốt.</p> : <p className="text-[14px] text-ink-2">Đủ thông tin. Chốt đơn thì khách nhận tin xác nhận.</p>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Input label="Người nhận" value={f.recipient_name} onChange={(e) => setF({ ...f, recipient_name: e.target.value })} />
        <Input label="Số điện thoại" type="tel" value={f.recipient_phone} onChange={(e) => setF({ ...f, recipient_phone: e.target.value })} />
        <Input label="Địa chỉ" value={f.address_line} onChange={(e) => setF({ ...f, address_line: e.target.value })} />
        <Input label="Tỉnh/thành" value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })} />
        <InlineSelect
          label="Thanh toán"
          value={f.payment_method}
          onChange={(v) => setF({ ...f, payment_method: v })}
          options={(["bank_transfer", "cod"] as PaymentMethod[]).map((m) => ({ value: m, label: PAYMENT_LABELS[m] }))}
        />
      </div>
      <Button className="self-start" loading={confirm.isPending} onClick={() => confirm.mutate(f, { onSuccess: () => notifySuccess("Đã chốt đơn và báo khách") })}>
        Chốt đơn
      </Button>
    </Card>
  );
}

function ShippingCard({ order: o }: { order: OrderDetail }) {
  const quotes = useShippingQuotes(o.id, o.can_ship);
  const create = useCreateShipments();
  const sync = useSyncShipment();
  const cancel = useCancelShipment();
  const confirm = useConfirm();
  const [choice, setChoice] = useState<string>("");
  const options = quotes.data?.options ?? [];
  const chosen = options.find((x) => `${x.driver}:${x.service}` === choice);
  return (
    <Card className="flex flex-col gap-3">
      <CardHeader title="Giao hàng" aside={<LevelTag level="auto" />} />
      {o.can_ship ? (
        <div className="flex flex-col gap-3">
          {quotes.isPending ? (
            <Skeleton className="h-11 w-full" />
          ) : quotes.isError ? (
            <p className="text-[14px] text-seal">{quotes.error.message}</p>
          ) : (
            <>
              <InlineSelect
                label="Hãng giao"
                value={choice || null}
                placeholder={quotes.data?.recommended ? `AI chọn: ${CARRIER_LABELS[quotes.data.recommended.carrier] ?? quotes.data.recommended.carrier} · ${quotes.data.recommended.service_name}` : "Chọn hãng"}
                onChange={setChoice}
                options={options.map((x) => ({
                  value: `${x.driver}:${x.service}`,
                  label: `${CARRIER_LABELS[x.carrier] ?? x.carrier} · ${x.service_name}`,
                  hint: `${new Intl.NumberFormat("vi-VN").format(x.fee_vnd)}đ · ${x.eta_days_min}–${x.eta_days_max} ngày`,
                }))}
              />
              {quotes.data?.reason ? <p className="text-[13px] text-ink-2">{quotes.data.reason}</p> : null}
            </>
          )}
          <Button
            className="self-start"
            icon={<Truck className="size-4" />}
            loading={create.isPending}
            disabled={!options.length}
            onClick={async () => {
              const r = (await create.mutateAsync({ order_ids: [o.id], driver: chosen?.driver, service: chosen?.service })).results[0];
              notifySuccess(r.status === "applied" ? `Đã tạo vận đơn ${r.tracking_code}` : r.status === "pending" ? "Đã gửi chị duyệt" : (r.message ?? "Chưa tạo được"));
            }}
          >
            Tạo vận đơn
          </Button>
        </div>
      ) : o.shipments.length === 0 ? (
        <p className="text-[14px] text-ink-2">{o.status === "awaiting_stock" || o.status === "confirmed" ? "Chờ hàng về rồi mới tạo vận đơn." : o.status === "pending_payment" ? "Chờ khách chuyển khoản." : "Chưa có vận đơn."}</p>
      ) : null}
      {o.shipments.map((s) => (
        <div key={s.id} className="flex flex-col gap-2 rounded-md border border-line p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[15px] font-semibold">
              {CARRIER_LABELS[s.carrier] ?? s.carrier} · <span className="tabular-nums">{s.tracking_code}</span>
            </p>
            <Badge tone={s.status === "delivered" ? "success" : s.status === "cancelled" || s.status.startsWith("return") || s.status === "failed_delivery" ? "danger" : "accent"}>{SHIPPING_LABELS[s.status]}</Badge>
          </div>
          <p className="text-[13px] text-ink-2">
            Phí <Money value={s.fee_vnd} /> · thu hộ <Money value={s.cod_amount_vnd} />
            {s.selection_reason ? ` · ${s.selection_reason}` : ""}
          </p>
          {s.events.length ? (
            <ul className="flex flex-col gap-0.5 text-[13px]">
              {s.events.slice(0, 5).map((e) => (
                <li key={e.id}>
                  <DateTime value={e.occurred_at} format="dateTime" className="text-ink-2" /> · {e.description}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {s.status !== "delivered" && s.status !== "cancelled" && s.status !== "returned" ? (
              <Button variant="secondary" size="sm" icon={<RefreshCw className="size-4" />} loading={sync.isPending} onClick={() => sync.mutate(s.id)}>
                Cập nhật trạng thái
              </Button>
            ) : null}
            {s.status !== "cancelled" ? (
              <ButtonLink href={`/desk/don-hang/in-nhan?ids=${o.id}`} variant="secondary" size="sm" icon={<Printer className="size-4" />}>
                In nhãn
              </ButtonLink>
            ) : null}
            {s.status === "created" ? (
              <Button
                variant="ghost"
                size="sm"
                className="text-seal"
                onClick={async () => {
                  if (await confirm({ title: "Huỷ vận đơn này?", message: "Hãng chưa lấy hàng nên huỷ được. Đơn quay về chờ giao.", confirmLabel: "Huỷ vận đơn", tone: "danger" }))
                    cancel.mutate(s.id);
                }}
              >
                Huỷ vận đơn
              </Button>
            ) : null}
          </div>
        </div>
      ))}
    </Card>
  );
}

function ReturnsCard({ order: o, onOpen, isOwner }: { order: OrderDetail; onOpen: () => void; isOwner: boolean }) {
  const received = useReturnReceived();
  const canOpen = o.status === "delivered" || o.status === "completed";
  if (!o.returns.length && !canOpen) return null;
  return (
    <Card className="flex flex-col gap-3">
      <CardHeader title="Đổi trả, hoàn tiền" aside={<LevelTag level="owner" />} />
      {o.returns.map((r) => (
        <div key={r.id} className="flex flex-col gap-1.5 rounded-md border border-line p-3 text-[14px]">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold">
              {r.code} · {RETURN_KIND_LABELS[r.kind]} · {RETURN_REASON_LABELS[r.reason]}
            </span>
            <Badge tone={r.status === "pending_decision" ? "warning" : r.status === "rejected" ? "danger" : "neutral"}>{RETURN_STATUS_LABELS[r.status]}</Badge>
          </div>
          {r.description ? <p className="text-ink-2">«{r.description}»</p> : null}
          {r.eligibility.summary ? <p>{r.eligibility.summary}</p> : null}
          {r.status === "pending_decision" ? (
            <ButtonLink href="/desk/duyet" variant="secondary" size="sm" className="self-start">
              Quyết ở hàng chờ duyệt
            </ButtonLink>
          ) : null}
          {r.status === "awaiting_item" && isOwner ? (
            <Button size="sm" className="self-start" icon={<PackageCheck className="size-4" />} loading={received.isPending} onClick={() => received.mutate(r.id, { onSuccess: () => notifySuccess("Đã ghi nhận và hoàn tất") })}>
              Đã nhận lại hàng
            </Button>
          ) : null}
        </div>
      ))}
      {canOpen ? (
        <Button variant="secondary" size="sm" icon={<RotateCcw className="size-4" />} onClick={onOpen} className="self-start">
          Mở yêu cầu đổi trả
        </Button>
      ) : null}
    </Card>
  );
}

function PaySheet({ open, onClose, order: o }: { open: boolean; onClose: () => void; order: OrderDetail }) {
  const add = useAddPayment(o.id);
  const [amount, setAmount] = useState(String(Math.max(0, o.total_vnd - o.paid_vnd)));
  const [method, setMethod] = useState<"cash" | "bank_transfer">("cash");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Ghi nhận tiền nhận tay"
      description="Tiền mặt, hoặc chuyển khoản không qua cổng tự khớp."
      footer={
        <Button loading={add.isPending} onClick={() => add.mutate({ amount_vnd: Number(amount.replace(/\D/g, "")), method }, { onSuccess: () => (notifySuccess("Đã ghi nhận"), onClose()) })}>
          Ghi nhận
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="Số tiền" inputMode="numeric" trailing="đ" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <InlineSelect label="Hình thức" value={method} onChange={setMethod} options={[{ value: "cash", label: "Tiền mặt" }, { value: "bank_transfer", label: "Chuyển khoản" }]} />
      </div>
    </Sheet>
  );
}

function EditSheet({ open, onClose, order: o }: { open: boolean; onClose: () => void; order: OrderDetail }) {
  const patch = usePatchOrder(o.id);
  const [f, setF] = useState({ recipient_name: o.recipient_name, recipient_phone: o.recipient_phone, address_line: o.address_line ?? "", ward: o.ward ?? "", district: o.district ?? "", province: o.province ?? "", internal_note: o.internal_note ?? "" });
  return (
    <Sheet open={open} onClose={onClose} title="Sửa người nhận" footer={<Button loading={patch.isPending} onClick={() => patch.mutate(f, { onSuccess: () => (notifySuccess("Đã lưu"), onClose()) })}>Lưu</Button>}>
      <div className="flex flex-col gap-3">
        <Input label="Người nhận" value={f.recipient_name} onChange={(e) => setF({ ...f, recipient_name: e.target.value })} />
        <Input label="Số điện thoại" type="tel" value={f.recipient_phone} onChange={(e) => setF({ ...f, recipient_phone: e.target.value })} />
        <Input label="Địa chỉ" value={f.address_line} onChange={(e) => setF({ ...f, address_line: e.target.value })} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Phường/xã" value={f.ward} onChange={(e) => setF({ ...f, ward: e.target.value })} />
          <Input label="Quận/huyện" value={f.district} onChange={(e) => setF({ ...f, district: e.target.value })} />
        </div>
        <Input label="Tỉnh/thành" value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })} />
        <Textarea label="Ghi chú nội bộ" rows={2} value={f.internal_note} onChange={(e) => setF({ ...f, internal_note: e.target.value })} />
      </div>
    </Sheet>
  );
}

function CancelSheet({ open, onClose, order: o }: { open: boolean; onClose: () => void; order: OrderDetail }) {
  const cancel = useCancelOrder(o.id);
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(true);
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={`Huỷ đơn ${o.code}?`}
      description={o.paid_vnd > 0 ? "Khách đã trả tiền: hệ thống mở yêu cầu hoàn tiền để chị duyệt." : "Suất của đơn được trả lại cho người khác."}
      footer={
        <Button variant="danger" loading={cancel.isPending} disabled={reason.trim().length < 2} onClick={() => cancel.mutate({ reason, notify_customer: notify }, { onSuccess: () => (notifySuccess("Đã huỷ đơn"), onClose()) })}>
          Huỷ đơn
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <Textarea label="Lý do" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Vd: khách nhắn huỷ" />
        <Switch label="Báo khách" checked={notify} onChange={setNotify} />
      </div>
    </Sheet>
  );
}

function ReturnSheet({ open, onClose, order: o }: { open: boolean; onClose: () => void; order: OrderDetail }) {
  const openReturn = useOpenReturn(o.id);
  const [kind, setKind] = useState<ReturnKind>("return");
  const [reason, setReason] = useState<ReturnReason>("defect");
  const [item, setItem] = useState(o.items[0]?.id ?? "");
  const [desc, setDesc] = useState("");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Mở yêu cầu đổi trả"
      description="AI kiểm điều kiện và soạn phương án; chị quyết ở hàng chờ duyệt."
      footer={
        <Button loading={openReturn.isPending} onClick={() => openReturn.mutate({ kind, reason, description: desc || undefined, order_item_id: item || null }, { onSuccess: () => (notifySuccess("Đã mở yêu cầu"), onClose()) })}>
          Mở yêu cầu
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <InlineSelect label="Món" value={item} onChange={setItem} options={o.items.map((i) => ({ value: i.id, label: i.name }))} />
        <InlineSelect label="Loại" value={kind} onChange={setKind} options={(Object.keys(RETURN_KIND_LABELS) as ReturnKind[]).map((k) => ({ value: k, label: RETURN_KIND_LABELS[k] }))} />
        <InlineSelect label="Lý do" value={reason} onChange={setReason} options={(Object.keys(RETURN_REASON_LABELS) as ReturnReason[]).map((r) => ({ value: r, label: RETURN_REASON_LABELS[r] }))} />
        <Textarea label="Mô tả" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} />
      </div>
    </Sheet>
  );
}
