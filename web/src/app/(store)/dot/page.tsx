import { Hourglass } from "lucide-react";
import { StorePlaceholder } from "@/components/store/store-placeholder";

/** Đợt gom đơn (e3): đợt đang mở, sắp mở, đã về. */
export default function DropsPage() {
  return (
    <StorePlaceholder
      title="Đợt gom đơn"
      description="Đặt trong đợt, hết hạn chót thì chị đặt hàng một lần cho cả nhóm."
      icon={<Hourglass />}
      emptyTitle="Chưa có đợt nào đang mở"
      emptyDescription="Mỗi đợt có hạn chót, số suất và ngày hàng về dự kiến. Đợt đầu tiên sẽ hiện ở đây."
    />
  );
}
