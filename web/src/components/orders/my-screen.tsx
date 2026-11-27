"use client";

import { CircleAlert, LogOut, Package } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Badge, Button, Card, DateTime, EmptyState, Input, Money, PageHeader, SkeletonList, Tabs } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import {
  useCustomerLogout,
  useCustomerMe,
  useMyOrders,
  useRequestLoginCode,
  useVerifyLoginCode,
  type CustomerMe,
  type MyOrder,
  type OrderStatus,
} from "@/lib/api/orders";
import { getRecentOrders, useCartCount, useIsClient } from "@/lib/cart";
import { CartScreen } from "./cart-screen";
import { OrderLookupForm, RecentOrdersList } from "./lookup-screen";

type Tab = "gio" | "don";

/** «Của tôi» (e4, e5): tab «Giỏ hàng» và «Đơn của tôi», tab ghi vào URL (`?tab=don`). */
export function MyScreen() {
  const router = useRouter();
  const tab: Tab = useSearchParams().get("tab") === "don" ? "don" : "gio";
  const count = useCartCount();
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Của tôi" />
      <Tabs<Tab>
        aria-label="Của tôi"
        value={tab}
        onChange={(v) => router.replace(v === "don" ? "/cua-toi?tab=don" : "/cua-toi", { scroll: false })}
        items={[
          { value: "gio", label: "Giỏ hàng", count: count || undefined },
          { value: "don", label: "Đơn của tôi" },
        ]}
      />
      {tab === "gio" ? <CartScreen /> : <MyOrders />}
    </div>
  );
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Chưa làm được, bạn thử lại nhé.";
}

function Alert({ children }: { children: string }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-md bg-seal-wash px-3 py-2.5 text-[14px] text-seal">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      {children}
    </p>
  );
}

/** Đơn của tôi: đã đăng nhập → mọi đơn; chưa → đơn đặt trên máy này, đăng nhập bằng mã, tra một đơn bằng mã đơn. */
function MyOrders() {
  const me = useCustomerMe();
  const isClient = useIsClient();
  const recent = isClient ? getRecentOrders() : [];
  if (me.isPending || !isClient) return <SkeletonList rows={2} />;
  if (me.data?.signed_in) return <SignedIn me={me.data} recentCodes={recent} />;
  return (
    <div className="flex flex-col gap-6 md:grid md:grid-cols-2 md:items-start md:gap-8">
      <div className="flex flex-col gap-6">
        <RecentOrdersList orders={recent} />
        <Card className="flex flex-col gap-3">
          <h2 className="font-sans text-[16px] font-semibold">Đăng nhập để xem mọi đơn</h2>
          <p className="text-[14px] text-ink-2">Không cần mật khẩu: nhập số điện thoại hoặc email đã dùng khi đặt, mình gửi mã 6 chữ số để bạn đăng nhập.</p>
          <SignInForm />
        </Card>
      </div>
      <section className="flex flex-col gap-3" aria-labelledby="tra-don">
        <h2 id="tra-don" className="font-sans text-[16px] font-semibold">
          Tra một đơn bằng mã đơn
        </h2>
        <p className="text-[14px] text-ink-2">Nhập số điện thoại và mã đơn (có trong tin nhắn xác nhận) để xem hành trình đơn.</p>
        <OrderLookupForm />
      </section>
    </div>
  );
}

function SignInForm() {
  const [contact, setContact] = useState("");
  const [code, setCode] = useState("");
  const send = useRequestLoginCode();
  const verify = useVerifyLoginCode();
  const sent = send.isSuccess ? send.data : null;

  async function onSend(e?: FormEvent) {
    e?.preventDefault();
    verify.reset();
    setCode("");
    if (contact.trim().length >= 3) await send.mutateAsync(contact.trim()).catch(() => undefined);
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    if (code.trim()) await verify.mutateAsync({ contact: contact.trim(), code: code.trim() }).catch(() => undefined);
  }

  if (!sent) {
    return (
      <form onSubmit={onSend} noValidate className="flex flex-col gap-3">
        {send.isError ? <Alert>{errorText(send.error)}</Alert> : null}
        <Input
          label="Số điện thoại hoặc email"
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          autoComplete="username"
          maxLength={254}
        />
        <Button type="submit" block loading={send.isPending} disabled={contact.trim().length < 3}>
          Gửi mã
        </Button>
      </form>
    );
  }
  return (
    <form onSubmit={onVerify} noValidate className="flex flex-col gap-3">
      <p role="status" className="text-[14px]">
        {sent.message}
      </p>
      {sent.dev_code ? <p className="text-[13px] text-ink-2">Bản chạy thử chưa nối kênh gửi tin: mã là {sent.dev_code}.</p> : null}
      {verify.isError ? <Alert>{errorText(verify.error)}</Alert> : null}
      <Input
        label="Mã 6 chữ số"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
      />
      <Button type="submit" block loading={verify.isPending} disabled={code.length < 6}>
        Đăng nhập
      </Button>
      <div className="flex flex-wrap justify-between gap-2 text-[14px]">
        <button type="button" className="text-accent" onClick={() => void onSend()} disabled={send.isPending}>
          Gửi lại mã
        </button>
        <button
          type="button"
          className="text-accent"
          onClick={() => {
            send.reset();
            verify.reset();
            setCode("");
          }}
        >
          Đổi số điện thoại / email
        </button>
      </div>
    </form>
  );
}

const STATUS_TONE: Partial<Record<OrderStatus, "warning" | "success" | "neutral">> = {
  pending_payment: "warning",
  delivered: "success",
  completed: "success",
  cancelled: "neutral",
  returned: "neutral",
};

function SignedIn({ me, recentCodes }: { me: CustomerMe; recentCodes: ReturnType<typeof getRecentOrders> }) {
  const orders = useMyOrders(true);
  const logout = useCustomerLogout();
  const items = orders.data?.items ?? [];
  const known = new Set(items.map((o) => o.code));
  const others = orders.data ? recentCodes.filter((o) => !known.has(o.code)) : [];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 text-[14px] text-ink-2">
          Đang đăng nhập: <span className="font-semibold text-ink">{me.contact}</span>
        </p>
        <Button variant="ghost" size="sm" icon={<LogOut className="size-4" />} loading={logout.isPending} onClick={() => logout.mutate()}>
          Đăng xuất
        </Button>
      </div>
      {orders.isPending ? (
        <SkeletonList rows={3} />
      ) : orders.isError ? (
        <EmptyState tone="error" title="Chưa tải được đơn" description={errorText(orders.error)} />
      ) : items.length ? (
        <ul className="flex flex-col gap-2">
          {items.map((o) => (
            <OrderRow key={o.code} o={o} />
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={<Package />}
          title="Chưa thấy đơn nào"
          description={
            me.kind === "email"
              ? "Đơn đặt trên website gắn với số điện thoại. Bạn đăng xuất rồi đăng nhập bằng số điện thoại đã dùng khi đặt nhé."
              : "Số này chưa có đơn nào ở Hàng Chọn."
          }
        />
      )}
      <RecentOrdersList orders={others} title="Đơn khác đặt trên máy này" />
    </div>
  );
}

function OrderRow({ o }: { o: MyOrder }) {
  return (
    <li>
      <Card flush>
        <Link href={`/don/${encodeURIComponent(o.code)}?t=${encodeURIComponent(o.token)}`} className="flex flex-col gap-1.5 p-3">
          <span className="flex items-center justify-between gap-2">
            <span className="font-semibold tabular-nums">{o.code}</span>
            <Badge tone={STATUS_TONE[o.status] ?? "accent"}>{o.status_label}</Badge>
          </span>
          <span className="text-[14px] [text-wrap:pretty] text-ink-2">{o.items_summary}</span>
          <span className="flex items-center justify-between gap-2 text-[13px] text-ink-2">
            <DateTime value={o.placed_at} format="date" />
            <Money value={o.total_vnd} className="text-[15px] font-semibold text-ink" />
          </span>
        </Link>
      </Card>
    </li>
  );
}
