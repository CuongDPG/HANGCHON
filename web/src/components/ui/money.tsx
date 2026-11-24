import { cn } from "@/lib/cn";
import { formatVnd, formatVndCompact } from "@/lib/format";

type MoneyProps = {
  /** Số nguyên VND (trường `*_vnd` của API). */
  value: number;
  /** Rút gọn kiểu "3,4 tr", "620k" cho ô số liệu. */
  compact?: boolean;
  /** Giá cũ: gạch ngang, màu mờ. */
  strike?: boolean;
  className?: string;
};

/** Hiển thị tiền: `<Money value={385000} />` → 385.000đ. Luôn dùng component này hoặc formatVnd, không tự ghép chuỗi. */
export function Money({ value, compact = false, strike = false, className }: MoneyProps) {
  return (
    <span className={cn("tabular-nums whitespace-nowrap", strike && "text-ink-3 line-through", className)}>
      {compact ? formatVndCompact(value) : formatVnd(value)}
    </span>
  );
}
