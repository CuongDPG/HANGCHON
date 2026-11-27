import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { IconLink } from "./icon-button";

type PageHeaderProps = {
  title: ReactNode;
  /** Dòng nhỏ phía trên tiêu đề, vd. "Thứ tư, 25/11" hoặc "ĐỢT 12 · ĐANG MỞ". */
  eyebrow?: ReactNode;
  /** Dòng mô tả dưới tiêu đề. */
  description?: ReactNode;
  /** Có thì hiện mũi tên quay lại (chỉ mũi tên, không kèm chữ). */
  backHref?: string;
  /** Thao tác bên phải: IconButton, Button nhỏ, InlineSelect inline… */
  actions?: ReactNode;
  className?: string;
};

/**
 * Đầu trang thống nhất cho mọi màn hình. Mỗi trang có đúng một PageHeader (một <h1>).
 * Trong bàn làm việc (khung có `data-desk`) đầu trang gọn một hàng: tiêu đề nhỏ, eyebrow và mô tả nằm cùng hàng
 * sau tiêu đề, nút thao tác canh giữa theo hàng và xuống dòng khi hẹp — dành chỗ cho dữ liệu. Website giữ cỡ lớn.
 */
export function PageHeader({ title, eyebrow, description, backHref, actions, className }: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex items-start gap-2",
        "in-data-desk:flex-wrap in-data-desk:items-center in-data-desk:gap-x-3 in-data-desk:gap-y-2",
        className,
      )}
    >
      {backHref ? <IconLink href={backHref} label="Quay lại" icon={<ArrowLeft />} className="-ml-2.5 shrink-0 in-data-desk:-mr-2" /> : null}
      <div
        className={cn(
          "min-w-0 flex-1",
          backHref && "pt-1.5 in-data-desk:pt-0",
          "in-data-desk:flex in-data-desk:flex-[1_1_12rem] in-data-desk:flex-wrap in-data-desk:items-baseline in-data-desk:gap-x-2.5",
        )}
      >
        {eyebrow ? (
          <p className="mb-0.5 text-[13px] font-medium text-ink-2 in-data-desk:order-2 in-data-desk:mb-0">{eyebrow}</p>
        ) : null}
        <h1 className="text-[26px] leading-tight font-bold md:text-[30px] in-data-desk:text-[21px] in-data-desk:md:text-[22px]">{title}</h1>
        {description ? (
          <p className="mt-1 text-[15px] text-ink-2 in-data-desk:order-3 in-data-desk:mt-0 in-data-desk:text-[13px]">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 items-center gap-1 pt-0.5 in-data-desk:max-w-full in-data-desk:flex-wrap in-data-desk:gap-1.5 in-data-desk:pt-0">{actions}</div>
      ) : null}
    </header>
  );
}
