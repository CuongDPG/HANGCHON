"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LogOut, Monitor, Moon, Palette, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Brand } from "@/components/layout/brand";
import { useLogout, type SessionUser } from "@/lib/api/auth";
import { api, type Paginated } from "@/lib/api/client";
import { controlKeys, type ApprovalItem } from "@/lib/api/control";
import { cn } from "@/lib/cn";
import { DESK_NAV, DESK_PUBLIC_ROUTES, type DeskNavItem } from "@/lib/desk-nav";
import { useThemePreference } from "@/lib/use-theme";
import type { ThemePreference } from "@/lib/theme";

/**
 * Hàng menu trên cùng của bàn làm việc (máy tính, ≥ md). Điện thoại dùng thanh tab dưới + «Thêm» (desk-shell).
 * Các khu hiện thẳng trên hàng: TOP_KEYS (theo thứ tự trong desk-nav). Mọi khu khác desk-nav khai báo → menu «Thêm».
 * Hàng hẹp không đủ chỗ thì các mục cuối tự dồn vào «Thêm» (đo bề rộng thật, không xuống dòng, không cuộn ngang).
 */
const TOP_KEYS = ["today", "sourcing", "selection", "content", "customers", "orders", "approvals"];
const TOP_NAV = DESK_NAV.filter((i) => TOP_KEYS.includes(i.key));
const MORE_NAV = DESK_NAV.filter((i) => !TOP_KEYS.includes(i.key));

/** Lề ngang của hàng menu = lề của nội dung (MAIN_CLASS) để logo thẳng mép nội dung. */
export const DESK_FRAME = "mx-auto w-full max-w-[120rem] md:px-8"; // bàn làm việc ưu tiên máy tính: dùng gần hết màn rộng (tới 1920px)

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
        <nav aria-label="Điều hướng" className="relative ml-2 flex min-w-0 flex-1 items-center">
          <div ref={navRef} className="flex min-w-0 flex-1 items-center overflow-hidden">
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
        <ThemeButton />
        <AccountMenu user={user} />
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

function CountPill({ count, label }: { count: number; label?: string }) {
  return (
    <span
      aria-label={label}
      className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-seal px-1 text-[11px] leading-none font-bold text-white tabular-nums dark:text-paper"
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

const THEME_NEXT: Record<ThemePreference, ThemePreference> = { system: "light", light: "dark", dark: "system" };
const THEME_LABEL: Record<ThemePreference, string> = { system: "theo máy", light: "sáng", dark: "tối" };

function ThemeButton() {
  const [pref, setPref] = useThemePreference();
  const Icon = pref === "dark" ? Moon : pref === "light" ? Sun : Monitor;
  const label = `Giao diện: ${THEME_LABEL[pref]} (bấm để đổi sang ${THEME_LABEL[THEME_NEXT[pref]]})`;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => setPref(THEME_NEXT[pref])}
      className="grid size-9 shrink-0 place-items-center rounded-md text-ink-2 transition-colors hover:bg-soft-2 hover:text-ink"
    >
      <Icon className="size-[18px]" aria-hidden />
    </button>
  );
}

function AccountMenu({ user }: { user?: SessionUser | null }) {
  const logout = useLogout();
  return (
    <Menu
      label={`Tài khoản${user?.name ? ` · ${user.name}` : ""}`}
      align="end"
      trigger={() => (
        <span className="grid size-9 place-items-center rounded-full bg-accent-wash text-[13px] font-bold text-accent">{initial(user?.name)}</span>
      )}
    >
      <div className="border-b border-line px-3 pt-1.5 pb-2.5" role="none">
        <p className="truncate text-sm font-semibold">{user?.name ?? "—"}</p>
        <p className="truncate text-[12px] text-ink-2">{user?.email}</p>
      </div>
      <MenuLink href="/desk/cai-dat" icon={<Settings />}>
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

/* ---------- menu thả xuống (WAI-ARIA menu button) ---------- */

const MENU_ITEM =
  "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[15px] whitespace-nowrap text-ink outline-none hover:bg-soft-2 focus-visible:bg-soft-2 focus-visible:outline-none disabled:opacity-50 [&_svg]:size-[18px] [&_svg]:shrink-0 [&_svg]:text-ink-2";

function MenuLink({
  href,
  icon,
  active,
  separator,
  count,
  children,
}: {
  href: string;
  icon: ReactNode;
  active?: boolean;
  separator?: boolean;
  count?: number;
  children: ReactNode;
}) {
  return (
    <>
      {separator ? <div role="separator" className="my-1 border-t border-line" /> : null}
      <Link
        href={href}
        role="menuitem"
        tabIndex={-1}
        aria-current={active ? "page" : undefined}
        className={cn(MENU_ITEM, active && "bg-accent-wash font-semibold text-accent [&_svg]:text-accent")}
      >
        {icon}
        <span className="flex-1">{children}</span>
        {count ? <CountPill count={count} /> : null}
      </Link>
    </>
  );
}

function Menu({
  label,
  trigger,
  align = "start",
  children,
}: {
  label: string;
  trigger: (open: boolean) => ReactNode;
  align?: "start" | "end";
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left?: number; right?: number }>({ top: 0 });

  const items = () => Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? []);
  const focusAt = (i: number) => {
    const list = items();
    if (list.length) list[(i + list.length) % list.length].focus();
  };
  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) buttonRef.current?.focus();
  };
  const openMenu = (focus: "first" | "last" | null) => {
    // menu vẽ ở <body> (portal), đặt theo vị trí nút: hàng menu có overflow-hidden + backdrop-filter sẽ cắt nó
    const r = buttonRef.current!.getBoundingClientRect();
    setPos(align === "end" ? { top: r.bottom + 6, right: window.innerWidth - r.right } : { top: r.bottom + 6, left: r.left });
    setOpen(true);
    if (focus) requestAnimationFrame(() => focusAt(focus === "first" ? 0 : -1));
  };

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!wrapRef.current?.contains(t) && !menuRef.current?.contains(t)) setOpen(false);
    };
    const onResize = () => setOpen(false);
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  function onMenuKey(e: KeyboardEvent<HTMLDivElement>) {
    const list = items();
    const i = list.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") focusAt(i + 1);
    else if (e.key === "ArrowUp") focusAt(i - 1);
    else if (e.key === "Home") focusAt(0);
    else if (e.key === "End") focusAt(-1);
    else if (e.key === "Escape") close(true);
    else if (e.key === "Tab") close(true); // menu nằm cuối <body>: trả tiêu điểm về nút thay vì rơi ra cuối trang
    else return;
    e.preventDefault();
  }

  return (
    <div ref={wrapRef} className="shrink-0">
      <button
        ref={buttonRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openMenu(null))}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openMenu("first");
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            openMenu("last");
          } else if (e.key === "Escape" && open) {
            close(true);
          }
        }}
        className="flex items-center rounded-md"
      >
        {trigger(open)}
      </button>
      {open
        ? createPortal(
        <div
          ref={menuRef}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKey}
          // bấm một mục (link điều hướng / đăng xuất) thì đóng menu
          onClick={(e) => {
            if ((e.target as HTMLElement).closest('[role="menuitem"]')) setOpen(false);
          }}
          style={pos}
          className="fixed z-30 flex max-h-[calc(100dvh-80px)] min-w-56 flex-col overflow-y-auto rounded-md border border-line bg-surface p-1.5 shadow-pop"
        >
          {children}
        </div>,
          document.body,
        )
        : null}
    </div>
  );
}
