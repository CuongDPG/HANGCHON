"use client";

import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";

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
 * Tab nên phản ánh vào URL (?tab=...) nếu người dùng cần quay lại đúng tab.
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
      className={cn("-mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 [scrollbar-width:none] md:mx-0 md:px-0", className)}
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
            className={cn(
              "relative -mb-px flex h-11 shrink-0 items-center gap-1.5 border-b-2 px-3 text-[15px] whitespace-nowrap transition-colors",
              on ? "border-accent font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink",
            )}
          >
            {t.label}
            {t.count !== undefined ? (
              <span className={cn("rounded-sm px-1.5 text-[12px] leading-5 tabular-nums", on ? "bg-accent-wash text-accent" : "bg-soft text-ink-2")}>
                {t.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
