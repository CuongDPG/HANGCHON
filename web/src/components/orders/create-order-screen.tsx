"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Card, CardHeader, EmptyState, IconButton, Input, InlineSelect, Money, PageHeader, SkeletonList, Switch, Textarea, notifySuccess } from "@/components/ui";
import { CHANNEL_LABELS, PAYMENT_LABELS, useCreateOrder, useSellable, type Channel, type PaymentMethod } from "@/lib/api/orders";
import { QuantityStepper } from "./quantity-stepper";

type Line = { key: number; product_id: string; source: string; quantity: number; price: string };
const CHANNELS: Channel[] = ["manual", "phone", "facebook", "instagram", "zalo", "zalo_group", "tiktok"];

/** Chị tạo đơn tay (g1): khách đặt qua điện thoại, tin nhắn, gặp trực tiếp. */
export function CreateOrderScreen() {
  const router = useRouter();
  const catalog = useSellable();
  const create = useCreateOrder();
  const [lines, setLines] = useState<Line[]>([]);
  const [f, setF] = useState({ name: "", phone: "", address_line: "", ward: "", province: "", customer_note: "", internal_note: "" });
  const [channel, setChannel] = useState<Channel>("phone");
  const [method, setMethod] = useState<PaymentMethod>("cod");
  const [fee, setFee] = useState("");
  const [paid, setPaid] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const products = catalog.data ?? [];

  function sourcesOf(pid: string) {
    const p = products.find((x) => x.product_id === pid);
    if (!p) return [];
    const opts = p.drops.map((d) => ({ value: `drop:${d.drop_id}`, label: `Đợt ${d.code}`, hint: `${new Intl.NumberFormat("vi-VN").format(d.price_vnd)}đ${d.available !== null ? ` · còn ${d.available} suất` : ""}` }));
    if (p.stock_available !== null) opts.push({ value: "stock", label: "Hàng có sẵn", hint: `còn ${p.stock_available} cái` });
    return opts;
  }
  function priceOf(l: Line) {
    if (l.price) return Number(l.price.replace(/\D/g, ""));
    const p = products.find((x) => x.product_id === l.product_id);
    const d = p?.drops.find((x) => `drop:${x.drop_id}` === l.source);
    return d?.price_vnd ?? p?.price_vnd ?? 0;
  }
  const subtotal = lines.reduce((s, l) => s + priceOf(l) * l.quantity, 0);

  async function submit() {
    setError(null);
    try {
      const o = await create.mutateAsync({
        items: lines.map((l) => ({ product_id: l.product_id, drop_id: l.source.startsWith("drop:") ? l.source.slice(5) : null, quantity: l.quantity, unit_price_vnd: l.price ? priceOf(l) : null })),
        name: f.name, phone: f.phone, address_line: f.address_line || null, ward: f.ward || null, province: f.province || null,
        channel, payment_method: method, shipping_fee_vnd: fee ? Number(fee.replace(/\D/g, "")) : null,
        customer_note: f.customer_note || null, internal_note: f.internal_note || null, already_paid: paid,
      });
      notifySuccess(`Đã tạo đơn ${o.code}`);
      router.push(`/desk/don-hang/${o.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chưa tạo được đơn.");
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Tạo đơn" backHref="/desk/don-hang" />
      <Card className="flex flex-col gap-3">
        <CardHeader title="Món" />
        {catalog.isPending ? (
          <SkeletonList rows={1} />
        ) : catalog.isError ? (
          <EmptyState tone="error" title="Chưa tải được danh sách món" description={catalog.error.message} />
        ) : products.length === 0 ? (
          <p className="text-[14px] text-ink-2">Chưa có món nào đang bán.</p>
        ) : (
          <>
            {lines.map((l) => (
              <div key={l.key} className="flex flex-col gap-2 rounded-md border border-line p-3">
                <div className="flex items-start gap-2">
                  <InlineSelect
                    className="min-w-0 flex-1"
                    aria-label="Món"
                    value={l.product_id || null}
                    placeholder="Chọn món"
                    onChange={(v) => setLines(lines.map((x) => (x.key === l.key ? { ...x, product_id: v, source: sourcesOf(v)[0]?.value ?? "stock" } : x)))}
                    options={products.map((p) => ({ value: p.product_id, label: p.name }))}
                  />
                  <IconButton label="Bỏ dòng này" icon={<Trash2 />} onClick={() => setLines(lines.filter((x) => x.key !== l.key))} />
                </div>
                {l.product_id ? (
                  <div className="grid grid-cols-2 items-end gap-2 md:grid-cols-[1fr_auto_10rem]">
                    <InlineSelect className="col-span-2 md:col-span-1" aria-label="Nguồn" value={l.source} onChange={(v) => setLines(lines.map((x) => (x.key === l.key ? { ...x, source: v } : x)))} options={sourcesOf(l.product_id)} />
                    <QuantityStepper value={l.quantity} onChange={(q) => setLines(lines.map((x) => (x.key === l.key ? { ...x, quantity: q } : x)))} />
                    <Input aria-label="Giá riêng" placeholder={String(priceOf({ ...l, price: "" }))} inputMode="numeric" trailing="đ" value={l.price} onChange={(e) => setLines(lines.map((x) => (x.key === l.key ? { ...x, price: e.target.value } : x)))} />
                  </div>
                ) : null}
              </div>
            ))}
            <Button variant="secondary" size="sm" icon={<Plus className="size-4" />} className="self-start" onClick={() => setLines([...lines, { key: Date.now(), product_id: "", source: "", quantity: 1, price: "" }])}>
              Thêm món
            </Button>
            <p className="text-[14px]">Tạm tính: <Money value={subtotal} className="font-semibold" /></p>
          </>
        )}
      </Card>
      <Card className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Input label="Họ tên" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <Input label="Số điện thoại" type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        <Input label="Địa chỉ" value={f.address_line} onChange={(e) => setF({ ...f, address_line: e.target.value })} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Phường/xã" value={f.ward} onChange={(e) => setF({ ...f, ward: e.target.value })} />
          <Input label="Tỉnh/thành" value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })} />
        </div>
        <InlineSelect label="Khách đặt qua" value={channel} onChange={setChannel} options={CHANNELS.map((c) => ({ value: c, label: CHANNEL_LABELS[c] }))} />
        <InlineSelect label="Thanh toán" value={method} onChange={setMethod} options={(["cod", "bank_transfer", "cash"] as PaymentMethod[]).map((m) => ({ value: m, label: PAYMENT_LABELS[m] }))} />
        <Input label="Phí giao" hint="Bỏ trống = tính qua hãng giao" inputMode="numeric" trailing="đ" value={fee} onChange={(e) => setFee(e.target.value)} />
        <div className="flex items-end">
          <Switch label="Đã nhận đủ tiền" description="Tiền mặt hoặc chuyển khoản trước" checked={paid} onChange={setPaid} className="w-full" />
        </div>
        <Textarea label="Khách dặn" rows={2} value={f.customer_note} onChange={(e) => setF({ ...f, customer_note: e.target.value })} />
        <Textarea label="Ghi chú nội bộ" rows={2} value={f.internal_note} onChange={(e) => setF({ ...f, internal_note: e.target.value })} />
      </Card>
      {error ? <p role="alert" className="rounded-md bg-seal-wash px-3 py-2.5 text-[14px] text-seal">{error}</p> : null}
      <Button size="lg" className="self-stretch md:self-end" loading={create.isPending} disabled={!lines.some((l) => l.product_id) || !f.name || !f.phone} onClick={submit}>
        Tạo đơn
      </Button>
    </div>
  );
}
