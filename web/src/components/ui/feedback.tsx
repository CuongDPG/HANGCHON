import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/* ---------- ProgressBar ---------- */

type ProgressTone = "accent" | "success" | "warning" | "danger" | "ink";
const barTone: Record<ProgressTone, string> = {
  accent: "bg-accent",
  success: "bg-auto",
  warning: "bg-review",
  danger: "bg-seal",
  ink: "bg-ink",
};

type ProgressBarProps = {
  value: number;
  max?: number;
  /** Nhãn đọc cho trình đọc màn hình, vd. "86 trên 120 suất". */
  label: string;
  tone?: ProgressTone;
  size?: "sm" | "md";
  className?: string;
};

/** Thanh tiến độ (suất đã đặt, ngày thử thứ 9/14…). */
export function ProgressBar({ value, max = 100, label, tone = "accent", size = "md", className }: ProgressBarProps) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className={cn("w-full overflow-hidden rounded-full bg-soft", size === "sm" ? "h-1.5" : "h-2", className)}
    >
      <div className={cn("h-full rounded-full transition-[width]", barTone[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ---------- ScoreBar ---------- */

type ScoreBarProps = { label: ReactNode; score: number; max: number; className?: string };

/** Một dòng điểm thẩm định: «Chất lượng ▬▬▬▬▬▬▬░ 22/25». Màu theo tỉ lệ: ≥ 80% chàm, ≥ 60% vàng nâu, còn lại đỏ son. */
export function ScoreBar({ label, score, max, className }: ScoreBarProps) {
  const ratio = max > 0 ? score / max : 0;
  const tone: ProgressTone = ratio >= 0.8 ? "accent" : ratio >= 0.6 ? "warning" : "danger";
  return (
    <div className={cn("grid grid-cols-[7.5rem_1fr_3rem] items-center gap-3 text-sm", className)}>
      <span className="truncate text-ink-2">{label}</span>
      <ProgressBar value={score} max={max} tone={tone} size="sm" label={`${typeof label === "string" ? label : "Điểm"}: ${score} trên ${max}`} />
      <span className="text-right font-semibold tabular-nums">
        {score}
        <span className="font-normal text-ink-3">/{max}</span>
      </span>
    </div>
  );
}

/* ---------- Skeleton ---------- */

/** Khối chờ tải. Đặt kích thước bằng className: `<Skeleton className="h-5 w-40" />`. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-shimmer rounded-md bg-soft", className)} />;
}

/** Vài dòng chờ tải cho danh sách. */
export function SkeletonList({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3", className)} role="status" aria-label="Đang tải">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-md border border-line bg-surface p-3">
          <Skeleton className="size-12 shrink-0" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-3 w-2/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- EmptyState ---------- */

type EmptyStateProps = {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  /** Nút/link hành động, vd. <ButtonLink href="/nho-tim">Nhờ tìm</ButtonLink>. */
  action?: ReactNode;
  tone?: "default" | "error";
  className?: string;
};

/** Trạng thái trống hoặc lỗi tải: nói rõ chuyện gì đang xảy ra và bước tiếp theo. */
export function EmptyState({ icon, title, description, action, tone = "default", className }: EmptyStateProps) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className={cn("flex flex-col items-center rounded-md border border-dashed border-line-strong px-6 py-10 text-center", className)}
    >
      {icon ? (
        <div
          className={cn(
            "mb-4 grid size-14 place-items-center rounded-full [&_svg]:size-6",
            tone === "error" ? "bg-seal-wash text-seal" : "bg-soft text-accent",
          )}
        >
          {icon}
        </div>
      ) : null}
      <h2 className="text-lg font-bold">{title}</h2>
      {description ? <p className="mt-1.5 max-w-sm text-[15px] text-ink-2">{description}</p> : null}
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}
