import { Hammer } from "lucide-react";
import { EmptyState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { DESK_NAV } from "@/lib/desk-nav";

/**
 * Trang giữ chỗ của một khu bàn làm việc: tiêu đề + mô tả lấy từ desk-nav.ts, kèm mã chức năng sẽ làm.
 * Khi làm màn hình thật, thay toàn bộ nội dung page.tsx của khu đó.
 */
export function DeskPlaceholder({ navKey }: { navKey: string }) {
  const item = DESK_NAV.find((i) => i.key === navKey);
  if (!item) throw new Error(`desk-nav.ts chưa khai báo khu "${navKey}"`);
  const Icon = item.icon;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={item.label} description={item.description} />
      <EmptyState
        icon={<Icon />}
        title="Màn hình đang được dựng"
        description={
          <>
            Khu này sẽ có các chức năng {item.features.join(", ")} trong danh mục chức năng.
          </>
        }
        action={
          <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-3">
            <Hammer className="size-3.5" aria-hidden /> Trang giữ chỗ
          </span>
        }
      />
    </div>
  );
}
