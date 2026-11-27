"use client";

import Link from "next/link";
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";

const BAR = "-mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 [scrollbar-width:none] md:mx-0 md:px-0";

function tabClass(on: boolean) {
  return cn(
    "relative -mb-px flex h-11 shrink-0 items-center gap-1.5 border-b-2 px-3 text-[15px] whitespace-nowrap transition-colors",
    on ? "border-accent font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink",
  );
}

function TabCount({ count, on }: { count?: number; on: boolean }) {
  if (count === undefined) return null;
  return (
    <span className={cn("rounded-sm px-1.5 text-[12px] leading-5 tabular-nums", on ? "bg-accent-wash text-accent" : "bg-soft text-ink-2")}>{count}</span>
  );
}

export type TabItem<V extends string> = { value: V; label: ReactNode; count?: number };

type TabsProps<V extends string> = {
  value: V;
  onChange: (value: V) => void;
  items: TabItem<V>[];
  "aria-label": string;
  className?: string;
};

/**
 * Thanh tab gạch chân, cuộn ngang được trên điện thoại. Nội dung từng tab do trang tự hiển thị:
 *   <Tabs value={tab} onChange={setTab} items={...} aria-label="Trạng thái đơn" />
 *   {tab === "cho-thanh-toan" && <DanhSach... />}
 * Bàn làm việc: tab là các bước/giai đoạn theo thứ tự công việc (tầng 2), luôn đồng bộ vào URL bằng `useUrlParam`
 * (router.replace) để quay lại/tải lại vẫn đúng tab. Bước là các trang riêng → `TabLinks` (cùng kiểu).
 */
export function Tabs<V extends string>({ value, onChange, items, className, ...aria }: TabsProps<V>) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);

  function onKeyDown(e: KeyboardEvent) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const idx = items.findIndex((t) => t.value === value);
    const next = items[(idx + (e.key === "ArrowRight" ? 1 : -1) + items.length) % items.length];
    onChange(next.value);
    ref.current?.querySelector<HTMLButtonElement>(`[data-value="${CSS.escape(next.value)}"]`)?.focus();
  }

  return (
    <div
      ref={ref}
      role="tablist"
      aria-label={aria["aria-label"]}
      onKeyDown={onKeyDown}
      className={cn(BAR, className)}
    >
      {items.map((t) => {
        const on = t.value === value;
        return (
          <button
            key={t.value}
            id={`${id}-${t.value}`}
            type="button"
            role="tab"
            aria-selected={on}
            data-value={t.value}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(t.value)}
            className={tabClass(on)}
          >
            {t.label}
            <TabCount count={t.count} on={on} />
          </button>
        );
      })}
    </div>
  );
}

export type TabLinkItem = { key: string; href: string; label: ReactNode; count?: number };

/**
 * Tab theo route (mỗi bước là một trang riêng), cùng kiểu với `Tabs`. Mục đang chọn có `aria-current="page"`
 * và tự cuộn vào tầm nhìn trên điện thoại.
 *   <TabLinks aria-label="Chăm khách" active="khach-quen" items={[{ key: "khach-quen", href: "/desk/khach/khach-quen", label: "Khách quen" }, …]} />
 */
export function TabLinks({ items, active, className, ...aria }: { items: readonly TabLinkItem[]; active: string; "aria-label": string; className?: string }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const nav = ref.current;
    const el = nav?.querySelector<HTMLElement>('[aria-current="page"]');
    if (nav && el && nav.clientWidth) nav.scrollLeft = Math.max(0, el.offsetLeft - nav.offsetLeft - 16);
  }, [active]);
  return (
    <nav ref={ref} aria-label={aria["aria-label"]} className={cn(BAR, className)}>
      {items.map((t) => {
        const on = t.key === active;
        return (
          <Link key={t.key} href={t.href} aria-current={on ? "page" : undefined} className={tabClass(on)}>
            {t.label}
            <TabCount count={t.count} on={on} />
          </Link>
        );
      })}
    </nav>
  );
}
