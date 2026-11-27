"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { PageHeader, TabLinks } from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";

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

/**
 * Đầu mỗi trang Cài đặt: tiêu đề «Cài đặt» + tab theo route (tầng 2; 8 mục > 5 nên không lên hàng tiêu đề).
 * Thanh tab cuộn ngang trên điện thoại; người phụ giúp không thấy mục `owner`.
 */
export function SettingsHeader({ actions }: { actions?: ReactNode }) {
  const path = usePathname();
  const { user } = useSession();
  const tabs = SETTINGS_TABS.filter((t) => !("owner" in t) || !user || isOwner(user));
  const active = tabs.find((t) => path === t.href || path.startsWith(`${t.href}/`))?.href ?? "";
  return (
    <>
      <PageHeader title="Cài đặt" actions={actions} />
      <TabLinks aria-label="Mục cài đặt" items={tabs.map((t) => ({ key: t.href, href: t.href, label: t.label }))} active={active} />
    </>
  );
}
