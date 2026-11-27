"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { STORE_NAV, isStoreNavActive } from "@/lib/store-nav";

/*
 * Phần điều hướng cần biết đường dẫn hiện tại. Với cacheComponents, usePathname() ở route động là dữ liệu
 * theo request → bản `...Active` được bọc trong <Suspense>, fallback là bản không tô mục nào (pathname = null).
 */

export function StoreHeaderNav({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Mục chính" className="ml-auto hidden items-center gap-1 md:flex">
      {STORE_NAV.map((item) => {
        const active = pathname !== null && isStoreNavActive(item.href, pathname);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative rounded-md px-3 py-2 text-[15px] transition-colors hover:text-ink",
              active ? "font-semibold text-ink after:absolute after:inset-x-3 after:-bottom-[9px] after:h-0.5 after:bg-accent" : "text-ink-2",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function StoreHeaderNavActive() {
  return <StoreHeaderNav pathname={usePathname()} />;
}

export function StoreTabBarList({ pathname }: { pathname: string | null }) {
  return (
    <ul className="grid h-tabbar grid-cols-6">
      {STORE_NAV.map((item) => {
        const active = pathname !== null && isStoreNavActive(item.href, pathname);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex h-full flex-col items-center justify-center gap-1 text-[11.5px] leading-none transition-colors",
                active ? "font-semibold text-accent" : "text-ink-2",
              )}
            >
              {active ? <span aria-hidden className="absolute inset-x-5 top-0 h-0.5 bg-accent" /> : null}
              <Icon className="size-[22px]" strokeWidth={active ? 2.2 : 1.8} aria-hidden />
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function StoreTabBarListActive() {
  return <StoreTabBarList pathname={usePathname()} />;
}
