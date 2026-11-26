import { ImageIcon } from "lucide-react";
import type { HTMLAttributeReferrerPolicy, ReactNode } from "react";
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
  /** Ảnh từ máy chủ ngoài (link ảnh nhà cung cấp chưa lưu về kho): "no-referrer" để CDN không chặn theo trang gọi. */
  referrerPolicy?: HTMLAttributeReferrerPolicy;
};

/**
 * Khung ảnh có tỉ lệ cố định + nền chờ (không nhảy bố cục khi ảnh tải).
 * Dùng <img> thường vì ảnh đến từ kho lưu trữ (local/S3) qua API; muốn tối ưu kích thước thì
 * API trả sẵn bản thu nhỏ. Không dùng ảnh do AI tạo cho sản phẩm (xem chức năng e6).
 */
export function ImageBox({ src, alt, ratio = "1/1", placeholder, priority = false, overlay, className, imgClassName, referrerPolicy }: ImageBoxProps) {
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
          referrerPolicy={referrerPolicy}
          className={cn("absolute inset-0 size-full object-cover", imgClassName)}
        />
      ) : (
        // ô giữ chỗ (không dùng ảnh giả): ô nhỏ chỉ có biểu tượng, ô lớn thêm lời ghi chú
        <div className="@container absolute inset-0 grid place-items-center bg-[repeating-linear-gradient(135deg,transparent_0_10px,var(--color-soft)_10px_11px)] text-ink-3">
          <span className="flex flex-col items-center gap-1.5 px-3 text-center text-[12.5px] @[16rem]:gap-2 @[16rem]:text-[14px]">
            <ImageIcon className="size-5 @[16rem]:size-7" strokeWidth={1.6} aria-hidden />
            {placeholder ? <span className="hidden @[7rem]:block">{placeholder}</span> : null}
          </span>
        </div>
      )}
      {overlay ? <div className="absolute right-2 bottom-2">{overlay}</div> : null}
    </div>
  );
}
