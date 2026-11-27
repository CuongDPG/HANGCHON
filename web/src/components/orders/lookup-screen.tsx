"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Card, DateTime, Input } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { storeOrdersApi } from "@/lib/api/orders";
import { rememberOrder, type RecentOrder } from "@/lib/cart";

const schema = z.object({
  phone: z.string().trim().min(8, "Nhập số điện thoại đã dùng khi đặt."),
  code: z.string().trim().min(3, "Nhập mã đơn, vd HC-48213."),
});
type FormValues = z.infer<typeof schema>;

/** Tra một đơn (e5) bằng số điện thoại + mã đơn, trong «Của tôi» → Đơn của tôi. */
export function OrderLookupForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { phone: "", code: "" } });

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    setPending(true);
    try {
      const r = await storeOrdersApi.lookup(v);
      rememberOrder({ code: r.code, token: r.token, placedAt: new Date().toISOString() });
      router.push(`/don/${encodeURIComponent(r.code)}?t=${encodeURIComponent(r.token)}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Chưa tra được, bạn thử lại nhé.");
      setPending(false);
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className="flex items-start gap-2 rounded-md bg-seal-wash px-3 py-2.5 text-[14px] text-seal">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {error}
        </p>
      ) : null}
      <Input label="Số điện thoại" type="tel" inputMode="tel" autoComplete="tel" error={errors.phone?.message} {...register("phone")} />
      <Input label="Mã đơn" placeholder="HC-48213" autoCapitalize="characters" error={errors.code?.message} {...register("code")} />
      <Button type="submit" size="lg" block variant="secondary" loading={pending} icon={<Search className="size-4" />}>
        Xem đơn
      </Button>
    </form>
  );
}

/** Đơn đặt trên máy này (localStorage): mở lại trang theo dõi không cần tra, kể cả khi chưa đăng nhập. */
export function RecentOrdersList({ orders, title = "Đơn đặt trên máy này" }: { orders: RecentOrder[]; title?: string }) {
  if (!orders.length) return null;
  return (
    <section className="flex flex-col gap-2" aria-label={title}>
      <h2 className="font-sans text-[15px] font-semibold">{title}</h2>
      {orders.map((o) => (
        <Card key={o.code} flush>
          <Link href={`/don/${encodeURIComponent(o.code)}?t=${encodeURIComponent(o.token)}`} className="flex items-center justify-between gap-3 p-3">
            <span className="font-semibold tabular-nums">{o.code}</span>
            <span className="text-[13px] text-ink-2">
              <DateTime value={o.placedAt} format="dayMonth" />
            </span>
          </Link>
        </Card>
      ))}
    </section>
  );
}
