import { ArrowLeft, Settings } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Skeleton } from "./feedback";
import { IconLink } from "./icon-button";
import { SectionTitle, type PageSection } from "./page-sections";

export type { PageSection } from "./page-sections";

type PageHeaderProps = {
  /** Tiêu đề (h1). Có `sections` thì bỏ trống: mục đang chọn là h1. */
  title?: ReactNode;
  /**
   * Tầng 1 «tiêu đề là tab» (chỉ bàn làm việc): các mục lớn của khu, mỗi mục một trang, hiện ngay trên hàng tiêu đề
   * `Mục A | Mục B | Mục C` (tối đa 5). Mục `active` là h1, các mục khác là liên kết mờ.
   */
  sections?: readonly PageSection[];
  /** `key` của mục tầng 1 đang mở. */
  active?: string;
  /** Dòng nhỏ cạnh tiêu đề, vd. "Thứ tư, 25/11". Desk: trạng thái dùng `badge`. */
  eyebrow?: ReactNode;
  /** Trạng thái (Badge) ngay sau tiêu đề. */
  badge?: ReactNode;
  /** Dòng mô tả dưới tiêu đề (website). Desk không viết câu hướng dẫn — số đếm nằm ở tab/chip. */
  description?: ReactNode;
  /** Có thì hiện mũi tên quay lại (chỉ mũi tên, không kèm chữ). */
  backHref?: string;
  /** Thao tác bên phải. Desk: tối đa 1 nút chính + 2 nút khác cao 36px (Button/IconButton `sm`), còn lại vào DeskMoreMenu. */
  actions?: ReactNode;
  /** Trang cấu hình của khu: một nút bánh răng ở cuối hàng tiêu đề. */
  settings?: { href: string; label: string };
  /** Đang tải: giữ nguyên khung đầu trang (cùng chiều cao), tiêu đề là khối xám. */
  loading?: boolean;
  className?: string;
};

/**
 * Đầu trang thống nhất cho mọi màn hình. Mỗi trang có đúng một PageHeader (một <h1>).
 * Trong bàn làm việc (khung có `data-desk`) đầu trang là MỘT hàng cao cố định 44px, không xuống dòng:
 * [←] tiêu đề hoặc «Mục A | Mục B» · badge · eyebrow … thao tác · ⋯ · ⚙ — chuyển màn không làm nội dung nhảy.
 * Website giữ cỡ lớn, mô tả dưới tiêu đề.
 */
export function PageHeader({
  title,
  sections,
  active,
  eyebrow,
  badge,
  description,
  backHref,
  actions,
  settings,
  loading = false,
  className,
}: PageHeaderProps) {
  const heading = loading ? (
    <>
      <h1 className="sr-only">Đang tải…</h1>
      <Skeleton className="h-6 w-48 max-w-full shrink" />
    </>
  ) : sections?.length ? (
    <SectionTitle sections={sections} active={active} />
  ) : (
    <h1
      className={cn(
        "text-[26px] leading-tight font-bold md:text-[30px]",
        "in-data-desk:min-w-0 in-data-desk:truncate in-data-desk:text-[21px] in-data-desk:md:text-[22px]",
      )}
    >
      {title}
    </h1>
  );
  const showActions = !loading && !!actions;
  return (
    <header
      data-page-header
      className={cn("flex items-start gap-2", "in-data-desk:h-11 in-data-desk:shrink-0 in-data-desk:items-center in-data-desk:gap-3", className)}
    >
      {backHref ? (
        <IconLink href={backHref} label="Quay lại" icon={<ArrowLeft />} className="-ml-2.5 shrink-0 in-data-desk:-mr-1.5 in-data-desk:size-9" />
      ) : null}
      <div
        className={cn(
          "min-w-0 flex-1",
          backHref && "pt-1.5 in-data-desk:pt-0",
          "in-data-desk:flex in-data-desk:items-center in-data-desk:gap-x-2.5 in-data-desk:overflow-hidden",
        )}
      >
        {eyebrow && !loading ? (
          <p
            className={cn(
              "mb-0.5 text-[13px] font-medium text-ink-2",
              "in-data-desk:order-3 in-data-desk:mb-0 in-data-desk:min-w-0 in-data-desk:shrink-[4] in-data-desk:truncate",
            )}
          >
            {eyebrow}
          </p>
        ) : null}
        {heading}
        {badge && !loading ? <span className="inline-flex shrink-0 in-data-desk:order-2">{badge}</span> : null}
        {description && !loading ? (
          <p
            className={cn(
              "mt-1 text-[15px] text-ink-2",
              "in-data-desk:order-4 in-data-desk:mt-0 in-data-desk:min-w-0 in-data-desk:shrink-[4] in-data-desk:truncate in-data-desk:text-[13px] in-data-desk:max-md:hidden",
            )}
          >
            {description}
          </p>
        ) : null}
      </div>
      {showActions || settings ? (
        <div
          className={cn(
            "flex shrink-0 items-center gap-1 pt-0.5 in-data-desk:gap-1.5 in-data-desk:pt-0",
            // điện thoại: nút có icon chỉ còn icon (chữ vẫn là tên đọc của nút) để hàng tiêu đề không chật
            "in-data-desk:max-md:[&_[data-icon]]:size-9 in-data-desk:max-md:[&_[data-icon]]:gap-0 in-data-desk:max-md:[&_[data-icon]]:px-0 in-data-desk:max-md:[&_[data-icon]]:text-[0px]",
          )}
        >
          {showActions ? actions : null}
          {settings ? <IconLink href={settings.href} label={settings.label} icon={<Settings />} size="sm" /> : null}
        </div>
      ) : null}
    </header>
  );
}
