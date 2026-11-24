"use client";

import { ShoppingBag, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { Badge, ButtonLink, Card, DataList, EmptyState, IconButton, ImageBox, Money, PageHeader, SkeletonList } from "@/components/ui";
import { useQuote } from "@/lib/api/orders";
import { cartSubtotal, groupByDrop, removeFromCart, setCartQuantity, useCart, useIsClient, type CartItem } from "@/lib/cart";
import { QuantityStepper } from "./quantity-stepper";

/** Giỏ hàng (e4): món theo đợt, đổi số lượng, kiểm suất còn lại với máy chủ. */
export function CartScreen() {
  const items = useCart();
  const hydrated = useIsClient();
  const lines = useMemo(() => items.map((i) => ({ product_id: i.productId, variant_id: i.variantId ?? null, drop_id: i.dropId ?? null, quantity: i.quantity })), [items]);
  const quote = useQuote({ items: lines });
  const byKey = new Map<string, { problem: string | null; price: number }>();
  quote.data?.lines.forEach((l, idx) => {
    const item = items[idx];
    if (item) byKey.set(item.key, { problem: l.problem, price: l.unit_price_vnd });
  });
  const groups = groupByDrop(items);
  const dropGroups = groups.filter((g) => g.dropId);
  const firstDrop = dropGroups[0]?.dropId;

  if (!hydrated) return <SkeletonList rows={2} />;

  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Giỏ hàng" />
        <EmptyState
          icon={<ShoppingBag />}
          title="Giỏ đang trống"
          description="Chọn món trên kệ hoặc trong đợt đang mở. Không cần tạo tài khoản để đặt."
          action={
            <>
              <ButtonLink href="/">Xem kệ hàng</ButtonLink>
              <ButtonLink href="/dot" variant="secondary">
                Đợt đang mở
              </ButtonLink>
            </>
          }
        />
      </div>
    );
  }

  const subtotal = quote.data ? quote.data.lines.reduce((s, l) => s + l.line_total_vnd, 0) : cartSubtotal(items);
  return (
    <div className="flex flex-col gap-6 md:grid md:grid-cols-[1fr_20rem] md:items-start md:gap-8">
      <div className="flex flex-col gap-5">
        <PageHeader title="Giỏ hàng" description="Giá và suất còn lại được kiểm lại lúc bạn đặt." />
        {groups.map((g) => (
          <section key={g.dropId ?? "stock"} className="flex flex-col gap-2" aria-label={g.label}>
            <div className="flex items-center gap-2">
              <h2 className="font-sans text-[15px] font-semibold">{g.label}</h2>
              {g.dropId ? <Badge tone="accent">Gom đơn</Badge> : null}
            </div>
            <ul className="flex flex-col gap-2">
              {g.items.map((i) => (
                <CartRow key={i.key} item={i} problem={byKey.get(i.key)?.problem ?? null} price={byKey.get(i.key)?.price ?? i.priceVnd} />
              ))}
            </ul>
          </section>
        ))}
      </div>
      <Card className="flex flex-col gap-3 md:sticky md:top-20">
        <DataList items={[{ label: "Tạm tính", value: <Money value={subtotal} /> }, { label: "Phí giao", value: <span className="text-ink-2">tính ở bước sau</span> }]} />
        {dropGroups.length > 1 ? (
          <p className="text-[14px] text-ink-2">Giỏ có món của {dropGroups.length} đợt. Mỗi đơn đặt trong một đợt, bạn đặt lần lượt nhé.</p>
        ) : null}
        <ButtonLink href={firstDrop ? `/dat-hang?dot=${encodeURIComponent(firstDrop)}` : "/dat-hang"} block size="lg">
          Đặt hàng
        </ButtonLink>
        <Link href="/" className="text-center text-[14px] text-accent">
          Chọn thêm món
        </Link>
      </Card>
    </div>
  );
}

function CartRow({ item, problem, price }: { item: CartItem; problem: string | null; price: number }) {
  return (
    <li className="flex gap-3 rounded-md border border-line bg-surface p-3">
      <Link href={`/san-pham/${encodeURIComponent(item.slug)}`} className="w-16 shrink-0">
        <ImageBox src={item.imageUrl} alt="" ratio="1/1" />
      </Link>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-start justify-between gap-2">
          <Link href={`/san-pham/${encodeURIComponent(item.slug)}`} className="min-w-0 text-[15px] leading-snug font-semibold [text-wrap:pretty]">
            {item.name}
          </Link>
          <IconButton label={`Bỏ ${item.name} khỏi giỏ`} icon={<Trash2 />} size="sm" onClick={() => removeFromCart(item.key)} className="-mt-1 -mr-1 text-ink-2" />
        </div>
        <div className="flex items-center justify-between gap-2">
          <QuantityStepper value={item.quantity} onChange={(q) => setCartQuantity(item.key, q)} size="sm" />
          <Money value={price * item.quantity} className="font-semibold" />
        </div>
        {problem ? <p className="text-[13px] text-seal">{problem}</p> : null}
      </div>
    </li>
  );
}
