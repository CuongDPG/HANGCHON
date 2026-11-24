import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

type ChipProps = Omit<ComponentProps<"button">, "children"> & {
  children: ReactNode;
  /** Đang chọn (bộ lọc đang bật). */
  selected?: boolean;
  count?: number;
  icon?: ReactNode;
};

/**
 * Nút lọc dạng thẻ (vd. «Tất cả 38», «Bếp», «Cho bé»). Đặt nhiều chip trong <ChipRow>.
 * Chỉ để hiển thị nhãn tĩnh, không bấm được → dùng Badge.
 */
export function Chip({ children, selected = false, count, icon, className, type = "button", ...props }: ChipProps) {
  return (
    <button
      type={type}
      aria-pressed={selected}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-3 text-sm whitespace-nowrap transition-colors [&_svg]:size-4",
        selected
          ? "border-ink bg-ink text-paper"
          : "border-line-strong bg-surface text-ink hover:border-ink-3",
        className,
      )}
      {...props}
    >
      {icon}
      {children}
      {count !== undefined ? <span className={cn("tabular-nums", selected ? "text-paper/70" : "text-ink-3")}>{count}</span> : null}
    </button>
  );
}

/** Hàng chip cuộn ngang trên điện thoại, xuống dòng trên máy tính. */
export function ChipRow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:flex-wrap md:px-0", className)}>
      {children}
    </div>
  );
}
