import type { ReactNode } from "react";
import { EmptyState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";

type StorePlaceholderProps = {
  title: string;
  description?: string;
  backHref?: string;
  /** Thay cho PageHeader mặc định (vd. đầu trang đọc params trong <Suspense>). */
  header?: ReactNode;
  icon: ReactNode;
  emptyTitle: string;
  emptyDescription: string;
  action?: ReactNode;
};

/** Trang giữ chỗ của website: đầu trang thật + trạng thái trống tử tế. Thay bằng nội dung thật khi làm màn hình. */
export function StorePlaceholder({ title, description, backHref, header, icon, emptyTitle, emptyDescription, action }: StorePlaceholderProps) {
  return (
    <div className="flex flex-col gap-6">
      {header ?? <PageHeader title={title} description={description} backHref={backHref} />}
      <EmptyState icon={icon} title={emptyTitle} description={emptyDescription} action={action} />
    </div>
  );
}
