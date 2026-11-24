import { Hourglass } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { StorePlaceholder } from "@/components/store/store-placeholder";

/** Chi tiết một đợt (e3): các món trong đợt, suất còn lại, hạn chót, ngày hàng về. */
export default function DropPage() {
  return (
    <StorePlaceholder
      title="Đợt gom"
      backHref="/dot"
      icon={<Hourglass />}
      emptyTitle="Đợt này chưa mở"
      emptyDescription="Khi mở, trang sẽ có các món trong đợt, số suất còn lại và ngày hàng về dự kiến."
      action={<ButtonLink href="/dot" variant="secondary">Xem các đợt</ButtonLink>}
    />
  );
}
