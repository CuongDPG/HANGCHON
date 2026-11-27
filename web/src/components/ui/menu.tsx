"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

/* ---------- menu thả xuống (WAI-ARIA menu button) ----------
 * Dùng cho menu «Thêm»/tài khoản ở hàng menu trên và menu «⋯» trên đầu trang desk (DeskMoreMenu). */

export const MENU_ITEM =
  "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[15px] whitespace-nowrap text-ink outline-none hover:bg-soft-2 focus-visible:bg-soft-2 focus-visible:outline-none disabled:opacity-50 [&_svg]:size-[18px] [&_svg]:shrink-0 [&_svg]:text-ink-2";

export function MenuLink({
  href,
  icon,
  active,
  separator,
  count,
  target,
  children,
}: {
  href: string;
  target?: string;
  icon?: ReactNode;
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
        target={target}
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

export function Menu({
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
  // trang bị ẩn do điều hướng (Activity) thì đóng menu
  useLayoutEffect(() => () => setOpen(false), []);

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

export function CountPill({ count, label }: { count: number; label?: string }) {
  return (
    <span
      aria-label={label}
      className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-seal px-1 text-[11px] leading-none font-bold text-white tabular-nums dark:text-paper"
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}
