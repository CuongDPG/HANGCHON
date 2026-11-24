"use client";

import { ShoppingBag } from "lucide-react";
import { IconLink } from "@/components/ui/icon-button";
import { useCartCount } from "@/lib/cart";

/** Nút giỏ ở đầu trang website, có số món trong giỏ (đọc từ trình duyệt). */
export function CartButton({ className }: { className?: string }) {
  const count = useCartCount();
  return <IconLink href="/gio-hang" label={count ? `Giỏ hàng, ${count} món` : "Giỏ hàng"} icon={<ShoppingBag />} count={count} className={className} />;
}
