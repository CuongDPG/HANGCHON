"use client";

import { useQueryClient } from "@tanstack/react-query";
import { MapPin, MessageCircleQuestion, PackageOpen, RotateCcw, Search } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  DataList,
  DateTime,
  EmptyState,
  ImageBox,
  Input,
  InlineSelect,
  Money,
  notifySuccess,
  PageHeader,
  Sheet,
  Skeleton,
  Textarea,
  Timeline,
} from "@/components/ui";
import {
  CARRIER_LABELS,
  PAYMENT_LABELS,
  RETURN_KIND_LABELS,
  RETURN_REASON_LABELS,
  RETURN_STATUS_LABELS,
  storeOrderKeys,
  storeOrdersApi,
  usePublicOrder,
  type PublicOrder,
  type ReturnKind,
  type ReturnReason,
} from "@/lib/api/orders";
import { recentToken, useIsClient } from "@/lib/cart";
import { PaymentBox } from "./payment-box";
import { ProvinceInput } from "./province-input";

/** Theo dõi đơn (e5): hành trình gồm cả chặng hàng từ nước ngoài về, chuyển khoản QR, hỏi về đơn, đổi địa chỉ. */
export function TrackingScreen() {
  const { code: raw } = useParams<{ code: string }>();
  const code = decodeURIComponent(raw ?? "");
  const isClient = useIsClient();
  const t = useSearchParams().get("t") ?? (isClient ? recentToken(code) : null);
  const q = usePublicOrder(code, t);

  if (!isClient || (t && q.isPending)) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title={`Đơn ${code}`} backHref="/don" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (!t || q.isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={`Đơn ${code}`} backHref="/don" />
        <EmptyState
          icon={<Search />}
          tone={q.isError ? "error" : "default"}
          title="Chưa xem được đơn này"
          description={q.error?.message ?? "Bạn tra đơn bằng số điện thoại và mã đơn nhé."}
          action={<ButtonLink href="/don">Tra cứu đơn</ButtonLink>}
        />
      </div>
    );
  }
  return <OrderView order={q.data!} token={t} />;
}

function OrderView({ order, token }: { order: PublicOrder; token: string }) {
  const [sheet, setSheet] = useState<null | "ask" | "address" | "return">(null);
  const waitingTransfer = order.payment_method === "bank_transfer" && order.payment && order.payment.amount_due_vnd > 0 && order.status === "pending_payment";
  const address = [order.address_line, order.ward, order.district, order.province].filter(Boolean).join(", ");
  return (
    <div className="flex flex-col gap-5 md:grid md:grid-cols-[1fr_20rem] md:items-start md:gap-8">
      <div className="flex flex-col gap-5">
        <PageHeader eyebrow={order.status_label} title={`Đơn ${order.code}`} backHref="/don" description={order.headline} />
        {waitingTransfer && order.payment ? <PaymentBox payment={order.payment} deposit={order.deposit_required_vnd > 0 && order.paid_vnd < order.deposit_required_vnd} /> : null}
        <Card>
          <Timeline
            items={order.timeline.map((s) => ({
              title: s.title,
              status: s.status,
              meta: s.at ? (
                <>
                  <DateTime value={s.at} format="dayMonth" />
                  {s.meta ? ` · ${s.meta}` : ""}
                </>
              ) : (
                s.meta
              ),
            }))}
          />
        </Card>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" icon={<MessageCircleQuestion className="size-4" />} onClick={() => setSheet("ask")}>
            Hỏi về đơn này
          </Button>
          {order.can_request_return ? (
            <Button variant="secondary" icon={<RotateCcw className="size-4" />} onClick={() => setSheet("return")}>
              Đổi trả
            </Button>
          ) : (
            <Button variant="secondary" icon={<MapPin className="size-4" />} onClick={() => setSheet("address")} disabled={!order.can_change_address}>
              Đổi địa chỉ
            </Button>
          )}
        </div>
        {order.notify_hint ? <p className="text-[14px] text-ink-2">{order.notify_hint}</p> : null}
        {order.reviews?.length ? (
          <Card className="flex flex-col gap-2">
            <h2 className="font-sans text-[15px] font-semibold">Đánh giá món đã nhận</h2>
            {order.reviews.map((r) => (
              <div key={r.token} className="flex items-center justify-between gap-2 text-[14px]">
                <span className="min-w-0 truncate">{r.name}</span>
                {r.status === "requested" ? (
                  <Link href={`/danh-gia/${r.token}`} className="shrink-0 text-accent">
                    Viết đánh giá
                  </Link>
                ) : (
                  <Badge tone={r.status === "published" ? "success" : "neutral"}>{r.status === "published" ? "Đã hiện trên web" : "Đã gửi, mình đang xem"}</Badge>
                )}
              </div>
            ))}
          </Card>
        ) : null}
        {order.returns.length ? (
          <Card className="flex flex-col gap-2">
            <h2 className="font-sans text-[15px] font-semibold">Đổi trả</h2>
            {order.returns.map((r) => (
              <div key={r.code} className="flex items-center justify-between gap-2 text-[14px]">
                <span>
                  {r.code} · {RETURN_KIND_LABELS[r.kind]}
                </span>
                <Badge tone={r.status === "rejected" ? "danger" : r.status === "refunded" || r.status === "exchanged" ? "success" : "warning"}>{r.status === "pending_decision" ? "Mình đang xem" : RETURN_STATUS_LABELS[r.status]}</Badge>
              </div>
            ))}
          </Card>
        ) : null}
      </div>

      <div className="flex flex-col gap-3">
        <Card className="flex flex-col gap-3">
          <ul className="flex flex-col gap-3">
            {order.items.map((i, idx) => (
              <li key={idx} className="flex items-center gap-3">
                <div className="w-12 shrink-0">
                  <ImageBox src={i.image_url} alt="" ratio="1/1" />
                </div>
                <div className="min-w-0 flex-1 text-[14px]">
                  <p className="leading-snug font-semibold">{i.name}</p>
                  <p className="text-ink-2">
                    {i.quantity} × <Money value={i.unit_price_vnd} />
                  </p>
                </div>
              </li>
            ))}
          </ul>
          <DataList
            items={[
              { label: "Tạm tính", value: <Money value={order.subtotal_vnd} /> },
              { label: "Phí giao", value: <Money value={order.shipping_fee_vnd} /> },
              ...(order.discount_vnd ? [{ label: "Giảm", value: <Money value={-order.discount_vnd} /> }] : []),
              { label: "Tổng", value: <Money value={order.total_vnd} />, strong: true },
              { label: "Đã trả", value: <Money value={order.paid_vnd} /> },
              ...(order.cod_amount_vnd && order.payment_state !== "paid" ? [{ label: "Trả khi nhận", value: <Money value={order.cod_amount_vnd} /> }] : []),
            ]}
          />
          <p className="text-[13px] text-ink-2">Thanh toán: {PAYMENT_LABELS[order.payment_method]}</p>
        </Card>
        <Card className="flex flex-col gap-1 text-[14px]">
          <h2 className="font-sans text-[15px] font-semibold">Giao tới</h2>
          <p>
            {order.recipient_name} · {order.recipient_phone}
          </p>
          <p className="text-ink-2">{address}</p>
          {order.shipment ? (
            <p className="mt-1 flex items-center gap-1.5 text-ink-2">
              <PackageOpen className="size-4" aria-hidden />
              {CARRIER_LABELS[order.shipment.carrier] ?? order.shipment.carrier}
              {order.shipment.tracking_code ? ` · ${order.shipment.tracking_code}` : ""}
            </p>
          ) : null}
        </Card>
      </div>

      <AskSheet open={sheet === "ask"} onClose={() => setSheet(null)} code={order.code} token={token} />
      <AddressSheet open={sheet === "address"} onClose={() => setSheet(null)} order={order} token={token} />
      <ReturnSheet open={sheet === "return"} onClose={() => setSheet(null)} order={order} token={token} />
    </div>
  );
}

function useSetOrder(code: string) {
  const qc = useQueryClient();
  return (o: PublicOrder) => qc.setQueryData(storeOrderKeys.order(code), o);
}

function AskSheet({ open, onClose, code, token }: { open: boolean; onClose: () => void; code: string; token: string }) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setOrder = useSetOrder(code);
  async function send() {
    if (text.trim().length < 2) return setError("Bạn ghi câu hỏi giúp mình nhé.");
    setPending(true);
    try {
      setOrder(await storeOrdersApi.ask(code, { t: token, message: text.trim() }));
      notifySuccess("Đã gửi câu hỏi, mình sẽ trả lời bạn sớm");
      setText("");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chưa gửi được.");
    } finally {
      setPending(false);
    }
  }
  return (
    <Sheet open={open} onClose={onClose} title="Hỏi về đơn này" description="Câu hỏi tới thẳng mình, mình trả lời bạn qua tin nhắn." footer={<Button onClick={send} loading={pending}>Gửi câu hỏi</Button>}>
      <Textarea label="Câu hỏi" rows={4} value={text} onChange={(e) => setText(e.target.value)} error={error} placeholder="Vd: Bao giờ hàng về tới mình?" />
    </Sheet>
  );
}

function AddressSheet({ open, onClose, order, token }: { open: boolean; onClose: () => void; order: PublicOrder; token: string }) {
  const [f, setF] = useState({ recipient_name: order.recipient_name, address_line: order.address_line ?? "", ward: order.ward ?? "", district: order.district ?? "", province: order.province ?? "" });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setOrder = useSetOrder(order.code);
  async function save() {
    setPending(true);
    setError(null);
    try {
      setOrder(await storeOrdersApi.changeAddress(order.code, { t: token, ...f, ward: f.ward || null, district: f.district || null }));
      notifySuccess("Đã đổi địa chỉ nhận hàng");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chưa đổi được.");
    } finally {
      setPending(false);
    }
  }
  return (
    <Sheet open={open} onClose={onClose} title="Đổi địa chỉ nhận hàng" description="Đổi được khi đơn chưa giao cho hãng vận chuyển." footer={<Button onClick={save} loading={pending}>Lưu địa chỉ</Button>}>
      <div className="flex flex-col gap-3">
        {error ? <p role="alert" className="text-[14px] text-seal">{error}</p> : null}
        <Input label="Người nhận" value={f.recipient_name} onChange={(e) => setF({ ...f, recipient_name: e.target.value })} />
        <Input label="Địa chỉ" value={f.address_line} onChange={(e) => setF({ ...f, address_line: e.target.value })} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Phường/xã" value={f.ward} onChange={(e) => setF({ ...f, ward: e.target.value })} />
          <Input label="Quận/huyện" value={f.district} onChange={(e) => setF({ ...f, district: e.target.value })} />
        </div>
        <ProvinceInput label="Tỉnh/thành" value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })} onPick={(v) => setF({ ...f, province: v })} />
      </div>
    </Sheet>
  );
}

function ReturnSheet({ open, onClose, order, token }: { open: boolean; onClose: () => void; order: PublicOrder; token: string }) {
  const [kind, setKind] = useState<ReturnKind>("return");
  const [reason, setReason] = useState<ReturnReason>("defect");
  const [item, setItem] = useState<string>("0");
  const [desc, setDesc] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setOrder = useSetOrder(order.code);
  async function send() {
    setPending(true);
    setError(null);
    try {
      setOrder(await storeOrdersApi.requestReturn(order.code, { t: token, kind, reason, description: desc || undefined, order_item_index: Number(item) }));
      notifySuccess("Đã gửi yêu cầu, mình sẽ xem và báo bạn");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chưa gửi được.");
    } finally {
      setPending(false);
    }
  }
  return (
    <Sheet open={open} onClose={onClose} title="Yêu cầu đổi trả" description="Mình xem từng yêu cầu và trả lời bạn." footer={<Button onClick={send} loading={pending}>Gửi yêu cầu</Button>}>
      <div className="flex flex-col gap-3">
        {error ? <p role="alert" className="text-[14px] text-seal">{error}</p> : null}
        <InlineSelect label="Món" value={item} onChange={setItem} options={order.items.map((i, idx) => ({ value: String(idx), label: i.name }))} />
        <InlineSelect label="Bạn muốn" value={kind} onChange={setKind} options={(["return", "exchange"] as ReturnKind[]).map((k) => ({ value: k, label: RETURN_KIND_LABELS[k] }))} />
        <InlineSelect label="Lý do" value={reason} onChange={setReason} options={(Object.keys(RETURN_REASON_LABELS) as ReturnReason[]).map((r) => ({ value: r, label: RETURN_REASON_LABELS[r] }))} />
        <Textarea label="Mô tả thêm" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Vd: nắp bị nứt khi mở hộp" />
      </div>
    </Sheet>
  );
}
