import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "outline";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-soft text-ink-2",
  accent: "bg-accent-wash text-accent",
  success: "bg-auto-wash text-auto",
  warning: "bg-review-wash text-review",
  danger: "bg-seal-wash text-seal",
  outline: "border border-line-strong text-ink-2",
};

/** Nhãn trạng thái tĩnh (vd. «Đợt 12 · còn 34 suất», «Chờ chuyển khoản»). Mức tự động → LevelTag. */
export function Badge({ tone = "neutral", icon, children, className }: { tone?: BadgeTone; icon?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-sm px-2 text-[12.5px] font-medium whitespace-nowrap [&_svg]:size-3.5",
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
