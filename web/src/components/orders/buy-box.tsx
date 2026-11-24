"use client";

import { Hourglass, ShoppingBag } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Money, notifySuccess } from "@/components/ui";
import { addToCart } from "@/lib/cart";
import { cn } from "@/lib/cn";
import { QuantityStepper } from "./quantity-stepper";

export type BuyBoxProps = {
  productId: string;
  slug: string;
  name: string;
  priceVnd: number;
  imageUrl?: string;
  /** Có = đặt trong đợt gom đang mở; không = hàng giữ sẵn. */
  dropId?: string;
  /** Vd. «Đợt 12 · chốt 28/11». */
  dropLabel?: string;
  /** Số suất còn lại của đợt / số cái còn trong kho (không truyền = không giới hạn). */
  slotsLeft?: number;
  available: boolean;
};

/**
 * Khối mua trên trang sản phẩm: chọn số lượng, thêm vào giỏ hoặc đặt ngay (đặt trong đợt nếu có `dropId`).
 * Giỏ lưu ở trình duyệt; trang đặt hàng hỏi lại máy chủ giá và suất thật.
 */
export function BuyBox({ productId, slug, name, priceVnd, imageUrl, dropId, dropLabel, slotsLeft, available }: BuyBoxProps) {
  const router = useRouter();
  const [qty, setQty] = useState(1);
  const max = Math.max(1, Math.min(99, slotsLeft ?? 99));
  const soldOut = !available || slotsLeft === 0;

  function add() {
    addToCart({ productId, slug, name, priceVnd, imageUrl, dropId, dropLabel }, qty);
  }

  return (
    <section aria-label="Đặt mua" className="flex flex-col gap-3 rounded-md border border-line bg-surface p-4">
      <div className="flex items-baseline justify-between gap-3">
        <Money value={priceVnd} className="font-display text-[24px] font-extrabold" />
        {dropId ? (
          <Badge tone="accent" icon={<Hourglass />}>
            {dropLabel ?? "Đặt trong đợt"}
          </Badge>
        ) : (
          <Badge tone="success">Có sẵn</Badge>
        )}
      </div>
      {slotsLeft !== undefined && !soldOut ? (
        <p className={cn("text-[14px]", slotsLeft <= 5 ? "font-semibold text-seal" : "text-ink-2")}>
          {dropId ? `Còn ${slotsLeft} suất trong đợt` : `Còn ${slotsLeft} cái`}
        </p>
      ) : null}
      {soldOut ? (
        <Button block disabled>
          {dropId ? "Đợt này đã hết suất" : "Tạm hết hàng"}
        </Button>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[15px] text-ink-2">Số lượng</span>
            <QuantityStepper value={Math.min(qty, max)} onChange={setQty} max={max} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="secondary"
              icon={<ShoppingBag className="size-4" />}
              onClick={() => {
                add();
                notifySuccess(`Đã thêm ${qty} ${name} vào giỏ`);
              }}
            >
              Thêm vào giỏ
            </Button>
            <Button
              onClick={() => {
                add();
                router.push(dropId ? `/dat-hang?dot=${encodeURIComponent(dropId)}` : "/dat-hang");
              }}
            >
              {dropId ? "Đặt trong đợt" : "Đặt ngay"}
            </Button>
          </div>
          {dropId ? <p className="text-[13px] text-ink-2">Không cần tạo tài khoản. Chuyển khoản bằng mã QR hoặc trả khi nhận.</p> : null}
        </>
      )}
    </section>
  );
}
