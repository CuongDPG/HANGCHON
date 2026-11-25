"use client";

import { attributionFields } from "@/lib/attribution";
import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, Gift, Hourglass, ShoppingBag } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Button, ButtonLink, Card, DataList, EmptyState, ImageBox, Input, Money, PageHeader, RadioGroup, SkeletonList, Textarea } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { storeOrdersApi, useQuote } from "@/lib/api/orders";
import { clearCart, rememberOrder, setCartQuantity, useCart, useIsClient } from "@/lib/cart";
import { ProvinceInput } from "./province-input";
import { QuantityStepper } from "./quantity-stepper";

const PHONE_RE = /^(?:\+?84|0)[\s.-]?[35789](?:[\s.-]?\d){8}$/;

const schema = z.object({
  phone: z.string().trim().min(1, "Nhập số điện thoại.").regex(PHONE_RE, "Số điện thoại chưa đúng (10 số, vd 09xx xxx xxx)."),
  name: z.string().trim().min(1, "Nhập họ tên người nhận.").max(120),
  address_line: z.string().trim().min(4, "Ghi số nhà, đường."),
  ward: z.string().trim().max(120).optional(),
  district: z.string().trim().max(120).optional(),
  province: z.string().trim().min(2, "Ghi tỉnh/thành."),
  note: z.string().trim().max(500).optional(),
  payment_method: z.enum(["bank_transfer", "cod"]),
});
type FormValues = z.infer<typeof schema>;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Đặt hàng một trang (e4): không cần tài khoản, phí giao tính qua hãng, nhắc ngày hàng về, QR hoặc trả khi nhận. */
export function CheckoutScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const isClient = useIsClient();
  const cart = useCart();
  const dropIds = [...new Set(cart.filter((i) => i.dropId).map((i) => i.dropId!))];
  const dot = params.get("dot") && dropIds.includes(params.get("dot")!) ? params.get("dot")! : dropIds[0];
  const items = cart.filter((i) => !i.dropId || i.dropId === dot);
  const otherDrops = dropIds.filter((d) => d !== dot).length;
  const [clientRef] = useState(() => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now())));
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { phone: "", name: "", address_line: "", province: "", payment_method: "bank_transfer" } });
  const watched = useWatch({ control });
  const address = useDebounced({ address_line: watched.address_line || null, province: watched.province || null, ward: watched.ward || null, district: watched.district || null }, 500);
  const method = (watched.payment_method ?? "bank_transfer") as "bank_transfer" | "cod";
  const lines = useMemo(() => items.map((i) => ({ product_id: i.productId, variant_id: i.variantId ?? null, drop_id: i.dropId ?? null, quantity: i.quantity })), [items]);
  const referralCode = isClient ? attributionFields().referral_code : undefined;
  const quote = useQuote({ items: lines, payment_method: method, ...address, ...(referralCode ? { referral_code: referralCode } : {}) });
  const q = quote.data;

  const onSubmit = handleSubmit(async (v) => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const order = await storeOrdersApi.checkout({
        items: lines, name: v.name, phone: v.phone, address_line: v.address_line, ward: v.ward || null, district: v.district || null,
        province: v.province, note: v.note || null, payment_method: v.payment_method, client_ref: clientRef,
        ...attributionFields(),
      });
      rememberOrder({ code: order.code, token: order.token, placedAt: order.placed_at });
      clearCart(items.map((i) => i.key));
      router.push(`/don/${encodeURIComponent(order.code)}?t=${encodeURIComponent(order.token)}`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Chưa đặt được, bạn thử lại giúp mình.");
      quote.refetch();
      setSubmitting(false);
    }
  });

  if (!isClient) return <SkeletonList rows={3} />;
  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Đặt hàng" backHref="/gio-hang" />
        <EmptyState icon={<ShoppingBag />} title="Chưa có món nào để đặt" description="Bạn chọn món trên kệ hoặc trong đợt mua chung đang mở nhé." action={<ButtonLink href="/">Xem kệ hàng</ButtonLink>} />
      </div>
    );
  }

  const lineByIdx = (idx: number) => q?.lines[idx];
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5 md:grid md:grid-cols-[1fr_22rem] md:items-start md:gap-8">
      <div className="flex flex-col gap-5">
        <PageHeader title="Đặt hàng" backHref="/gio-hang" description="Không cần tạo tài khoản. Số điện thoại là khoá để bạn tra đơn về sau." />
        <section aria-label="Món đặt" className="flex flex-col gap-2">
          {items.map((i, idx) => (
            <div key={i.key} className="flex items-center gap-3 rounded-md border border-line bg-surface p-3">
              <div className="w-14 shrink-0">
                <ImageBox src={i.imageUrl} alt="" ratio="1/1" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[15px] leading-snug font-semibold">{i.name}</p>
                <p className="text-[13px] text-ink-2">
                  <Money value={lineByIdx(idx)?.unit_price_vnd ?? i.priceVnd} />
                  {i.dropLabel ? ` · ${i.dropLabel}` : ""}
                </p>
                {lineByIdx(idx)?.problem ? <p className="text-[13px] text-seal">{lineByIdx(idx)?.problem}</p> : null}
              </div>
              <QuantityStepper value={i.quantity} onChange={(n) => setCartQuantity(i.key, n)} size="sm" max={Math.max(1, Math.min(99, lineByIdx(idx)?.available ?? 99))} />
            </div>
          ))}
          {otherDrops ? <p className="text-[13px] text-ink-2">Món của {otherDrops} đợt khác vẫn nằm trong giỏ, bạn đặt riêng sau nhé.</p> : null}
        </section>

        <section aria-label="Người nhận" className="flex flex-col gap-3">
          <Input label="Số điện thoại" type="tel" inputMode="tel" autoComplete="tel" required error={errors.phone?.message} {...register("phone")} />
          <Input label="Họ tên" autoComplete="name" required error={errors.name?.message} {...register("name")} />
          <Input label="Địa chỉ nhận hàng" placeholder="Số nhà, ngõ, đường" autoComplete="street-address" required error={errors.address_line?.message} {...register("address_line")} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Phường/xã" autoComplete="address-level3" error={errors.ward?.message} {...register("ward")} />
            <Input label="Quận/huyện" hint="Nếu còn dùng" autoComplete="address-level2" error={errors.district?.message} {...register("district")} />
          </div>
          <ProvinceInput
            label="Tỉnh/thành"
            required
            error={errors.province?.message}
            value={watched.province ?? ""}
            onChange={(e) => setValue("province", e.target.value, { shouldValidate: !!errors.province })}
            onPick={(v) => setValue("province", v, { shouldValidate: true })}
          />
          <Textarea label="Ghi chú cho người bán" rows={2} placeholder="Giờ nhận hàng, gửi kèm thiệp…" error={errors.note?.message} {...register("note")} />
        </section>

        <Card>
          <RadioGroup
            legend="Thanh toán"
            name="payment_method"
            value={method}
            onChange={(v) => setValue("payment_method", v)}
            options={[
              { value: "bank_transfer", label: "Chuyển khoản bằng mã QR, tự xác nhận", description: q?.deposit_required_vnd ? `Đợt này đặt cọc ${new Intl.NumberFormat("vi-VN").format(q.deposit_required_vnd)}đ, phần còn lại trả khi nhận.` : "Có mã QR và nội dung chuyển khoản ngay sau khi đặt." },
              { value: "cod", label: "Trả tiền khi nhận hàng", description: "Bạn trả cho người giao hàng." },
            ]}
          />
        </Card>
      </div>

      <div className="flex flex-col gap-3 md:sticky md:top-20">
        {q?.delivery_hint ? (
          <Card tone="soft" className="flex items-start gap-2 text-[14px]">
            <Hourglass className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
            <span>{q.delivery_hint}</span>
          </Card>
        ) : null}
        <Card>
          <DataList
            items={[
              { label: "Tạm tính", value: q ? <Money value={q.subtotal_vnd} /> : "…" },
              { label: q?.shipping_estimated ? "Phí giao (ước tính)" : "Phí giao", value: q ? <Money value={q.shipping_fee_vnd} /> : "…" },
              ...(q?.referral_discount_vnd ? [{ label: "Quà giới thiệu (đơn đầu)", value: <Money value={-q.referral_discount_vnd} /> }] : []),
              { label: q?.referral_discount_vnd ? "Tổng (chưa trừ quà)" : "Tổng", value: q ? <Money value={q.total_vnd} /> : "…", strong: true },
            ]}
          />
          {q?.referral_note ? <p className="mt-2 flex items-start gap-1.5 text-[13px] text-ink-2"><Gift className="mt-0.5 size-3.5 shrink-0 text-auto" aria-hidden />{q.referral_note}</p> : null}
        </Card>
        {q && !q.ok && q.problems.length ? (
          <p role="alert" className="flex items-start gap-2 rounded-md bg-seal-wash px-3 py-2.5 text-[14px] text-seal">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            {q.problems.join(" ")}
          </p>
        ) : null}
        {submitError ? (
          <p role="alert" className="flex items-start gap-2 rounded-md bg-seal-wash px-3 py-2.5 text-[14px] text-seal">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            {submitError}
          </p>
        ) : null}
        {quote.isError ? <p className="text-[14px] text-seal">{quote.error.message}</p> : null}
        <Button type="submit" block size="lg" loading={submitting} disabled={!q?.ok}>
          Đặt hàng
        </Button>
      </div>
    </form>
  );
}
