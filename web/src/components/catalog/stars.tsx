import { Star } from "lucide-react";
import { cn } from "@/lib/cn";

/** Số sao (1–5) — chỉ hiển thị, có nhãn cho trình đọc màn hình. */
export function Stars({ value, className }: { value: number; className?: string }) {
  const full = Math.round(value);
  return (
    <span role="img" aria-label={`${value.toLocaleString("vi-VN")} trên 5 sao`} className={cn("inline-flex gap-0.5 text-review", className)}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} aria-hidden className={cn("size-3.5", i <= full ? "fill-current" : "text-line-strong")} />
      ))}
    </span>
  );
}
