import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Ba mức tự động (xem docs/features.md), mã hoá bằng CẢ hình và màu để người mù màu vẫn phân biệt được:
 *   owner  — «Chị quyết»          đỏ son,     ô vuông (nghiêng nhẹ như con dấu)
 *   review — «AI làm, chị duyệt»  vàng nâu,   nửa hình tròn (nửa tô, nửa viền)
 *   auto   — «AI tự làm»          xanh cổ vịt, hình tròn đặc
 */
export type Level = "owner" | "review" | "auto";

export const LEVEL_LABELS: Record<Level, string> = {
  owner: "Chị quyết",
  review: "AI làm, chị duyệt",
  auto: "AI tự làm",
};

const tone: Record<Level, string> = {
  owner: "bg-seal-wash text-seal",
  review: "bg-review-wash text-review",
  auto: "bg-auto-wash text-auto",
};

/** Chỉ riêng hình nhận diện của mức (dùng trong chú giải, cột bảng hẹp). */
export function LevelMark({ level, className }: { level: Level; className?: string }) {
  if (level === "owner") {
    return <span aria-hidden className={cn("inline-block size-[9px] shrink-0 -rotate-8 rounded-[1px] bg-seal", className)} />;
  }
  if (level === "review") {
    return (
      <span
        aria-hidden
        className={cn(
          "inline-block size-[10px] shrink-0 rounded-full bg-[linear-gradient(90deg,var(--color-review)_50%,transparent_50%)] shadow-[inset_0_0_0_1.5px_var(--color-review)]",
          className,
        )}
      />
    );
  }
  return <span aria-hidden className={cn("inline-block size-[10px] shrink-0 rounded-full bg-auto", className)} />;
}

type LevelTagProps = {
  level: Level;
  /** Thay nhãn mặc định khi cần nói cụ thể hơn (vd. «Chờ duyệt», «Luôn hỏi chị», «AI đã tự làm · 23 việc»). */
  children?: ReactNode;
  size?: "sm" | "md";
  className?: string;
};

export function LevelTag({ level, children, size = "md", className }: LevelTagProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm font-semibold whitespace-nowrap",
        size === "sm" ? "h-5 px-1.5 text-[11.5px]" : "h-6 px-2 text-[12.5px]",
        tone[level],
        className,
      )}
    >
      <LevelMark level={level} />
      {children ?? LEVEL_LABELS[level]}
    </span>
  );
}
