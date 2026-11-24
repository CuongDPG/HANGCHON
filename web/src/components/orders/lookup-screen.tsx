"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Card, DateTime, Input, PageHeader } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { storeOrdersApi } from "@/lib/api/orders";
import { getRecentOrders, rememberOrder, useIsClient } from "@/lib/cart";

const schema = z.object({
  phone: z.string().trim().min(8, "Nhập số điện thoại đã dùng khi đặt."),
  code: z.string().trim().min(3, "Nhập mã đơn, vd HC-48213."),
});
type FormValues = z.infer<typeof schema>;

/** Tra cứu đơn (e5): số điện thoại + mã đơn. */
export function LookupScreen() {
  const router = useRouter();
  const isClient = useIsClient();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { phone: "", code: "" } });
  const recent = isClient ? getRecentOrders() : [];

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
    <div className="mx-auto flex w-full max-w-prose flex-col gap-6">
      <PageHeader title="Tra cứu đơn" description="Nhập số điện thoại và mã đơn (có trong tin nhắn xác nhận) để xem hành trình đơn." />
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {error ? (
          <p role="alert" className="flex items-start gap-2 rounded-md bg-seal-wash px-3 py-2.5 text-[14px] text-seal">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            {error}
          </p>
        ) : null}
        <Input label="Số điện thoại" type="tel" inputMode="tel" autoComplete="tel" error={errors.phone?.message} {...register("phone")} />
        <Input label="Mã đơn" placeholder="HC-48213" autoCapitalize="characters" error={errors.code?.message} {...register("code")} />
        <Button type="submit" size="lg" block loading={pending} icon={<Search className="size-4" />}>
          Xem đơn
        </Button>
      </form>
      {recent.length ? (
        <section className="flex flex-col gap-2">
          <h2 className="font-sans text-[15px] font-semibold">Đơn đặt trên máy này</h2>
          {recent.map((o) => (
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
      ) : null}
    </div>
  );
}
