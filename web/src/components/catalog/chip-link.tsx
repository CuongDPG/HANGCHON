import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Chip lọc dạng đường dẫn (bộ lọc nằm trên URL để trang chạy được không cần JavaScript). Giống `Chip` của ui. */
export function ChipLink({ href, selected, count, children }: { href: string; selected?: boolean; count?: number; children: ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={selected ? "page" : undefined}
      prefetch={false}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-3 text-sm whitespace-nowrap transition-colors",
        selected ? "border-ink bg-ink text-paper" : "border-line-strong bg-surface text-ink hover:border-ink-3",
      )}
    >
      {children}
      {count !== undefined ? <span className={cn("tabular-nums", selected ? "text-paper/70" : "text-ink-3")}>{count}</span> : null}
    </Link>
  );
}
