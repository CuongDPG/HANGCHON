"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isOwner, useSession } from "@/lib/api/auth";
import { cn } from "@/lib/cn";

/** Các tab của Cài đặt (theo URL), xếp theo mức chị hay dùng. `owner`: người phụ giúp không thấy. */
export const SETTINGS_TABS = [
  { href: "/desk/cai-dat/cua-hang", label: "Cửa hàng" },
  { href: "/desk/cai-dat/mang-xa-hoi", label: "Mạng xã hội", owner: true },
  { href: "/desk/cai-dat/nguon-hang", label: "Nguồn hàng", owner: true },
  { href: "/desk/cai-dat/tich-hop", label: "Tích hợp" },
  { href: "/desk/cai-dat/ai", label: "AI", owner: true },
  { href: "/desk/cai-dat/nguoi-phu-giup", label: "Người phụ giúp", owner: true },
  { href: "/desk/cai-dat/tai-khoan", label: "Tài khoản" },
  { href: "/desk/cai-dat/sao-luu", label: "Sao lưu", owner: true },
] as const;

/** Trang vào mặc định của Cài đặt (/desk/cai-dat chuyển tới đây). */
export const SETTINGS_HOME = SETTINGS_TABS[0].href;

/** Thanh tab dưới tiêu đề mỗi trang Cài đặt — cùng kiểu thanh phụ của khu Sản phẩm (`DeskSubnav`). */
export function SettingsNav() {
  const path = usePathname();
  const { user } = useSession();
  const tabs = SETTINGS_TABS.filter((t) => !("owner" in t) || !user || isOwner(user));
  return (
    <nav aria-label="Mục cài đặt" className="-mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 [scrollbar-width:none] md:mx-0 md:px-0">
      {tabs.map((t) => {
        const on = path === t.href || path.startsWith(`${t.href}/`);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={on ? "page" : undefined}
            className={cn(
              "-mb-px shrink-0 border-b-2 px-3 py-2.5 text-[15px] whitespace-nowrap",
              on ? "border-accent font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink",
            )}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
