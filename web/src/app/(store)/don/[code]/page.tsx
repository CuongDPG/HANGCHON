import { Truck } from "lucide-react";
import { StorePlaceholder } from "@/components/store/store-placeholder";

/** Theo dõi một đơn (e5, g5): hành trình theo mốc, hỏi về đơn, đổi địa chỉ. */
export default function OrderTrackingPage() {
  return (
    <StorePlaceholder
      title="Theo dõi đơn"
      backHref="/don"
      icon={<Truck />}
      emptyTitle="Chưa xem được đơn này"
      emptyDescription="Trang theo dõi đơn đang được dựng. Mỗi mốc của đơn bạn cũng sẽ nhận một tin nhắn."
    />
  );
}
