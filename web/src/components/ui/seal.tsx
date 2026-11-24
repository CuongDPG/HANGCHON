import { cn } from "@/lib/cn";

type SealProps = {
  /** Số món được chọn (thường là 1). Không truyền cùng `total` thì chỉ hiện chữ «ĐÃ CHỌN». */
  chosen?: number;
  /** Tổng số ứng viên đã xem trong cùng đề săn hàng. */
  total?: number;
  /** Đường kính (px). Mặc định 56; trên ảnh thẻ sản phẩm dùng 44–48, trang sản phẩm 64–72. */
  size?: number;
  className?: string;
};

/**
 * Con dấu «ĐÃ CHỌN 1/24» — dấu hiệu nhận diện của Hàng Chọn, đi theo món hàng ở mọi nơi nó xuất hiện.
 * Vòng đôi (ngoài liền, trong nét đứt), màu đỏ son, xoay nhẹ như dấu đóng tay.
 */
export function Seal({ chosen, total, size = 56, className }: SealProps) {
  const hasRatio = chosen !== undefined && total !== undefined;
  const label = hasRatio ? `Đã chọn ${chosen} trong ${total} món đã xem` : "Đã chọn";
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      style={{ width: size, height: size, fontSize: size }}
      className={cn(
        "relative inline-grid shrink-0 -rotate-8 place-items-center rounded-full border-2 border-seal bg-surface text-center font-display leading-none text-seal",
        "after:absolute after:inset-[0.06em] after:rounded-full after:border after:border-dashed after:border-seal/50",
        className,
      )}
    >
      <span className="relative z-[1] flex flex-col items-center pt-[0.02em]">
        <span className="text-[0.125em] font-bold tracking-[0.04em]">ĐÃ CHỌN</span>
        {hasRatio ? (
          <span className="mt-[0.03em] text-[0.26em] font-extrabold tabular-nums">
            {chosen}/{total}
          </span>
        ) : null}
      </span>
    </span>
  );
}
