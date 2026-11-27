import type { ComponentProps } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { SkeletonList } from "@/components/ui/feedback";

/**
 * Khung tạm của một trang desk (fallback của <Suspense>): cùng đầu trang 44px với trang thật — không bao giờ
 * mất đầu trang khi đang tải. Không truyền `title`/`sections` thì tiêu đề là khối xám.
 */
export function DeskPageFallback({ rows = 3, ...header }: ComponentProps<typeof PageHeader> & { rows?: number }) {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader loading={!header.title && !header.sections} {...header} />
      <SkeletonList rows={rows} />
    </div>
  );
}
