"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { FieldShell } from "./field";

export type SelectOption<V extends string = string> = {
  value: V;
  label: string;
  /** Dòng phụ nhỏ dưới nhãn. */
  hint?: string;
  disabled?: boolean;
};

type InlineSelectProps<V extends string> = {
  value: V | null;
  onChange: (value: V) => void;
  options: SelectOption<V>[];
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  placeholder?: string;
  disabled?: boolean;
  /** `inline`: gọn như chữ có mũi tên, đặt giữa câu/dòng tiêu đề. `field`: ô như Input. */
  appearance?: "field" | "inline";
  /** Nhãn đọc cho trình đọc màn hình khi không có `label`. */
  "aria-label"?: string;
  className?: string;
};

/**
 * Ô chọn một giá trị — thay cho `<select>` của trình duyệt (không dùng `<select>` thuần trong dự án).
 * Bàn phím: ↑/↓ di chuyển, Enter/Space chọn, Esc đóng, gõ chữ cái để nhảy tới.
 */
export function InlineSelect<V extends string>({
  value,
  onChange,
  options,
  label,
  hint,
  error,
  placeholder = "Chọn…",
  disabled,
  appearance = "field",
  className,
  ...aria
}: InlineSelectProps<V>) {
  const id = useId();
  const listId = `${id}-list`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const selected = options.find((o) => o.value === value) ?? null;

  // Đóng khi bấm ra ngoài
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  // Đóng khi trang bị ẩn do điều hướng (Activity của Next.js giữ trạng thái)
  useLayoutEffect(() => () => setOpen(false), []);

  useEffect(() => {
    if (open && active >= 0) {
      listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
    }
  }, [open, active]);

  function openList() {
    if (disabled) return;
    const idx = options.findIndex((o) => o.value === value);
    setActive(idx >= 0 ? idx : options.findIndex((o) => !o.disabled));
    setOpen(true);
  }

  function choose(i: number) {
    const opt = options[i];
    if (!opt || opt.disabled) return;
    onChange(opt.value);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function move(delta: number) {
    if (options.length === 0) return;
    let i = active;
    for (let step = 0; step < options.length; step++) {
      i = (i + delta + options.length) % options.length;
      if (!options[i].disabled) break;
    }
    setActive(i);
  }

  function onKeyDown(e: KeyboardEvent) {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        openList();
      }
      return;
    }
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        move(1);
        return;
      case "ArrowUp":
        e.preventDefault();
        move(-1);
        return;
      case "Home":
        e.preventDefault();
        setActive(0);
        return;
      case "End":
        e.preventDefault();
        setActive(options.length - 1);
        return;
      case "Enter":
      case " ":
        e.preventDefault();
        choose(active);
        return;
      case "Escape":
      case "Tab":
        setOpen(false);
        return;
    }
    if (e.key.length === 1) {
      const ch = e.key.toLowerCase();
      const i = options.findIndex((o) => !o.disabled && o.label.toLowerCase().startsWith(ch));
      if (i >= 0) setActive(i);
    }
  }

  const trigger = (
    <button
      ref={buttonRef}
      id={id}
      type="button"
      role="combobox"
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={listId}
      aria-activedescendant={open && active >= 0 ? `${id}-opt-${active}` : undefined}
      aria-invalid={error ? true : undefined}
      aria-label={aria["aria-label"]}
      disabled={disabled}
      onClick={() => (open ? setOpen(false) : openList())}
      onKeyDown={onKeyDown}
      className={cn(
        appearance === "field"
          ? "flex h-11 w-full items-center justify-between gap-2 rounded-md border border-line-strong bg-surface px-3 text-left text-[16px] hover:border-ink-3 aria-expanded:border-accent aria-invalid:border-seal"
          : "inline-flex h-9 items-center gap-1 rounded-md px-2 font-semibold text-accent hover:bg-accent-wash",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-50",
      )}
    >
      <span className={cn("truncate", !selected && "text-ink-3")}>{selected?.label ?? placeholder}</span>
      <ChevronDown className={cn("size-4 shrink-0 transition-transform", open && "rotate-180", appearance === "field" && "text-ink-2")} aria-hidden />
    </button>
  );

  const list = open ? (
    <ul
      ref={listRef}
      id={listId}
      role="listbox"
      aria-labelledby={id}
      className="absolute left-0 top-[calc(100%+4px)] z-30 max-h-72 min-w-full overflow-auto rounded-md border border-line bg-surface py-1 shadow-pop"
    >
      {options.map((o, i) => {
        const isSelected = o.value === value;
        return (
          <li
            key={o.value}
            id={`${id}-opt-${i}`}
            data-index={i}
            role="option"
            aria-selected={isSelected}
            aria-disabled={o.disabled || undefined}
            onPointerEnter={() => setActive(i)}
            onClick={() => choose(i)}
            className={cn(
              "flex cursor-pointer items-start gap-2 px-3 py-2.5 text-[15px]",
              i === active && "bg-soft-2",
              o.disabled && "cursor-not-allowed opacity-45",
            )}
          >
            <Check className={cn("mt-0.5 size-4 shrink-0 text-accent", !isSelected && "invisible")} aria-hidden />
            <span className="min-w-0">
              <span className={cn("block whitespace-nowrap", isSelected && "font-semibold")}>{o.label}</span>
              {o.hint ? <span className="block text-[13px] text-ink-2">{o.hint}</span> : null}
            </span>
          </li>
        );
      })}
    </ul>
  ) : null;

  if (appearance === "inline") {
    return (
      <div ref={rootRef} className={cn("relative inline-block", className)}>
        {trigger}
        {list}
      </div>
    );
  }

  return (
    <FieldShell id={id} label={label} hint={hint} error={error} className={className}>
      <div ref={rootRef} className="relative">
        {trigger}
        {list}
      </div>
    </FieldShell>
  );
}
