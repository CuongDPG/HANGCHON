"use client";

import { ShoppingBag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Money } from "@/components/ui/money";

/**
 * BẢN TẠM của lát cắt store — khi gộp sẽ thay bằng bản của agent orders (cùng đường dẫn, cùng props).
 * Chỉ hiện giá và một nút «Đặt hàng» bị vô hiệu.
 */
export type BuyBoxProps = {
  productId: string;
  slug: string;
  name: string;
  priceVnd: number;
  imageUrl?: string;
  dropId?: string;
  dropLabel?: string;
  slotsLeft?: number;
  available: boolean;
};

export function BuyBox({ priceVnd, dropLabel, slotsLeft, available }: BuyBoxProps) {
  return (
    <div className="flex items-center gap-3">
      <div className="min-w-0 flex-1">
        <Money value={priceVnd} className="font-display text-[22px] font-bold" />
        {dropLabel ? (
          <p className="truncate text-[13px] text-ink-2">
            {dropLabel}
            {slotsLeft !== undefined ? ` · còn ${slotsLeft} suất` : null}
          </p>
        ) : null}
      </div>
      <Button disabled icon={<ShoppingBag className="size-4" />} title={available ? "Đặt hàng sắp có" : "Chưa mở bán"}>
        Đặt hàng
      </Button>
    </div>
  );
}
