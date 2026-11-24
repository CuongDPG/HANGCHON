import { ImageIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type ImageRatio = "1/1" | "4/5" | "3/4" | "4/3" | "16/9";

const ratioClass: Record<ImageRatio, string> = {
  "1/1": "aspect-square",
  "4/5": "aspect-[4/5]",
  "3/4": "aspect-[3/4]",
  "4/3": "aspect-[4/3]",
  "16/9": "aspect-video",
};

type ImageBoxProps = {
  src?: string | null;
  /** Mô tả ảnh cho trình đọc màn hình. Ảnh trang trí thuần thì truyền "". */
  alt: string;
  ratio?: ImageRatio;
  /** Ghi chú khi chưa có ảnh, vd. "Ảnh chị chụp". */
  placeholder?: string;
  /** Ảnh đầu trang (LCP) thì bật để tải ngay. */
  priority?: boolean;
  /** Lớp phủ góc ảnh, vd. <Seal /> hoặc Badge. Đặt ở góc phải dưới. */
  overlay?: ReactNode;
  className?: string;
  imgClassName?: string;
};

/**
 * Khung ảnh có tỉ lệ cố định + nền chờ (không nhảy bố cục khi ảnh tải).
 * Dùng <img> thường vì ảnh đến từ kho lưu trữ (local/S3) qua API; muốn tối ưu kích thước thì
 * API trả sẵn bản thu nhỏ. Không dùng ảnh do AI tạo cho sản phẩm (xem chức năng e6).
 */
export function ImageBox({ src, alt, ratio = "1/1", placeholder, priority = false, overlay, className, imgClassName }: ImageBoxProps) {
  return (
    <div className={cn("relative overflow-hidden rounded-md bg-soft-2", ratioClass[ratio], className)}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- xem chú thích ở trên
        <img
          src={src}
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : undefined}
          decoding="async"
          className={cn("absolute inset-0 size-full object-cover", imgClassName)}
        />
      ) : (
        <div className="absolute inset-0 grid place-items-center bg-[repeating-linear-gradient(135deg,transparent_0_10px,var(--color-soft)_10px_11px)] text-ink-3">
          <span className="flex flex-col items-center gap-1.5 px-3 text-center text-[12.5px]">
            <ImageIcon className="size-5" aria-hidden />
            {placeholder}
          </span>
        </div>
      )}
      {overlay ? <div className="absolute right-2 bottom-2">{overlay}</div> : null}
    </div>
  );
}
