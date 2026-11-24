import Link from "next/link";
import { Check } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/* ---------- StatTile ---------- */

type StatTileProps = {
  /** Con số chính, đã định dạng (dùng formatVndCompact, formatNumber…). */
  value: ReactNode;
  label: ReactNode;
  /** Dòng phụ: so với tuần trước, "· 34%"… */
  hint?: ReactNode;
  href?: string;
  className?: string;
};

/** Ô số liệu: «9 đơn mới», «3,4 tr tiền về». Xếp trong lưới `grid grid-cols-3 gap-2`. */
export function StatTile({ value, label, hint, href, className }: StatTileProps) {
  const body = (
    <>
      <span className="block font-display text-[22px] leading-tight font-extrabold tabular-nums">{value}</span>
      <span className="mt-0.5 block text-[13px] text-ink-2">{label}</span>
      {hint ? <span className="block text-[12px] text-ink-3">{hint}</span> : null}
    </>
  );
  const cls = cn("block min-w-0 rounded-md border border-line bg-surface p-3", href && "transition-colors hover:border-ink-3", className);
  return href ? (
    <Link href={href} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/* ---------- DataList ---------- */

export type DataListItem = {
  label: ReactNode;
  value: ReactNode;
  /** Dòng tổng: chữ đậm, có kẻ trên. */
  strong?: boolean;
};

/** Danh sách nhãn — giá trị (giá vốn, tạm tính, phí giao, tổng…). */
export function DataList({ items, className }: { items: DataListItem[]; className?: string }) {
  return (
    <dl className={cn("flex flex-col text-[15px]", className)}>
      {items.map((it, i) => (
        <div
          key={i}
          className={cn(
            "flex items-baseline justify-between gap-4 py-1.5",
            it.strong && "mt-1 border-t border-line pt-2.5 font-semibold",
          )}
        >
          <dt className={cn("min-w-0", !it.strong && "text-ink-2")}>{it.label}</dt>
          <dd className="text-right tabular-nums">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- Timeline ---------- */

export type TimelineItem = {
  title: ReactNode;
  /** Thời gian hoặc "Dự kiến 12/12". */
  meta?: ReactNode;
  description?: ReactNode;
  status: "done" | "current" | "todo";
};

/** Hành trình theo mốc (đơn hàng, lô hàng về). Mốc hiện tại nổi bật bằng chàm. */
export function Timeline({ items, className }: { items: TimelineItem[]; className?: string }) {
  return (
    <ol className={cn("relative flex flex-col", className)}>
      {items.map((it, i) => {
        const last = i === items.length - 1;
        return (
          <li key={i} className="relative flex gap-3 pb-5 last:pb-0" aria-current={it.status === "current" ? "step" : undefined}>
            {!last ? (
              <span
                aria-hidden
                className={cn("absolute top-6 bottom-0 left-[11px] w-0.5", it.status === "done" ? "bg-accent" : "bg-line")}
              />
            ) : null}
            <span
              aria-hidden
              className={cn(
                "relative z-[1] mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border-2",
                it.status === "done" && "border-accent bg-accent text-on-accent",
                it.status === "current" && "border-accent bg-surface ring-4 ring-accent-wash",
                it.status === "todo" && "border-line-strong bg-surface",
              )}
            >
              {it.status === "done" ? <Check className="size-3.5" strokeWidth={3} /> : null}
              {it.status === "current" ? <span className="size-2 rounded-full bg-accent" /> : null}
            </span>
            <div className="min-w-0 pt-0.5">
              <p className={cn("text-[15px] leading-snug", it.status === "todo" ? "text-ink-2" : "font-semibold text-ink")}>{it.title}</p>
              {it.meta ? <p className="text-[13px] text-ink-2">{it.meta}</p> : null}
              {it.description ? <p className="mt-1 text-[14px] text-ink-2">{it.description}</p> : null}
              <span className="sr-only">
                {it.status === "done" ? "Đã xong" : it.status === "current" ? "Đang ở bước này" : "Chưa tới"}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
