import { ShoppingBag } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import { Brand } from "@/components/layout/brand";
import { IconLink } from "@/components/ui/icon-button";
import { StoreHeaderNav, StoreHeaderNavActive } from "./store-nav-links";

/** Đầu trang website: tên + giỏ; trên máy tính có thêm hàng menu. */
export function StoreHeader({ cartCount = 0 }: { cartCount?: number }) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-paper/92 pt-safe backdrop-blur-md">
      <div className="mx-auto flex h-header max-w-page items-center gap-4 px-4 md:px-6">
        <Link href="/" aria-label="Hàng Chọn — về kệ hàng" className="-ml-1 rounded-md px-1 py-1">
          <Brand />
        </Link>
        <Suspense fallback={<StoreHeaderNav pathname={null} />}>
          <StoreHeaderNavActive />
        </Suspense>
        <IconLink href="/gio-hang" label="Giỏ hàng" icon={<ShoppingBag />} count={cartCount} className="-mr-2 ml-auto md:ml-2" />
      </div>
    </header>
  );
}
