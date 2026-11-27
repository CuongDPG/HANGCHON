"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LogOut, Palette, Settings } from "lucide-react";
import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";
import { Brand } from "@/components/layout/brand";
import { CountPill, Menu, MENU_ITEM, MenuLink } from "@/components/ui/menu";
import { useLogout, type SessionUser } from "@/lib/api/auth";
import { api, type Paginated } from "@/lib/api/client";
import { controlKeys, type ApprovalItem } from "@/lib/api/control";
import { cn } from "@/lib/cn";
import { DESK_NAV, DESK_PUBLIC_ROUTES, type DeskNavItem } from "@/lib/desk-nav";

/**
 * Hàng menu trên cùng của bàn làm việc (máy tính, ≥ md). Điện thoại dùng thanh tab dưới + «Thêm» (desk-shell).
 * Logo bên trái; mục chính + «Thêm» + ảnh đại diện là MỘT cụm canh phải.
 * Các khu hiện thẳng trên hàng: TOP_KEYS (theo thứ tự trong desk-nav). Mọi khu khác desk-nav khai báo → menu «Thêm»,
 * trừ Cài đặt: Cài đặt chỉ nằm ở menu tài khoản (ảnh đại diện) cùng tên/email, Bộ giao diện, Đăng xuất.
 * Sáng/tối đổi ở Cài đặt → Tài khoản → Giao diện (hoặc Bộ giao diện), không có nút riêng trên hàng.
 * Hàng hẹp không đủ chỗ thì các mục cuối tự dồn vào «Thêm» (đo bề rộng thật, không xuống dòng, không cuộn ngang).
 */
const TOP_KEYS = ["today", "sourcing", "selection", "products", "content", "customers", "orders", "approvals"];
const ACCOUNT_KEYS = ["settings"];
const TOP_NAV = DESK_NAV.filter((i) => TOP_KEYS.includes(i.key));
const MORE_NAV = DESK_NAV.filter((i) => !TOP_KEYS.includes(i.key) && !ACCOUNT_KEYS.includes(i.key));

/** Lề ngang của hàng menu = lề của nội dung (MAIN_CLASS) để logo thẳng mép nội dung. */
export const DESK_FRAME = "w-full md:px-6"; // bàn làm việc ưu tiên máy tính: phủ hết bề ngang màn hình

const ITEM = "relative flex h-header shrink-0 items-center gap-1.5 px-3 text-[15px] whitespace-nowrap transition-colors";
const ACTIVE_MARK = "after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-accent";

export function DeskTopBar({ activeKey, user, ready }: { activeKey?: string; user?: SessionUser | null; ready: boolean }) {
  const pending = useQuery({
    queryKey: controlKeys.approvals({ status: ["pending"], size: 1 }),
    queryFn: () => api.get<Paginated<ApprovalItem>>("/api/desk/control/approvals", { query: { status: ["pending"], size: 1 } }),
    enabled: ready,
    meta: { silentError: true },
  }).data?.total;

  // số mục chính hiện thẳng; còn lại dồn vào «Thêm». Máy chủ dựng đủ cả (khung cắt phần thừa tới khi đo xong).
  const [fit, setFit] = useState(TOP_NAV.length);
  const navRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const nav = navRef.current;
    const measure = measureRef.current;
    if (!nav || !measure) return;
    const calc = () => {
      const widths = Array.from(measure.children, (c) => c.getBoundingClientRect().width);
      const more = widths.pop() ?? 0; // phần tử cuối = nút «Thêm»
      let used = more;
      let n = 0;
      for (const w of widths) {
        if (used + w > nav.clientWidth) break;
        used += w;
        n++;
      }
      setFit(n);
    };
    calc();
    const ro = new ResizeObserver(calc);
    ro.observe(nav);
    ro.observe(measure);
    return () => ro.disconnect();
  }, []);

  const shown = TOP_NAV.slice(0, fit);
  const overflow = TOP_NAV.slice(fit);
  const moreItems = [...overflow, ...MORE_NAV];
  const moreActive = moreItems.some((i) => i.key === activeKey);
  const pendingInMore = !!pending && overflow.some((i) => i.key === "approvals");

  return (
    <header className="sticky top-0 z-20 hidden border-b border-line bg-paper/92 backdrop-blur-md md:block">
      <div className={cn(DESK_FRAME, "flex h-header items-center gap-2")}>
        <Link href="/desk" aria-label="Hàng Chọn · Bàn làm việc" className="-ml-1 shrink-0 rounded-md px-1 py-1">
          <Brand />
        </Link>
        <nav aria-label="Điều hướng" className="relative ml-4 flex min-w-0 flex-1 items-center">
          <div ref={navRef} className="flex min-w-0 flex-1 items-center justify-end overflow-hidden">
            {shown.map((item) => (
              <TopLink key={item.key} item={item} active={item.key === activeKey} count={item.key === "approvals" ? pending : undefined} />
            ))}
            <Menu
              label={pendingInMore ? `Thêm, ${pending} việc chờ duyệt` : "Thêm"}
              trigger={(open) => (
                <span className={cn(ITEM, moreActive ? cn("font-semibold text-ink", ACTIVE_MARK) : "text-ink-2 hover:text-ink", open && "text-ink")}>
                  Thêm
                  {pendingInMore ? <CountPill count={pending!} /> : null}
                  <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
                </span>
              )}
            >
              {moreItems.map((item, i) => (
                <MenuLink
                  key={item.key}
                  href={item.href}
                  active={item.key === activeKey}
                  icon={<item.icon />}
                  separator={i === overflow.length && overflow.length > 0}
                  count={item.key === "approvals" ? pending : undefined}
                >
                  {item.label}
                </MenuLink>
              ))}
            </Menu>
          </div>
          {/* hàng đo bề rộng (ẩn): cùng kiểu chữ với mục thật, kèm nút «Thêm» ở cuối */}
          <div ref={measureRef} aria-hidden className="pointer-events-none invisible absolute top-0 left-0 flex h-0 overflow-hidden">
            {TOP_NAV.map((item) => (
              <span key={item.key} className={cn(ITEM, "font-semibold")}>
                {item.label}
                {item.key === "approvals" && pending ? <CountPill count={pending} /> : null}
              </span>
            ))}
            <span className={cn(ITEM, "font-semibold")}>
              Thêm
              {pending ? <CountPill count={pending} /> : null}
              <ChevronDown className="size-4" />
            </span>
          </div>
        </nav>
        <AccountMenu user={user} active={!!activeKey && ACCOUNT_KEYS.includes(activeKey)} />
      </div>
    </header>
  );
}

function TopLink({ item, active, count }: { item: DeskNavItem; active: boolean; count?: number }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(ITEM, active ? cn("font-semibold text-ink", ACTIVE_MARK) : "text-ink-2 hover:text-ink")}
    >
      {item.label}
      {count ? <CountPill count={count} label={`${count} việc chờ duyệt`} /> : null}
    </Link>
  );
}

function AccountMenu({ user, active }: { user?: SessionUser | null; active: boolean }) {
  const logout = useLogout();
  return (
    <Menu
      label={`Tài khoản${user?.name ? ` · ${user.name}` : ""}`}
      align="end"
      trigger={(open) => (
        <span
          className={cn(
            "ml-1 grid size-9 place-items-center rounded-full bg-accent-wash text-[13px] font-bold text-accent",
            (active || open) && "ring-2 ring-accent ring-offset-2 ring-offset-paper",
          )}
        >
          {initial(user?.name)}
        </span>
      )}
    >
      <div className="border-b border-line px-3 pt-1.5 pb-2.5" role="none">
        <p className="truncate text-sm font-semibold">{user?.name ?? "—"}</p>
        <p className="truncate text-[12px] text-ink-2">{user?.email}</p>
      </div>
      <MenuLink href="/desk/cai-dat" icon={<Settings />} active={active}>
        Cài đặt
      </MenuLink>
      <MenuLink href={DESK_PUBLIC_ROUTES.kit} icon={<Palette />}>
        Bộ giao diện
      </MenuLink>
      <button
        type="button"
        role="menuitem"
        tabIndex={-1}
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
        className={MENU_ITEM}
      >
        <LogOut aria-hidden />
        Đăng xuất
      </button>
    </Menu>
  );
}

/** Chữ cái đầu của tên gọi (từ cuối, kiểu tên Việt: «Nguyễn Thu Hà» → «H»). */
function initial(name?: string) {
  const last = name?.trim().split(/\s+/).pop();
  return last ? last[0].toUpperCase() : "·";
}
