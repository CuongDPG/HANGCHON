"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export type SegmentedOption<V extends string> = { value: V; label: ReactNode; disabled?: boolean };

type SegmentedProps<V extends string> = {
  value: V;
  onChange: (value: V) => void;
  options: SegmentedOption<V>[];
  "aria-label": string;
  size?: "sm" | "md";
  /** Chia đều hết bề ngang. */
  block?: boolean;
  className?: string;
};

/**
 * Nhóm nút chọn một trong vài giá trị ngắn (vd. «Tự làm · Hỏi chị · Tắt», «Sáng · Tối»).
 * Từ 5 lựa chọn trở lên, hoặc nhãn dài → dùng InlineSelect.
 */
export function Segmented<V extends string>({ value, onChange, options, size = "md", block, className, ...aria }: SegmentedProps<V>) {
  const ref = useRef<HTMLDivElement>(null);

  function onKeyDown(e: KeyboardEvent) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const enabled = options.filter((o) => !o.disabled);
    const idx = enabled.findIndex((o) => o.value === value);
    const next = enabled[(idx + (e.key === "ArrowRight" ? 1 : -1) + enabled.length) % enabled.length];
    if (!next) return;
    onChange(next.value);
    ref.current?.querySelector<HTMLButtonElement>(`[data-value="${CSS.escape(next.value)}"]`)?.focus();
  }

  return (
    <div
      ref={ref}
      role="radiogroup"
      aria-label={aria["aria-label"]}
      onKeyDown={onKeyDown}
      className={cn("inline-flex gap-0.5 rounded-md bg-soft p-0.5", block && "flex w-full", className)}
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            data-value={o.value}
            tabIndex={on ? 0 : -1}
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={cn(
              "rounded-[3px] px-3 font-medium whitespace-nowrap text-ink-2 transition-colors hover:text-ink disabled:opacity-40",
              size === "sm" ? "h-8 text-[13px]" : "h-9 text-sm",
              block && "flex-1",
              on && "bg-surface text-ink shadow-sm",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
