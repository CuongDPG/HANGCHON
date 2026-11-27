"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCartCount } from "@/lib/cart";
import { cn } from "@/lib/cn";
import { STORE_NAV, isStoreNavActive, type StoreNavItem } from "@/lib/store-nav";

/*
 * Phần điều hướng cần biết đường dẫn hiện tại. Với cacheComponents, usePathname() ở route động là dữ liệu
 * theo request → bản `...Active` được bọc trong <Suspense>, fallback là bản không tô mục nào (pathname = null).
 */

/** Số món trong giỏ (đọc từ trình duyệt) cho mục «Của tôi»; nhãn đọc màn hình ghi rõ số món. */
function useItemCount(item: StoreNavItem): number {
  const count = useCartCount();
  return item.cartCount ? count : 0;
}

function navLabel(item: StoreNavItem, count: number): string | undefined {
  return count ? `${item.label}, giỏ hàng ${count} món` : undefined;
}

function CountDot({ count, className }: { count: number; className?: string }) {
  if (!count) return null;
  return (
    <span
      aria-hidden
      className={cn(
        "grid h-[18px] min-w-[18px] place-items-center rounded-full bg-seal px-1 text-[11px] leading-none font-bold text-white tabular-nums dark:text-paper",
        className,
      )}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

function HeaderLink({ item, pathname }: { item: StoreNavItem; pathname: string | null }) {
  const active = pathname !== null && isStoreNavActive(item.href, pathname);
  const count = useItemCount(item);
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      aria-label={navLabel(item, count)}
      className={cn(
        "relative flex items-center gap-1.5 rounded-md px-3 py-2 text-[15px] transition-colors hover:text-ink",
        active ? "font-semibold text-ink after:absolute after:inset-x-3 after:-bottom-[9px] after:h-0.5 after:bg-accent" : "text-ink-2",
      )}
    >
      {item.label}
      <CountDot count={count} />
    </Link>
  );
}

function TabLink({ item, pathname }: { item: StoreNavItem; pathname: string | null }) {
  const active = pathname !== null && isStoreNavActive(item.href, pathname);
  const count = useItemCount(item);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      aria-label={navLabel(item, count)}
      className={cn(
        "relative flex h-full flex-col items-center justify-center gap-1 text-[11.5px] leading-none transition-colors",
        active ? "font-semibold text-accent" : "text-ink-2",
      )}
    >
      {active ? <span aria-hidden className="absolute inset-x-5 top-0 h-0.5 bg-accent" /> : null}
      <span className="relative">
        <Icon className="size-[22px]" strokeWidth={active ? 2.2 : 1.8} aria-hidden />
        <CountDot count={count} className="absolute -top-1.5 -right-2.5" />
      </span>
      {item.label}
    </Link>
  );
}

export function StoreHeaderNav({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Mục chính" className="ml-auto hidden items-center gap-1 md:flex">
      {STORE_NAV.map((item) => (
        <HeaderLink key={item.href} item={item} pathname={pathname} />
      ))}
    </nav>
  );
}

export function StoreHeaderNavActive() {
  return <StoreHeaderNav pathname={usePathname()} />;
}

export function StoreTabBarList({ pathname }: { pathname: string | null }) {
  return (
    <ul className="grid h-tabbar grid-cols-5">
      {STORE_NAV.map((item) => (
        <li key={item.href}>
          <TabLink item={item} pathname={pathname} />
        </li>
      ))}
    </ul>
  );
}

export function StoreTabBarListActive() {
  return <StoreTabBarList pathname={usePathname()} />;
}
